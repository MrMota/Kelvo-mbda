import { Moon, Settings as SettingsIcon, Sparkles, Sun, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import Editor from "./pages/Editor";
import Home from "./pages/Home";
import Settings from "./pages/Settings";
import Skills from "./pages/Skills";

export function Brand() {
  return (
    <NavLink to="/" className="brand" aria-label="MBDAflow home">
      <span className="brand-mark">
        <svg width="16" height="16" viewBox="0 0 32 32" aria-hidden="true">
          <circle cx="9" cy="10" r="4" fill="currentColor" />
          <circle cx="23" cy="22" r="4" fill="currentColor" />
          <path d="M12 12.5 20 19.5" stroke="currentColor" strokeWidth="3" />
        </svg>
      </span>
      MBDAflow
    </NavLink>
  );
}

export function OllamaStatus() {
  const [h, setH] = useState<any>(null);
  useEffect(() => {
    const load = () => api("/api/health").then(setH).catch(() => setH(null));
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);
  const ok = h?.ollama?.reachable;
  return (
    <NavLink to="/settings" className="row faint" style={{ fontSize: 12.5 }} title={ok ? `Ollama at ${h.ollama.url}` : h?.ollama?.error ?? "Checking Ollama…"}>
      <span className={`status-dot ${h ? (ok ? "ok" : "err") : ""}`} />
      {h ? (ok ? `Ollama · ${h.ollama.models} models` : "Ollama offline") : "…"}
    </NavLink>
  );
}

export function ThemeToggle() {
  const [dark, setDark] = useState(() =>
    document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
  return (
    <button className="icon-btn" aria-label="Toggle theme" title="Toggle theme" onClick={() => {
      const next = dark ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("mbdaflow-theme", next); } catch {}
      setDark(!dark);
    }}>{dark ? <Sun size={17} /> : <Moon size={17} />}</button>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <header className="topbar">
        <Brand />
        <nav className="nav">
          <NavLink to="/" end><Workflow size={16} /><span>Flows</span></NavLink>
          <NavLink to="/skills"><Sparkles size={16} /><span>Skills</span></NavLink>
          <NavLink to="/settings"><SettingsIcon size={16} /><span>Settings</span></NavLink>
        </nav>
        <span className="spacer" />
        <OllamaStatus />
        <ThemeToggle />
      </header>
      <main className="page">{children}</main>
    </div>
  );
}

export default function App() {
  const loc = useLocation();
  if (loc.pathname.startsWith("/flow/")) {
    return <Routes><Route path="/flow/:id" element={<Editor />} /></Routes>;
  }
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/skills" element={<Skills />} />
        <Route path="/skills/:id" element={<Skills />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/settings/:tab" element={<Settings />} />
        <Route path="*" element={<div className="container"><h1>Not found</h1></div>} />
      </Routes>
    </Shell>
  );
}
