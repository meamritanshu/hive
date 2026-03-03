// ── Status ──
export interface SystemStatus {
  status: string;
  version: string;
  model: string;
  provider: string;
  memory_backend: string;
}

// ── Chat ──
export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp: string;
  tool_calls?: ToolCallInfo[];
}

export interface ToolCallInfo {
  name: string;
  arguments: Record<string, unknown>;
  result?: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  tool_calls?: ToolCallInfo[];
}

// ── Memory ──
export interface MemoryStats {
  short_term_count: number;
  long_term_count: number;
  file_memory_count: number;
  vector_memory_count: number;
  memory_types: Record<string, number>;
}

export interface MemoryEntry {
  id: string;
  content: string;
  memory_type: string;
  created_at: string;
  metadata: Record<string, unknown>;
  score?: number;
}

export interface MemorySearchResult {
  entries: MemoryEntry[];
  query: string;
  total: number;
}

// ── Skills ──
export interface SkillParameter {
  name: string;
  type: string;
  description: string;
  required: boolean;
  default?: unknown;
}

export interface SkillInfo {
  name: string;
  description: string;
  category: string;
  parameters: SkillParameter[];
  enabled: boolean;
}

// ── Config ──
export interface ConfigData {
  [key: string]: unknown;
}

// ── Scheduler ──
export interface ScheduledJob {
  id: string;
  name: string;
  trigger: string;
  next_run_time: string | null;
  enabled: boolean;
  description?: string;
}

// ── WebSocket ──
export interface WsChunkMessage {
  type: "chunk";
  content: string;
}

export interface WsDoneMessage {
  type: "done";
  conversation_id: string;
}

export interface WsErrorMessage {
  type: "error";
  message: string;
}

export type WsMessage = WsChunkMessage | WsDoneMessage | WsErrorMessage;
