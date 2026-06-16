/**
 * App.tsx
 * 根组件：主布局 + 状态驱动的页面切换
 * （不使用 URL 路由，因为 Electron 生产模式用 loadFile，路径不稳定）
 */
import Layout from "@/components/Layout";
import { useAppStore } from "@/store/appStore";

import HomePage from "@/pages/HomePage";
import FolderSetup from "@/pages/FolderSetup";
import ScanPage from "@/pages/ScanPage";
import ArchivePage from "@/pages/ArchivePage";
import MapPage from "@/pages/MapPage";
import TestConsole from "@/pages/TestConsole";

function PageRouter() {
  const { currentPage } = useAppStore();

  switch (currentPage) {
    case "home":         return <HomePage />;
    case "folder-setup": return <FolderSetup />;
    case "scan":         return <ScanPage />;
    case "archive":      return <ArchivePage />;
    case "map":          return <MapPage />;
    case "test":         return <TestConsole />;
    default:             return <HomePage />;
  }
}

function App() {
  return (
    <Layout>
      <PageRouter />
    </Layout>
  );
}

export default App;
