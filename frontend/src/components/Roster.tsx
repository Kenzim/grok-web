import type { Agent } from "../api";
import { initial } from "../transcript";

export default function Roster({
  agents,
  selectedId,
  running,
  composing,
  query,
  onQuery,
  onSelect,
}: {
  agents: Agent[];
  selectedId: string | null;
  running: Set<string>;
  composing: Set<string>;
  query: string;
  onQuery: (q: string) => void;
  onSelect: (agent: Agent) => void;
}) {
  const q = query.trim().toLowerCase();
  const filtered = q
    ? agents.filter(
        (a) =>
          a.name.toLowerCase().includes(q) ||
          a.agent_id.toLowerCase().includes(q) ||
          a.harness.toLowerCase().includes(q),
      )
    : agents;

  return (
    <aside className="roster">
      <input
        className="search"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        placeholder="Search agents"
      />
      <ul>
        {filtered.map((agent) => {
          const live = running.has(agent.agent_id);
          const typing = composing.has(agent.agent_id);
          return (
            <li key={agent.agent_id}>
              <button
                type="button"
                className={agent.agent_id === selectedId ? "agent active" : "agent"}
                onClick={() => onSelect(agent)}
              >
                <span className="avatar">{initial(agent.name)}</span>
                <span className="meta">
                  <span className="name">
                    {agent.name || agent.title || "Untitled"}
                    {live ? <em className="dot" title="running" /> : null}
                  </span>
                  <span className="sub">
                    {agent.harness || "box"}
                    {typing ? " · composing" : ""}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {!filtered.length ? <div className="muted pad">No agents</div> : null}
    </aside>
  );
}
