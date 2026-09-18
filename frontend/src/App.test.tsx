import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

class MockSocket {
  static OPEN = 1;
  static instances: MockSocket[] = [];
  onmessage: ((ev: { data: string }) => void) | null = null;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  readyState = MockSocket.OPEN;
  sent: string[] = [];
  url: string;
  constructor(url: string) {
    this.url = url;
    MockSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
  }
  emit(payload: unknown) {
    this.onmessage?.({ data: typeof payload === "string" ? payload : JSON.stringify(payload) });
  }
}

const boxAgent = {
  id: "1",
  agent_id: "a1",
  name: "Finder",
  description: "",
  harness: "box",
  kind: "DEFAULT",
  created_at_ms: 1,
  title: "",
  viewer_session_id: "",
};

const temporalAgent = { ...boxAgent, id: "2", agent_id: "t1", name: "Workflow", harness: "temporal" };

function jsonRes(data: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => data,
    text: async () => (typeof data === "string" ? data : JSON.stringify(data)),
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  MockSocket.instances = [];
});

describe("App", () => {
  beforeEach(() => {
    MockSocket.instances = [];
    vi.stubGlobal("WebSocket", MockSocket);
  });

  it("boots roster and chat, then applies live events", async () => {
    const fetchMock = vi.fn(async (path: string) => {
      const p = String(path);
      if (p === "/api/me") return jsonRes({ email: "a@b.c", user_id: 1, first_name: "A" });
      if (p === "/api/agents") return jsonRes([boxAgent, temporalAgent]);
      if (p.includes("/history")) {
        return jsonRes({
          generation: 1,
          session_id: "",
          entries: [{ seq: 1, entry_id: "u1", entry_kind: "message", role: "user", text: "hi" }],
        });
      }
      if (p === "/api/desktop") {
        return jsonRes({ token: "", run_state: "HIBERNATED", has_vnc: false });
      }
      return jsonRes({ ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(screen.getByText("a@b.c")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("hi")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Desktop" })).toBeInTheDocument();

    const ws = MockSocket.instances.at(-1)!;
    ws.emit("{not json");
    ws.emit({ type: "Hello" });
    ws.emit({ type: "AgentStateUpdate", agent_id: "a1", is_running: true, is_composing: true });
    ws.emit({
      type: "Message",
      agent_id: "a1",
      entry_id: "a2",
      text: "live",
      role: "assistant",
      entry_kind: "send-message",
    });
    ws.emit({
      type: "HandoffRequested",
      agent_id: "a1",
      request_id: "h1",
      instruction: "Need desktop",
    });
    ws.emit({ type: "TurnFailed", agent_id: "a1", reason: "model down" });

    await waitFor(() => expect(screen.getByText("live")).toBeInTheDocument());
    expect(screen.getByText("Need desktop")).toBeInTheDocument();
    expect(screen.getByText("model down")).toBeInTheDocument();

    ws.emit({ type: "RosterChanged", kind: "UPDATED" });
    ws.emit({ type: "StreamReset", agent_id: "a1" });
    await waitFor(() => expect(screen.getByText("hi")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Open VNC" }));
    await waitFor(() => expect(screen.getByText("Cloud desktop")).toBeInTheDocument());
  });

  it("shows boot errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "unauthorized" }),
        text: async () => JSON.stringify({ detail: "unauthorized" }),
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText("unauthorized")).toBeInTheDocument());
  });
});
