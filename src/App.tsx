import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bot,
  CalendarPlus,
  CheckCircle2,
  ClipboardList,
  Code2,
  Compass,
  FileText,
  Home,
  Loader2,
  MessageSquareText,
  MonitorDot,
  PanelLeft,
  Play,
  Search,
  Settings,
  Sparkles,
  Terminal,
  UploadCloud,
} from "lucide-react";
import { getDesktopConfig, loadDashboardData, runBackendAction } from "./api";
import type { AppCard, BackendAction, BackendActionResult, CaptureEvent, DesktopEvent, SettingsStatus } from "./types";

type ViewId = "home" | "history" | "apps" | "actions" | "settings";

const navItems: Array<{ id: ViewId; label: string; icon: typeof Home }> = [
  { id: "home", label: "Home", icon: Home },
  { id: "history", label: "Context History", icon: ClipboardList },
  { id: "apps", label: "Connected Apps", icon: MonitorDot },
  { id: "actions", label: "AI Actions", icon: Sparkles },
  { id: "settings", label: "Settings", icon: Settings },
];

const appIcons: Record<string, typeof Home> = {
  outlook: MessageSquareText,
  teams: MessageSquareText,
  word: FileText,
  powerpoint: UploadCloud,
  excel: ClipboardList,
  browser_chrome: Compass,
  browser_edge: Compass,
  vs_code: Code2,
  terminal: Terminal,
};

const quickActions = ["ai.summarize_clipboard", "ai.explain_clipboard", "references.search_clipboard", "context.copy_markdown"];

export function App() {
  const [view, setView] = useState<ViewId>("home");
  const [query, setQuery] = useState("");
  const [events, setEvents] = useState<CaptureEvent[]>([]);
  const [apps, setApps] = useState<AppCard[]>([]);
  const [actions, setActions] = useState<BackendAction[]>([]);
  const [settings, setSettings] = useState<SettingsStatus | null>(null);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [health, setHealth] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastResult, setLastResult] = useState<BackendActionResult | null>(null);
  const [busyAction, setBusyAction] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await loadDashboardData();
        if (cancelled) return;
        setHealth(data.health);
        setEvents(data.events);
        setStats(data.stats);
        setApps(data.apps);
        setActions(data.actions);
        setSettings(data.settings);
        setError("");
      } catch (exc) {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    const timer = window.setInterval(load, 12000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let alive = true;
    getDesktopConfig().then((config) => {
      if (!alive) return;
      socket = new WebSocket(config.wsUrl);
      socket.onmessage = (message) => {
        const payload = JSON.parse(message.data) as DesktopEvent;
        if ("event" in payload && (payload.type === "copy" || payload.type === "paste")) {
          setEvents((current) => [...current.filter((item) => item.id !== payload.event.id), payload.event].slice(-40));
        }
        if (payload.type === "action_result") {
          setLastResult(payload.result);
        }
      };
    });
    return () => {
      alive = false;
      socket?.close();
    };
  }, []);

  const filteredEvents = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [...events].reverse();
    return [...events]
      .reverse()
      .filter((event) => `${event.display.title} ${event.display.preview} ${event.display.source}`.toLowerCase().includes(needle));
  }, [events, query]);

  const actionMap = useMemo(() => new Map(actions.map((action) => [action.id, action])), [actions]);
  const preferredActions = quickActions.map((id) => actionMap.get(id)).filter(Boolean) as BackendAction[];

  async function execute(actionId: string) {
    setBusyAction(actionId);
    try {
      setLastResult(await runBackendAction(actionId));
    } catch (exc) {
      setLastResult({
        action_id: actionId,
        success: false,
        message: exc instanceof Error ? exc.message : String(exc),
        data: {},
      });
    } finally {
      setBusyAction("");
    }
  }

  return (
    <main className="desktop-stage">
      <div className="ambient-grid" />
      <section className="shell">
        <aside className="sidebar">
          <div className="brand-lockup">
            <div className="brand-mark"><ClipboardList size={23} /></div>
            <span>ContextClip</span>
          </div>
          <nav className="nav-list" aria-label="Primary navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  className={view === item.id ? "nav-item active" : "nav-item"}
                  onClick={() => setView(item.id)}
                  aria-label={item.label}
                >
                  <Icon size={20} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
          <div className="companion-tile">
            <Sparkles size={18} />
            <strong>Always with you</strong>
            <span>{health.agent_running ? "Listening for copy context." : "Desktop API ready."}</span>
          </div>
        </aside>

        <section className="workspace">
          <header className="topbar">
            <label className="searchbox">
              <Search size={18} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search your clips, ask anything..." />
            </label>
            <div className="profile-pill">CC</div>
          </header>

          {loading && <StatusPanel icon={Loader2} title="Starting ContextClip" text="Connecting to the local desktop agent..." spin />}
          {error && <StatusPanel icon={Activity} title="Backend unavailable" text={error} />}
          {!loading && !error && (
            <>
              {view === "home" && (
                <HomeView
                  apps={apps}
                  events={filteredEvents}
                  stats={stats}
                  actions={preferredActions}
                  busyAction={busyAction}
                  lastResult={lastResult}
                  onRunAction={execute}
                />
              )}
              {view === "history" && <HistoryView events={filteredEvents} />}
              {view === "apps" && <AppsView apps={apps} />}
              {view === "actions" && <ActionsView actions={actions} busyAction={busyAction} onRunAction={execute} lastResult={lastResult} />}
              {view === "settings" && settings && <SettingsView settings={settings} />}
            </>
          )}
        </section>
      </section>
    </main>
  );
}

