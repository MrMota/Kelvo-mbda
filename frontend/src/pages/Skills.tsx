import { ArrowLeft, Download, Plus, Search, Sparkles, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, download, pickFile } from "../api";
import { useStore } from "../store";
import type { Skill } from "../types";
import { renderMarkdown, timeAgo, useToast } from "../ui/kit";

const NEW_BODY = "# Steps\n\n1. \n2. \n3. \n\n## Rules\n\n- ";

function SkillEditor({ skill, onDone }: { skill: Skill | null; onDone: () => void }) {
  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [body, setBody] = useState(skill?.body ?? NEW_BODY);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const { refreshSkills } = useStore();
  const toast = useToast();
  const nav = useNavigate();
  const nameOk = /^[a-z0-9][a-z0-9-]{0,63}$/.test(name);
  const dirty = !skill || name !== skill.name || description !== skill.description || body !== skill.body;

  const save = async () => {
    setError(null);
    if (!nameOk) return setError("Name: lowercase letters, numbers and dashes, like code-review.");
    if (!description.trim()) return setError("Say when the agent should use this skill. It's what the agent reads to decide.");
    setSaving(true);
    try {
      const s = skill
        ? await api<Skill>(`/api/skills/${skill.id}`, { method: "PATCH", body: { name, description, body } })
        : await api<Skill>("/api/skills", { body: { name, description, body } });
      await refreshSkills();
      toast("Skill saved");
      nav(`/skills/${s.id}`, { replace: true });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <button className="icon-btn" onClick={onDone} aria-label="Back to skills"><ArrowLeft size={18} /></button>
        <h1 className="grow">{skill ? skill.name : "New skill"}</h1>
        {skill && <button className="btn" onClick={async () => download(`${skill.name}.SKILL.md`, await api<string>(`/api/skills/${skill.id}/export`), "text/markdown")}><Download size={15} /> Export SKILL.md</button>}
        {skill && <button className="btn danger" onClick={async () => {
          if (!confirm(`Delete the skill “${skill.name}”? Agents that list it will stop loading it.`)) return;
          await api(`/api/skills/${skill.id}`, { method: "DELETE" });
          await refreshSkills();
          onDone();
        }}><Trash2 size={15} /> Delete</button>}
        <button className="btn primary" onClick={save} disabled={saving || !dirty}>{saving ? "Saving…" : "Save skill"}</button>
      </div>
      {error && <div className="error-text" role="alert">{error}</div>}
      <div className="panel">
        <label className="field">
          <span className="label">Name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))} placeholder="code-review" style={{ maxWidth: 360 }} />
          <span className="help">The agent calls <code>load_skill("{name || "name"}")</code> to read it.</span>
        </label>
        <label className="field">
          <span className="label">When to use it</span>
          <textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} maxLength={1024}
            placeholder="Use when the user asks to review code, find bugs or suggest improvements." />
          <span className="help">Always in the agent's context, so keep it to one or two sentences. {description.length}/1024</span>
        </label>
      </div>
      <div className="skill-editor">
        <label className="field">
          <span className="label">Instructions (Markdown)</span>
          <textarea className="textarea code" value={body} onChange={(e) => setBody(e.target.value)} style={{ minHeight: 380 }} />
          <span className="help">Only loaded when the agent needs it, so it can be long and detailed.</span>
        </label>
        <div className="field">
          <span className="label">Preview</span>
          <div className="md-preview" style={{ minHeight: 380 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(body) }} />
        </div>
      </div>
    </div>
  );
}

export default function Skills() {
  const { id } = useParams();
  const { skills, refreshSkills } = useStore();
  const [q, setQ] = useState("");
  const nav = useNavigate();
  const toast = useToast();
  useEffect(() => { refreshSkills(); }, [refreshSkills]);
  const shown = useMemo(() => skills.filter((s) => (s.name + s.description).toLowerCase().includes(q.toLowerCase())), [skills, q]);

  if (id) {
    const skill = id === "new" ? null : skills.find((s) => s.id === id);
    if (id !== "new" && !skill) return <div className="container">{skills.length ? <><h1>Skill not found</h1><Link to="/skills" className="btn">Back</Link></> : null}</div>;
    return <div className="container"><SkillEditor key={id} skill={skill ?? null} onDone={() => nav("/skills")} /></div>;
  }

  const importSkill = async () => {
    const text = await pickFile(".md,text/markdown");
    if (!text) return;
    try {
      const s = await api<Skill>("/api/skills/import", { body: { content: text } });
      await refreshSkills();
      toast(`Imported “${s.name}”`);
    } catch (e: any) { toast(e.message, "error"); }
  };

  return (
    <div className="container col" style={{ gap: 18 }}>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <div className="grow">
          <h1>Skills</h1>
          <p className="muted" style={{ margin: "4px 0 0", maxWidth: 680 }}>
            Instructions your agents pick up only when a request calls for them. An agent always sees each skill's name and when to use it; the full text loads when it calls <code>load_skill</code>. That keeps small local models fast and on task.
          </p>
        </div>
        <button className="btn" onClick={importSkill}><Upload size={15} /> Import SKILL.md</button>
        <Link className="btn primary" to="/skills/new"><Plus size={16} /> New skill</Link>
      </div>
      {skills.length > 0 && (
        <div className="search" style={{ maxWidth: 360 }}>
          <Search size={15} />
          <input className="input" placeholder="Search skills" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search skills" />
        </div>
      )}
      {skills.length === 0 ? (
        <div className="empty">
          <span className="card-icon" style={{ width: 44, height: 44 }}><Sparkles size={22} /></span>
          <h2>No skills yet</h2>
          <span>Write your first skill, then give it to an agent with the Skill component or the agent's Library skills field.</span>
          <Link className="btn primary" to="/skills/new"><Plus size={16} /> New skill</Link>
        </div>
      ) : shown.length === 0 ? <div className="empty">No skills match “{q}”.</div> : (
        <div className="cards">
          {shown.map((s) => (
            <Link key={s.id} to={`/skills/${s.id}`} className="card">
              <span className="card-icon"><Sparkles size={17} /></span>
              <h3 className="mono" style={{ fontSize: 13.5 }}>{s.name}</h3>
              <span className="card-desc">{s.description}</span>
              <span className="faint" style={{ fontSize: 12, marginTop: "auto" }}>Edited {timeAgo(s.updated_at)}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
