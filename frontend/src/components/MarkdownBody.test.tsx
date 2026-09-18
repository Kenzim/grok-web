import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MarkdownBody from "./MarkdownBody";

describe("MarkdownBody", () => {
  it("renders links, emphasis, and lists", () => {
    render(
      <MarkdownBody text={"See **bold** and [docs](https://example.com).\n\n- one\n- two"} />,
    );
    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("one").tagName).toBe("LI");
  });

  it("drops file urls", () => {
    render(<MarkdownBody text={"![x](file:///tmp/x.png)"} />);
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("renders https images", () => {
    render(<MarkdownBody text={"![cat](https://cdn.example/cat.png)"} />);
    expect(screen.getByRole("img", { name: "cat" })).toHaveAttribute(
      "src",
      "https://cdn.example/cat.png",
    );
  });
});
