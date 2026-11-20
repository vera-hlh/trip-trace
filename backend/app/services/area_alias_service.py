"""景区名归一化（别名）服务。"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.area_alias import AreaAlias


async def load_aliases(db: AsyncSession) -> dict[tuple[str, str], str]:
    rows = (await db.execute(select(AreaAlias))).scalars().all()
    return {(row.city, row.alias_name): row.canonical_name for row in rows}


def resolve_area_alias(
    aliases: dict[tuple[str, str], str],
    city: str,
    area_name: str,
) -> str:
    """按城市解析别名，最多跟随 5 层，避免环。"""
    current = area_name
    seen: set[str] = set()
    for _ in range(5):
        if not current or current in seen:
            break
        seen.add(current)
        mapped = aliases.get((city, current))
        if not mapped or mapped == current:
            break
        current = mapped
    return current


async def upsert_alias(
    db: AsyncSession,
    city: str,
    alias_name: str,
    canonical_name: str,
) -> AreaAlias:
    row = (
        await db.execute(
            select(AreaAlias).where(
                AreaAlias.city == city,
                AreaAlias.alias_name == alias_name,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = AreaAlias(
            city=city,
            alias_name=alias_name,
            canonical_name=canonical_name,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        db.add(row)
    else:
        row.canonical_name = canonical_name
    return row
