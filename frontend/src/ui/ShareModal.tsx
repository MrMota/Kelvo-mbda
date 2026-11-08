import { Download, Share2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, download } from "../api";
import type { Flow } from "../types";
import { Code, Modal, Toggle, useToast } from "./kit";

export type ShareTab = "api" | "mcp" | "export";

export function ShareModal({ flow, initialTab = "api", onClose, onChange }: {
  flow: Flow; initialTab?: ShareTab; onClose: () => void; onChange: (f: Flow) => void;
}) {
  const [tab, setTab] = useState<ShareTab>(initialTab);
  const [lang, setLang] = useState<"curl" | "python" | "js">("curl");
  const [endpoint, setEndpoint] = useState(flow.endpoint_name ?? "");
  const [toolName, setToolName] = useState(flow.mcp_tool_name ?? "");
  const [toolDesc, setToolDesc] = useState(flow.mcp_description ?? "");
  const toast = useToast();
  const origin = window.location.origin;
  const target = flow.endpoint_name || flow.id;
  const url = `${origin}/api/v1/run/${target}`;

  const save = async (body: Partial<Flow>) => {
    try {
      const f = await api<Flow>(`/api/flows/${flow.id}`, { method: "PATCH", body });
      onChange(f);
      return true;
    } catch (e: any) {
      toast(e.message, "error");
      return false;
    }
  };

  const payload = `{"input_value": "Hello!", "session_id": "user-1", "output_type": "chat", "input_type": "chat"}`;
  const snippets = {
    curl: `curl -X POST "${url}" \\\n  -H "Content-Type: application/json" \\\n  -H "x-api-key: $KELVO_API_KEY" \\\n  -d '${payload}'\n\n# Stream tokens and agent steps as server-sent events:\n# add ?stream=true to the URL`,
    python: `import os, requests\n\nresp = requests.post(\n    "${url}",\n    headers={"x-api-key": os.environ["KELVO_API_KEY"]},\n    json=${payload.replace(/"(\w+)":/g, '"$1":')},\n    timeout=600,\n)\nresp.raise_for_status()\nprint(resp.json()["outputs"][0]["outputs"][0]["results"]["message"]["text"])`,
    js: `const resp = await fetch("${url}", {\n  method: "POST",\n  headers: { "Content-Type": "application/json", "x-api-key": process.env.KELVO_API_KEY },\n  body: JSON.stringify(${payload}),\n});\nconst data = await resp.json();\nconsole.log(data.outputs[0].outputs[0].results.message.text);`,
  };
  const mcpConfig = JSON.stringify({ mcpServers: { kelvo: { type: "http", url: `${origin}/mcp`, headers: { "x-api-key": "YOUR_KELVO_API_KEY" } } } }, null, 2);

  return (
    <Modal title="Share" icon={<Share2 size={18} />} onClose={onClose} size="lg">
      <div className="tabs" role="tablist">
        {(["api", "mcp", "export"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t === "api" ? "API access" : t === "mcp" ? "MCP server" : "Export"}
          </button>
        ))}
      </div>
      {tab === "api" && (
        <>
          <p className="muted" style={{ margin: 0 }}>
            Call this flow from any app. Requests need an API key in the <code>x-api-key</code> header — <Link to="/settings/keys" style={{ color: "var(--accent-strong)" }}>create one in Settings</Link>.
            Override any field at runtime with <code>"tweaks": {"{"}"node_id": {"{"}"field": value{"}"}{"}"}</code>.
          </p>
          <label className="field" style={{ maxWidth: 420 }}>
            <span className="label">Endpoint name</span>
            <div className="row">
              <input className="input" value={endpoint} placeholder={flow.id} onChange={(e) => setEndpoint(e.target.value)} aria-label="Endpoint name" />
              <button className="btn" disabled={endpoint === (flow.endpoint_name ?? "")} onClick={async () => { if (await save({ endpoint_name: endpoint || null })) toast("Endpoint saved"); }}>Save</button>
            </div>
            <span className="help">A readable alias for the flow ID in the URL.</span>
          </label>
          <div className="tabs">
            {(["curl", "python", "js"] as const).map((l) => (
              <button key={l} className={`tab ${lang === l ? "active" : ""}`} onClick={() => setLang(l)}>{l === "js" ? "JavaScript" : l === "python" ? "Python" : "cURL"}</button>
            ))}
          </div>
          <Code>{snippets[lang]}</Code>
        </>
      )}
      {tab === "mcp" && (
        <>
          <p className="muted" style={{ margin: 0 }}>
            Expose this flow as a tool on Kelvo's MCP server so MCP clients (Claude Desktop, Cursor, other agents) can call it.
          </p>
          <div className="row">
            <Toggle on={!!flow.mcp_enabled} onChange={async (v) => { if (await save({ mcp_enabled: v ? 1 : 0 } as any)) toast(v ? "Exposed as MCP tool" : "Removed from MCP"); }} label="Expose as MCP tool" />
            <b>Expose as MCP tool</b>
          </div>
          <label className="field"><span className="label">Tool name</span>
            <input className="input" value={toolName} placeholder={flow.name.toLowerCase().replace(/[^a-z0-9]+/g, "_")} onChange={(e) => setToolName(e.target.value)} />
          </label>
          <label className="field"><span className="label">Tool description</span>
            <textarea className="textarea" value={toolDesc} placeholder="Say exactly what the flow does, so agents pick it at the right time." onChange={(e) => setToolDesc(e.target.value)} />
          </label>
          <div><button className="btn" onClick={async () => { if (await save({ mcp_tool_name: toolName || null, mcp_description: toolDesc || null })) toast("Tool details saved"); }}>Save tool details</button></div>
          <span className="label">Client configuration (Streamable HTTP)</span>
          <Code>{mcpConfig}</Code>
        </>
      )}
      {tab === "export" && (
        <>
          <p className="muted" style={{ margin: 0 }}>Download the flow as JSON. Import it on the Flows page of any Kelvo install.</p>
          <div>
            <button className="btn primary" onClick={() => download(`${flow.name.replace(/[^\w-]+/g, "_")}.json`, JSON.stringify({ name: flow.name, description: flow.description, data: flow.data }, null, 2))}>
              <Download size={15} /> Download JSON
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
