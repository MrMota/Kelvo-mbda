import { Cpu, Download, KeyRound, Plus, RefreshCw, Trash2, UserRound, Variable } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, useParams } from "react-router-dom";
import { androidApp, api, stream } from "../api";
import { useAuth } from "../auth";
import { useStore } from "../store";
import { Code, Modal, timeAgo, useToast } from "../ui/kit";

function Models() {
  const { models, modelsError, refreshModels, settings, refreshSettings } = useStore();
  const [url, setUrl] = useState(settings.ollama_base_url);
  const [def, setDef] = useState(settings.default_model);
  const [apiKey, setApiKey] = useState("");
  const [pullName, setPullName] = useState("");
  const [pull, setPull] = useState<{ status: string; pct: number } | null>(null);
  const toast = useToast();
  useEffect(() => { setUrl(settings.ollama_base_url); setDef(settings.default_model); }, [settings]);

  const save = async () => {
    await api("/api/settings", { method: "PUT", body: { ollama_base_url: url, default_model: def } });
    await refreshSettings();
    await refreshModels();
    toast("Settings saved");
  };
  const doPull = async () => {
    if (!pullName.trim()) return;
    setPull({ status: "starting", pct: 0 });
    try {
      await stream("/api/ollama/pull", { model: pullName.trim() }, (e) => {
        if (e.event === "progress") setPull({ status: e.data.status, pct: e.data.total ? Math.round((100 * (e.data.completed ?? 0)) / e.data.total) : 0 });
        if (e.event === "error") throw new Error(e.data.error);
      });
      toast(`Pulled ${pullName}`);
      setPullName("");
      refreshModels();
    } catch (e: any) { toast(e.message, "error"); }
    setPull(null);
  };
  const chat = models.filter((m) => !/embed|minilm|bge/i.test(m.name));
  return (
    <div className="col" style={{ gap: 18 }}>
      <div className="panel">
        <h2>Ollama server</h2>
        <label className="field">
          <span className="label">Base URL</span>
          <div className="row">
            <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://127.0.0.1:11434" style={{ maxWidth: 420 }} />
            <button className="btn" onClick={save}>Save & test</button>
          </div>
          <span className="help">Where <code>ollama serve</code> runs. Remote servers work too (set <code>OLLAMA_HOST=0.0.0.0</code> on that machine).</span>
        </label>
        <div className="row">
          <span className={`status-dot ${modelsError ? "err" : "ok"}`} />
          {modelsError ? <span className="error-text">{modelsError}</span> : <span className="muted">Connected · {models.length} models</span>}
          <button className="icon-btn sm" onClick={refreshModels} aria-label="Refresh"><RefreshCw size={13} /></button>
        </div>
        <label className="field">
          <span className="label">API key (optional)</span>
          <div className="row">
            <input className="input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={{ maxWidth: 420 }}
              placeholder={settings.has_ollama_api_key ? "Saved. Type a new one to replace it" : "Only for ollama.com or an Ollama behind a login"} autoComplete="off" />
            <button className="btn" disabled={!apiKey} onClick={async () => { await api("/api/settings", { method: "PUT", body: { ollama_api_key: apiKey } }); setApiKey(""); await refreshSettings(); await refreshModels(); toast("API key saved"); }}>Save</button>
            {settings.has_ollama_api_key && <button className="btn ghost" onClick={async () => { await api("/api/settings", { method: "PUT", body: { ollama_api_key: "" } }); await refreshSettings(); await refreshModels(); toast("API key removed"); }}>Remove</button>}
          </div>
          <span className="help">Sent as a Bearer token to your Ollama URL. Stored on this server, never shown again.</span>
        </label>
        <label className="field">
          <span className="label">Default model</span>
          <div className="row">
            <select className="select" value={def} onChange={(e) => setDef(e.target.value)} style={{ maxWidth: 420 }}>
              <option value="">None</option>
              {def && !chat.some((m) => m.name === def) && <option value={def}>{def}</option>}
              {chat.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
            </select>
            <button className="btn" onClick={save} disabled={def === settings.default_model}>Save</button>
          </div>
          <span className="help">Used by every Ollama and Agent component whose model is left blank, including all templates. For agents, pick a model marked “tools”.</span>
        </label>
      </div>
      <div className="panel">
        <h2>Pull a model</h2>
        <div className="row">
          <input className="input" value={pullName} onChange={(e) => setPullName(e.target.value)} placeholder="qwen3:8b, llama3.1:8b, nomic-embed-text…" style={{ maxWidth: 420 }}
            onKeyDown={(e) => e.key === "Enter" && doPull()} />
          <button className="btn primary" onClick={doPull} disabled={!!pull || !pullName.trim()}><Download size={15} /> Pull</button>
        </div>
        {pull && <div className="col" style={{ gap: 4, maxWidth: 420 }}><div className="progress"><div style={{ width: `${pull.pct}%` }} /></div><span className="help">{pull.status} {pull.pct ? `${pull.pct}%` : ""}</span></div>}
        <span className="help">Good starting points: <code>qwen3:8b</code> or <code>llama3.1:8b</code> for agents with tools, <code>gemma3</code> for chat, <code>nomic-embed-text</code> for RAG.</span>
      </div>
      <div className="panel">
        <h2>Installed models</h2>
        {models.length === 0 ? <span className="muted">No models found.</span> : (
          <table className="table"><thead><tr><th>Model</th><th>Size</th><th>Can do</th></tr></thead>
            <tbody>{models.map((m: any) => <tr key={m.name}><td className="mono">{m.name}</td><td>{m.parameter_size ?? ""}</td>
              <td>{m.capabilities ? m.capabilities.filter((c: string) => c !== "completion").map((c: string) => <span key={c} className={`badge ${c === "tools" ? "accent" : ""}`} style={{ marginRight: 4 }}>{c}</span>) : <span className="faint">unknown</span>}</td></tr>)}</tbody></table>
        )}
      </div>
    </div>
  );
}

function Variables() {
  const [vars, setVars] = useState<any[] | null>(null);
  const [edit, setEdit] = useState<any | null>(null);
  const toast = useToast();
  const load = () => api<any[]>("/api/variables").then(setVars);
  useEffect(() => { load(); }, []);
  const save = async () => {
    try {
      if (edit.id) await api(`/api/variables/${edit.id}`, { method: "PATCH", body: edit });
      else await api("/api/variables", { body: edit });
      setEdit(null);
      load();
    } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <div className="panel">
      <div className="row"><h2 className="grow">Global variables</h2><button className="btn primary" onClick={() => setEdit({ name: "", type: "generic", value: "" })}><Plus size={15} /> Add variable</button></div>
      <p className="muted" style={{ margin: 0 }}>Reuse values across flows. Write <code>{"${NAME}"}</code> in any text field and it is replaced at run time. Credential values are never shown again after saving.</p>
      {vars && vars.length === 0 ? <div className="empty">No variables yet.</div> : (
        <table className="table"><thead><tr><th>Name</th><th>Type</th><th>Value</th><th /></tr></thead>
          <tbody>{vars?.map((v) => (
            <tr key={v.id}>
              <td className="mono"><button className="btn ghost sm" onClick={() => setEdit({ ...v })}>{v.name}</button></td>
              <td><span className="badge">{v.type}</span></td>
              <td className="mono ellipsis" style={{ maxWidth: 280 }}>{v.value}</td>
              <td style={{ textAlign: "right" }}><button className="icon-btn sm" aria-label={`Delete ${v.name}`} onClick={async () => { if (confirm(`Delete ${v.name}?`)) { await api(`/api/variables/${v.id}`, { method: "DELETE" }); load(); } }}><Trash2 size={14} /></button></td>
            </tr>))}</tbody></table>
      )}
      {edit && (
        <Modal title={edit.id ? "Edit variable" : "New variable"} onClose={() => setEdit(null)} footer={<><button className="btn" onClick={() => setEdit(null)}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
          <label className="field"><span className="label">Name</span><input className="input mono" value={edit.name} autoFocus onChange={(e) => setEdit({ ...edit, name: e.target.value })} placeholder="COMPANY_NAME" /></label>
          {!edit.id && <label className="field"><span className="label">Type</span>
            <select className="select" value={edit.type} onChange={(e) => setEdit({ ...edit, type: e.target.value })}><option value="generic">Generic</option><option value="credential">Credential (hidden)</option></select></label>}
          <label className="field"><span className="label">Value</span>
            {edit.type === "credential" ? <input className="input" type="password" value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} />
              : <textarea className="textarea" value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} />}</label>
        </Modal>
      )}
    </div>
  );
}

