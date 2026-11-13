/** 扫描/归档进度条 */
export function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className="bg-slate-700 rounded-full h-2 overflow-hidden">
      <div
        className="bg-blue-500 h-2 rounded-full transition-all duration-100"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
