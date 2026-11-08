import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../store";
import type { Flow, FieldSpec } from "../types";
import { Toggle } from "./kit";

type Props = { field: FieldSpec; value: unknown; onChange: (v: unknown) => void; compact?: boolean; disabled?: boolean; nodeType?: string };

let flowsCache: Promise<Flow[]> | null = null;

const TAGS: Record<string, string> = { tools: "tools", vision: "vision", embedding: "embed", thinking: "thinks" };
const tagLine = (caps?: string[] | null) => (caps ?? []).filter((c) => TAGS[c]).map((c) => TAGS[c]).join(", ");

function ModelSelect({ value, onChange, embed, disabled, needsTools }: { value: string; onChange: (v: string) => void; embed?: boolean; disabled?: boolean; needsTools?: boolean }) {
  const { models, modelsError, refreshModels, settings } = useStore();
  const [busy, setBusy] = useState(false);
  const isEmbed = (n: string) => {
    const caps = models.find((m) => m.name === n)?.capabilities;
    return caps ? caps.includes("embedding") && !caps.includes("completion") : /embed|minilm|bge|e5-|gte|arctic-embed/i.test(n);
  };
  const effective = value || settings.default_model;
  const chosen = models.find((m) => m.name === effective || m.name === `${effective}:latest`);
  const noTools = needsTools && chosen?.capabilities && !chosen.capabilities.includes("tools");
  const list = models.filter((m) => (embed ? true : !isEmbed(m.name)));
  const sorted = embed ? [...list].sort((a, b) => Number(isEmbed(b.name)) - Number(isEmbed(a.name))) : list;
  const known = !value || models.some((m) => m.name === value || m.name === `${value}:latest`);
  return (
    <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
      <select className="select nodrag" value={value} style={{ flex: 1, minWidth: 0 }} disabled={disabled} onChange={(e) => onChange(e.target.value)}
        title={modelsError ?? undefined} aria-label="Model">
        {!embed && <option value="">{settings.default_model ? `Default (${settings.default_model})` : "Choose a model…"}</option>}
        {!known && <option value={value}>{value} (not pulled)</option>}
        {sorted.map((m) => <option key={m.name} value={m.name}>{m.name}{m.parameter_size ? ` · ${m.parameter_size}` : ""}{tagLine(m.capabilities) ? ` · ${tagLine(m.capabilities)}` : ""}</option>)}
      </select>
      <button className="icon-btn sm nodrag" aria-label="Refresh models" title={modelsError ?? "Refresh models"} disabled={busy}
        onClick={async () => { setBusy(true); await refreshModels(); setBusy(false); }}>
        <RefreshCw size={13} className={busy ? "spin" : ""} />
      </button>
      {noTools && (
        <span className="error-text" role="alert" style={{ flexBasis: "100%", fontSize: 12 }}>
          {chosen!.name} can't call tools, so this agent can't use any. Pick a model marked “tools”.
        </span>
      )}
    </div>
  );
}

function FlowSelect({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  const [flows, setFlows] = useState<Flow[]>([]);
  useEffect(() => {
    flowsCache = flowsCache ?? api<Flow[]>("/api/flows");
    flowsCache.then(setFlows);
    return () => { flowsCache = null; };
  }, []);
  return (
    <select className="select nodrag" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-label="Flow">
      <option value="">Choose a flow…</option>
      {flows.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
    </select>
  );
}

function SkillsMulti({ value, onChange, disabled }: { value: string[]; onChange: (v: string[]) => void; disabled?: boolean }) {
  const { skills } = useStore();
  const all = value.includes("*");
  const set = (name: string, on: boolean) => onChange(on ? [...value.filter((v) => v !== name), name] : value.filter((v) => v !== name));
  return (
    <div className="col nodrag" style={{ gap: 4, maxHeight: 150, overflow: "auto" }}>
      <label className="row" style={{ fontSize: 12.5 }}>
        <input type="checkbox" checked={all} disabled={disabled} onChange={(e) => onChange(e.target.checked ? ["*"] : [])} /> All library skills
      </label>
      {!all && skills.map((s) => (
        <label key={s.id} className="row" style={{ fontSize: 12.5 }} title={s.description}>
          <input type="checkbox" checked={value.includes(s.name)} disabled={disabled} onChange={(e) => set(s.name, e.target.checked)} />
          <span className="ellipsis">{s.name}</span>
        </label>
      ))}
      {!skills.length && <span className="help">No skills yet. Create them on the Skills page.</span>}
    </div>
  );
}

export function FieldInput({ field, value, onChange, compact, disabled, nodeType }: Props) {
  const { skills } = useStore();
  const v = value ?? field.default ?? "";
  const cls = "nodrag nowheel";
  switch (field.type) {
    case "bool":
      return <Toggle on={!!v} onChange={onChange} label={field.display} disabled={disabled} />;
    case "int":
    case "float":
      return (
        <input className={`input ${cls}`} type="number" value={v as number} disabled={disabled} min={field.min} max={field.max}
          step={field.step ?? (field.type === "int" ? 1 : 0.1)} aria-label={field.display}
          onChange={(e) => onChange(e.target.value === "" ? "" : field.type === "int" ? parseInt(e.target.value) : parseFloat(e.target.value))} />
      );
    case "select":
      return (
        <select className={`select ${cls}`} value={v as string} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-label={field.display}>
          {field.options?.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    case "model":
      return <ModelSelect value={v as string} onChange={onChange} disabled={disabled} needsTools={nodeType === "Agent"} />;
    case "embed_model":
      return <ModelSelect value={v as string} onChange={onChange} embed disabled={disabled} />;
    case "flow":
      return <FlowSelect value={v as string} onChange={onChange} disabled={disabled} />;
    case "skills":
      return <SkillsMulti value={Array.isArray(v) ? (v as string[]) : []} onChange={onChange} disabled={disabled} />;
    case "skill":
      return (
        <select className={`select ${cls}`} value={v as string} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-label={field.display}>
          <option value="">— Write inline —</option>
          {skills.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
        </select>
      );
    case "text":
    case "json":
      return (
        <textarea className={`textarea ${field.type === "json" ? "code" : ""} ${cls}`} value={v as string} disabled={disabled}
          rows={compact ? 3 : field.type === "json" ? 10 : 5} placeholder={field.placeholder} aria-label={field.display}
          onChange={(e) => onChange(e.target.value)} />
      );
    case "secret":
      return <input className={`input ${cls}`} type="password" value={v as string} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-label={field.display} />;
    default:
      return <input className={`input ${cls}`} value={v as string} disabled={disabled} placeholder={field.placeholder} onChange={(e) => onChange(e.target.value)} aria-label={field.display} />;
  }
}