function ApiKeys() {
  const [keys, setKeys] = useState<any[] | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const load = () => api<any[]>("/api/api-keys").then(setKeys);
  useEffect(() => { load(); }, []);
  return (
    <div className="panel">
      <div className="row"><h2 className="grow">API keys</h2>
        <button className="btn primary" onClick={async () => {
          const name = prompt("Name this key (e.g. my-app)") ?? "";
          const r = await api<any>("/api/api-keys", { body: { name } });
          setCreated(r.key);
          load();
        }}><Plus size={15} /> Create key</button></div>
      <p className="muted" style={{ margin: 0 }}>Keys authorise the run API (<code>/api/v1/run/…</code>) and the MCP server (<code>/mcp</code>). Send one as <code>x-api-key</code>.</p>
      {keys && keys.length === 0 ? <div className="empty">No keys yet.</div> : (
        <table className="table"><thead><tr><th>Name</th><th>Key</th><th>Created</th><th>Last used</th><th /></tr></thead>
          <tbody>{keys?.map((k) => (
            <tr key={k.id}><td>{k.name}</td><td className="mono">{k.prefix}…</td><td>{timeAgo(k.created_at)}</td><td>{k.last_used_at ? timeAgo(k.last_used_at) : "never"}</td>
              <td style={{ textAlign: "right" }}><button className="btn danger sm" onClick={async () => { if (confirm(`Revoke “${k.name}”? Apps using it stop working.`)) { await api(`/api/api-keys/${k.id}`, { method: "DELETE" }); load(); } }}>Revoke</button></td></tr>))}</tbody></table>
      )}
      {created && (
        <Modal title="Your new API key" icon={<KeyRound size={18} />} onClose={() => setCreated(null)} footer={<button className="btn primary" onClick={() => setCreated(null)}>Done</button>}>
          <p className="muted" style={{ margin: 0 }}>Copy it now. This is the only time you'll see it.</p>
          <Code>{created}</Code>
        </Modal>
      )}
    </div>
  );
}

