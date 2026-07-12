import { useEffect } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { SpotlightNavbar } from "./components/SpotlightNavbar";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";
import VoicePage from "./pages/VoicePage";

const navItems = [
  { label: "Chat", to: "/" },
  { label: "Voice", to: "/voice" },
  { label: "Dashboard", to: "/dashboard" },
];

export default function App() {
  const location = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  const isChatPage = location.pathname === "/";

  return (
    <div className={`flex flex-col bg-slate-50/40 relative overflow-x-hidden ${
      isChatPage ? "h-screen overflow-hidden" : "min-h-full"
    }`}>
      {/* Background ambient glowing blobs (Surreal Blue & Yellow animated blobs) */}
      <div className="absolute top-[-10%] left-[-10%] w-[55%] aspect-square rounded-full bg-gradient-to-br from-blue-300/20 to-indigo-300/10 blur-[130px] pointer-events-none -z-10 animate-blob-1" />
      <div className="absolute bottom-[-15%] right-[-15%] w-[55%] aspect-square rounded-full bg-gradient-to-tr from-amber-300/15 to-yellow-250/15 blur-[130px] pointer-events-none -z-10 animate-blob-2" />
      <div className="absolute top-[15%] right-[-5%] w-[40%] aspect-square rounded-full bg-gradient-to-tr from-yellow-200/10 to-amber-300/10 blur-[110px] pointer-events-none -z-10 animate-blob-3" />
      <div className="absolute bottom-[15%] left-[-5%] w-[40%] aspect-square rounded-full bg-gradient-to-tr from-blue-300/15 to-cyan-200/10 blur-[110px] pointer-events-none -z-10 animate-blob-1" />

      <header className="border-b border-slate-200/60 bg-white/70 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-3 hover:opacity-90 transition-opacity">
            <div className="relative w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 via-indigo-600 to-blue-500 shadow-md shadow-brand-500/20 flex items-center justify-center overflow-hidden">
              <div className="absolute inset-0 bg-white/10 opacity-50"></div>
              <span className="relative font-display font-extrabold text-xl text-white tracking-tighter">
                B
              </span>
              <span className="absolute top-2.5 right-2.5 w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse shadow-[0_0_8px_#34d399]" />
            </div>
            <span className="font-display font-bold text-xl tracking-tight text-slate-900">
              BKAi
            </span>
          </Link>
          <SpotlightNavbar items={navItems} />
        </div>
      </header>
      <main className="flex-1 relative z-10 min-h-0 flex flex-col">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/voice" element={<VoicePage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </main>
    </div>
  );
}
