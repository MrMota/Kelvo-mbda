import {
  Binary, Bot, Box, Braces, Calculator, Calendar, Cpu, Database, FileText, Globe, History,
  Folder, MessageSquare, Plug, MessageSquareReply, ScanText, Scissors, Search, Sparkles, Split, Table, Terminal, Type, Users, Workflow,
  type LucideProps,
} from "lucide-react";

const ICONS: Record<string, React.ComponentType<LucideProps>> = {
  bot: Bot, box: Box, braces: Braces, calculator: Calculator, calendar: Calendar, cpu: Cpu, database: Database,
  "file-text": FileText, folder: Folder, plug: Plug, search: Search, terminal: Terminal, globe: Globe, history: History, "message-square": MessageSquare,
  "message-square-reply": MessageSquareReply, "scan-text": ScanText, scissors: Scissors, sparkles: Sparkles,
  split: Split, table: Table, type: Type, users: Users, workflow: Workflow, binary: Binary,
};

export function Icon({ name, ...p }: { name: string } & LucideProps) {
  const C = ICONS[name] ?? Box;
  return <C size={16} {...p} />;
}

export const CATEGORY_COLORS: Record<string, string> = {
  "Input & Output": "#2f6fe4",
  Prompts: "#0b7f9c",
  Models: "#4a5568",
  Agents: "#0b7c70",
  Tools: "#1b8545",
  Memory: "#c45a0c",
  "Vector Stores": "#0b8478",
  Processing: "#6b6560",
  Logic: "#9a7206",
};

export const typeColor = (t: string) => `var(--t-${t}, #94a3b8)`;
