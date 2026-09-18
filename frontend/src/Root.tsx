import { useCallback, useEffect, useState } from "react";
import { AUTH_EVENT, api, type AuthStatus } from "./api";
import App from "./App";
import LocalLogin from "./components/LocalLogin";

export default function Root() {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const next = (await api("/api/auth/status")) as AuthStatus;
    setStatus(next);
    setError(null);
  }, []);

  useEffect(() => {
    void load().catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [load]);

  useEffect(() => {
    function onAuth() {
      void load().catch(() => undefined);
    }
    window.addEventListener(AUTH_EVENT, onAuth);
    return () => window.removeEventListener(AUTH_EVENT, onAuth);
  }, [load]);

  if (error) return <div className="error pad">{error}</div>;
  if (!status) return <div className="muted pad">Loading…</div>;
  if (status.needs_login) return <LocalLogin onDone={() => void load()} />;
  return <App />;
}
