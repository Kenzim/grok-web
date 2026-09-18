import { useMemo, useState } from "react";
import type { WidgetPayload } from "../api";
import { api } from "../api";

function kindOf(widget: WidgetPayload): string {
  return (widget.kind || "").toLowerCase();
}

function isApproval(kind: string): boolean {
  return (
    kind.includes("approval") ||
    kind.includes("permission") ||
    kind.includes("virtual_card") ||
    kind.includes("card")
  );
}

function isSecret(kind: string): boolean {
  return kind.includes("secret") || kind.includes("credential") || kind.includes("password");
}

function isForm(kind: string): boolean {
  return kind.includes("form");
}

function optionLabel(v: unknown): string {
  if (typeof v === "string") return v;
  if (!v || typeof v !== "object") return "";
  const o = v as Record<string, unknown>;
  const label = o.label || o.value || o.text || o.title || o.content;
  return typeof label === "string" ? label : "";
}

function collectOptions(v: unknown, into: string[], depth = 0): void {
  if (depth > 4 || v == null) return;
  if (Array.isArray(v)) {
    for (const item of v) {
      const label = optionLabel(item);
      if (label) into.push(label);
      else collectOptions(item, into, depth + 1);
    }
    return;
  }
  if (typeof v !== "object") return;
  const o = v as Record<string, unknown>;
  collectOptions(o.options, into, depth + 1);
  collectOptions(o.choices, into, depth + 1);
  collectOptions(o.items, into, depth + 1);
  collectOptions(o.fields, into, depth + 1);
  collectOptions(o.widget, into, depth + 1);
  collectOptions(o.message, into, depth + 1);
}

function formFields(body: unknown): { name: string; label: string }[] {
  if (!body || typeof body !== "object") return [];
  const o = body as Record<string, unknown>;
  const raw = o.fields || o.items;
  if (!Array.isArray(raw)) return [];
  const out: { name: string; label: string }[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const name = String(row.name || row.id || row.key || "");
    const label = String(row.label || row.title || name);
    if (name) out.push({ name, label });
  }
  return out;
}

export default function WidgetCard({
  widget,
  onDone,
}: {
  widget: WidgetPayload;
  onDone?: () => void;
}) {
  const kind = kindOf(widget);
  const options = useMemo(() => {
    const into: string[] = [];
    collectOptions(widget.body, into);
    return [...new Set(into)];
  }, [widget.body]);
  const fields = useMemo(() => formFields(widget.body), [widget.body]);
  const [value, setValue] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function post(path: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    setError(null);
    try {
      await api(path, {
        method: "POST",
        body: JSON.stringify({
          agent_id: widget.agent_id,
          session_id: widget.session_id,
          entry_id: widget.entry_id,
          kind: widget.kind,
          request_id: widget.request_id,
          prompt: widget.prompt,
          ...extra,
        }),
      });
      onDone?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="widget">
      <div className="widget-kind">{widget.kind || "widget"}</div>
      {widget.prompt ? <p className="widget-prompt">{widget.prompt}</p> : null}
      {isApproval(kind) ? (
        <div className="row">
          <button disabled={busy} className="primary" onClick={() => void post("/api/widgets/resolve-approval", { approved: true })}>
            Approve
          </button>
          <button disabled={busy} onClick={() => void post("/api/widgets/resolve-approval", { approved: false })}>
            Deny
          </button>
        </div>
      ) : isSecret(kind) ? (
        <form
          className="col"
          onSubmit={(e) => {
            e.preventDefault();
            void post("/api/widgets/submit-secret", { value });
          }}
        >
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Secret"
            autoComplete="off"
          />
          <div className="row">
            <button className="primary" disabled={busy || !value} type="submit">
              Submit
            </button>
            <button type="button" disabled={busy} onClick={() => void post("/api/widgets/dismiss")}>
              Dismiss
            </button>
          </div>
        </form>
      ) : isForm(kind) && fields.length ? (
        <form
          className="col"
          onSubmit={(e) => {
            e.preventDefault();
            void post("/api/widgets/submit-form", { values });
          }}
        >
          {fields.map((f) => (
            <label key={f.name} className="col">
              <span>{f.label}</span>
              <input
                value={values[f.name] || ""}
                onChange={(e) => setValues((prev) => ({ ...prev, [f.name]: e.target.value }))}
              />
            </label>
          ))}
          <div className="row">
            <button className="primary" disabled={busy} type="submit">
              Submit
            </button>
            <button type="button" disabled={busy} onClick={() => void post("/api/widgets/dismiss")}>
              Dismiss
            </button>
          </div>
        </form>
      ) : options.length ? (
        <div className="col">
          {options.map((opt) => (
            <button key={opt} disabled={busy} onClick={() => void post("/api/widgets/respond", { value: opt })}>
              {opt}
            </button>
          ))}
          <button disabled={busy} onClick={() => void post("/api/widgets/dismiss")}>
            Dismiss
          </button>
        </div>
      ) : (
        <form
          className="col"
          onSubmit={(e) => {
            e.preventDefault();
            void post("/api/widgets/respond", { value });
          }}
        >
          <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="Response" />
          <div className="row">
            <button className="primary" disabled={busy || !value} type="submit">
              Respond
            </button>
            <button type="button" disabled={busy} onClick={() => void post("/api/widgets/dismiss")}>
              Dismiss
            </button>
          </div>
        </form>
      )}
      {error ? <div className="error">{error}</div> : null}
    </div>
  );
}
