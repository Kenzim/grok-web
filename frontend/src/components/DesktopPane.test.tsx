import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DesktopPane from "./DesktopPane";

const disconnect = vi.fn();

vi.mock("@novnc/novnc", () => {
  class RFB {
    scaleViewport = false;
    resizeSession = false;
    disconnect = disconnect;
    constructor(
      public el: HTMLElement,
      public url: string,
    ) {}
  }
  return { default: RFB };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  disconnect.mockReset();
});

describe("DesktopPane", () => {
  beforeEach(() => {
    disconnect.mockReset();
  });

  it("asks before waking a hibernated sandbox", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ token: "", run_state: "HIBERNATED", has_vnc: false }),
        text: async () => "",
      }),
    );
    render(<DesktopPane onClose={() => undefined} />);
    await waitFor(() => expect(screen.getByText(/Waking it uses cloud quota/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Wake sandbox" })).toBeInTheDocument();
  });

  it("connects noVNC when a token is returned", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ token: "tok", run_state: "RUNNING", has_vnc: true }),
        text: async () => "",
      }),
    );
    const onClose = vi.fn();
    render(<DesktopPane onClose={onClose} />);
    await waitFor(() => expect(screen.getByText("RUNNING")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("shows an error when desktop has no VNC", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ token: "", run_state: "RUNNING", has_vnc: false }),
        text: async () => "",
      }),
    );
    render(<DesktopPane onClose={() => undefined} />);
    await waitFor(() => expect(screen.getByText(/No VNC endpoint/)).toBeInTheDocument());
  });
});
