import { AlertTriangle, Bot, Brain, Check, ChevronDown, ChevronRight, CircleCheck, CircleDashed, CircleDot, FileText, FoldVertical, History, Image as ImageIcon, ListChecks, Loader2, Maximize2, Minimize2, MoreHorizontal, Paperclip, Plus, Search, Send, ShieldAlert, Square, Trash2, Undo2, User, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, newSessionId, stream, type StreamEvent } from "../api";
import type { Attachment, ChatMessage, FlowGraph, PlanStep, Step, Usage } from "../types";
import { Menu, timeAgo, useToast } from "./kit";
import { Markdown } from "./Markdown";

type Session = { session_id: string; count: number; last: string; title: string | null };

type Approval = { id: string; tool: string; summary: string; details: Record<string, unknown>; answering?: boolean };
type Answer = { approve: boolean; scope?: "once" | "chat" | "always"; pattern?: string };

/** A unified diff with red/green lines. */
export function Diff({ text }: { text: string }) {
  return (
    <pre className="diff" aria-label="Changes">
      {text.split("\n").map((l, i) => {
        const cls = l.startsWith("+++") || l.startsWith("---") ? "meta" : l.startsWith("@@") ? "hunk" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : "";
        return <span key={i} className={cls}>{l || " "}{"\n"}</span>;
      })}
    </pre>
  );
}

const TITLES: Record<string, string> = {
  files: "Change this file?", skill: "Save this as a skill?", browser: "Let the agent do this in the browser?",
};

/** An agent is waiting for you: run this command / write this file? Nothing happens until you choose. */
function ApprovalCard({ a, onAnswer }: { a: Approval; onAnswer: (ans: Answer) => void }) {
  const cmd = a.details.command as string | undefined;
  const diff = a.details.diff as string | undefined;
  const [more, setMore] = useState(false);
  const [pattern, setPattern] = useState(String(a.details.suggest ?? cmd ?? ""));
  const rest = Object.fromEntries(Object.entries(a.details).filter(([k]) => !["command", "diff", "suggest", "folder", "shell", "instructions", "full path"].includes(k)));
  return (
    <div className="approval" role="alertdialog" aria-label={`Approve ${a.tool}?`}>
      <div className="row" style={{ gap: 8 }}>
        <ShieldAlert size={18} color="var(--warn)" />
        <b className="grow">{cmd ? "Run this command on your computer?" : TITLES[a.tool] ?? `Allow this ${a.tool} action?`}</b>
      </div>
      <pre className="approval-cmd">{cmd ?? a.summary}</pre>
      {"folder" in a.details && <div className="help">In {String(a.details.folder)}{a.details.shell && a.details.shell !== "default" ? ` · ${String(a.details.shell)}` : ""}</div>}
      {"full path" in a.details && <div className="help">{String(a.details["full path"])}</div>}
      {diff ? <Diff text={diff} /> : null}
      {a.tool === "skill" && <div className="md-box"><Markdown text={String(a.details.instructions ?? "")} /></div>}
      {!cmd && !diff && a.tool !== "skill" && Object.keys(rest).length > 0 && (
        <pre className="approval-cmd" style={{ fontSize: 12 }}>{JSON.stringify(rest, null, 2)}</pre>
      )}
      {a.tool === "skill" && <div className="help">{String(a.details.description ?? "")}</div>}
      {more && cmd && (
        <div className="col" style={{ gap: 6 }}>
          <label className="field">
            <span className="label">Don't ask again for commands matching</span>
            <input className="input" value={pattern} onChange={(e) => setPattern(e.target.value)} aria-label="Command pattern" />
          </label>
          <span className="help">* matches anything. A pattern with * never covers commands that chain (&, |, ;) or redirect (&gt;).</span>
          <div className="row" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
            <button className="btn sm" disabled={a.answering || !pattern.trim()} onClick={() => onAnswer({ approve: true, scope: "chat", pattern })}>Allow in this chat</button>
            <button className="btn sm" disabled={a.answering || !pattern.trim()} onClick={() => onAnswer({ approve: true, scope: "always", pattern })}>Always allow</button>
          </div>
        </div>
      )}
      <div className="row" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
        {cmd && <button className="btn ghost sm" aria-expanded={more} onClick={() => setMore(!more)}>More <ChevronDown size={13} /></button>}
        {(a.tool === "files" || a.tool === "browser") && (
          <button className="btn ghost sm" disabled={a.answering} onClick={() => onAnswer({ approve: true, scope: "chat", pattern: "*" })}>
            Allow all {a.tool === "files" ? "file changes" : "browser actions"} in this chat
          </button>
        )}
        <span className="grow" />
        <button className="btn sm" disabled={a.answering} onClick={() => onAnswer({ approve: false })}><X size={14} /> Reject</button>
        <button className="btn primary sm" disabled={a.answering} onClick={() => onAnswer({ approve: true })}><Check size={14} /> Approve</button>
      </div>
    </div>
  );
}

