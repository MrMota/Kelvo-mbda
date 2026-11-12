import { Bot, Check, ChevronRight, FileText, History, Loader2, Maximize2, Minimize2, MoreHorizontal, Paperclip, Plus, Search, Send, ShieldAlert, Square, Trash2, User, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, newSessionId, stream, type StreamEvent } from "../api";
import type { Attachment, ChatMessage, FlowGraph, Step } from "../types";
import { Menu, timeAgo, useToast } from "./kit";
import { Markdown } from "./Markdown";

type Session = { session_id: string; count: number; last: string; title: string | null };

type Approval = { id: string; tool: string; summary: string; details: Record<string, unknown>; answering?: boolean };

/** An agent is waiting for you: run this command / write this file? Nothing happens until you choose. */
function ApprovalCard({ a, onAnswer }: { a: Approval; onAnswer: (approve: boolean) => void }) {
  const cmd = a.details.command as string | undefined;
  return (
    <div className="approval" role="alertdialog" aria-label={`Approve ${a.tool}?`}>
      <div className="row" style={{ gap: 8 }}>
        <ShieldAlert size={18} color="var(--warn)" />
        <b className="grow">{cmd ? "Run this command on your computer?" : `Allow this ${a.tool} action?`}</b>
      </div>
      <pre className="approval-cmd">{cmd ?? a.summary}</pre>
      {"folder" in a.details && <div className="help">In {String(a.details.folder)}{a.details.shell && a.details.shell !== "default" ? ` · ${String(a.details.shell)}` : ""}</div>}
      {!cmd && Object.keys(a.details).length > 0 && (
        <pre className="approval-cmd" style={{ fontSize: 12 }}>{JSON.stringify(a.details, null, 2)}</pre>
      )}
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn sm" disabled={a.answering} onClick={() => onAnswer(false)}><X size={14} /> Reject</button>
        <button className="btn primary sm" disabled={a.answering} onClick={() => onAnswer(true)}><Check size={14} /> Approve</button>
      </div>
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

function MessageView({ m }: { m: ChatMessage }) {
  const steps = m.properties?.steps ?? [];
  return (
    <div className={`msg ${m.sender}`}>
      <span className="msg-avatar">{m.sender === "user" ? <User size={15} /> : <Bot size={15} />}</span>
      <div className="msg-body">
        <div className="msg-name">{m.sender_name}{m.properties?.source?.source && <span className="faint" style={{ fontWeight: 500 }}>· {m.properties.source.source}</span>}</div>
        {steps.length > 0 && <div className="steps">{steps.map((s, i) => <StepCard key={i} step={s} />)}</div>}
        {(m.properties?.files?.length ?? 0) > 0 && (
          <div className="chips">{m.properties!.files!.map((f) => <span key={f.id ?? f.name} className="chip"><FileText size={12} /> {f.name}</span>)}</div>
        )}
        {(m.text || m.streaming) && (m.sender === "machine" && !m.error
          ? <Markdown text={m.text} className={`msg-text md-reply ${m.streaming ? "cursor" : ""}`} />
          : <div className={`msg-text ${m.error ? "err" : ""} ${m.streaming ? "cursor" : ""}`}>{m.text}</div>)}
        {!m.text && !m.streaming && !steps.length && <div className="faint">(empty reply)</div>}
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
  const fileInput = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const toast = useToast();

  const loadSessions = useCallback(async () => {
    const s = await api<Session[]>(`/api/flows/${flowId}/sessions`);
    setSessions(s);
    return s;
  }, [flowId]);

  const openSession = useCallback(async (sid: string) => {
    setSessionId(sid);
    const ms = await api<ChatMessage[]>(`/api/flows/${flowId}/messages?session_id=${encodeURIComponent(sid)}`);
    setMessages(ms);
  }, [flowId]);

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
    try {
      await stream(`/api/flows/${flowId}/build`, { input_value: input, session_id: sessionId, data: getGraph?.(), files: ready.map((f) => f.id) }, (e) => {
        onEvent?.(e);
        if (e.event === "token") patchDraft((d) => ({ ...d, text: d.text + e.data.chunk }));
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
          patchDraft((d) => ({ ...d, streaming: false, error: true, text: e.data.error }));
        }
      }, abort.current.signal);
    } catch (err: any) {
      if (err.name !== "AbortError") patchDraft((d) => ({ ...d, streaming: false, error: true, text: err.message }));
    } finally {
      patchDraft((d) => (d.text || d.properties?.steps?.length ? { ...d, streaming: false } : null));
      setBusy(false);
      loadSessions();
    }
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
          {variant === "page" && <button className="btn sm" onClick={newChat}><Plus size={14} /> New chat</button>}
          {variant === "panel" && <button className="icon-btn" aria-label={full ? "Exit full screen" : "Full screen"} onClick={() => setFull(!full)}>{full ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>}
          {onClose && <button className="icon-btn" aria-label="Close playground" onClick={onClose}><X size={17} /></button>}
        </div>
        <div className="pg-msgs">
          {messages.length === 0 && (
            <div className="empty" style={{ margin: "auto 0", border: 0 }}>
              <Bot size={28} className="faint" />
              {hasChatInput ? <><h3>{variant === "page" ? "What can I help with?" : "Say something to your flow"}</h3><span>Replies come from your own Ollama models. Attach files with the paperclip. When the agent uses a tool, you'll see the call and its result here.</span></>
                : <><h3>This flow doesn't take chat</h3><span>Add a Chat Input to talk to it here, or press Run to run it once.</span></>}
            </div>
          )}
          {messages.map((m, i) => <MessageView key={m.id ?? i} m={m} />)}
          {approvals.map((a) => (
            <ApprovalCard key={a.id} a={a} onAnswer={async (approve) => {
              setApprovals((as) => as.map((x) => (x.id === a.id ? { ...x, answering: true } : x)));
              try {
                await api(`/api/approvals/${a.id}`, { body: { approve } });
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
                  {f.uploading ? <Loader2 size={12} className="spin" /> : <FileText size={12} />} {f.name}
                  <button className="chip-x" aria-label={`Remove ${f.name}`} onClick={() => setFiles((fs) => fs.filter((x) => x.id !== f.id))}><X size={11} /></button>
                </span>
              ))}
            </div>
          )}
          <div className="pg-box">
            <input ref={fileInput} type="file" multiple hidden onChange={(e) => attach(e.target.files)} />
            <button className="icon-btn" aria-label="Attach files" title="Attach files (PDF, Word, text, code…)" disabled={!hasChatInput}
              onClick={() => fileInput.current?.click()}><Paperclip size={17} /></button>
            <textarea rows={1} value={text} placeholder={hasChatInput ? "Send a message…" : "This flow has no Chat Input"} aria-label="Message"
              onChange={(e) => setText(e.target.value)} disabled={!hasChatInput}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            {busy ? (
              <button className="btn sm" onClick={() => abort.current?.abort()} aria-label="Stop"><Square size={13} /> Stop</button>
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
