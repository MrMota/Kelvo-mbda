import { Copy, Download, FolderPlus, MoreHorizontal, Pencil, Plus, Search, Trash2, Upload, Workflow } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, download, pickFile } from "../api";
import type { Flow, Project, Template } from "../types";
import { Icon } from "../ui/Icon";
import { Menu, Modal, timeAgo, useToast } from "../ui/kit";

export function NewFlowModal({ projectId, onClose }: { projectId?: string; onClose: () => void }) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const nav = useNavigate();
  const toast = useToast();
  useEffect(() => { api<Template[]>("/api/templates").then(setTemplates); }, []);
  const create = async (template?: string) => {
    try {
      const f = await api<Flow>("/api/flows", { body: { template, project_id: projectId, name: template ? undefined : "Untitled Flow" } });
      nav(`/flow/${f.id}`);
    } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <Modal title="New flow" onClose={onClose} size="lg">
      <div className="cards">
        <button className="card" onClick={() => create()} style={{ textAlign: "left", borderStyle: "dashed" }}>
          <span className="card-icon"><Plus size={18} /></span>
          <h3>Blank Flow</h3>
          <span className="card-desc">Start from an empty canvas.</span>
        </button>
        {templates.map((t) => (
          <button key={t.id} className="card" onClick={() => create(t.id)} style={{ textAlign: "left" }}>
            <span className="card-icon"><Icon name={t.icon} size={18} /></span>
            <h3>{t.name}</h3>
            <span className="card-desc">{t.description}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
}

function EditFlowModal({ flow, projects, onClose, onSaved }: { flow: Flow; projects: Project[]; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(flow.name);
  const [description, setDescription] = useState(flow.description);
  const [projectId, setProjectId] = useState(flow.project_id);
  const [locked, setLocked] = useState(!!flow.locked);
  const toast = useToast();
  const save = async () => {
    try {
      await api(`/api/flows/${flow.id}`, { method: "PATCH", body: { name, description, project_id: projectId, locked } });
      onSaved(); onClose();
    } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <Modal title="Flow details" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
      <label className="field"><span className="label">Name</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <label className="field"><span className="label">Description</span><textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <label className="field"><span className="label">Project</span>
        <select className="select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      </label>
      <label className="row"><input type="checkbox" checked={locked} onChange={(e) => setLocked(e.target.checked)} /> Lock flow (read-only on the canvas)</label>
    </Modal>
  );
}

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [flows, setFlows] = useState<Flow[] | null>(null);
  const [project, setProject] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [menu, setMenu] = useState<string | null>(null);
  const [editing, setEditing] = useState<Flow | null>(null);
  const nav = useNavigate();
  const toast = useToast();

  const load = useCallback(async () => {
    const [ps, fs] = await Promise.all([api<Project[]>("/api/projects"), api<Flow[]>("/api/flows")]);
    setProjects(ps);
    setFlows(fs);
    setProject((p) => p ?? ps[0]?.id ?? null);
  }, []);
  useEffect(() => { load(); }, [load]);

  const shown = useMemo(() => (flows ?? []).filter((f) => f.project_id === project && (f.name + " " + f.description).toLowerCase().includes(q.toLowerCase())), [flows, project, q]);
  const current = projects.find((p) => p.id === project);

  const importFlow = async () => {
    const text = await pickFile(".json,application/json");
    if (!text) return;
    try {
      const j = JSON.parse(text);
      const f = await api<Flow>("/api/flows", { body: { name: j.name ?? "Imported flow", description: j.description ?? "", data: j.data ?? j, project_id: project } });
      toast(`Imported “${f.name}”`);
      load();
    } catch (e: any) { toast(`Import failed: ${e.message}`, "error"); }
  };
  const exportFlow = async (id: string) => {
    const f = await api<Flow>(`/api/flows/${id}`);
    download(`${f.name.replace(/[^\w-]+/g, "_")}.json`, JSON.stringify({ name: f.name, description: f.description, data: f.data }, null, 2));
  };
  const newProject = async () => {
    const name = prompt("Project name");
    if (!name) return;
    const p = await api<Project>("/api/projects", { body: { name } });
    await load();
    setProject(p.id);
  };

  return (
    <div className="container">
      <div className="home">
        <aside className="col">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <span className="section-title">Projects</span>
            <button className="icon-btn sm" onClick={newProject} aria-label="New project" title="New project"><FolderPlus size={15} /></button>
          </div>
          <div className="side-list">
            {projects.map((p) => (
              <button key={p.id} className={`side-item ${p.id === project ? "active" : ""}`} onClick={() => setProject(p.id)}>
                <span className="grow ellipsis">{p.name}</span>
                <span className="faint" style={{ fontSize: 12 }}>{flows?.filter((f) => f.project_id === p.id).length ?? ""}</span>
              </button>
            ))}
          </div>
        </aside>
        <section className="col" style={{ gap: 18 }}>
          <div className="row" style={{ flexWrap: "wrap" }}>
            <h1 className="grow">{current?.name ?? "Flows"}</h1>
            <button className="btn" onClick={importFlow}><Upload size={15} /> Import</button>
            <button className="btn primary" onClick={() => setShowNew(true)}><Plus size={16} /> New Flow</button>
          </div>
          {flows && flows.filter((f) => f.project_id === project).length > 0 && (
            <div className="search" style={{ maxWidth: 360 }}>
              <Search size={15} />
              <input className="input" placeholder="Search flows" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search flows" />
            </div>
          )}
          {flows === null ? null : shown.length === 0 && !q ? (
            <div className="empty">
              <span className="card-icon" style={{ width: 44, height: 44 }}><Workflow size={22} /></span>
              <h2>Your first agent is two clicks away</h2>
              <span>Pick <b>Simple Agent</b> for one that already works, or start blank. Every model call goes to your own Ollama.</span>
              <button className="btn primary" onClick={() => setShowNew(true)}><Plus size={16} /> New Flow</button>
            </div>
          ) : shown.length === 0 ? (
            <div className="empty">No flows match “{q}”.</div>
          ) : (
            <div className="cards">
              {shown.map((f) => (
                <div key={f.id} className="card" onClick={() => nav(`/flow/${f.id}`)} role="link" tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && nav(`/flow/${f.id}`)}>
                  <div className="row">
                    <span className="card-icon"><Icon name={f.kind === "agent" ? "bot" : "workflow"} size={18} /></span>
                    <span className="grow" />
                    {!!f.mcp_enabled && <span className="badge accent">MCP</span>}
                    {!!f.locked && <span className="badge">Locked</span>}
                    <button className="icon-btn sm" aria-label="Flow menu" onClick={(e) => { e.stopPropagation(); setMenu(menu === f.id ? null : f.id); }}><MoreHorizontal size={16} /></button>
                  </div>
                  <h3 className="ellipsis">{f.name}</h3>
                  <span className="card-desc">{f.description || `${f.node_count} components`}</span>
                  <span className="faint" style={{ fontSize: 12, marginTop: "auto" }}>Edited {timeAgo(f.updated_at)}</span>
                  {menu === f.id && (
                    <Menu onClose={() => setMenu(null)} style={{ right: 10, top: 44 }}>
                      <button onClick={() => { setEditing(f); setMenu(null); }}><Pencil size={14} /> Edit details</button>
                      <button onClick={async () => { await api(`/api/flows/${f.id}/duplicate`, { method: "POST" }); setMenu(null); load(); }}><Copy size={14} /> Duplicate</button>
                      <button onClick={() => { exportFlow(f.id); setMenu(null); }}><Download size={14} /> Export JSON</button>
                      <button className="danger" onClick={async () => {
                        setMenu(null);
                        if (!confirm(`Delete “${f.name}” and its chat history? This can't be undone.`)) return;
                        await api(`/api/flows/${f.id}`, { method: "DELETE" });
                        toast("Flow deleted");
                        load();
                      }}><Trash2 size={14} /> Delete</button>
                    </Menu>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
      {showNew && <NewFlowModal projectId={project ?? undefined} onClose={() => setShowNew(false)} />}
      {editing && <EditFlowModal flow={editing} projects={projects} onClose={() => setEditing(null)} onSaved={load} />}
    </div>
  );
}