function PlanBox({ plan }: { plan: PlanStep[] }) {
  const done = plan.filter((s) => s.status === "done").length;
  return (
    <div className="plan" aria-label="Plan">
      <div className="plan-head"><ListChecks size={14} /> Plan <span className="faint">{done}/{plan.length}</span></div>
      <ol>
        {plan.map((s, i) => (
          <li key={i} className={s.status}>
            {s.status === "done" ? <CircleCheck size={14} /> : s.status === "in_progress" ? <CircleDot size={14} /> : <CircleDashed size={14} />}
            <span>{s.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

const k = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n));

/** Speed and memory meter: tokens per second, and how full the model's context window is. */
function UsageLine({ u }: { u: Usage }) {
  const pct = u.used && u.limit ? Math.min(100, Math.round((100 * u.used) / u.limit)) : null;
  return (
    <div className="usage" title="Speed of the model, and how much of its context window (memory) this chat uses">
      {u.tokens_per_sec != null && <span>{u.tokens_per_sec} tok/s</span>}
      {pct != null && (
        <span className="row" style={{ gap: 6 }}>
          memory {k(u.used!)} / {k(u.limit!)}
          <span className="meter" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Context window used">
            <span style={{ width: `${pct}%` }} className={pct > 85 ? "hot" : pct > 60 ? "warm" : ""} />
          </span>
          {pct}%
        </span>
      )}
    </div>
  );
}

function StepCard({ step }: { step: Step }) {
  const running = step.status === "running";
  return (
    <details className="step">
      <summary>
        {running ? <Loader2 size={13} className="spin" color="var(--warn)" /> : <Wrench size={13} color={step.error ? "var(--danger)" : "var(--t-Tool)"} />}
        <span className="grow ellipsis">{running ? "Calling" : step.error ? "Failed" : "Used"} <code>{step.name}</code></span>
        <ChevronRight size={13} className="faint" />
      </summary>
      <pre><b>Input</b>{"\n"}{JSON.stringify(step.input, null, 2)}{step.output != null && <>{"\n\n"}<b>Output</b>{"\n"}{step.output}</>}</pre>
    </details>
  );
}

function MessageView({ m, onUndo }: { m: ChatMessage; onUndo?: (m: ChatMessage) => void }) {
  const steps = m.properties?.steps ?? [];
  if (m.properties?.summary) {
    return (
      <details className="summary-msg">
        <summary><FoldVertical size={13} /> Earlier messages summarized{m.properties.covered ? ` (${m.properties.covered})` : ""}: the agent remembers this summary instead</summary>
        <div className="msg-text">{m.text}</div>
      </details>
    );
  }
  const ch = m.properties?.changes;
  return (
    <div className={`msg ${m.sender}`}>
      <span className="msg-avatar">{m.sender === "user" ? <User size={15} /> : <Bot size={15} />}</span>
      <div className="msg-body">
        <div className="msg-name">{m.sender_name}{m.properties?.source?.source && <span className="faint" style={{ fontWeight: 500 }}>· {m.properties.source.source}</span>}</div>
        {steps.length > 0 && <div className="steps">{steps.map((s, i) => <StepCard key={i} step={s} />)}</div>}
        {m.properties?.warning && <div className="notice warn"><AlertTriangle size={14} /> {m.properties.warning}</div>}
        {m.properties?.thinking && (
          <details className="thinking" open={m.streaming && !m.text}>
            <summary>{m.streaming && !m.text ? <Loader2 size={13} className="spin" /> : <Brain size={13} />} {m.streaming && !m.text ? "Thinking…" : "Thought process"}</summary>
            <div className="thinking-text">{m.properties.thinking}</div>
          </details>
        )}
        {(m.properties?.plan?.length ?? 0) > 0 && <PlanBox plan={m.properties!.plan!} />}
        {m.streaming && m.properties?.status && <div className="notice"><Loader2 size={13} className="spin" /> {m.properties.status}</div>}
        {(m.properties?.files?.length ?? 0) > 0 && (
          <div className="chips">{m.properties!.files!.map((f) => f.kind === "image" && f.id
            ? <a key={f.id} href={`/api/uploads/${f.id}/file`} target="_blank" rel="noreferrer"><img className="thumb" src={`/api/uploads/${f.id}/file`} alt={f.name} /></a>
            : <span key={f.id ?? f.name} className="chip"><FileText size={12} /> {f.name}</span>)}</div>
        )}
        {(m.text || m.streaming) && (m.sender === "machine" && !m.error
          ? <Markdown text={m.text} className={`msg-text md-reply ${m.streaming ? "cursor" : ""}`} />
          : <div className={`msg-text ${m.error ? "err" : ""} ${m.streaming ? "cursor" : ""}`}>{m.text}</div>)}
        {!m.text && !m.streaming && !steps.length && <div className="faint">(empty reply)</div>}
        {ch && ch.files.length > 0 && !m.streaming && (
          <div className="changes">
            <span className="grow ellipsis" title={ch.files.join("\n")}>
              {ch.undone ? "Undone: " : "Changed "}{ch.files.length} file{ch.files.length > 1 ? "s" : ""}: {ch.files.map((f) => f.split(/[\\/]/).pop()).join(", ")}
            </span>
            {!ch.undone && onUndo && <button className="btn sm" onClick={() => onUndo(m)}><Undo2 size={13} /> Undo</button>}
          </div>
        )}
        {m.sender === "machine" && m.properties?.usage && <UsageLine u={m.properties.usage} />}
      </div>
    </div>
  );
}

const MAX_UPLOAD = 25 * 1024 * 1024;

function readAsBase64(f: File): Promise<string> {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(",", 2)[1] ?? "");
    r.onerror = () => rej(r.error);
    r.readAsDataURL(f);
  });
}

/**
 * The chat: used as the editor's Playground panel (variant "panel", runs the unsaved graph)
 * and as the Chat page (variant "page", runs the saved flow).
 */
export function Playground({ flowId, getGraph, hasChatInput = true, onEvent, onClose, variant = "panel", header }: {
  flowId: string;
  getGraph?: () => FlowGraph;
  hasChatInput?: boolean;
  onEvent?: (e: StreamEvent) => void;
  onClose?: () => void;
  variant?: "panel" | "page";
  header?: ReactNode;
}) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string>(() => newSessionId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [full, setFull] = useState(false);
  const [menu, setMenu] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [files, setFiles] = useState<(Attachment & { uploading?: boolean })[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [working, setWorking] = useState(false);  // an agent is still running in this chat (e.g. after a disconnect)
  const poll = useRef<number | null>(null);
  const watchRef = useRef<(sid: string) => void>(() => {});
  const fileInput = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const stoppedByUser = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);
  const toast = useToast();

  const loadSessions = useCallback(async () => {
    const s = await api<Session[]>(`/api/flows/${flowId}/sessions`);
    setSessions(s);
    return s;
  }, [flowId]);

  const openSession = useCallback(async (sid: string) => {
    setSessionId(sid);
    setWorking(false);
    const ms = await api<ChatMessage[]>(`/api/flows/${flowId}/messages?session_id=${encodeURIComponent(sid)}`);
    setMessages(ms);
    const st = await api<{ running: boolean }>(`/api/flows/${flowId}/status?session_id=${encodeURIComponent(sid)}`).catch(() => null);
    if (st?.running) watchRef.current(sid);  // came back while the agent is still busy
  }, [flowId]);

  /** Ask the server whether this chat's agent is still working (and waiting for approvals); refresh when done. */
  const watch = useCallback((sid: string) => {
    if (poll.current) window.clearTimeout(poll.current);
    const tick = async () => {
      try {
        const st = await api<{ running: boolean; approvals: Approval[] }>(`/api/flows/${flowId}/status?session_id=${encodeURIComponent(sid)}`);
        setApprovals(st.approvals);
        if (st.running) {
          setWorking(true);
          poll.current = window.setTimeout(tick, 3000);
          return;
        }
      } catch {
        poll.current = window.setTimeout(tick, 5000);  // offline for a moment: try again
        return;
      }
      setWorking(false);
      poll.current = null;
      const ms = await api<ChatMessage[]>(`/api/flows/${flowId}/messages?session_id=${encodeURIComponent(sid)}`);
      setMessages(ms);
      loadSessions();
    };
    tick();
  }, [flowId, loadSessions]);
  watchRef.current = watch;
  useEffect(() => () => { if (poll.current) window.clearTimeout(poll.current); }, []);

  useEffect(() => {
    setMessages([]);
    setSessionId(newSessionId());
    setFiles([]);
    loadSessions().then((s) => { if (s[0]) openSession(s[0].session_id); });
  }, [loadSessions, openSession]);

  const attach = async (list: FileList | null) => {
    for (const f of Array.from(list ?? [])) {
      if (f.size > MAX_UPLOAD) { toast(`${f.name} is larger than 25 MB.`, "error"); continue; }
      const tmp = `tmp-${Math.random().toString(36).slice(2)}`;
      setFiles((fs) => [...fs, { id: tmp, name: f.name, size: f.size, uploading: true }]);
      try {
        const up = await api<Attachment>("/api/uploads", { body: { name: f.name, data: await readAsBase64(f) } });
        setFiles((fs) => fs.map((x) => (x.id === tmp ? up : x)));
        if (up.warning) toast(up.warning);
      } catch (err: any) {
        toast(`${f.name}: ${err.message}`, "error");
        setFiles((fs) => fs.filter((x) => x.id !== tmp));
      }
    }
    if (fileInput.current) fileInput.current.value = "";
  };
  const newChat = () => { setSessionId(newSessionId()); setMessages([]); setShowHistory(false); };
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [messages, approvals]);

  const send = async () => {
    const input = text.trim();
    const ready = files.filter((f) => !f.uploading);
    if (busy || files.some((f) => f.uploading) || (hasChatInput && !input && !ready.length)) return;
    setText("");
    setFiles([]);
    setBusy(true);
    const draft: ChatMessage = { sender: "machine", sender_name: "AI", text: "", streaming: true, properties: { steps: [] } };
    const mine: ChatMessage = { sender: "user", sender_name: "User", text: input, properties: { files: ready } };
    setMessages((ms) => [...ms, ...(input || ready.length ? [mine] : []), draft]);
    const patchDraft = (fn: (d: ChatMessage) => ChatMessage | null) =>
      setMessages((ms) => {
        const i = ms.findIndex((m) => m.streaming);
        if (i < 0) return ms;
        const next = fn(ms[i]);
        return next ? [...ms.slice(0, i), next, ...ms.slice(i + 1)] : [...ms.slice(0, i), ...ms.slice(i + 1)];
      });
    abort.current = new AbortController();
    const ctrl = abort.current;
    let finished = false;
    let lastActivity = Date.now();
    // keep-alives arrive every 15 s; 45 s of silence means the connection died without telling us
    const watchdog = window.setInterval(() => { if (Date.now() - lastActivity > 45000) ctrl.abort(); }, 5000);
    stoppedByUser.current = false;
    try {
      await stream(`/api/flows/${flowId}/build`, { input_value: input, session_id: sessionId, data: getGraph?.(), files: ready.map((f) => f.id) }, (e) => {
        onEvent?.(e);
        if (e.event === "start") setRunId(e.data.run_id);
        else if (e.event === "end") finished = true;
        else if (e.event === "token") patchDraft((d) => ({ ...d, text: d.text + e.data.chunk, properties: { ...d.properties, status: undefined } }));
        else if (e.event === "thinking") patchDraft((d) => ({ ...d, properties: { ...d.properties, thinking: (d.properties?.thinking ?? "") + e.data.chunk } }));
        else if (e.event === "status") patchDraft((d) => ({ ...d, properties: { ...d.properties, status: e.data.text } }));
        else if (e.event === "plan") patchDraft((d) => ({ ...d, properties: { ...d.properties, plan: e.data.steps } }));
        else if (e.event === "usage") patchDraft((d) => ({ ...d, properties: { ...d.properties, usage: e.data } }));
        else if (e.event === "context_warning") patchDraft((d) => ({ ...d, properties: { ...d.properties, warning:
          `This chat is using about ${Math.round((100 * e.data.used) / e.data.limit)}% of the model's context window (${e.data.limit} tokens)` +
          (e.data.trimmed ? `, so ${e.data.trimmed} older tool result(s) were shortened.` : ".") +
          " For long tasks, start a new chat or raise Context window on the Agent." } }));
        else if (e.event === "token_reset") patchDraft((d) => ({ ...d, text: "" }));
        else if (e.event === "step") {
          const s: Step = e.data.step;
          patchDraft((d) => {
            const steps = [...(d.properties?.steps ?? [])];
            const i = steps.findIndex((x) => x.status === "running" && x.name === s.name);
            if (i >= 0) steps[i] = s; else steps.push(s);
            return { ...d, properties: { ...d.properties, steps } };
          });
        } else if (e.event === "message") {
          const m = e.data.message as ChatMessage;
          setMessages((ms) => {
            const i = ms.findIndex((x) => x.streaming);
            return i < 0 ? [...ms, m] : [...ms.slice(0, i), m, ...ms.slice(i + 1), { ...ms[i], text: "", properties: { steps: [] } }];
          });
        } else if (e.event === "text_output") {
          setMessages((ms) => {
            const i = ms.findIndex((x) => x.streaming);
            const m: ChatMessage = { sender: "machine", sender_name: "Text Output", text: e.data.text };
            return i < 0 ? [...ms, m] : [...ms.slice(0, i), m, ...ms.slice(i)];
          });
        } else if (e.event === "approval") {
          setApprovals((as) => [...as, e.data as Approval]);
        } else if (e.event === "approval_done") {
          setApprovals((as) => as.filter((x) => x.id !== e.data.id));
        } else if (e.event === "error") {
          finished = true;
          patchDraft((d) => ({ ...d, streaming: false, error: true, text: e.data.error }));
        }
      }, ctrl.signal, () => { lastActivity = Date.now(); });
    } catch (err: any) {
      if (err.name !== "AbortError" && !(err instanceof TypeError)) {  // TypeError = network dropped
        finished = true;
        patchDraft((d) => ({ ...d, streaming: false, error: true, text: err.message }));
      }
    } finally {
      window.clearInterval(watchdog);
      setBusy(false);
      setRunId(null);
      if (!finished && !stoppedByUser.current) {
        // The connection dropped (phone locked, network change), but the agent keeps working on the server.
        patchDraft(() => null);
        watch(sessionId);
      } else {
        patchDraft((d) => (d.text || d.properties?.steps?.length ? { ...d, streaming: false } : null));
      }
      loadSessions();
    }
  };

  const undo = async (m: ChatMessage) => {
    const ch = m.properties?.changes;
    if (!ch) return;
    if (!confirm(`Put back ${ch.files.length} file(s) the way they were before this reply?\n\n${ch.files.join("\n")}\n\nFiles it created are deleted. Later edits to these files are lost too. Commands it ran are not undone.`)) return;
    try {
      const r = await api<{ restored: string[]; skipped: string[] }>(`/api/runs/${ch.run_id}/undo`, { method: "POST" });
      setMessages((ms) => ms.map((x) => (x === m ? { ...x, properties: { ...x.properties, changes: { ...ch, undone: true } } } : x)));
      toast(r.skipped.length ? `Undone ${r.restored.length}; couldn't restore: ${r.skipped.join(", ")}` : `Undone: ${r.restored.length} file(s) restored`, r.skipped.length ? "error" : "info");
    } catch (err: any) {
      toast(err.message, "error");
    }
  };

  const [compacting, setCompacting] = useState(false);
  const compactChat = async () => {
    setCompacting(true);
    try {
      await api(`/api/flows/${flowId}/compact`, { body: { session_id: sessionId } });
      setMessages(await api<ChatMessage[]>(`/api/flows/${flowId}/messages?session_id=${encodeURIComponent(sessionId)}`));
      toast("Earlier messages summarized: the agent now remembers the summary instead");
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setCompacting(false);
    }
  };

  const stop = async () => {
    stoppedByUser.current = true;
    if (runId) await api(`/api/runs/${runId}/cancel`, { method: "POST" }).catch(() => {});
    abort.current?.abort();
  };

  return (
    <aside className={`playground ${variant} ${full ? "full" : ""}`} aria-label={variant === "page" ? "Chat" : "Playground"}>
      <div className={`pg-sessions ${showHistory ? "open" : ""}`}>
        <div className="panel-head" style={{ padding: "10px 10px 8px" }}>
          <span className="section-title grow">{variant === "page" ? "Chats" : "Sessions"}</span>
          <button className="icon-btn sm" aria-label="New session" title="New chat" onClick={newChat}><Plus size={15} /></button>
          {showHistory && <button className="icon-btn sm" aria-label="Close history" onClick={() => setShowHistory(false)}><X size={15} /></button>}
        </div>
        {sessions.length > 4 && (
          <div className="search" style={{ padding: "6px 8px 0" }}>
            <Search size={14} style={{ left: 18 }} />
            <input className="input" style={{ height: 30, fontSize: 13 }} placeholder="Search chats" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search chats" />
          </div>
        )}
        <div className="side-list" style={{ padding: 6, overflow: "auto" }}>
          {!sessions.some((s) => s.session_id === sessionId) && <button className="side-item active"><span className="ellipsis">New chat</span></button>}
          {sessions.filter((s) => !query || (s.title || s.session_id).toLowerCase().includes(query.toLowerCase())).map((s) => (
            <div key={s.session_id} style={{ position: "relative" }}>
              <button className={`side-item ${s.session_id === sessionId ? "active" : ""}`} onClick={() => { openSession(s.session_id); setShowHistory(false); }} title={s.session_id}>
                <span className="grow col" style={{ gap: 0, minWidth: 0 }}>
                  <span className="ellipsis">{s.title || s.session_id}</span>
                  <span className="faint" style={{ fontSize: 11 }}>{timeAgo(s.last)} · {s.count}</span>
                </span>
              </button>
              <button className="icon-btn sm" style={{ position: "absolute", right: 2, top: 6 }} aria-label="Session options" onClick={() => setMenu(s.session_id)}><MoreHorizontal size={14} /></button>
              {menu === s.session_id && (
                <Menu onClose={() => setMenu(null)} style={{ right: 0, top: 30 }}>
                  <button className="danger" onClick={async () => {
                    setMenu(null);
                    await api(`/api/flows/${flowId}/messages?session_id=${encodeURIComponent(s.session_id)}`, { method: "DELETE" });
                    if (s.session_id === sessionId) { setSessionId(newSessionId()); setMessages([]); }
                    loadSessions();
                    toast("Session deleted");
                  }}><Trash2 size={14} /> Delete session</button>
                </Menu>
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="pg-main">
        <div className="panel-head">
          <button className="icon-btn history-btn" aria-label="Chat history" title="Chat history" onClick={() => setShowHistory(true)}><History size={17} /></button>
          {header ?? <h2 className="grow">Playground</h2>}
          {messages.length > 3 && (
            <button className="icon-btn" aria-label="Compact chat" title="Summarize earlier messages to free up the model's memory"
              disabled={busy || working || compacting} onClick={compactChat}>{compacting ? <Loader2 size={16} className="spin" /> : <FoldVertical size={16} />}</button>
          )}
          {variant === "page" && <button className="btn sm" onClick={newChat}><Plus size={14} /> New chat</button>}
          {variant === "panel" && <button className="icon-btn" aria-label={full ? "Exit full screen" : "Full screen"} onClick={() => setFull(!full)}>{full ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>}
          {onClose && <button className="icon-btn" aria-label="Close playground" onClick={onClose}><X size={17} /></button>}
        </div>
        <div className="pg-msgs">
          {messages.length === 0 && (
            <div className="empty" style={{ margin: "auto 0", border: 0 }}>
              <Bot size={28} className="faint" />
              {hasChatInput ? <><h3>{variant === "page" ? "What can I help with?" : "Say something to your flow"}</h3><span>Replies come from your own Ollama models. Attach files or photos with the paperclip. When the agent uses a tool, you'll see the call and its result here.</span></>
                : <><h3>This flow doesn't take chat</h3><span>Add a Chat Input to talk to it here, or press Run to run it once.</span></>}
            </div>
          )}
          {messages.map((m, i) => <MessageView key={m.id ?? i} m={m} onUndo={undo} />)}
          {working && (
            <div className="notice" role="status"><Loader2 size={14} className="spin" /> The agent is still working on this chat. The reply appears here when it's done; you can leave and come back.</div>
          )}
          {approvals.map((a) => (
            <ApprovalCard key={a.id} a={a} onAnswer={async (ans) => {
              setApprovals((as) => as.map((x) => (x.id === a.id ? { ...x, answering: true } : x)));
              try {
                await api(`/api/approvals/${a.id}`, { body: ans });
                if (ans.scope === "always") toast(`Added to Settings → Approvals: ${ans.pattern}`);
              } catch (err: any) {
                toast(err.message, "error");
              }
              setApprovals((as) => as.filter((x) => x.id !== a.id));
            }} />
          ))}
          <div ref={bottom} />
        </div>
        <div className="pg-input">
          {files.length > 0 && (
            <div className="chips" style={{ marginBottom: 8 }}>
              {files.map((f) => (
                <span key={f.id} className="chip">
                  {f.uploading ? <Loader2 size={12} className="spin" /> : f.kind === "image" ? <ImageIcon size={12} /> : <FileText size={12} />} {f.name}
                  <button className="chip-x" aria-label={`Remove ${f.name}`} onClick={() => setFiles((fs) => fs.filter((x) => x.id !== f.id))}><X size={11} /></button>
                </span>
              ))}
            </div>
          )}
          <div className="pg-box">
            <input ref={fileInput} type="file" multiple hidden onChange={(e) => attach(e.target.files)} />
            <button className="icon-btn" aria-label="Attach files" title="Attach files or photos (images go to vision models such as qwen2.5vl or gemma3)" disabled={!hasChatInput}
              onClick={() => fileInput.current?.click()}><Paperclip size={17} /></button>
            <textarea rows={1} value={text} placeholder={hasChatInput ? "Send a message…" : "This flow has no Chat Input"} aria-label="Message"
              onChange={(e) => setText(e.target.value)} disabled={!hasChatInput}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            {busy || working ? (
              <button className="btn sm" onClick={stop} aria-label="Stop" disabled={working && !busy}><Square size={13} /> Stop</button>
            ) : (
              <button className="btn primary sm" onClick={send} disabled={hasChatInput ? (!text.trim() && !files.length) || files.some((f) => f.uploading) : false} aria-label={hasChatInput ? "Send" : "Run"}>
                <Send size={14} />{hasChatInput ? "" : " Run"}
              </button>
            )}
          </div>
          {variant === "panel" && <div className="help" style={{ marginTop: 6 }}>Session <code>{sessionId}</code> · Enter to send, Shift+Enter for a new line</div>}
        </div>
      </div>
    </aside>
  );
}
