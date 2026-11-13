/** POI 类型标签（静态 Tailwind 类，避免生产构建被 purge） */
export function PoiTypeTag({ poiType }: { poiType?: string }) {
  if (!poiType) return null;
  let icon = "";
  let cls = "";
  let label = "";

  if (poiType.includes("风景名胜")) {
    icon = "🏞️"; cls = "bg-emerald-900/30 text-emerald-400 border-emerald-700/40"; label = "风景名胜";
  } else if (poiType.includes("热点地名") || poiType.includes("标志性建筑")) {
    icon = "📍"; cls = "bg-blue-900/30 text-blue-400 border-blue-700/40"; label = "热点地标";
  } else if (poiType.includes("自然地名")) {
    icon = "🌊"; cls = "bg-cyan-900/30 text-cyan-400 border-cyan-700/40"; label = "自然地名";
  } else if (poiType.includes("公园")) {
    icon = "🌳"; cls = "bg-green-900/30 text-green-400 border-green-700/40"; label = "公园";
  } else if (poiType.includes("博物馆") || poiType.includes("展览馆") || poiType.includes("美术馆")) {
    icon = "🏛️"; cls = "bg-indigo-900/30 text-indigo-400 border-indigo-700/40"; label = "文化场馆";
  } else if (poiType.includes("火车站")) {
    icon = "🚉"; cls = "bg-slate-800 text-slate-300 border-slate-600"; label = "火车站";
  } else if (poiType.includes("休闲") || poiType.includes("度假") || poiType.includes("商业街")) {
    icon = "🎪"; cls = "bg-purple-900/30 text-purple-400 border-purple-700/40"; label = "休闲";
  } else if (poiType.includes("村庄")) {
    icon = "⚠️"; cls = "bg-amber-900/30 text-amber-400 border-amber-700/40"; label = "村庄（请核实）";
  } else {
    icon = "📌"; cls = "bg-slate-800 text-slate-500 border-slate-700"; label = poiType.split(";")[0];
  }

  return (
    <span className={`flex-shrink-0 text-xs px-1.5 py-0.5 rounded border ${cls}`} title={poiType}>
      {icon} {label}
    </span>
  );
}
