import { afterEach, describe, expect, it, vi } from "vitest";
import { applyEvent, bubblesFromEntries, initial } from "./transcript";
import type { HistoryEntry } from "./api";

describe("bubblesFromEntries", () => {
  it("maps user message and assistant send-message, hides spend-initiation", () => {
    const entries: HistoryEntry[] = [
      {
        seq: 1,
        entry_id: "u1",
        entry_kind: "message",
        role: "user",
        text: "hello",
        ts: 1,
      },
      {
        seq: 2,
        entry_id: "s1",
        entry_kind: "spend-initiation",
        text: "hidden",
      },
      {
        seq: 3,
        entry_id: "a1",
        entry_kind: "send-message",
        role: "assistant",
        text: "hi back",
        ts: 2,
      },
    ];
    const bubbles = bubblesFromEntries(entries);
    expect(bubbles.map((b) => b.id)).toEqual(["u1", "a1"]);
    expect(bubbles[0]?.role).toBe("user");
    expect(bubbles[1]?.role).toBe("assistant");
  });

  it("keeps nested widgets from history", () => {
    const entries: HistoryEntry[] = [
      {
        seq: 1,
        entry_id: "w1",
        entry_kind: "send-message",
        widget: {
          agent_id: "a",
          session_id: "",
          entry_id: "w1",
          kind: "approval",
          prompt: "Continue?",
          request_id: "r",
        },
      },
    ];
    const bubbles = bubblesFromEntries(entries);
    expect(bubbles[0]?.widget?.kind).toBe("approval");
  });

  it("dedupes ids, maps human role, and sorts by timestamp", () => {
    const entries: HistoryEntry[] = [
      { seq: 2, entry_id: "b", entry_kind: "send-message", text: "later", ts: 2000, role: "assistant" },
      { seq: 1, entry_id: "a", entry_kind: "message", text: "first", ts: 1000, role: "human" },
      { seq: 3, entry_id: "a", entry_kind: "message", text: "dup", ts: 3000, role: "user" },
      { seq: 4, entry_kind: "box_state", text: "hidden" },
      { seq: 5, entry_id: "empty", entry_kind: "send-message", text: "  " },
    ];
    const bubbles = bubblesFromEntries(entries);
    expect(bubbles.map((b) => b.id)).toEqual(["a", "b"]);
    expect(bubbles[0]?.role).toBe("user");
  });

  it("uses seconds timestamps from the body when needed", () => {
    const bubbles = bubblesFromEntries([
      {
        seq: 1,
        entry_id: "t",
        entry_kind: "message",
        text: "x",
        body: { timestampMs: 1_700_000_000 },
      },
    ]);
    expect(bubbles[0]?.tsMs).toBe(1_700_000_000_000);
  });

  it("maps roles from kind and keeps images", () => {
    const bubbles = bubblesFromEntries([
      { seq: 1, entry_id: "u", entry_kind: "user-note", text: "q" },
      { seq: 2, entry_id: "a", entry_kind: "agent-reply", text: "r", images: [{ url: "https://x/a.png" }] },
      { seq: 3, entry_kind: "message", text: "no-id" },
      { seq: 4, entry_id: "h", entry_kind: "computer_actions", text: "hidden" },
    ]);
    expect(bubbles.map((b) => b.id)).toEqual(["u", "a", "seq-3"]);
    expect(bubbles[0]?.role).toBe("user");
    expect(bubbles[1]?.role).toBe("assistant");
    expect(bubbles[1]?.images).toEqual([{ url: "https://x/a.png" }]);
  });
});

describe("applyEvent", () => {
  it("appends live messages and widgets by entry id", () => {
    let bubbles = applyEvent([], {
      type: "Message",
      entry_id: "m1",
      seq: 1,
      text: "ping",
      role: "user",
      entry_kind: "message",
    });
    bubbles = applyEvent(bubbles, {
      type: "WidgetRequest",
      entry_id: "w1",
      kind: "form",
      prompt: "Name?",
      agent_id: "a",
      session_id: "",
    });
    expect(bubbles).toHaveLength(2);
    expect(bubbles[1]?.widget?.prompt).toBe("Name?");
  });

  it("updates an existing message and ignores hidden kinds", () => {
    let bubbles = applyEvent([], {
      type: "Message",
      entry_id: "m1",
      text: "one",
      role: "assistant",
      entry_kind: "send-message",
    });
    bubbles = applyEvent(bubbles, {
      type: "Message",
      entry_id: "m1",
      text: "two",
      role: "assistant",
      entry_kind: "send-message",
    });
    expect(bubbles).toHaveLength(1);
    expect(bubbles[0]?.text).toBe("two");
    const hidden = applyEvent(bubbles, {
      type: "Message",
      entry_id: "h",
      text: "nope",
      entry_kind: "spend-initiation",
    });
    expect(hidden).toHaveLength(1);
  });

  it("attaches a widget onto an existing bubble", () => {
    const start = applyEvent([], {
      type: "Message",
      entry_id: "w1",
      text: "choose",
      role: "assistant",
      entry_kind: "send-message",
    });
    const next = applyEvent(start, {
      type: "WidgetRequest",
      entry_id: "w1",
      kind: "approval",
      prompt: "Go?",
    });
    expect(next[0]?.widget?.prompt).toBe("Go?");
    expect(next[0]?.text).toBe("choose");
  });

  it("ignores unknown event types and empty messages", () => {
    expect(applyEvent([], { type: "Hello" })).toEqual([]);
    expect(applyEvent([], { type: "Message", entry_id: "x", text: "  " })).toEqual([]);
  });
});

describe("initial", () => {
  it("uses the first letter or a fallback", () => {
    expect(initial(" job")).toBe("J");
    expect(initial("   ")).toBe("?");
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});
