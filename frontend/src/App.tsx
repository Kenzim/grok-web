import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Account, Agent, GrokEvent, HistoryPage } from "./api";
import { api, wsUrl } from "./api";
import Chat from "./components/Chat";
import DesktopPane from "./components/DesktopPane";
import HandoffToast, { type Handoff } from "./components/HandoffToast";
import Roster from "./components/Roster";
import Settings from "./components/Settings";
import { applyEvent, bubblesFromEntries, type Bubble } from "./transcript";

export default function App() {
  const [me, setMe] = useState<Account | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [bootError, setBootError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [composing, setComposing] = useState<Set<string>>(new Set());
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [desktopOpen, setDesktopOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const selected = useMemo(
    () => agents.find((a) => a.agent_id === selectedId) || null,
    [agents, selectedId],
  );
  const selectedIdRef = useRef(selectedId);
  selectedIdRef.current = selectedId;

  const loadAgents = useCallback(async () => {
    const rows = (await api("/api/agents")) as Agent[];
    setAgents(rows);
    setSelectedId((cur) => cur || rows[0]?.agent_id || null);
  }, []);

  const loadHistory = useCallback(async (agentId: string) => {
    setChatError(null);
    try {
      const page = (await api(
        `/api/agents/${encodeURIComponent(agentId)}/history?limit=100`,
      )) as HistoryPage;
      setBubbles(bubblesFromEntries(page.entries || []));
    } catch (e) {
      setChatError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const account = (await api("/api/me")) as Account;
        if (cancelled) return;
        setMe(account);
        setBootError(null);
        try {
          await loadAgents();
        } catch (e) {
          if (!cancelled) setChatError(e instanceof Error ? e.message : String(e));
        }
      } catch (e) {
        if (!cancelled) setBootError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadAgents]);

  useEffect(() => {
    if (!selectedId) {
      setBubbles([]);
      return;
    }
    setBubbles([]);
    setChatError(null);
    void loadHistory(selectedId);
  }, [selectedId, loadHistory]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let ping: number | undefined;
    let closed = false;

    function connect() {
      ws = new WebSocket(wsUrl("/ws/events"));
      ws.onmessage = (ev) => {
        let data: GrokEvent;
        try {
          data = JSON.parse(String(ev.data)) as GrokEvent;
        } catch {
          return;
        }
        const current = selectedIdRef.current;
        if (data.type === "Hello") return;
        if (data.type === "AgentStateUpdate" && data.agent_id) {
          const id = data.agent_id;
          setRunning((prev) => patchSet(prev, id, Boolean(data.is_running)));
          setComposing((prev) => patchSet(prev, id, Boolean(data.is_composing)));
        }
        if (data.type === "RosterChanged") {
          void loadAgents().catch(() => undefined);
        }
        if (data.type === "StreamReset" && data.agent_id && data.agent_id === current) {
          void loadHistory(data.agent_id);
        }
        if (data.type === "TurnFailed" && data.agent_id === current) {
          setChatError(data.reason || data.code || "Turn failed");
        }
        if (data.type === "HandoffRequested" && data.agent_id) {
          const item: Handoff = {
            id: `${data.agent_id}-${data.request_id || Date.now()}`,
            agentId: data.agent_id,
            instruction: data.instruction || "",
            reason: data.reason || "",
          };
          setHandoffs((prev) => [...prev.filter((h) => h.id !== item.id).slice(-2), item]);
        }
        if (data.agent_id && data.agent_id === current) {
          setBubbles((prev) => applyEvent(prev, data));
        }
      };
      ws.onopen = () => {
        if (ping) window.clearInterval(ping);
        ping = window.setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
        }, 25000);
      };
      ws.onclose = () => {
        if (ping) window.clearInterval(ping);
        if (closed) return;
        timer = window.setTimeout(connect, 1500);
      };
    }
    connect();
    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      if (ping) window.clearInterval(ping);
      ws?.close();
    };
  }, [loadAgents, loadHistory]);

  return (
    <div className="app">
      <header className="top">
        <div>
          <strong>Grok Bot</strong>
          <span className="muted">{me?.email || ""}</span>
        </div>
        <div className="row">
          {selected && selected.harness !== "temporal" ? (
            <button type="button" onClick={() => setDesktopOpen(true)}>
              Desktop
            </button>
          ) : null}
          <button type="button" onClick={() => setSettingsOpen(true)}>
            Settings
          </button>
        </div>
      </header>
      {bootError ? (
        <div className="error pad">
          {bootError}{" "}
          <button type="button" onClick={() => setSettingsOpen(true)}>
            Open settings
          </button>
        </div>
      ) : null}
      <div className="shell">
        <Roster
          agents={agents}
          selectedId={selectedId}
          running={running}
          composing={composing}
          query={query}
          onQuery={setQuery}
          onSelect={(a) => setSelectedId(a.agent_id)}
        />
        <Chat
          agent={selected}
          bubbles={bubbles}
          composing={Boolean(selectedId && composing.has(selectedId))}
          running={Boolean(selectedId && running.has(selectedId))}
          error={chatError}
          onSent={() => undefined}
        />
        {desktopOpen ? <DesktopPane onClose={() => setDesktopOpen(false)} /> : null}
      </div>
      {settingsOpen ? (
        <Settings
          onClose={() => setSettingsOpen(false)}
          onCursorChanged={() => {
            void loadAgents().catch(() => undefined);
            void api("/api/me")
              .then((account) => setMe(account as Account))
              .catch((e) => setBootError(e instanceof Error ? e.message : String(e)));
          }}
        />
      ) : null}
      <HandoffToast
        items={handoffs}
        onOpen={(agentId) => {
          setSelectedId(agentId);
          setDesktopOpen(true);
          setHandoffs((prev) => prev.filter((h) => h.agentId !== agentId));
        }}
        onDismiss={(id) => setHandoffs((prev) => prev.filter((h) => h.id !== id))}
      />
    </div>
  );
}

function patchSet(prev: Set<string>, id: string, on: boolean): Set<string> {
  const next = new Set(prev);
  if (on) next.add(id);
  else next.delete(id);
  return next;
}
