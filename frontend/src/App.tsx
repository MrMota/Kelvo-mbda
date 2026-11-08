import { LogOut, Moon, Settings as SettingsIcon, Sparkles, Sun, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import { useAuth } from "./auth";
import Editor from "./pages/Editor";
import Home from "./pages/Home";
import Settings from "./pages/Settings";
import Skills from "./pages/Skills";

export function Brand() {
  return (
    <NavLink to="/" className="brand" aria-label="Kelvo home">
      <span className="brand-mark">
        <svg width="16" height="16" viewBox="0 0 32 32" aria-hidden="true">
          <circle cx="9" cy="10" r="4" fill="currentColor" />
          <circle cx="23" cy="22" r="4" fill="currentColor" />
          <path d="M12 12.5 20 19.5" stroke="currentColor" strokeWidth="3" />
        </svg>
      </span>
      Kelvo
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
      <span className={`status-dot ${h ? (ok ? "ok" : "err") : ""}`} aria-hidden="true" />
      <span className="status-text">{h ? (ok ? `Ollama · ${h.ollama.models} models` : "Ollama not running") : "…"}</span>
    </NavLink>
  );
}

export function SignOut() {
  const { username, signOut } = useAuth();
  return (
    <button className="icon-btn" aria-label={`Sign out ${username}`} title={`Signed in as ${username}. Sign out`} onClick={signOut}>
      <LogOut size={17} />
    </button>
  );
}

export function ThemeToggle() {
  const [dark, setDark] = useState(() =>
    document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
  return (
    <button className="icon-btn" aria-label="Toggle theme" title="Toggle theme" onClick={() => {
      const next = dark ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("kelvo-theme", next); } catch {}
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
        <SignOut />
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
