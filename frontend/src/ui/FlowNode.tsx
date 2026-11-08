import { Handle, Position, useEdges, useUpdateNodeInternals, type NodeProps } from "@xyflow/react";
import { AlertCircle, CheckCircle2, Loader2, Wrench } from "lucide-react";
import { createContext, memo, useContext, useEffect, useMemo } from "react";
import type { ComponentSpec, FieldSpec, NodeData, NodeRun } from "../types";
import { FieldInput } from "./FieldInput";
import { CATEGORY_COLORS, Icon, typeColor } from "./Icon";

export type EditorApi = {
  spec: (key: string) => ComponentSpec | undefined;
  updateData: (id: string, patch: Partial<NodeData>) => void;
  updateParams: (id: string, patch: Record<string, unknown>) => void;
  runs: Record<string, NodeRun>;
  locked: boolean;
};
export const EditorCtx = createContext<EditorApi>(null as unknown as EditorApi);

const VAR_RE = /(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})/g;

/** Static fields plus dynamic ones (Prompt variables), mirroring the backend. */
export function nodeFields(spec: ComponentSpec, params: Record<string, unknown>): FieldSpec[] {
  if (!spec.dynamic) return spec.fields;
  const tpl = String(params.template ?? spec.fields.find((f) => f.name === "template")?.default ?? "");
  const vars: string[] = [];
  for (const m of tpl.matchAll(VAR_RE)) if (!vars.includes(m[1])) vars.push(m[1]);
  return [...spec.fields, ...vars.map((v) => ({ name: v, display: v, type: "text", default: "", accepts: ["Message", "Text", "Data"], tool_param: true }))];
}

export function outputType(spec: ComponentSpec | undefined, data: NodeData, handle: string | null | undefined): string | undefined {
  if (!spec) return undefined;
  if (handle === "tool") return "Tool";
  return spec.outputs.find((o) => o.name === handle)?.type;
}

function StatusBadge({ run }: { run?: NodeRun }) {
  if (!run) return null;
  if (run.status === "running") return <Loader2 size={15} className="spin" color="var(--warn)" aria-label="Running" />;
  if (run.status === "error") return <AlertCircle size={15} color="var(--danger)" aria-label="Error" />;
  if (run.status === "skipped") return <span className="faint" style={{ fontSize: 11 }}>skipped</span>;
  return <span className="row faint" style={{ gap: 3, fontSize: 11 }}><CheckCircle2 size={14} color="var(--ok)" />{run.ms != null ? `${(run.ms / 1000).toFixed(1)}s` : ""}</span>;
}

