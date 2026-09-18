import { useState } from "react";
import { api } from "../api";

export default function LocalLogin({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="gate">
      <form
        className="gate-card"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <h1>Grok Bot</h1>
        <p className="muted">This instance is password protected.</p>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Instance password"
          autoFocus
        />
        {error ? <div className="error">{error}</div> : null}
        <button className="primary" type="submit" disabled={busy || !password}>
          Sign in
        </button>
      </form>
    </div>
  );
}