function HomeView({
  apps,
  events,
  stats,
  actions,
  busyAction,
  lastResult,
  onRunAction,
}: {
  apps: AppCard[];
  events: CaptureEvent[];
  stats: Record<string, number>;
  actions: BackendAction[];
  busyAction: string;
  lastResult: BackendActionResult | null;
  onRunAction: (actionId: string) => void;
}) {
  return (
    <div className="dashboard-grid">
      <section className="hero-strip">
        <span className="eyebrow">Clipboard working smarter today</span>
        <h1>Good morning</h1>
        <div className="stat-row">
          <Metric label="Copies" value={stats.copies_today ?? 0} />
          <Metric label="Pastes" value={stats.pastes_today ?? 0} />
          <Metric label="Total events" value={stats.total_events ?? 0} />
        </div>
      </section>

      <section className="app-grid" aria-label="Connected applications">
        {apps.slice(0, 6).map((app) => <AppTile key={app.family} app={app} />)}
      </section>

      <section className="recent-panel">
        <div className="section-heading">
          <h2>Recent Context</h2>
          <span>{events.length} shown</span>
        </div>
        <EventList events={events.slice(0, 7)} />
      </section>

      <aside className="right-rail">
        <div className="notification-stack">
          {events.slice(0, 3).map((event) => <ToastRow key={event.id} event={event} />)}
          {events.length === 0 && <span className="empty-note">No live clips captured yet.</span>}
        </div>
        <div className="action-dock">
          <div className="section-heading">
            <h2>AI Actions</h2>
            <Sparkles size={17} />
          </div>
          {actions.map((action) => (
            <button key={action.id} className="action-row" onClick={() => onRunAction(action.id)} disabled={busyAction === action.id}>
              {busyAction === action.id ? <Loader2 size={17} className="spin" /> : <Play size={17} />}
              <span>{action.name}</span>
            </button>
          ))}
          {lastResult && <ResultStrip result={lastResult} />}
        </div>
      </aside>
    </div>
  );
}

function HistoryView({ events }: { events: CaptureEvent[] }) {
  return (
    <section className="wide-panel">
      <div className="section-heading"><h1>Context History</h1><span>{events.length} events</span></div>
      <EventList events={events} />
    </section>
  );
}

function AppsView({ apps }: { apps: AppCard[] }) {
  return (
    <section className="wide-panel">
      <div className="section-heading"><h1>Connected Apps</h1><span>{apps.filter((app) => app.connected).length} ready</span></div>
      <div className="app-grid expanded">{apps.map((app) => <AppTile key={app.family} app={app} />)}</div>
    </section>
  );
}

