import {
  addEdge, Background, BackgroundVariant, Controls, MiniMap, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState, useReactFlow,
  type Connection, type Edge, type Node,
} from "@xyflow/react";
import {
  ArrowLeft, Check, ChevronDown, ChevronRight, Copy, Loader2, Lock, Play, Redo2, ScrollText, Search, Share2, StickyNote, Trash2, Undo2, X, Zap,
} from "lucide-react";
import { Fragment, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { OllamaStatus, SignOut, ThemeToggle } from "../App";
import { api, stream, type StreamEvent } from "../api";
import { useStore } from "../store";
import type { ComponentSpec, Flow, FlowGraph, NodeData, NodeRun } from "../types";
import { FieldInput } from "../ui/FieldInput";
import { ComponentNode, EditorCtx, NoteNode, nodeFields, outputType } from "../ui/FlowNode";
import { CATEGORY_COLORS, Icon, typeColor } from "../ui/Icon";
import { Modal, timeAgo, useToast } from "../ui/kit";
import { Playground } from "../ui/Playground";
import { ShareModal } from "../ui/ShareModal";

const nodeTypes = { component: ComponentNode, note: NoteNode };
const rid = (p: string) => `${p}-${Math.random().toString(36).slice(2, 8)}`;

function toGraph(nodes: Node[], edges: Edge[], viewport?: FlowGraph["viewport"]): FlowGraph {
  return {
    nodes: nodes.map(({ id, type, position, data }) => ({ id, type, position, data })),
    edges: edges.map(({ id, source, sourceHandle, target, targetHandle }) => ({ id, source, sourceHandle, target, targetHandle })),
    viewport,
  };
}

function styleEdges(edges: Edge[], nodes: Node[], spec: (k: string) => ComponentSpec | undefined): Edge[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return edges.map((e) => {
    const src = byId.get(e.source);
    const t = src ? outputType(spec((src.data as NodeData).type), src.data as NodeData, e.sourceHandle) : undefined;
    return { ...e, style: { stroke: t ? typeColor(t) : undefined } };
  });
}

/* ---------------- palette */
function Palette({ onAdd, locked }: { onAdd: (key: string) => void; locked: boolean }) {
  const { registry } = useStore();
  const [q, setQ] = useState("");
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  if (!registry) return <aside className="palette" />;
  const match = (c: ComponentSpec) => (c.display + " " + c.description + " " + c.category).toLowerCase().includes(q.toLowerCase());
  return (
    <aside className="palette" aria-label="Components">
      <div style={{ padding: 10 }} className="search">
        <Search size={15} style={{ left: 20 }} />
        <input className="input" placeholder="Search components" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search components" />
      </div>
      <div className="palette-list">
        {registry.categories.map((cat) => {
          const items = registry.components.filter((c) => c.category === cat && match(c));
          if (!items.length) return null;
          const open = q ? true : !closed[cat];
          return (
            <div key={cat}>
              <button className="cat-head" onClick={() => setClosed({ ...closed, [cat]: open })} aria-expanded={open}>
                {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}{cat}
              </button>
              {open && items.map((c) => (
                <div key={c.key} className="pal-item" draggable={!locked} title={c.description} role="button" tabIndex={0}
                  onDragStart={(e) => { e.dataTransfer.setData("application/kelvo", c.key); e.dataTransfer.effectAllowed = "move"; }}
                  onClick={() => !locked && onAdd(c.key)} onKeyDown={(e) => e.key === "Enter" && !locked && onAdd(c.key)}>
                  <span className="pal-icon" style={{ color: CATEGORY_COLORS[c.category] }}><Icon name={c.icon} size={15} /></span>
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600 }}>{c.display}</div>
                    <div className="faint ellipsis" style={{ fontSize: 11.5 }}>{c.description}</div>
                  </div>
                </div>
              ))}
            </div>
          );
        })}
        {!registry.components.some(match) && <div className="faint" style={{ padding: 12 }}>No components match “{q}”.</div>}
      </div>
    </aside>
  );
}

