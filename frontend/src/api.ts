export interface Account {
  user_id: number;
  email: string;
  first_name: string;
}

export interface Agent {
  id: string;
  agent_id: string;
  name: string;
  description: string;
  harness: string;
  kind: string;
  created_at_ms: number;
  title: string;
  viewer_session_id: string;
}

export interface WidgetPayload {
  agent_id: string;
  session_id: string;
  entry_id: string;
  kind: string;
  prompt: string;
  request_id: string;
  body?: unknown;
}

export interface HistoryEntry {
  seq: number;
  entry_id?: string | null;
  entry_kind?: string;
  body?: unknown;
  text?: string;
  role?: string;
  ts?: number;
  images?: { url: string; alt?: string }[];
  widget?: WidgetPayload | null;
}

export interface HistoryPage {
  generation: number;
  session_id: string;
  entries: HistoryEntry[];
}

export type GrokEvent = {
  type: string;
  agent_id?: string;
  session_id?: string;
  entry_id?: string;
  seq?: number;
  text?: string;
  role?: string;
  ts?: number;
  entry_kind?: string;
  body?: unknown;
  kind?: string;
  prompt?: string;
  request_id?: string;
  instruction?: string;
  reason?: string;
  tab_id?: string;
  is_running?: boolean;
  is_composing?: boolean;
  run_state?: string;
  code?: string;
  turn_id?: string;
};

async function parseError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const data = JSON.parse(text) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* ignore */
  }
  return text || `HTTP ${res.status}`;
}

export async function api(path: string, init?: RequestInit): Promise<unknown> {
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) throw new Error(await parseError(res));
  return await res.json();
}

export function wsUrl(path: string): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}`;
}
