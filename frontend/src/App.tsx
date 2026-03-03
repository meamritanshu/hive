import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import DashboardPage from "./pages/DashboardPage";
import ChatPage from "./pages/ChatPage";
import MemoryPage from "./pages/MemoryPage";
import SkillsPage from "./pages/SkillsPage";
import ConfigPage from "./pages/ConfigPage";
import SchedulerPage from "./pages/SchedulerPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="memory" element={<MemoryPage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route path="config" element={<ConfigPage />} />
        <Route path="scheduler" element={<SchedulerPage />} />
      </Route>
    </Routes>
  );
}
