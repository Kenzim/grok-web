import type { GrokEvent, HistoryEntry, WidgetPayload } from "./api";

export interface Bubble {
  id: string;
  seq: number;
  role: "user" | "assistant";
  text: string;
  tsMs: number;
  images: { url: string; alt?: string }[];
  widget?: WidgetPayload;
}

const HIDDEN_KINDS = new Set([
  "spend-initiation",
  "spend_initiation",
  "computer_actions",
  "computer-actions",
  "agent_state",
  "agent_state_changed",
  "box_state",
]);

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function tsMs(ts: number | undefined, body: Record<string, unknown> | null): number {
  if (ts && ts > 0) return ts > 1e12 ? ts : ts * 1000;
  if (!body) return 0;
  const raw = body.timestampMs ?? body.timestamp_ms ?? body.ts ?? body.created_at_ms;
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return n > 1e12 ? n : n * 1000;
}

export function bubblesFromEntries(entries: HistoryEntry[]): Bubble[] {
  const out: Bubble[] = [];
  const seen = new Set<string>();
  for (const entry of entries) {
    const kind = (entry.entry_kind || "").toLowerCase();
    if (HIDDEN_KINDS.has(kind)) continue;
    const id = entry.entry_id || `seq-${entry.seq}`;
    if (seen.has(id)) continue;
    const body = asRecord(entry.body);
    const widget = entry.widget || undefined;
    const images = entry.images?.length ? entry.images : [];
    let text = (entry.text || "").trim();
    let role = (entry.role || "").toLowerCase();
    if (role === "human") role = "user";
    if (role !== "user" && role !== "assistant") {
      if (kind === "message" || kind.includes("user")) role = "user";
      else if (kind === "send-message" || kind.includes("assistant") || kind.includes("agent")) {
        role = "assistant";
      } else {
        role = "";
      }
    }
    if (!text && !widget && images.length === 0) continue;
    seen.add(id);
    out.push({
      id,
      seq: entry.seq || 0,
      role: role === "user" ? "user" : "assistant",
      text,
      tsMs: tsMs(entry.ts, body),
      images,
      widget,
    });
  }
  out.sort((a, b) => (a.tsMs || a.seq) - (b.tsMs || b.seq) || a.seq - b.seq);
  return out;
}

export function applyEvent(bubbles: Bubble[], event: GrokEvent): Bubble[] {
  if (event.type === "Message") {
    const kind = (event.entry_kind || "").toLowerCase();
    if (HIDDEN_KINDS.has(kind)) return bubbles;
    const id = event.entry_id || `seq-${event.seq || 0}`;
    const role = event.role === "user" ? "user" : "assistant";
    const next: Bubble = {
      id,
      seq: event.seq || 0,
      role,
      text: (event.text || "").trim(),
      tsMs: tsMs(event.ts, asRecord(event.body)),
      images: [],
    };
    if (!next.text) return bubbles;
    const idx = bubbles.findIndex((b) => b.id === id);
    if (idx >= 0) {
      const copy = bubbles.slice();
      copy[idx] = { ...copy[idx], ...next, widget: copy[idx].widget };
      return copy;
    }
    return [...bubbles, next];
  }
  if (event.type === "WidgetRequest" && event.entry_id) {
    const widget: WidgetPayload = {
      agent_id: event.agent_id || "",
      session_id: event.session_id || "",
      entry_id: event.entry_id,
      kind: event.kind || "widget",
      prompt: event.prompt || "",
      request_id: event.request_id || "",
      body: event.body,
    };
    const idx = bubbles.findIndex((b) => b.id === event.entry_id);
    if (idx >= 0) {
      const copy = bubbles.slice();
      copy[idx] = { ...copy[idx], widget };
      return copy;
    }
    return [
      ...bubbles,
      {
        id: event.entry_id,
        seq: event.seq || Date.now(),
        role: "assistant",
        text: "",
        tsMs: Date.now(),
        images: [],
        widget,
      },
    ];
  }
  return bubbles;
}

export function initial(name: string): string {
  const t = name.trim();
  return t ? t[0]!.toUpperCase() : "?";
}