/* ---------------- inspector */
function Inspector({ node, onClose, onDelete, onDuplicate }: { node: Node; onClose: () => void; onDelete: () => void; onDuplicate: () => void }) {
  const { spec: getSpec } = useStore();
  const d = node.data as NodeData;
  const spec = getSpec(d.type);
  const { updateData, updateParams, runs, locked } = useContext(EditorCtx);
  if (!spec) return null;
  const fields = nodeFields(spec, d.params ?? {});
  const basic = fields.filter((f) => !f.advanced && f.show_field !== false);
  const adv = fields.filter((f) => f.advanced);
  const run = runs[node.id];
  const renderField = (f: (typeof fields)[number]) => (
    <label className="field" key={f.name}>
      <span className="label">{f.display}{f.required && <span style={{ color: "var(--danger)" }}>*</span>}</span>
      <FieldInput field={f} value={d.params?.[f.name]} onChange={(v) => updateParams(node.id, { [f.name]: v })} disabled={locked} nodeType={d.type} />
      {f.info && <span className="help">{f.info}</span>}
    </label>
  );
  return (
    <aside className="inspector" aria-label="Component settings">
      <div className="panel-head">
        <span className="node-icon" style={{ background: CATEGORY_COLORS[spec.category] }}><Icon name={spec.icon} size={15} /></span>
        <h2 className="grow ellipsis">{d.display_name || spec.display}</h2>
        <button className="icon-btn" onClick={onDuplicate} aria-label="Duplicate" title="Duplicate" disabled={locked}><Copy size={15} /></button>
        <button className="icon-btn" onClick={onDelete} aria-label="Delete" title="Delete" disabled={locked}><Trash2 size={15} /></button>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={17} /></button>
      </div>
      <div className="panel-body">
        <span className="muted" style={{ fontSize: 13 }}>{spec.description}</span>
        <label className="field">
          <span className="label">Display name</span>
          <input className="input" value={d.display_name ?? ""} placeholder={spec.display} disabled={locked} onChange={(e) => updateData(node.id, { display_name: e.target.value })} />
        </label>
        {spec.tool_mode && (
          <div className="col" style={{ gap: 10, padding: 12, border: "1px solid var(--border)", borderRadius: 9 }}>
            <label className="row" style={{ justifyContent: "space-between" }}>
              <span><b>Tool mode</b><div className="help">Let an agent call this component.</div></span>
              <input type="checkbox" checked={!!d.tool_mode} disabled={locked} onChange={(e) => updateData(node.id, { tool_mode: e.target.checked })} aria-label="Tool mode" />
            </label>
            {d.tool_mode && (
              <>
                <label className="field"><span className="label">Tool name</span>
                  <input className="input" value={d.tool_name ?? ""} disabled={locked} placeholder={(d.display_name || spec.display).toLowerCase().replace(/\W+/g, "_")} onChange={(e) => updateData(node.id, { tool_name: e.target.value })} />
                </label>
                <label className="field"><span className="label">Tool description</span>
                  <textarea className="textarea" value={d.tool_description ?? ""} disabled={locked} placeholder={spec.description} onChange={(e) => updateData(node.id, { tool_description: e.target.value })} />
                  <span className="help">Agents choose tools by this text. Be specific.</span>
                </label>
              </>
            )}
          </div>
        )}
        <span className="section-title">Parameters</span>
        {basic.map(renderField)}
        {adv.length > 0 && <><span className="section-title">Advanced</span>{adv.map(renderField)}</>}
        {run && (
          <>
            <span className="section-title">Last run</span>
            {run.status === "error" ? <div className="node-error" style={{ margin: 0 }}>{run.error}</div>
              : <pre className="codeblock" style={{ whiteSpace: "pre-wrap" }}>{run.preview || `(${run.status})`}</pre>}
          </>
        )}
        <span className="help">Node ID <code>{node.id}</code> — use it in API tweaks.</span>
      </div>
    </aside>
  );
}

