import { afterEach, describe, expect, it, vi } from "vitest";
import { api, wsUrl } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("returns json on success and sets content-type for bodies", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ email: "a@b.c" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const out = await api("/api/me", { method: "POST", body: JSON.stringify({ x: 1 }) });
    expect(out).toEqual({ email: "a@b.c" });
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
    expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe("include");
  });

  it("throws FastAPI detail strings", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        text: async () => JSON.stringify({ detail: "text required" }),
      }),
    );
    await expect(api("/api/agents/a/send", { method: "POST", body: "{}" })).rejects.toThrow(
      "text required",
    );
  });

  it("falls back to status text when the body is not json", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        text: async () => "upstream",
      }),
    );
    await expect(api("/api/me")).rejects.toThrow("upstream");
  });

  it("falls back to HTTP status when the body is empty", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: async () => "",
      }),
    );
    await expect(api("/api/me")).rejects.toThrow("HTTP 503");
  });

  it("dispatches an auth event on 401", async () => {
    const seen: string[] = [];
    window.addEventListener("grokweb:auth", () => seen.push("yes"));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () => JSON.stringify({ detail: "auth required" }),
      }),
    );
    await expect(api("/api/me")).rejects.toThrow("auth required");
    expect(seen).toEqual(["yes"]);
  });
});

describe("wsUrl", () => {
  it("uses the current host", () => {
    expect(wsUrl("/ws/events")).toMatch(/\/ws\/events$/);
    expect(wsUrl("/ws/vnc")).toContain("://");
  });
});
