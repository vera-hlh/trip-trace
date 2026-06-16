import { BrowserRouter, Routes, Route, Navigate, Link } from "react-router-dom";
import Home from "./pages/Home";
import TestConsole from "./pages/TestConsole";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/test" element={<TestConsole />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
