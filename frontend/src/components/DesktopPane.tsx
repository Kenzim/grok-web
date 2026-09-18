import { useEffect, useRef, useState } from "react";
import { api, wsUrl } from "../api";

type RfbHandle = { disconnect: () => void };

export default function DesktopPane({
  onClose,
}: {
  onClose: () => void;
}) {
  const screenRef = useRef<HTMLDivElement | null>(null);
  const rfbRef = useRef<RfbHandle | null>(null);
  const [runState, setRunState] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [needWake, setNeedWake] = useState(false);

  function disconnect() {
    const rfb = rfbRef.current;
    rfbRef.current = null;
    if (rfb) {
      try {
        rfb.disconnect();
      } catch {
        /* ignore */
      }
    }
  }

  async function connect(wake: boolean, cancelled?: () => boolean) {
    setBusy(true);
    setError(null);
    setNeedWake(false);
    try {
      const info = (await api("/api/desktop", {
        method: "POST",
        body: JSON.stringify({ wake }),
      })) as { token?: string; run_state?: string; has_vnc?: boolean };
      if (cancelled?.()) return;
      setRunState(info.run_state || "");
      const hibernated = ["HIBERNATED", "ABSENT"].includes((info.run_state || "").toUpperCase());
      if (!wake && hibernated) {
        setNeedWake(true);
        return;
      }
      if (!info.token) throw new Error("No VNC endpoint (temporal agents have no desktop)");
      if (!screenRef.current) return;
      disconnect();
      const mod = await import("@novnc/novnc");
      if (cancelled?.()) return;
      const RFB = mod.default;
      const url = wsUrl(`/ws/vnc?token=${encodeURIComponent(info.token)}`);
      const rfb = new RFB(screenRef.current, url);
      rfb.scaleViewport = true;
      rfb.resizeSession = true;
      rfbRef.current = rfb;
    } catch (e) {
      if (cancelled?.()) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!cancelled?.()) setBusy(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    void connect(false, () => cancelled);
    return () => {
      cancelled = true;
      disconnect();
    };
    // connect once when the pane mounts
  }, []);

  return (
    <div className="desktop">
      <header className="desktop-bar">
        <strong>Cloud desktop</strong>
        <span className="muted">{runState}</span>
        {busy ? <span className="muted">connecting…</span> : null}
        <button className="ml" type="button" onClick={onClose}>
          Close
        </button>
      </header>
      {needWake ? (
        <div className="banner">
          Sandbox is {runState || "hibernated"}. Waking it uses cloud quota.
          <div className="row">
            <button className="primary" type="button" onClick={() => void connect(true)}>
              Wake sandbox
            </button>
          </div>
        </div>
      ) : null}
      {error ? <div className="error pad">{error}</div> : null}
      <div className="vnc" ref={screenRef} />
    </div>
  );
}