function ActionsView({
  actions,
  busyAction,
  onRunAction,
  lastResult,
}: {
  actions: BackendAction[];
  busyAction: string;
  onRunAction: (actionId: string) => void;
  lastResult: BackendActionResult | null;
}) {
  return (
    <section className="wide-panel">
      <div className="section-heading"><h1>AI Actions</h1><span>{actions.length} available</span></div>
      <div className="action-catalog">
        {actions.map((action) => (
          <button key={action.id} className="catalog-action" onClick={() => onRunAction(action.id)} disabled={busyAction === action.id}>
            <Sparkles size={19} />
            <strong>{action.name}</strong>
            <span>{action.description}</span>
          </button>
        ))}
      </div>
      {lastResult && <ResultStrip result={lastResult} />}
    </section>
  );
}

function SettingsView({ settings }: { settings: SettingsStatus }) {
  return (
    <section className="wide-panel">
      <div className="section-heading"><h1>Settings</h1><span>Local runtime</span></div>
      <div className="settings-grid">
        <SettingTile title="OpenRouter" status={settings.openrouter.configured} rows={[
          ["Model", settings.openrouter.model || "not set"],
          ["Analyzer", settings.openrouter.analyzer_model || "not set"],
          ["Actions", settings.openrouter.action_model || "not set"],
        ]} />
        <SettingTile title="Exa" status={settings.exa.configured} rows={[
          ["Search type", settings.exa.search_type],
          ["Results", String(settings.exa.num_results)],
        ]} />
        <SettingTile title="Capture" status rows={[
          ["Poll", `${settings.capture.clipboard_poll_ms} ms`],
          ["Settle", `${settings.capture.copy_settle_ms} ms`],
          ["Screenshots", settings.capture.screenshot_mode],
          ["Bubble hide", `${settings.capture.bubble_auto_hide_ms} ms`],
        ]} />
      </div>
    </section>
  );
}

function EventList({ events }: { events: CaptureEvent[] }) {
  if (events.length === 0) {
    return <div className="empty-state"><ClipboardList size={28} /><span>No captured context yet.</span></div>;
  }
  return (
    <div className="event-list">
      {events.map((event) => (
        <article key={event.id} className="event-row">
          <EventIcon source={event.display.source} />
          <div>
            <strong>{event.display.title}</strong>
            <span>{event.display.preview}</span>
          </div>
          <time>{event.display.time || `#${event.seq}`}</time>
        </article>
      ))}
    </div>
  );
}

function AppTile({ app }: { app: AppCard }) {
  const Icon = appIcons[app.family] ?? MonitorDot;
  return (
    <article className="app-tile">
      <Icon size={27} />
      <strong>{app.name}</strong>
      <span><CheckCircle2 size={12} /> {app.connected ? "Connected" : "Unavailable"}</span>
      <small>{app.event_count} events</small>
    </article>
  );
}

function ToastRow({ event }: { event: CaptureEvent }) {
  return (
    <article className="toast-row">
      <EventIcon source={event.display.source} />
      <div>
        <strong>{event.display.title}</strong>
        <span>From {formatSource(event.display.source)}</span>
      </div>
      <time>{event.display.time || "now"}</time>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

function StatusPanel({ icon: Icon, title, text, spin = false }: { icon: typeof Loader2; title: string; text: string; spin?: boolean }) {
  return (
    <div className="status-panel">
      <Icon className={spin ? "spin" : ""} />
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

function ResultStrip({ result }: { result: BackendActionResult }) {
  return (
    <div className={result.success ? "result-strip success" : "result-strip"}>
      <strong>{result.success ? "Done" : "Needs attention"}</strong>
      <span>{result.message}</span>
    </div>
  );
}

function SettingTile({ title, status, rows }: { title: string; status: boolean; rows: Array<[string, string]> }) {
  return (
    <article className="setting-tile">
      <div className="setting-head"><strong>{title}</strong><span>{status ? "Configured" : "Missing"}</span></div>
      {rows.map(([label, value]) => <p key={label}><span>{label}</span><strong>{value}</strong></p>)}
    </article>
  );
}

function EventIcon({ source }: { source: string }) {
  const Icon = appIcons[source] ?? appIcons[source.toLowerCase()] ?? ClipboardList;
  return <div className="event-icon"><Icon size={20} /></div>;
}

function formatSource(source: string) {
  return source.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