function Account() {
  const { username, signOut, refresh } = useAuth();
  const [name, setName] = useState(username);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const save = async () => {
    setError(null);
    if (next.length < 8) return setError("Use at least 8 characters for the new password.");
    if (next !== repeat) return setError("The two new passwords don't match.");
    try {
      await api("/api/account/password", { body: { current_password: current, new_password: next, username: name } });
      setCurrent(""); setNext(""); setRepeat("");
      await refresh();
      toast("Password changed. Other devices were signed out.");
    } catch (e: any) { setError(e.message); }
  };
  return (
    <div className="panel">
      <h2>Your account</h2>
      <p className="muted" style={{ margin: 0 }}>Kelvo has one account: yours. Nobody can sign up. If you forget the password, run <code>kelvo set-password</code> on the server.</p>
      <label className="field" style={{ maxWidth: 360 }}><span className="label">Username</span>
        <input className="input" autoComplete="username" value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="field" style={{ maxWidth: 360 }}><span className="label">Current password</span>
        <input className="input" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} /></label>
      <label className="field" style={{ maxWidth: 360 }}><span className="label">New password</span>
        <input className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></label>
      <label className="field" style={{ maxWidth: 360 }}><span className="label">Repeat new password</span>
        <input className="input" type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} /></label>
      {error && <div className="error-text" role="alert">{error}</div>}
      <div className="row">
        <button className="btn primary" onClick={save} disabled={!current || !next}>Save</button>
        <button className="btn" onClick={signOut}>Sign out</button>
      </div>
      {androidApp() && (
        <div className="row" style={{ borderTop: "1px solid var(--border)", paddingTop: 14 }}>
          <span className="grow muted">This phone app connects to your Kelvo server by its address.</span>
          <button className="btn" onClick={() => androidApp()!.changeServer()}>Change server address</button>
        </div>
      )}
    </div>
  );
}

export default function Settings() {
  const { tab = "models" } = useParams();
  return (
    <div className="container">
      <div className="settings">
        <aside className="col">
          <h1 style={{ marginBottom: 8 }}>Settings</h1>
          <div className="side-list">
            <NavLink to="/settings/models" className={() => `side-item ${tab === "models" ? "active" : ""}`}><Cpu size={15} /> Models</NavLink>
            <NavLink to="/settings/variables" className={() => `side-item ${tab === "variables" ? "active" : ""}`}><Variable size={15} /> Global variables</NavLink>
            <NavLink to="/settings/keys" className={() => `side-item ${tab === "keys" ? "active" : ""}`}><KeyRound size={15} /> API keys</NavLink>
            <NavLink to="/settings/account" className={() => `side-item ${tab === "account" ? "active" : ""}`}><UserRound size={15} /> Account</NavLink>
          </div>
        </aside>
        <section>{tab === "variables" ? <Variables /> : tab === "keys" ? <ApiKeys /> : tab === "account" ? <Account /> : <Models />}</section>
      </div>
    </div>
  );
}
