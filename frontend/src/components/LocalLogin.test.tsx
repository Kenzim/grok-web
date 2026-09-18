import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LocalLogin from "./LocalLogin";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LocalLogin", () => {
  it("posts the password and calls onDone", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();
    render(<LocalLogin onDone={onDone} />);
    fireEvent.change(screen.getByPlaceholderText("Instance password"), {
      target: { value: "secret-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/auth/login");
  });
});
