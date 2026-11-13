import clsx from "clsx";

/** 统计数字格子 */
export function StatBox({
  value,
  label,
  color = "text-slate-300",
}: {
  value: number | string;
  label: string;
  color?: string;
}) {
  return (
    <div className="bg-slate-800/80 rounded-lg p-3 text-center">
      <div className={clsx("text-xl font-bold font-mono", color)}>{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}
