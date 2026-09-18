import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Root from "./Root";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Root", () => {
  it("shows the instance login gate when required", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ password_enabled: true, authenticated: false, needs_login: true }),
        text: async () => "",
      }),
    );
    render(<Root />);
    await waitFor(() => expect(screen.getByText(/password protected/)).toBeInTheDocument());
    expect(screen.getByPlaceholderText("Instance password")).toBeInTheDocument();
  });

  it("renders the app when authenticated", async () => {
    vi.stubGlobal("WebSocket", class {
      static OPEN = 1;
      readyState = 1;
      onmessage = null;
      onopen: (() => void) | null = null;
      onclose = null;
      send() {}
      close() {}
      constructor() {
        queueMicrotask(() => this.onopen?.());
      }
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        const p = String(path);
        const json = async (data: unknown) => ({
          ok: true,
          status: 200,
          json: async () => data,
          text: async (): Promise<string> => "",
        });
        if (p === "/api/auth/status") {
          return json({ password_enabled: false, authenticated: true, needs_login: false });
        }
        if (p === "/api/me") return json({ email: "a@b.c", user_id: 1, first_name: "A" });
        if (p === "/api/agents") return json([]);
        if (p === "/api/settings" || p.includes("/api/settings/")) {
          return json({
            password_enabled: false,
            cursor: {
              signed_in: false,
              source: null,
              has_refresh: false,
              has_api_key: false,
              expires_at: null,
              expired: false,
              subject: "",
              account: null,
            },
            login: { state: "idle", url: null, error: null },
          });
        }
        return json({ ok: true });
      }),
    );
    render(<Root />);
    await waitFor(() => expect(screen.getByText("a@b.c")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    await waitFor(() => expect(screen.getByText("Cursor account")).toBeInTheDocument());
  });
});
