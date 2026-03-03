import type {
  SystemStatus,
  ChatRequest,
  ChatResponse,
  MemoryStats,
  MemorySearchResult,
  SkillInfo,
  ConfigData,
  ScheduledJob,
  WsMessage,
} from "../types";

const BASE_URL = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Status ──
export async function getStatus(): Promise<SystemStatus> {
  return request("/status");
}

// ── Chat ──
export async function sendMessage(data: ChatRequest): Promise<ChatResponse> {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Memory ──
export async function getMemoryStats(): Promise<MemoryStats> {
  return request("/memory/stats");
}

export async function searchMemory(
  query: string,
  topK = 10
): Promise<MemorySearchResult> {
  return request(`/memory/search?q=${encodeURIComponent(query)}&top_k=${topK}`);
}

// ── Skills ──
export async function getSkills(): Promise<SkillInfo[]> {
  return request("/skills");
}

// ── Config ──
export async function getConfig(): Promise<ConfigData> {
  return request("/config");
}

export async function updateConfig(
  section: string,
  updates: Record<string, unknown>
): Promise<{ section: string; updated: unknown }> {
  return request("/config", {
    method: "PATCH",
    body: JSON.stringify({ section, updates }),
  });
}

export async function restartServer(): Promise<{ status: string }> {
  return request("/restart", { method: "POST" });
}

// ── Scheduler ──
export async function getScheduledJobs(): Promise<ScheduledJob[]> {
  return request("/scheduler/jobs");
}

// ── WebSocket Chat ──
export function createChatSocket(
  onMessage: (msg: WsMessage) => void,
  onError?: (err: Event) => void,
  onClose?: () => void
): {
  send: (message: string) => void;
  close: () => void;
} {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws/chat`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as WsMessage;
      onMessage(data);
    } catch {
      onMessage({ type: "chunk", content: event.data });
    }
  };

  ws.onerror = (event) => onError?.(event);
  ws.onclose = () => onClose?.();

  const send = (message: string) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ message }));
    }
  };

  const close = () => ws.close();

  return { send, close };
}
