export type FieldSpec = {
  name: string;
  display: string;
  type: string;
  default?: unknown;
  accepts?: string[];
  list?: boolean;
  required?: boolean;
  advanced?: boolean;
  tool_param?: boolean;
  options?: string[];
  info?: string;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  show_field?: boolean;
};
export type OutputSpec = { name: string; display: string; type: string };
export type ComponentSpec = {
  key: string;
  display: string;
  category: string;
  description: string;
  icon: string;
  fields: FieldSpec[];
  outputs: OutputSpec[];
  tool_mode: boolean;
  tool_default: boolean;
  dynamic: boolean;
};
export type Registry = { categories: string[]; components: ComponentSpec[] };

export type NodeData = {
  type: string;
  params: Record<string, unknown>;
  tool_mode?: boolean;
  tool_name?: string;
  tool_description?: string;
  display_name?: string;
  text?: string; // notes
};
export type FlowGraph = { nodes: any[]; edges: any[]; viewport?: { x: number; y: number; zoom: number } };
export type Flow = {
  id: string;
  project_id: string;
  name: string;
  description: string;
  data: FlowGraph;
  endpoint_name: string | null;
  locked: number;
  mcp_enabled: number;
  mcp_tool_name: string | null;
  mcp_description: string | null;
  created_at: string;
  updated_at: string;
  node_count?: number;
  kind?: string;
};
export type Project = { id: string; name: string; flow_count?: number };
export type Template = { id: string; name: string; description: string; icon: string; data: FlowGraph };
export type Skill = { id: string; name: string; description: string; body: string; updated_at: string };
export type Step = { type: string; name: string; input: unknown; output?: string; status?: string; error?: boolean };
export type ChatMessage = {
  id?: string;
  sender: "user" | "machine";
  sender_name: string;
  text: string;
  properties?: { steps?: Step[]; source?: { source?: string } };
  error?: boolean;
  streaming?: boolean;
};
export type NodeRun = { status: "running" | "done" | "error" | "skipped"; preview?: string; ms?: number; error?: string };
