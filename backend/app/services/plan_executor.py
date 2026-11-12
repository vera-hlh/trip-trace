"""归档方案执行器（M2.4）

只消费 archive_plans / plan_trips / plan_files，不再重算行程。
"""
import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.archive_log import ArchiveLog
from app.models.archive_plan import ArchivePlan, PlanFile, PlanTrip
from app.models.file import MediaFile
from app.models.trip_record import TripRecord
from app.services.remark_service import format_remark, write_remark

logger = logging.getLogger(__name__)


def source_snapshot(files: list) -> str:
    """文件集合指纹：路径 + size + mtime_ns。"""
    digest = hashlib.sha256()
    for f in sorted(files, key=lambda x: x.original_path):
        try:
            stat = os.stat(f.original_path)
            signature = f"{f.original_path}|{stat.st_size}|{stat.st_mtime_ns}"
        except OSError:
            signature = f"{f.original_path}|missing"
        digest.update(signature.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


async def load_plan_media(db: AsyncSession, plan: ArchivePlan) -> list[MediaFile]:
    """按方案中的 media_file_id 加载当前媒体记录。"""
    ids = (
        await db.execute(
            select(PlanFile.media_file_id).where(
                PlanFile.plan_id == plan.id,
                PlanFile.media_file_id.is_not(None),
            )
        )
    ).scalars().all()
    if not ids:
        return []
    rows = (
        await db.execute(select(MediaFile).where(MediaFile.id.in_(ids)))
    ).scalars().all()
    return rows


def _plan_trip_log(
    plan: ArchivePlan,
    big: PlanTrip,
    subs: list[PlanTrip],
    counts: dict[int, int],
) -> str:
    start = (big.start_date or "")[:10]
    end = (big.end_date or "")[:10]
    days = 0
    try:
        from datetime import date

        days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    except Exception:
        pass

    lines = [
        f"# 🗺️ {big.display_name or big.folder_name}",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        f"| 行程时间 | {start or '未知'} — {end or '未知'}（共 **{days}天**）|",
        f"| 子行程数 | {len(subs)} 段 |",
        f"| 媒体文件 | 共 **{sum(counts.get(s.id, 0) for s in subs)}** 个 |",
        "",
        "---",
        "",
        "## 子行程详情",
        "",
    ]
    for sub in subs:
        lines += [
            f"### 📂 {sub.display_name or sub.folder_name}",
            "",
            f"- **时间段**：{(sub.start_date or '?')[:10]} — {(sub.end_date or '?')[:10]}",
            f"- **地点**：{sub.location_label or '未识别'}",
            f"- **媒体文件**：{counts.get(sub.id, 0)} 个",
            "",
        ]
    lines += ["---", "", "*由 旅迹 TripTrace 根据归档方案自动生成*"]
    return "\n".join(lines)


async def run_plan(
    db: AsyncSession,
    plan: ArchivePlan,
    media: list[MediaFile],
    write_remarks: bool,
    remark_template: str,
) -> AsyncGenerator[dict, None]:
    """执行方案；yield 进度事件（由 API 层转成 SSE）。"""
    started = time.time()
    trips = (
        await db.execute(select(PlanTrip).where(PlanTrip.plan_id == plan.id))
    ).scalars().all()
    bigs = {t.id: t for t in trips if t.kind == "big"}
    subs = {t.id: t for t in trips if t.kind == "sub"}
    media_by_id = {m.id: m for m in media}

    files = (
        await db.execute(
            select(PlanFile)
            .where(PlanFile.plan_id == plan.id)
            .order_by(PlanFile.id)
        )
    ).scalars().all()

    counts: dict[int, int] = {}
    for pf in files:
        if pf.trip_id is not None:
            counts[pf.trip_id] = counts.get(pf.trip_id, 0) + 1

    total = len(files)
    yield {"type": "start", "plan_id": plan.id, "total": total,
           "output_path": plan.output_folder}
    await asyncio.sleep(0)

    root = os.path.abspath(plan.output_folder)
    copied = skipped = errors = remarks_written = 0

    for index, pf in enumerate(files, start=1):
        media_file = media_by_id.get(pf.media_file_id)
        file_label = (
            media_file.file_name if media_file else os.path.basename(pf.target_rel_path)
        )

        if media_file is None:
            errors += 1
            pf.status = "failed"
            pf.error = "媒体记录不存在"
            yield {"type": "error", "current": index, "total": total,
                   "file": file_label, "message": pf.error}
            continue

        target = os.path.abspath(os.path.join(root, pf.target_rel_path))
        try:
            if os.path.normcase(os.path.commonpath([root, target])) != os.path.normcase(root):
                raise ValueError("目标路径越界")
        except ValueError:
            errors += 1
            pf.status = "failed"
            pf.error = "目标路径越界"
            yield {"type": "error", "current": index, "total": total,
                   "file": file_label, "message": pf.error}
            continue

        try:
            if os.path.exists(target):
                skipped += 1
                pf.status = "skipped"
                yield {"type": "skip", "current": index, "total": total,
                       "file": file_label, "reason": "already_exists"}
                continue

            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(media_file.original_path, target)
            pf.status = "copied"
            media_file.current_path = target
            copied += 1

            if write_remarks and remark_template:
                sub = subs.get(pf.trip_id)
                big = bigs.get(sub.parent_id) if sub and sub.parent_id else None
                try:
                    text = format_remark(
                        remark_template,
                        country=media_file.country or "",
                        province=media_file.province or "",
                        city=media_file.city or "",
                        district=getattr(media_file, "district", "") or "",
                        poi=media_file.poi or "",
                        trip_name=(big.display_name or big.folder_name) if big else "",
                        sub_trip_name=(sub.display_name or sub.folder_name) if sub else "",
                    )
                    result = write_remark(target, text)
                    if result.success:
                        remarks_written += 1
                    yield {"type": "remark", "current": index, "total": total,
                           "file": file_label, "success": result.success}
                except Exception as exc:
                    logger.warning("写入备注失败 %s: %s", target, exc)
                    yield {"type": "remark", "current": index, "total": total,
                           "file": file_label, "success": False}

            yield {"type": "progress", "current": index, "total": total,
                   "file": file_label, "target": pf.target_rel_path}
        except Exception as exc:
            errors += 1
            pf.status = "failed"
            pf.error = str(exc)
            logger.error("复制失败 %s: %s", media_file.original_path, exc)
            yield {"type": "error", "current": index, "total": total,
                   "file": file_label, "message": str(exc)}

        await asyncio.sleep(0)

    # ── trip_log.md ─────────────────────────────────────────
    trip_log_count = 0
    for big in bigs.values():
        big_dir = os.path.join(root, big.folder_name)
        if not os.path.isdir(big_dir):
            continue
        try:
            content = _plan_trip_log(
                plan, big, [s for s in subs.values() if s.parent_id == big.id], counts
            )
            with open(os.path.join(big_dir, "trip_log.md"), "w", encoding="utf-8") as f:
                f.write(content)
            trip_log_count += 1
        except Exception as exc:
            logger.warning("生成 trip_log.md 失败 %s: %s", big.folder_name, exc)

    # ── 方案状态 + 日志 + 我的旅迹 ─────────────────────────
    now = datetime.now()
    plan.status = "executed"
    plan.executed_at = now.isoformat(timespec="seconds")

    gaode_calls = len({
        (m.city, m.poi or getattr(m, "township", "") or "")
        for m in media
        if getattr(m, "geocode_source", None) == "gaode"
    })
    status = "success" if errors == 0 else ("partial" if copied > 0 else "failed")

    db.add(ArchiveLog(
        user_id="local",
        created_at=now.isoformat(timespec="seconds"),
        source_folder=plan.source_folder,
        output_folder=plan.output_folder,
        photo_count=sum(1 for m in media if m.file_type == "photo"),
        video_count=sum(1 for m in media if m.file_type == "video"),
        copied_count=copied,
        skipped_count=skipped,
        error_count=errors,
        big_trips_count=len(bigs),
        sub_trips_count=len(subs),
        api_calls_used=gaode_calls,
        duration_sec=round(time.time() - started, 1),
        status=status,
        trip_log_generated=trip_log_count > 0,
        remarks_written=remarks_written,
        options_json=json.dumps(
            {"plan_id": plan.id, "write_remarks": write_remarks},
            ensure_ascii=False,
        ),
    ))

    for big in bigs.values():
        big_dir = os.path.join(root, big.folder_name)
        if not os.path.isdir(big_dir):
            continue
        big_subs = [s for s in subs.values() if s.parent_id == big.id]
        sub_payload = [
            {
                "name": s.display_name or s.folder_name,
                "location": s.location_label or "",
                "start_date": s.start_date,
                "end_date": s.end_date,
                "file_count": counts.get(s.id, 0),
            }
            for s in big_subs
        ]
        db.add(TripRecord(
            user_id="local",
            big_trip_name=big.display_name or big.folder_name,
            start_date=big.start_date,
            end_date=big.end_date,
            sub_trip_count=len(big_subs),
            total_files=sum(counts.get(s.id, 0) for s in big_subs),
            output_folder=plan.output_folder,
            big_trip_folder=big.folder_name,
            created_at=plan.created_at or now.isoformat(timespec="seconds"),
            sub_trips_json=json.dumps(sub_payload, ensure_ascii=False),
            poster_path=None,
        ))

    await db.commit()

    yield {
        "type": "complete",
        "plan_id": plan.id,
        "total": total,
        "copied": copied,
        "skipped": skipped,
        "errors": errors,
        "remarks_written": remarks_written,
        "trip_log_generated": trip_log_count,
        "output_path": plan.output_folder,
    }
