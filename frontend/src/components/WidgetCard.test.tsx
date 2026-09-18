import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import WidgetCard from "./WidgetCard";
import type { WidgetPayload } from "../api";

const base: WidgetPayload = {
  agent_id: "a1",
  session_id: "",
  entry_id: "e1",
  kind: "widget",
  prompt: "Pick one",
  request_id: "r1",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function okFetch() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ok: true }),
    text: async () => "",
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("WidgetCard", () => {
  it("posts option clicks to respond", async () => {
    const fetchMock = okFetch();
    render(
      <WidgetCard
        widget={{ ...base, body: { options: [{ label: "Yes" }, "No"] } }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/widgets/respond");
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).toContain("Yes");
  });

  it("resolves approvals including card kinds", async () => {
    const fetchMock = okFetch();
    render(<WidgetCard widget={{ ...base, kind: "virtual_card", prompt: "Charge?" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Deny" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/widgets/resolve-approval");
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).toContain('"approved":false');
  });

  it("submits secrets", async () => {
    const fetchMock = okFetch();
    render(<WidgetCard widget={{ ...base, kind: "secret", prompt: "Token" }} />);
    fireEvent.change(screen.getByPlaceholderText("Secret"), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/widgets/submit-secret");
  });

  it("submits named form fields from id", async () => {
    const fetchMock = okFetch();
    render(
      <WidgetCard
        widget={{
          ...base,
          kind: "user_form",
          body: { fields: [{ id: "city", title: "City" }, "skip"] },
        }}
      />,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "London" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/widgets/submit-form");
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).toContain("London");
  });

  it("dismisses option widgets and shows API errors", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      text: async () => JSON.stringify({ detail: "refused" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<WidgetCard widget={{ ...base, body: { choices: ["A"] } }} />);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(screen.getByText("refused")).toBeInTheDocument());
  });

  it("posts free-text respond", async () => {
    const fetchMock = okFetch();
    const onDone = vi.fn();
    render(<WidgetCard widget={{ ...base, kind: "ask", prompt: "Why?" }} onDone={onDone} />);
    fireEvent.change(screen.getByPlaceholderText("Response"), { target: { value: "because" } });
    fireEvent.click(screen.getByRole("button", { name: "Respond" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/widgets/respond");
  });
});
