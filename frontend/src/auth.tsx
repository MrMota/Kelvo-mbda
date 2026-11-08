import { LogIn } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api } from "./api";

type Status = { setup_required: boolean; authenticated: boolean; username: string | null };
type AuthApi = { username: string; signOut: () => Promise<void>; refresh: () => Promise<void> };
const Ctx = createContext<AuthApi>(null as unknown as AuthApi);
export const useAuth = () => useContext(Ctx);

function Mark() {
  return (
    <span className="brand-mark" style={{ width: 40, height: 40, borderRadius: 11 }}>
      <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
        <circle cx="9" cy="10" r="4" fill="currentColor" />
        <circle cx="23" cy="22" r="4" fill="currentColor" />
        <path d="M12 12.5 20 19.5" stroke="currentColor" strokeWidth="3" />
      </svg>
    </span>
  );
}

function AuthCard({ title, sub, children }: { title: string; sub: ReactNode; children: ReactNode }) {
  return (
    <div style={{ minHeight: "100%", display: "grid", placeItems: "center", padding: 16 }}>
      <div className="panel" style={{ width: "min(400px, 100%)", gap: 16, padding: 28 }}>
        <div className="col" style={{ alignItems: "center", gap: 10, textAlign: "center" }}>
          <Mark />
          <h1>{title}</h1>
          <span className="muted">{sub}</span>
        </div>
        {children}
      </div>
    </div>
  );
}

function Login({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/auth/login", { body: { username, password } });
      onDone();
    } catch (err: any) {
      setError(err.message);
      setBusy(false);
    }
  };
  return (
    <AuthCard title="Sign in to Kelvo" sub="Your agents, on your own models.">
      <form className="col" style={{ gap: 12 }} onSubmit={submit}>
        <label className="field"><span className="label">Username</span>
          <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required /></label>
        <label className="field"><span className="label">Password</span>
          <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {error && <div className="error-text" role="alert">{error}</div>}
        <button className="btn primary" type="submit" disabled={busy}><LogIn size={16} /> {busy ? "Signing in…" : "Sign in"}</button>
        <span className="help" style={{ textAlign: "center" }}>Forgot it? On the server, run <code>kelvo set-password</code>.</span>
      </form>
    </AuthCard>
  );
}

function Setup({ onDone }: { onDone: () => void }) {
  const [token, setToken] = useState(() => new URLSearchParams(location.search).get("token") ?? "");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) return setError("Use at least 8 characters for the password.");
    if (password !== repeat) return setError("The two passwords don't match.");
    setBusy(true);
    try {
      await api("/api/auth/setup", { body: { token, username, password } });
      history.replaceState(null, "", location.pathname);
      onDone();
    } catch (err: any) {
      setError(err.message);
      setBusy(false);
    }
  };
  return (
    <AuthCard title="Create your account" sub="Kelvo is just for you. Pick the username and password you'll sign in with.">
      <form className="col" style={{ gap: 12 }} onSubmit={submit}>
        <label className="field"><span className="label">Setup token</span>
          <input className="input mono" value={token} onChange={(e) => setToken(e.target.value)} required autoFocus={!token} />
          <span className="help">Printed in the server log when Kelvo started.</span></label>
        <label className="field"><span className="label">Username</span>
          <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus={!!token} /></label>
        <label className="field"><span className="label">Password</span>
          <input className="input" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <span className="help">At least 8 characters.</span></label>
        <label className="field"><span className="label">Repeat password</span>
          <input className="input" type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} required /></label>
        {error && <div className="error-text" role="alert">{error}</div>}
        <button className="btn primary" type="submit" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
      </form>
    </AuthCard>
  );
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const refresh = useCallback(async () => setStatus(await api<Status>("/api/auth/status")), []);
  useEffect(() => {
    refresh();
    const onUnauth = () => refresh();
    window.addEventListener("kelvo:unauthorized", onUnauth);
    return () => window.removeEventListener("kelvo:unauthorized", onUnauth);
  }, [refresh]);
  const signOut = useCallback(async () => {
    await api("/api/auth/logout", { method: "POST" });
    await refresh();
  }, [refresh]);
  if (!status) return null;
  if (status.setup_required) return <Setup onDone={refresh} />;
  if (!status.authenticated) return <Login onDone={refresh} />;
  return <Ctx.Provider value={{ username: status.username ?? "", signOut, refresh }}>{children}</Ctx.Provider>;
}
