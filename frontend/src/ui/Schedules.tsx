import { CalendarClock, Pause, Play, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Flow } from "../types";
import { timeAgo, Toggle, useToast } from "./kit";

export type Schedule = {
  id: string; flow_id: string; flow_name?: string; name: string; message: string;
  kind: "daily" | "interval"; time_of_day: string | null; days: string; every_minutes: number | null;
  enabled: number; next_run: string | null; last_run: string | null; last_status: string | null; last_output: string | null;
};

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function when(s: Schedule): string {
  if (s.kind === "interval") return `Every ${s.every_minutes} min`;
  const d = s.days === "0123456" ? "every day" : s.days === "01234" ? "weekdays" : s.days === "56" ? "weekends" : s.days.split("").map((x) => DAYS[+x]).join(", ");
  return `${s.time_of_day}, ${d}`;
}
const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" }) : "—");

function NewSchedule({ flows, flowId, onCreated }: { flows?: Flow[]; flowId?: string; onCreated: () => void }) {
  const [target, setTarget] = useState(flowId ?? flows?.[0]?.id ?? "");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [kind, setKind] = useState<"daily" | "interval">("daily");
  const [time, setTime] = useState("07:30");
  const [days, setDays] = useState("0123456");
  const [every, setEvery] = useState(60);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!target && flows?.[0]) setTarget(flows[0].id); }, [flows, target]);
  const save = async () => {
    setError(null);
    try {
      await api(`/api/flows/${target}/schedules`, { body: { name: name || message.slice(0, 40), message, kind, time_of_day: kind === "daily" ? time : null, days, every_minutes: kind === "interval" ? every : null } });
      setName(""); setMessage("");
      onCreated();
    } catch (e: any) { setError(e.message); }
  };
  return (
    <div className="col" style={{ gap: 10, padding: 14, border: "1px solid var(--border)", borderRadius: 10 }}>
      <b>New schedule</b>
      {flows && (
        <label className="field"><span className="label">Flow</span>
          <select className="select" value={target} onChange={(e) => setTarget(e.target.value)}>{flows.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select>
        </label>
      )}
      <label className="field"><span className="label">Message the agent gets each time</span>
        <textarea className="textarea" rows={2} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Search this week's Ollama news and save a summary to news.md" />
      </label>
      <label className="field"><span className="label">Name (optional)</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Morning news" />
      </label>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <select className="select" value={kind} onChange={(e) => setKind(e.target.value as any)} style={{ width: "auto" }} aria-label="Repeat">
          <option value="daily">Daily at</option><option value="interval">Every</option>
        </select>
        {kind === "daily" ? (
          <input className="input" type="time" value={time} onChange={(e) => setTime(e.target.value)} style={{ width: 130 }} aria-label="Time of day" />
        ) : (
          <><input className="input" type="number" min={5} value={every} onChange={(e) => setEvery(+e.target.value)} style={{ width: 90 }} aria-label="Minutes" /> minutes</>
        )}
      </div>
      {kind === "daily" && (
        <div className="row" style={{ gap: 4, flexWrap: "wrap" }} role="group" aria-label="Days">
          {DAYS.map((d, i) => {
            const on = days.includes(String(i));
            return <button key={d} type="button" className={`btn sm ${on ? "primary" : ""}`} aria-pressed={on}
              onClick={() => setDays(on ? days.replace(String(i), "") : [...days, String(i)].sort().join(""))}>{d}</button>;
          })}
        </div>
      )}
      <span className="help">Uses this computer's clock. Results appear in Chat. Commands that need approval don't run in scheduled runs.</span>
      {error && <div className="error-text" role="alert">{error}</div>}
      <div><button className="btn primary" onClick={save} disabled={!message.trim() || !target}><Plus size={15} /> Add schedule</button></div>
    </div>
  );
}

/** Schedules for one flow (editor) or for all flows (Settings). */
export function SchedulesPanel({ flowId }: { flowId?: string }) {
  const [items, setItems] = useState<Schedule[] | null>(null);
  const [flows, setFlows] = useState<Flow[]>();
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  const load = useCallback(() => api<Schedule[]>(`/api/schedules${flowId ? `?flow_id=${flowId}` : ""}`).then(setItems), [flowId]);
  useEffect(() => { load(); if (!flowId) api<Flow[]>("/api/flows").then(setFlows); }, [load, flowId]);
  return (
    <div className="col" style={{ gap: 14 }}>
      {items && items.length === 0 && <div className="empty" style={{ padding: 24 }}><CalendarClock size={22} className="faint" /><span>No schedules yet.</span></div>}
      {items?.map((s) => (
        <div key={s.id} className="col" style={{ gap: 6, padding: 12, border: "1px solid var(--border)", borderRadius: 10 }}>
          <div className="row">
            <Toggle on={!!s.enabled} label={s.enabled ? "Pause" : "Resume"} onChange={async (v) => { await api(`/api/schedules/${s.id}`, { method: "PATCH", body: { enabled: v } }); load(); }} />
            <b className="grow ellipsis">{s.name}</b>
            <button className="btn sm" disabled={busy === s.id} onClick={async () => {
              setBusy(s.id);
              try { const r = await api<any>(`/api/schedules/${s.id}/run`, { method: "POST" }); toast(r.status === "success" ? "Ran: the result is in Chat" : `Failed: ${r.output}`, r.status === "success" ? "info" : "error"); }
              finally { setBusy(null); load(); }
            }}><Play size={13} /> {busy === s.id ? "Running…" : "Run now"}</button>
            <button className="icon-btn sm" aria-label={`Delete ${s.name}`} onClick={async () => { if (confirm(`Delete the schedule “${s.name}”?`)) { await api(`/api/schedules/${s.id}`, { method: "DELETE" }); load(); } }}><Trash2 size={14} /></button>
          </div>
          <span className="muted" style={{ fontSize: 13 }}>{when(s)}{!flowId && s.flow_name ? <> · <Link to={`/chat/${s.flow_id}`} style={{ color: "var(--accent-strong)" }}>{s.flow_name}</Link></> : null}</span>
          <span className="help">“{s.message}”</span>
          <span className="help">
            {s.enabled ? <>Next: {fmt(s.next_run)}</> : <><Pause size={11} /> Paused</>}
            {s.last_run && <> · Last: {timeAgo(s.last_run)} <span className={`badge ${s.last_status === "error" ? "err" : "ok"}`} style={{ marginLeft: 4 }}>{s.last_status}</span></>}
          </span>
          {s.last_status === "error" && s.last_output && <div className="error-text" style={{ fontSize: 12 }}>{s.last_output.slice(0, 300)}</div>}
        </div>
      ))}
      <NewSchedule flowId={flowId} flows={flowId ? undefined : flows} onCreated={() => { load(); toast("Schedule added"); }} />
    </div>
  );
}
