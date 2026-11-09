import { Bot, Check, ChevronRight, Loader2, Maximize2, Minimize2, MoreHorizontal, Plus, Send, ShieldAlert, Square, Trash2, User, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, newSessionId, stream, type StreamEvent } from "../api";
import type { ChatMessage, FlowGraph, Step } from "../types";
import { Menu, timeAgo, useToast } from "./kit";

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
        {(m.text || m.streaming) && <div className={`msg-text ${m.error ? "err" : ""} ${m.streaming ? "cursor" : ""}`}>{m.text}</div>}
        {!m.text && !m.streaming && !steps.length && <div className="faint">(empty reply)</div>}
      </div>
    </div>
  );
}

export function Playground({ flowId, getGraph, hasChatInput, onEvent, onClose }: {
  flowId: string;
  getGraph: () => FlowGraph;
  hasChatInput: boolean;
  onEvent: (e: StreamEvent) => void;
  onClose: () => void;
}) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string>(() => newSessionId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [full, setFull] = useState(false);
  const [menu, setMenu] = useState<string | null>(null);
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
    loadSessions().then((s) => { if (s[0]) openSession(s[0].session_id); });
  }, [loadSessions, openSession]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [messages, approvals]);

  const send = async () => {
    const input = text.trim();
    if (busy || (hasChatInput && !input)) return;
    setText("");
    setBusy(true);
    const draft: ChatMessage = { sender: "machine", sender_name: "AI", text: "", streaming: true, properties: { steps: [] } };
    setMessages((ms) => [...ms, ...(input ? [{ sender: "user" as const, sender_name: "User", text: input }] : []), draft]);
    const patchDraft = (fn: (d: ChatMessage) => ChatMessage | null) =>
      setMessages((ms) => {
        const i = ms.findIndex((m) => m.streaming);
        if (i < 0) return ms;
        const next = fn(ms[i]);
        return next ? [...ms.slice(0, i), next, ...ms.slice(i + 1)] : [...ms.slice(0, i), ...ms.slice(i + 1)];
      });
    abort.current = new AbortController();
    try {
      await stream(`/api/flows/${flowId}/build`, { input_value: input, session_id: sessionId, data: getGraph() }, (e) => {
        onEvent(e);
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
    <aside className={`playground ${full ? "full" : ""}`} aria-label="Playground">
      <div className="pg-sessions">
        <div className="panel-head" style={{ padding: "10px 10px 8px" }}>
          <span className="section-title grow">Sessions</span>
          <button className="icon-btn sm" aria-label="New session" title="New session" onClick={() => { setSessionId(newSessionId()); setMessages([]); }}><Plus size={15} /></button>
        </div>
        <div className="side-list" style={{ padding: 6, overflow: "auto" }}>
          {!sessions.some((s) => s.session_id === sessionId) && <button className="side-item active"><span className="ellipsis">New chat</span></button>}
          {sessions.map((s) => (
            <div key={s.session_id} style={{ position: "relative" }}>
              <button className={`side-item ${s.session_id === sessionId ? "active" : ""}`} onClick={() => openSession(s.session_id)} title={s.session_id}>
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
          <h2 className="grow">Playground</h2>
          <button className="icon-btn" aria-label={full ? "Exit full screen" : "Full screen"} onClick={() => setFull(!full)}>{full ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>
          <button className="icon-btn" aria-label="Close playground" onClick={onClose}><X size={17} /></button>
        </div>
        <div className="pg-msgs">
          {messages.length === 0 && (
            <div className="empty" style={{ margin: "auto 0", border: 0 }}>
              <Bot size={28} className="faint" />
              {hasChatInput ? <><h3>Say something to your flow</h3><span>Replies come from your own Ollama models. When the agent uses a tool, you'll see the call and its result here.</span></>
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
          <div className="pg-box">
            <textarea rows={1} value={text} placeholder={hasChatInput ? "Send a message…" : "This flow has no Chat Input"} aria-label="Message"
              onChange={(e) => setText(e.target.value)} disabled={!hasChatInput}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            {busy ? (
              <button className="btn sm" onClick={() => abort.current?.abort()} aria-label="Stop"><Square size={13} /> Stop</button>
            ) : (
              <button className="btn primary sm" onClick={send} disabled={hasChatInput ? !text.trim() : false} aria-label={hasChatInput ? "Send" : "Run"}>
                <Send size={14} />{hasChatInput ? "" : " Run"}
              </button>
            )}
          </div>
          <div className="help" style={{ marginTop: 6 }}>Session <code>{sessionId}</code> · Enter to send, Shift+Enter for a new line</div>
        </div>
      </div>
    </aside>
  );
}
