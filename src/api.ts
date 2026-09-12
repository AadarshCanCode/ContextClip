import type {
  AppCard,
  BackendAction,
  BackendActionResult,
  CaptureEvent,
  DesktopConfig,
  SettingsStatus,
} from "./types";

const fallbackConfig: DesktopConfig = {
  apiBase: "http://127.0.0.1:8765",
  wsUrl: "ws://127.0.0.1:8765/events",
};

let configPromise: Promise<DesktopConfig> | null = null;

export function getDesktopConfig(): Promise<DesktopConfig> {
  if (!configPromise) {
    configPromise = window.contextClip?.getConfig?.() ?? Promise.resolve(fallbackConfig);
  }
  return configPromise;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const config = await getDesktopConfig();
  const response = await fetch(`${config.apiBase}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function loadDashboardData() {
  const [health, events, stats, apps, actions, settings] = await Promise.all([
    requestJson<Record<string, unknown>>("/health"),
    requestJson<{ events: CaptureEvent[] }>("/events/recent?limit=40"),
    requestJson<Record<string, number>>("/stats"),
    requestJson<{ apps: AppCard[] }>("/apps"),
    requestJson<{ actions: BackendAction[] }>("/actions"),
    requestJson<SettingsStatus>("/settings/status"),
  ]);
  return { health, events: events.events, stats, apps: apps.apps, actions: actions.actions, settings };
}

export function runBackendAction(actionId: string, args: Record<string, unknown> = {}) {
  return requestJson<BackendActionResult>("/actions/run", {
    method: "POST",
    body: JSON.stringify({ action_id: actionId, args }),
  });
}
