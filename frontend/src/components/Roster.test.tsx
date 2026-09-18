import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Roster from "./Roster";
import type { Agent } from "../api";

const agents: Agent[] = [
  {
    id: "1",
    agent_id: "finder",
    name: "Job finder",
    description: "",
    harness: "box",
    kind: "DEFAULT",
    created_at_ms: 1,
    title: "",
    viewer_session_id: "",
  },
  {
    id: "2",
    agent_id: "coder",
    name: "",
    description: "",
    harness: "temporal",
    kind: "DEFAULT",
    created_at_ms: 1,
    title: "Coder",
    viewer_session_id: "",
  },
];

afterEach(() => cleanup());

describe("Roster", () => {
  it("filters by name and reports empty", () => {
    const onQuery = vi.fn();
    const onSelect = vi.fn();
    const { rerender } = render(
      <Roster
        agents={agents}
        selectedId="finder"
        running={new Set(["finder"])}
        composing={new Set(["coder"])}
        query=""
        onQuery={onQuery}
        onSelect={onSelect}
      />,
    );
    expect(screen.getByText("Job finder")).toBeInTheDocument();
    expect(screen.getByTitle("running")).toBeInTheDocument();
    expect(screen.getByText(/composing/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Coder"));
    expect(onSelect).toHaveBeenCalled();
    fireEvent.change(screen.getByPlaceholderText("Search agents"), { target: { value: "nope" } });
    expect(onQuery).toHaveBeenCalledWith("nope");
    rerender(
      <Roster
        agents={agents}
        selectedId="finder"
        running={new Set()}
        composing={new Set()}
        query="nope"
        onQuery={onQuery}
        onSelect={onSelect}
      />,
    );
    expect(screen.getByText("No agents")).toBeInTheDocument();
  });
});
