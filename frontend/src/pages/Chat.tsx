import { Bot, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type { Flow } from "../types";
import { useToast } from "../ui/kit";
import { Playground } from "../ui/Playground";

const LAST = "kelvo-chat-agent";

/** ChatGPT-style chat with any of your agents (flows that have a Chat Input). */
export default function Chat() {
  const { flowId } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [agents, setAgents] = useState<Flow[] | null>(null);

  useEffect(() => {
    api<Flow[]>("/api/flows").then((fs) => setAgents(fs.filter((f) => f.has_chat)));
  }, []);

  // pick: URL → last used → first agent
  useEffect(() => {
    if (!agents || flowId || !agents.length) return;
    let last: string | null = null;
    try { last = localStorage.getItem(LAST); } catch {}
    const pick = agents.find((a) => a.id === last) ?? agents.find((a) => a.kind === "agent") ?? agents[0];
    nav(`/chat/${pick.id}`, { replace: true });
  }, [agents, flowId, nav]);
  useEffect(() => {
    if (flowId) try { localStorage.setItem(LAST, flowId); } catch {}
  }, [flowId]);

  const createPowerAgent = async () => {
    try {
      const f = await api<Flow>("/api/flows", { body: { template: "power-agent" } });
      nav(`/chat/${f.id}`);
      setAgents((as) => [...(as ?? []), { ...f, has_chat: true, kind: "agent" }]);
    } catch (e: any) { toast(e.message, "error"); }
  };

  if (agents === null) return null;
  if (!agents.length) {
    return (
      <div className="container">
        <div className="empty">
          <span className="card-icon" style={{ width: 44, height: 44 }}><Bot size={22} /></span>
          <h2>No agent to chat with yet</h2>
          <span>Start with <b>Power Agent</b>: it searches the web, works with files and runs commands you approve.</span>
          <button className="btn primary" onClick={createPowerAgent}><Plus size={16} /> Create Power Agent</button>
        </div>
      </div>
    );
  }
  const current = agents.find((a) => a.id === flowId);
  if (!current) return null;

  const picker = (
    <div className="grow row" style={{ minWidth: 0 }}>
      <select className="select" aria-label="Agent" value={current.id} style={{ maxWidth: 320, fontWeight: 600 }}
        onChange={(e) => nav(`/chat/${e.target.value}`)}>
        {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
      </select>
      <Link to={`/flow/${current.id}`} className="faint wide-only" style={{ fontSize: 13, whiteSpace: "nowrap" }}>Edit agent</Link>
    </div>
  );
  return (
    <div className="chat-page">
      <Playground key={current.id} flowId={current.id} variant="page" header={picker} />
    </div>
  );
}
