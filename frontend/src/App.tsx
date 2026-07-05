import { Link, Route, Routes } from "react-router-dom";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";
import VoicePage from "./pages/VoicePage";

export default function App() {
  return (
    <div className="min-h-full flex flex-col bg-white">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-brand-600 text-white flex items-center justify-center font-display font-bold text-lg">
              Bk
            </div>
            <div>
              <div className="font-display font-bold text-lg text-slate-900">BkAI</div>
              <div className="text-sm text-slate-500">Tư vấn tuyển sinh HCMUT</div>
            </div>
          </Link>
          <nav className="flex items-center gap-2">
            <Link
              to="/"
              className="px-4 py-2 rounded-lg text-sm font-medium text-slate-700 hover:bg-brand-50 hover:text-brand-700 transition"
            >
              Chat
            </Link>
            <Link
              to="/voice"
              className="px-4 py-2 rounded-lg text-sm font-medium text-slate-700 hover:bg-brand-50 hover:text-brand-700 transition"
            >
              Voice
            </Link>
            <Link
              to="/dashboard"
              className="px-4 py-2 rounded-lg text-sm font-medium text-slate-700 hover:bg-brand-50 hover:text-brand-700 transition"
            >
              Dashboard
            </Link>
          </nav>
        </div>
      </header>
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/voice" element={<VoicePage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </main>
    </div>
  );
}
