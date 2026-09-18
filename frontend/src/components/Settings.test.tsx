import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Settings from "./Settings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const settings = {
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
};

function json(data: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => data,
    text: async (): Promise<string> => "",
  };
}

describe("Settings", () => {
  it("starts Cursor login and opens the URL", async () => {
    const fetchMock = vi.fn(async (path: string) => {
      const p = String(path);
      if (p.includes("/login/start")) {
        return json({
          state: "pending",
          url: "https://cursor.com/loginDeepControl?x=1",
          error: null,
        });
      }
      return json(settings);
    });
    vi.stubGlobal("fetch", fetchMock);
    const open = vi.fn();
    vi.stubGlobal("open", open);
    render(<Settings onClose={() => undefined} onCursorChanged={() => undefined} />);
    await waitFor(() => expect(screen.getByText("Not signed in")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Sign in with Cursor" }));
    await waitFor(() => expect(open).toHaveBeenCalled());
    expect(String(open.mock.calls[0]?.[0])).toContain("loginDeepControl");
  });

  it("enables an instance password", async () => {
    const fetchMock = vi.fn(async (path: string) => {
      if (String(path).includes("/password")) {
        return json({ ok: true, password_enabled: true });
      }
      return json(settings);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<Settings onClose={() => undefined} onCursorChanged={() => undefined} />);
    await waitFor(() => expect(screen.getByText(/Password protection is off/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("At least 8 characters"), {
      target: { value: "long-enough" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enable password" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("/settings/password"))).toBe(
        true,
      ),
    );
  });
});
