const BACKEND_URL = "http://localhost:17890";

export default function Home() {
  const handleSelectFolder = async () => {
    const folder = await (window as any).electronAPI?.openFolderDialog();
    if (folder) {
      alert(`已选择文件夹: ${folder}\n（后续功能待 Phase 2 实现）`);
    }
  };

  const handleCheckBackend = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/health`);
      const data = await res.json();
      alert(`✅ 后端连接正常\n${JSON.stringify(data, null, 2)}`);
    } catch {
      alert("❌ 后端未启动，请先运行: uvicorn app.main:app --port 17890");
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-slate-800 mb-2">旅迹 · TripTrace</h1>
        <p className="text-slate-500 text-lg">旅行照片与视频智能归档工具</p>
      </div>

      <div className="flex flex-col gap-3 w-full max-w-sm">
        <button
          onClick={handleSelectFolder}
          className="px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition font-medium text-lg"
        >
          📂 选择照片文件夹
        </button>
        <button
          onClick={handleCheckBackend}
          className="px-6 py-3 bg-slate-100 text-slate-700 rounded-xl hover:bg-slate-200 transition font-medium"
        >
          🔗 检查后端连接
        </button>
      </div>

      <p className="text-slate-400 text-sm mt-4">
        Phase 1 · 项目骨架已就绪，开发中...
      </p>
    </div>
  );
}
