import {
  Binary, Bot, Box, Braces, Calculator, Calendar, Cpu, Database, FileText, Globe, History,
  MessageSquare, MessageSquareReply, ScanText, Scissors, Sparkles, Split, Table, Type, Users, Workflow,
  type LucideProps,
} from "lucide-react";

const ICONS: Record<string, React.ComponentType<LucideProps>> = {
  bot: Bot, box: Box, braces: Braces, calculator: Calculator, calendar: Calendar, cpu: Cpu, database: Database,
  "file-text": FileText, globe: Globe, history: History, "message-square": MessageSquare,
  "message-square-reply": MessageSquareReply, "scan-text": ScanText, scissors: Scissors, sparkles: Sparkles,
  split: Split, table: Table, type: Type, users: Users, workflow: Workflow, binary: Binary,
};

export function Icon({ name, ...p }: { name: string } & LucideProps) {
  const C = ICONS[name] ?? Box;
  return <C size={16} {...p} />;
}

export const CATEGORY_COLORS: Record<string, string> = {
  "Input & Output": "#3b82f6",
  Prompts: "#8b5cf6",
  Models: "#e0457b",
  Agents: "#0e9f8e",
  Tools: "#22a559",
  Memory: "#ef7d22",
  "Vector Stores": "#14b8a6",
  Processing: "#64748b",
  Logic: "#d4a014",
};

export const typeColor = (t: string) => `var(--t-${t}, #94a3b8)`;
