import { useEffect, useState } from "react";
import { AUTH_EVENT, api, type SettingsPayload } from "../api";

export default function Settings({
  onClose,
  onCursorChanged,
}: {
  onClose: () => void;
  onCursorChanged: () => void;
}) {
  const [data, setData] = useState<SettingsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [password, setPassword] = useState("");
  const [current, setCurrent] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [accessToken, setAccessToken] = useState("");

  async function refresh() {
    const next = (await api("/api/settings")) as SettingsPayload;
    setData(next);
    return next;
  }

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await refresh();
        if (cancelled) return;
        setData(next);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (data?.login?.state !== "pending") return;
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const login = (await api("/api/settings/cursor/login")) as SettingsPayload["login"];
          setData((prev) => (prev ? { ...prev, login } : prev));
          if (login.state === "complete") {
            const next = await refresh();
            setData(next);
            onCursorChanged();
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
        }
      })();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [data?.login?.state, onCursorChanged]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const cursor = data?.cursor;
  const login = data?.login;

  return (
    <div className="settings-overlay">
      <div className="settings">
        <header className="settings-bar">
          <strong>Settings</strong>
          <button type="button" className="ml" onClick={onClose}>
            Close
          </button>
        </header>
        {error ? <div className="error pad">{error}</div> : null}
        {!data ? <div className="muted pad">Loading…</div> : null}

        <section className="settings-block">
          <h2>Cursor account</h2>
          <p className="muted">
            Sign-in happens on cursor.com. Access tokens stay on this server; the browser never
            stores them.
          </p>
          {cursor ? (
            <p>
              {cursor.signed_in
                ? `Signed in${cursor.account?.email ? ` as ${cursor.account.email}` : cursor.subject ? ` as ${cursor.subject}` : ""}${cursor.source ? ` (${cursor.source})` : ""}`
                : "Not signed in"}
              {cursor.expired ? " — token expired" : ""}
            </p>
          ) : null}
          {login?.state === "pending" && login.url ? (
            <p className="muted">
              Waiting for Cursor. If a tab did not open,{" "}
              <a href={login.url} target="_blank" rel="noreferrer">
                continue sign-in
              </a>
              .
            </p>
          ) : null}
          {login?.error ? <div className="error">{login.error}</div> : null}
          <div className="row">
            <button
              className="primary"
              type="button"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const started = (await api("/api/settings/cursor/login/start", {
                    method: "POST",
                  })) as { url?: string; state: string; error?: string | null };
                  setData((prev) =>
                    prev ? { ...prev, login: { state: started.state, url: started.url || null, error: started.error || null } } : prev,
                  );
                  if (started.url) window.open(started.url, "_blank", "noopener");
                })
              }
            >
              Sign in with Cursor
            </button>
            {login?.state === "pending" ? (
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await api("/api/settings/cursor/login/cancel", { method: "POST" });
                    await refresh();
                  })
                }
              >
                Cancel
              </button>
            ) : null}
            {cursor?.source === "instance" ? (
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await api("/api/settings/cursor/logout", { method: "POST" });
                    await refresh();
                    onCursorChanged();
                  })
                }
              >
                Forget instance login
              </button>
            ) : null}
          </div>
          <form
            className="col tight"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                await api("/api/settings/cursor/creds", {
                  method: "POST",
                  body: JSON.stringify({ api_key: apiKey }),
                });
                setApiKey("");
                await refresh();
                onCursorChanged();
              });
            }}
          >
            <label>
              Cursor API key
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="From cursor.com dashboard"
                autoComplete="off"
              />
            </label>
            <button className="primary" type="submit" disabled={busy || !apiKey.trim()}>
              Save API key
            </button>
          </form>
          <form
            className="col tight"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                await api("/api/settings/cursor/creds", {
                  method: "POST",
                  body: JSON.stringify({ access_token: accessToken }),
                });
                setAccessToken("");
                await refresh();
                onCursorChanged();
              });
            }}
          >
            <label>
              Access token
              <input
                type="password"
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                placeholder="Paste a Cursor JWT"
                autoComplete="off"
              />
            </label>
            <button className="primary" type="submit" disabled={busy || !accessToken.trim()}>
              Save token
            </button>
          </form>
        </section>

        <section className="settings-block">
          <h2>Instance password</h2>
          <p className="muted">
            When set, every API and WebSocket call requires a session cookie. Health and the login
            endpoints stay reachable.
          </p>
          {data ? (
            <p>
              {data.password_enabled
                ? "Password protection is on."
                : "Password protection is off."}
            </p>
          ) : null}
          <form
            className="col tight"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                await api("/api/settings/password", {
                  method: "POST",
                  body: JSON.stringify({
                    password,
                    current: current || null,
                  }),
                });
                setPassword("");
                setCurrent("");
                await refresh();
              });
            }}
          >
            {data?.password_enabled ? (
              <label>
                Current password
                <input
                  type="password"
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                  autoComplete="current-password"
                />
              </label>
            ) : null}
            <label>
              {data?.password_enabled ? "New password" : "Password"}
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                autoComplete="new-password"
              />
            </label>
            <div className="row">
              <button className="primary" type="submit" disabled={busy || password.length < 8}>
                {data?.password_enabled ? "Change password" : "Enable password"}
              </button>
              {data?.password_enabled ? (
                <button
                  type="button"
                  disabled={busy || !current}
                  onClick={() =>
                    void run(async () => {
                      await api("/api/settings/password/disable", {
                        method: "POST",
                        body: JSON.stringify({ current }),
                      });
                      setCurrent("");
                      setPassword("");
                      await refresh();
                    })
                  }
                >
                  Turn off
                </button>
              ) : null}
              {data?.password_enabled ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await api("/api/auth/logout", { method: "POST" });
                      window.dispatchEvent(new Event(AUTH_EVENT));
                    })
                  }
                >
                  Sign out of this instance
                </button>
              ) : null}
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
