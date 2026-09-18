export interface Handoff {
  id: string;
  agentId: string;
  instruction: string;
  reason: string;
}

export default function HandoffToast({
  items,
  onOpen,
  onDismiss,
}: {
  items: Handoff[];
  onOpen: (agentId: string) => void;
  onDismiss: (id: string) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="toasts">
      {items.map((t) => (
        <div key={t.id} className="toast">
          <strong>Take over desktop</strong>
          <p>{t.instruction || t.reason || "Grok Bot needs you on the cloud desktop."}</p>
          <div className="row">
            <button className="primary" type="button" onClick={() => onOpen(t.agentId)}>
              Open VNC
            </button>
            <button type="button" onClick={() => onDismiss(t.id)}>
              Dismiss
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
