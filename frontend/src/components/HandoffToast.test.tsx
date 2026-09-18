import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import HandoffToast from "./HandoffToast";

afterEach(() => {
  cleanup();
});

describe("HandoffToast", () => {
  it("renders nothing without items", () => {
    const { container } = render(
      <HandoffToast items={[]} onOpen={() => undefined} onDismiss={() => undefined} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("opens VNC and dismisses", () => {
    const onOpen = vi.fn();
    const onDismiss = vi.fn();
    render(
      <HandoffToast
        items={[
          { id: "1", agentId: "a1", instruction: "Solve captcha", reason: "captcha" },
          { id: "2", agentId: "a2", instruction: "", reason: "" },
        ]}
        onOpen={onOpen}
        onDismiss={onDismiss}
      />,
    );
    expect(screen.getByText("Solve captcha")).toBeInTheDocument();
    expect(screen.getByText("Grok Bot needs you on the cloud desktop.")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Open VNC" })[0]!);
    expect(onOpen).toHaveBeenCalledWith("a1");
    fireEvent.click(screen.getAllByRole("button", { name: "Dismiss" })[1]!);
    expect(onDismiss).toHaveBeenCalledWith("2");
  });
});
