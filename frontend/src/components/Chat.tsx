import { useEffect, useRef, useState } from "react";
import type { Agent } from "../api";
import { api } from "../api";
import { type Bubble } from "../transcript";
import MarkdownBody from "./MarkdownBody";
import WidgetCard from "./WidgetCard";

export default function Chat({
  agent,
  bubbles,
  composing,
  running,
  error,
  onSent,
}: {
  agent: Agent | null;
  bubbles: Bubble[];
  composing: boolean;
  running: boolean;
  error: string | null;
  onSent: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [bubbles, composing]);

  if (!agent) {
    return <main className="chat empty">Select an agent</main>;
  }

  async function send() {
    const value = text.trim();
    if (!value || !agent) return;
    setBusy(true);
    setLocalError(null);
    try {
      await api(`/api/agents/${encodeURIComponent(agent.agent_id)}/send`, {
        method: "POST",
        body: JSON.stringify({ text: value }),
      });
      setText("");
      onSent();
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function interrupt() {
    if (!agent) return;
    setBusy(true);
    setLocalError(null);
    try {
      await api(`/api/agents/${encodeURIComponent(agent.agent_id)}/interrupt`, { method: "POST" });
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="chat">
      <header className="chat-bar">
        <div>
          <h2>{agent.name || agent.title || "Agent"}</h2>
          <div className="muted">
            {agent.harness}
            {running ? " · running" : ""}
            {composing ? " · composing" : ""}
          </div>
        </div>
        <button type="button" disabled={busy || !running} onClick={() => void interrupt()}>
          Interrupt
        </button>
      </header>
      <div className="thread" ref={scroller}>
        {bubbles.map((b) => (
          <article key={b.id} className={`bubble ${b.role}`}>
            <div className="who">{b.role === "user" ? "You" : agent.name}</div>
            {b.text ? <MarkdownBody text={b.text} /> : null}
            {b.images.map((img) => (
              <img key={img.url} src={img.url} alt={img.alt || ""} className="shot" />
            ))}
            {b.widget ? <WidgetCard widget={b.widget} /> : null}
          </article>
        ))}
        {composing ? <div className="muted pad">Composing…</div> : null}
      </div>
      {error || localError ? <div className="error pad">{error || localError}</div> : null}
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Message"
          rows={3}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button className="primary" disabled={busy || !text.trim()} type="submit">
          Send
        </button>
      </form>
    </main>
  );
}
