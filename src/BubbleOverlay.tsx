import { useEffect, useRef, useState } from "react";
import {
  CheckSquare,
  ClipboardList,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquareText,
  Pin,
  Search,
  Send,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import { getDesktopConfig, runBackendAction } from "./api";
import type { BackendActionResult, BubblePayload, DesktopEvent } from "./types";

const iconByAction: Record<string, typeof Sparkles> = {
  summarize: FileText,
  explain: Sparkles,
  help_fix: Wrench,
  search_references: Search,
  draft_reply: MessageSquareText,
  extract_information: CheckSquare,
  open: ExternalLink,
  copy_context: ClipboardList,
};

export function BubbleOverlay() {
  const [bubble, setBubble] = useState<BubblePayload | null>(null);
  const [result, setResult] = useState<BackendActionResult | null>(null);
  const [busyAction, setBusyAction] = useState("");
  const hideTimer = useRef<number | null>(null);

  function scheduleHide() {
    if (hideTimer.current) window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => {
      setBubble(null);
      setResult(null);
      window.contextClip?.hideBubble();
    }, 12000);
  }

  function hide() {
    if (hideTimer.current) window.clearTimeout(hideTimer.current);
    setBubble(null);
    setResult(null);
    window.contextClip?.hideBubble();
  }

  useEffect(() => {
    let socket: WebSocket | null = null;
    let alive = true;
    getDesktopConfig().then((config) => {
      if (!alive) return;
      socket = new WebSocket(config.wsUrl);
      socket.onmessage = (message) => {
        const payload = JSON.parse(message.data) as DesktopEvent;
        if ((payload.type === "copy" || payload.type === "copy_analysis") && payload.bubble.visible) {
          setBubble(payload.bubble);
          setResult(null);
          window.contextClip?.showBubble({ anchor: payload.bubble.anchor });
          scheduleHide();
        }
        if (payload.type === "paste") {
          hide();
        }
        if (payload.type === "action_result") {
          setResult(payload.result);
          scheduleHide();
        }
      };
    });

    function onKeydown(event: KeyboardEvent) {
      if (event.key === "Escape") hide();
    }
    window.addEventListener("keydown", onKeydown);
    return () => {
      alive = false;
      socket?.close();
      window.removeEventListener("keydown", onKeydown);
      if (hideTimer.current) window.clearTimeout(hideTimer.current);
    };
  }, []);

  async function execute(actionId: string) {
    setBusyAction(actionId);
    try {
      setResult(await runBackendAction(actionId));
    } catch (exc) {
      setResult({
        action_id: actionId,
        success: false,
        message: exc instanceof Error ? exc.message : String(exc),
        data: {},
      });
    } finally {
      setBusyAction("");
    }
  }

  if (!bubble) {
    return <div className="bubble-root empty" />;
  }

  return (
    <div className="bubble-root">
      <section className="context-bubble" role="dialog" aria-label="ContextClip action bubble">
        <header className="bubble-header">
          <div className="bubble-brand">
            <div className="brand-mark"><ClipboardList size={23} /></div>
            <div>
              <strong>ContextClip</strong>
              <span>{bubble.phase === "ready" ? bubble.content_type : "Analyzing copy"}</span>
            </div>
          </div>
          <div className="bubble-controls">
            <button aria-label="Pin bubble"><Pin size={18} /></button>
            <button aria-label="Close bubble" onClick={hide}><X size={20} /></button>
          </div>
        </header>

        <article className="copied-card">
          <div className="copied-icon"><ClipboardList size={28} /></div>
          <div>
            <p>{bubble.subtitle}</p>
            <span>From {formatSource(bubble.source)}</span>
          </div>
          <time>Just now</time>
        </article>

        <div className="bubble-actions">
          {bubble.phase === "captured" && (
            <button className="bubble-action primary" disabled>
              <Loader2 size={24} className="spin" />
              <span>Reading context</span>
            </button>
          )}
          {bubble.actions.map((action, index) => {
            const Icon = iconByAction[action.action_id] ?? Sparkles;
            return (
              <button
                key={action.action_id}
                className={index === 0 ? "bubble-action primary" : "bubble-action"}
                onClick={() => execute(action.backend_action_id)}
                disabled={Boolean(busyAction)}
              >
                {busyAction === action.backend_action_id ? <Loader2 size={24} className="spin" /> : <Icon size={24} />}
                <span>{action.label}</span>
              </button>
            );
          })}
        </div>

        <footer className="bubble-prompt">
          <Sparkles size={19} />
          <span>{result ? result.message : "Ask anything about this..."}</span>
          <button aria-label="Run contextual ask" disabled><Send size={18} /></button>
        </footer>
      </section>
    </div>
  );
}

function formatSource(source: string) {
  return source.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