/* ---------------- logs */
function LogsModal({ flowId, onClose }: { flowId: string; onClose: () => void }) {
  const [runs, setRuns] = useState<any[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { api<any[]>(`/api/flows/${flowId}/runs`).then(setRuns); }, [flowId]);
  return (
    <Modal title="Run logs" icon={<ScrollText size={18} />} onClose={onClose} size="lg">
      {!runs ? <Loader2 className="spin" /> : runs.length === 0 ? <div className="empty">No runs yet. Open the Playground and send a message.</div> : (
        <table className="table">
          <thead><tr><th>When</th><th>Status</th><th>Session</th><th>Steps</th><th>Time</th></tr></thead>
          <tbody>
            {runs.map((r) => {
              const ms = r.finished_at ? new Date(r.finished_at).getTime() - new Date(r.started_at).getTime() : null;
              return (
                <Fragment key={r.id}>
                  <tr onClick={() => setOpen(open === r.id ? null : r.id)} style={{ cursor: "pointer" }}>
                    <td>{timeAgo(r.started_at)}</td>
                    <td><span className={`badge ${r.status === "error" ? "err" : r.status === "success" ? "ok" : ""}`}>{r.status}</span></td>
                    <td className="mono ellipsis" style={{ maxWidth: 160 }}>{r.session_id}</td>
                    <td>{r.trace.length}</td>
                    <td>{ms != null ? `${(ms / 1000).toFixed(1)}s` : "—"}</td>
                  </tr>
                  {open === r.id && (
                    <tr><td colSpan={5} style={{ background: "var(--surface-2)" }}>
                      {r.error && <div className="error-text" style={{ marginBottom: 8 }}>{r.error}</div>}
                      {r.trace.map((t: any, i: number) => (
                        <div key={i} className="row" style={{ fontSize: 12.5 }}>
                          <span className="grow">{t.name} <span className="faint">→ {t.output}</span>{t.skipped && <span className="faint"> (skipped)</span>}</span>
                          <span className="mono faint">{t.ms} ms</span>
                        </div>
                      ))}
                    </td></tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </Modal>
  );
}

/* ---------------- editor */

function EditorInner({ initial }: { initial: Flow }) {
  const { spec, registry } = useStore();
  const toast = useToast();
  const nav = useNavigate();
  const rf = useReactFlow();
  const [flow, setFlow] = useState(initial);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(initial.data.nodes as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initial.data.edges as Edge[]);
  const [runs, setRuns] = useState<Record<string, NodeRun>>({});
  const [saveState, setSaveState] = useState<"saved" | "saving" | "dirty" | "error">("saved");
  const [showPg, setShowPg] = useState(false);
  const [share, setShare] = useState<null | "api" | "mcp" | "export">(null);
  const [showLogs, setShowLogs] = useState(false);
  const [running, setRunning] = useState(false);
  const [name, setName] = useState(initial.name);
  const locked = !!flow.locked;
  const loaded = useRef(false);
  const history = useRef<{ past: string[]; future: string[]; last: string }>({ past: [], future: [], last: "" });
  const restoring = useRef(false);

  const updateData = useCallback((id: string, patch: Partial<NodeData>) =>
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n))), [setNodes]);
  const updateParams = useCallback((id: string, patch: Record<string, unknown>) =>
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, params: { ...((n.data as NodeData).params ?? {}), ...patch } } } : n))), [setNodes]);
  const editorApi = useMemo(() => ({ spec, updateData, updateParams, runs, locked }), [spec, updateData, updateParams, runs, locked]);

  // drop edges whose target handle no longer exists (e.g. a prompt variable was removed)
  useEffect(() => {
    const valid = new Map<string, Set<string>>();
    for (const n of nodes) {
      if (n.type !== "component") continue;
      const s = spec((n.data as NodeData).type);
      if (!s) continue;
      valid.set(n.id, new Set(nodeFields(s, (n.data as NodeData).params ?? {}).map((f) => f.name)));
    }
    const bad = edges.filter((e) => valid.has(e.target) && !valid.get(e.target)!.has(e.targetHandle ?? ""));
    const badSrc = edges.filter((e) => {
      const n = nodes.find((x) => x.id === e.source);
      return n && (n.data as NodeData).tool_mode ? e.sourceHandle !== "tool" : n && e.sourceHandle === "tool";
    });
    if (bad.length || badSrc.length) {
      const drop = new Set([...bad, ...badSrc].map((e) => e.id));
      setEdges((es) => es.filter((e) => !drop.has(e.id)));
    }
  }, [nodes, edges, spec, setEdges]);

  // autosave + undo snapshots
  const graphJson = useMemo(() => JSON.stringify(toGraph(nodes, edges)), [nodes, edges]);
  useEffect(() => {
    if (!loaded.current) { loaded.current = true; history.current.last = graphJson; return; }
    if (graphJson === history.current.last) return;
    if (locked) return;
    setSaveState("dirty");
    const t = setTimeout(async () => {
      if (!restoring.current) {
        history.current.past.push(history.current.last);
        if (history.current.past.length > 60) history.current.past.shift();
        history.current.future = [];
      }
      restoring.current = false;
      history.current.last = graphJson;
      setSaveState("saving");
      try {
        await api(`/api/flows/${flow.id}`, { method: "PATCH", body: { data: { ...JSON.parse(graphJson), viewport: rf.getViewport() } } });
        setSaveState("saved");
      } catch (e: any) {
        setSaveState("error");
        toast(`Save failed: ${e.message}`, "error");
      }
    }, 700);
    return () => clearTimeout(t);
  }, [graphJson, flow.id, locked, rf, toast]);

  const restore = (json: string) => {
    const g = JSON.parse(json) as FlowGraph;
    restoring.current = true;
    setNodes(g.nodes as Node[]);
    setEdges(g.edges as Edge[]);
  };
  const undo = () => {
    const h = history.current;
    const prev = h.past.pop();
    if (!prev) return;
    h.future.push(graphJson);
    restore(prev);
  };
  const redo = () => {
    const h = history.current;
    const next = h.future.pop();
    if (!next) return;
    h.past.push(graphJson);
    restore(next);
  };
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });

  const isValidConnection = useCallback((c: Connection | Edge) => {
    const src = nodes.find((n) => n.id === c.source);
    const dst = nodes.find((n) => n.id === c.target);
    if (!src || !dst || src.id === dst.id || dst.type !== "component") return false;
    const t = outputType(spec((src.data as NodeData).type), src.data as NodeData, c.sourceHandle);
    const ds = spec((dst.data as NodeData).type);
    const f = ds && nodeFields(ds, (dst.data as NodeData).params ?? {}).find((x) => x.name === c.targetHandle);
    return !!t && !!f?.accepts?.includes(t);
  }, [nodes, spec]);

  const onConnect = useCallback((c: Connection) => {
    const dst = nodes.find((n) => n.id === c.target);
    const ds = dst && spec((dst.data as NodeData).type);
    const f = ds && nodeFields(ds, (dst!.data as NodeData).params ?? {}).find((x) => x.name === c.targetHandle);
    setEdges((es) => addEdge({ ...c, id: rid("e") }, f?.list ? es : es.filter((e) => !(e.target === c.target && e.targetHandle === c.targetHandle))));
  }, [nodes, spec, setEdges]);

  const addNode = useCallback((key: string, position?: { x: number; y: number }) => {
    const s = spec(key);
    if (!s) return;
    const pos = position ?? rf.screenToFlowPosition({ x: window.innerWidth / 2 - 160, y: window.innerHeight / 2 - 120 });
    const n: Node = { id: rid(key), type: "component", position: pos, data: { type: key, params: {}, tool_mode: s.tool_default } };
    setNodes((ns) => [...ns.map((x) => ({ ...x, selected: false })), { ...n, selected: true }]);
  }, [spec, rf, setNodes]);

  const addNote = () => {
    const pos = rf.screenToFlowPosition({ x: window.innerWidth / 2 - 130, y: 140 });
    setNodes((ns) => [...ns, { id: rid("note"), type: "note", position: pos, data: { text: "" } }]);
  };

  const onRunEvent = useCallback((e: StreamEvent) => {
    if (e.event === "start") setRuns({});
    else if (e.event === "node_start") setRuns((r) => ({ ...r, [e.data.node_id]: { status: "running" } }));
    else if (e.event === "node_end") setRuns((r) => ({ ...r, [e.data.node_id]: e.data.skipped ? { status: "skipped" } : { status: "done", preview: e.data.preview, ms: e.data.ms } }));
    else if (e.event === "node_error") setRuns((r) => ({ ...r, [e.data.node_id]: { status: "error", error: e.data.error } }));
    else if (e.event === "error" && e.data.node_id) setRuns((r) => ({ ...r, [e.data.node_id]: { status: "error", error: e.data.error } }));
  }, []);

  const runOnce = async () => {
    setRunning(true);
    let err: string | null = null;
    try {
      await stream(`/api/flows/${flow.id}/build`, { input_value: "", data: toGraph(nodes, edges) }, (e) => {
        onRunEvent(e);
        if (e.event === "error") err = e.data.error;
      });
      if (err) toast(err, "error"); else toast("Run finished");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setRunning(false);
    }
  };

  const selected = nodes.filter((n) => n.selected);
  const inspected = selected.length === 1 && selected[0].type === "component" ? selected[0] : null;
  const hasChatInput = nodes.some((n) => (n.data as NodeData).type === "ChatInput");
  const styled = useMemo(() => styleEdges(edges, nodes, spec), [edges, nodes, spec]);

  const saveName = async () => {
    if (!name.trim() || name === flow.name) return setName(flow.name);
    const f = await api<Flow>(`/api/flows/${flow.id}`, { method: "PATCH", body: { name: name.trim() } });
    setFlow(f);
  };

  if (!registry) return null;
  return (
    <EditorCtx.Provider value={editorApi}>
      <div className="app">
        <header className="editor-top">
          <button className="icon-btn" onClick={() => nav("/")} aria-label="Back to flows" title="Back to flows"><ArrowLeft size={18} /></button>
          <input className="flow-name" value={name} onChange={(e) => setName(e.target.value)} onBlur={saveName} aria-label="Flow name"
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
          <span className="save-state" aria-live="polite">
            {locked ? <><Lock size={12} /> Locked</> : saveState === "saving" ? <><Loader2 size={12} className="spin" /> Saving</> : saveState === "dirty" ? "Unsaved" : saveState === "error" ? <span className="error-text">Not saved</span> : <><Check size={12} /> Saved</>}
          </span>
          <button className="icon-btn" onClick={undo} aria-label="Undo" title="Undo (Ctrl+Z)" disabled={locked}><Undo2 size={16} /></button>
          <button className="icon-btn" onClick={redo} aria-label="Redo" title="Redo (Ctrl+Shift+Z)" disabled={locked}><Redo2 size={16} /></button>
          <span className="spacer" />
          <OllamaStatus />
          <button className="btn ghost" onClick={addNote} disabled={locked} title="Add note"><StickyNote size={15} /> Note</button>
          <button className="btn ghost" onClick={() => setShowLogs(true)}><ScrollText size={15} /> Logs</button>
          <button className="btn" onClick={runOnce} disabled={running} title="Run the whole flow once">{running ? <Loader2 size={15} className="spin" /> : <Zap size={15} />} Run</button>
          <button className="btn" onClick={() => setShare("api")}><Share2 size={15} /> Share</button>
          <button className={`btn ${showPg ? "" : "primary"}`} onClick={() => setShowPg(!showPg)}><Play size={15} /> Playground</button>
          <ThemeToggle />
          <SignOut />
        </header>
        <div className="editor">
          <Palette onAdd={(k) => addNode(k)} locked={locked} />
          <div className="canvas-wrap"
            onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }}
            onDrop={(e) => {
              e.preventDefault();
              const key = e.dataTransfer.getData("application/kelvo");
              if (key && !locked) addNode(key, rf.screenToFlowPosition({ x: e.clientX - 160, y: e.clientY - 30 }));
            }}>
            <ReactFlow
              nodes={nodes} edges={styled} nodeTypes={nodeTypes}
              onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
              isValidConnection={isValidConnection}
              defaultViewport={initial.data.viewport}
              fitView={!initial.data.viewport} fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
              minZoom={0.15} maxZoom={2}
              nodesDraggable={!locked} nodesConnectable={!locked} elementsSelectable
              deleteKeyCode={locked ? null : ["Backspace", "Delete"]}
              proOptions={{ hideAttribution: true }}
            >
              <Background variant={BackgroundVariant.Dots} gap={18} size={1.4} color="var(--canvas-dot)" />
              <Controls showInteractive={false} />
              {!showPg && <MiniMap pannable zoomable nodeColor={(n) => (n.type === "note" ? "#ecd97a" : CATEGORY_COLORS[spec((n.data as NodeData).type)?.category ?? ""] ?? "#94a3b8")} />}
            </ReactFlow>
            {nodes.length === 0 && (
              <div className="canvas-empty">
                <div className="col" style={{ alignItems: "center" }}>
                  <h2>Nothing here yet</h2>
                  <span>Drag a component in from the left, or click one.<br />A good start: Chat Input → Agent → Chat Output.</span>
                </div>
              </div>
            )}
          </div>
          {inspected && !showPg && (
            <Inspector node={inspected} onClose={() => setNodes((ns) => ns.map((n) => ({ ...n, selected: false })))}
              onDelete={() => { setNodes((ns) => ns.filter((n) => n.id !== inspected.id)); setEdges((es) => es.filter((e) => e.source !== inspected.id && e.target !== inspected.id)); }}
              onDuplicate={() => setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), { ...inspected, id: rid((inspected.data as NodeData).type), position: { x: inspected.position.x + 40, y: inspected.position.y + 40 }, selected: true, data: structuredClone(inspected.data) }])} />
          )}
          {showPg && <Playground flowId={flow.id} getGraph={() => toGraph(nodes, edges)} hasChatInput={hasChatInput} onEvent={onRunEvent} onClose={() => setShowPg(false)} />}
        </div>
      </div>
      {share && <ShareModal flow={{ ...flow, data: toGraph(nodes, edges) }} initialTab={share} onClose={() => setShare(null)} onChange={setFlow} />}
      {showLogs && <LogsModal flowId={flow.id} onClose={() => setShowLogs(false)} />}
    </EditorCtx.Provider>
  );
}

export default function Editor() {
  const { id } = useParams();
  const [flow, setFlow] = useState<Flow | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setFlow(null);
    api<Flow>(`/api/flows/${id}`).then(setFlow).catch((e) => setError(e.message));
  }, [id]);
  if (error) return <div className="container"><h1>Flow not found</h1><p className="muted">{error}</p><Link className="btn" to="/">Back to flows</Link></div>;
  if (!flow) return <div className="canvas-empty"><Loader2 className="spin" /></div>;
  return <ReactFlowProvider><EditorInner key={flow.id} initial={flow} /></ReactFlowProvider>;
}
