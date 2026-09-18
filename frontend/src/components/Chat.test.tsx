import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Chat from "./Chat";
import type { Agent } from "../api";
import type { Bubble } from "../transcript";

const agent: Agent = {
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

const bubbles: Bubble[] = [
  {
    id: "u1",
    seq: 1,
    role: "user",
    text: "hello **there**",
    tsMs: 1,
    images: [{ url: "https://cdn.example/a.png", alt: "shot" }],
  },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Chat", () => {
  it("shows empty state without an agent", () => {
    render(
      <Chat
        agent={null}
        bubbles={[]}
        composing={false}
        running={false}
        error={null}
        onSent={() => undefined}
      />,
    );
    expect(screen.getByText("Select an agent")).toBeInTheDocument();
  });

  it("sends on submit and Enter, interrupts while running", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSent = vi.fn();
    render(
      <Chat
        agent={agent}
        bubbles={bubbles}
        composing
        running
        error={null}
        onSent={onSent}
      />,
    );
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByAltText("shot")).toHaveAttribute("src", "https://cdn.example/a.png");
    expect(screen.getByText("Composing…")).toBeInTheDocument();
    const box = screen.getByPlaceholderText("Message");
    fireEvent.change(box, { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: "ping" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
    await waitFor(() => expect(onSent).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Interrupt" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("/interrupt"))).toBe(true),
    );
  });

  it("surfaces send failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        text: async () => JSON.stringify({ detail: "refused" }),
      }),
    );
    render(
      <Chat agent={agent} bubbles={[]} composing={false} running={false} error={null} onSent={() => undefined} />,
    );
    fireEvent.change(screen.getByPlaceholderText("Message"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByText("refused")).toBeInTheDocument());
  });
});