export const ComponentNode = memo(function ComponentNode({ id, data, selected }: NodeProps) {
  const d = data as unknown as NodeData;
  const ed = useContext(EditorCtx);
  const spec = ed.spec(d.type);
  const edges = useEdges();
  const updateInternals = useUpdateNodeInternals();
  const params = d.params ?? {};
  const fields = useMemo(() => (spec ? nodeFields(spec, params) : []), [spec, params]);
  const connected = useMemo(() => new Set(edges.filter((e) => e.target === id).map((e) => e.targetHandle)), [edges, id]);
  const fieldKey = fields.map((f) => f.name).join("|") + (d.tool_mode ? "T" : "");
  useEffect(() => updateInternals(id), [fieldKey, id, updateInternals]);

  if (!spec) return <div className="node error"><div className="node-head">Unknown component: {d.type}</div></div>;
  const run = ed.runs[id];
  const color = CATEGORY_COLORS[spec.category] ?? "#64748b";
  const visible = fields.filter((f) => !f.advanced);

  return (
    <div className={`node ${selected ? "selected" : ""} ${run?.status ?? ""}`}>
      <div className="node-head">
        <span className="node-icon" style={{ background: color }}><Icon name={spec.icon} size={15} /></span>
        <div className="grow">
          <div className="node-title ellipsis">{d.display_name || spec.display}</div>
          {d.tool_mode && <div className="tool-tag">Tool · {d.tool_name || spec.display.toLowerCase().replace(/\W+/g, "_")}</div>}
        </div>
        <div className="node-status"><StatusBadge run={run} /></div>
        {spec.tool_mode && (
          <button className={`icon-btn sm nodrag ${d.tool_mode ? "" : ""}`} title={d.tool_mode ? "Tool mode on: an agent can call this" : "Turn into a tool for an agent"}
            aria-pressed={!!d.tool_mode} disabled={ed.locked} style={d.tool_mode ? { background: "color-mix(in srgb, var(--t-Tool) 18%, transparent)", color: "var(--t-Tool)" } : undefined}
            onClick={() => ed.updateData(id, { tool_mode: !d.tool_mode })}><Wrench size={14} /></button>
        )}
      </div>
      <div className="node-desc">{spec.description}</div>
      {visible.length > 0 && (
        <div className="node-section">
          {visible.map((f) => {
            const isConn = connected.has(f.name);
            const agentFills = d.tool_mode && f.tool_param && !isConn;
            const showEditor = f.show_field !== false && !isConn && !agentFills;
            return (
              <div className="nf" key={f.name}>
                {f.accepts && (
                  <Handle type="target" position={Position.Left} id={f.name} className="handle"
                    style={{ background: typeColor(f.accepts[0]), top: 17 }} title={`Accepts ${f.accepts.join(", ")}`} />
                )}
                <span className="label">
                  {f.display}{f.required && <span style={{ color: "var(--danger)" }}>*</span>}
                  {isConn && <span className="faint" style={{ fontWeight: 500 }}>· connected</span>}
                  {agentFills && <span className="tool-tag">· filled by agent</span>}
                  {f.list && !isConn && f.show_field === false && <span className="faint" style={{ fontWeight: 500 }}>· connect one or more</span>}
                </span>
                {showEditor && f.type === "skills" ? (
                  <SkillsSummary value={params[f.name]} />
                ) : showEditor && (
                  <FieldInput field={f} value={params[f.name]} compact disabled={ed.locked} nodeType={d.type}
                    onChange={(v) => ed.updateParams(id, { [f.name]: v })} />
                )}
              </div>
            );
          })}
        </div>
      )}
      <div className="node-section">
        {d.tool_mode ? (
          <div className="nout">
            Toolset
            <Handle type="source" position={Position.Right} id="tool" className="handle" style={{ background: typeColor("Tool") }} />
          </div>
        ) : (
          spec.outputs.map((o) => (
            <div className="nout" key={o.name}>
              {o.display}
              <span className="faint" style={{ fontWeight: 500, fontSize: 11 }}>{o.type}</span>
              <Handle type="source" position={Position.Right} id={o.name} className="handle" style={{ background: typeColor(o.type) }} />
            </div>
          ))
        )}
      </div>
      {run?.status === "error" && run.error && <div className="node-error">{run.error}</div>}
      {run?.status === "done" && run.preview && <div className="node-preview nowheel">{run.preview}</div>}
    </div>
  );
});

function SkillsSummary({ value }: { value: unknown }) {
  const v = Array.isArray(value) ? (value as string[]) : [];
  return (
    <span className="help" style={{ fontSize: 12 }}>
      {v.includes("*") ? "All library skills" : v.length ? v.join(", ") : "None"} · <span className="faint">edit in settings panel</span>
    </span>
  );
}

export const NoteNode = memo(function NoteNode({ id, data }: NodeProps) {
  const ed = useContext(EditorCtx);
  return (
    <div className="note-node">
      <textarea className="nodrag nowheel" value={(data as any).text ?? ""} placeholder="Write a note…" disabled={ed.locked}
        aria-label="Note" onChange={(e) => ed.updateData(id, { text: e.target.value })} />
    </div>
  );
});
