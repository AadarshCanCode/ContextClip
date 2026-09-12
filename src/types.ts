export type DesktopConfig = {
  apiBase: string;
  wsUrl: string;
};

export type AppCard = {
  family: string;
  name: string;
  kind: string;
  connected: boolean;
  event_count: number;
  copies: number;
  pastes: number;
};

export type BackendAction = {
  id: string;
  name: string;
  description: string;
  requires: string[];
  mutates: boolean;
};

export type BackendActionResult = {
  action_id: string;
  success: boolean;
  message: string;
  data: Record<string, unknown>;
};

export type CaptureEvent = {
  id: string;
  seq: number;
  type: "copy" | "paste";
  timestamp_utc: string;
  source_app: {
    process_name: string;
    app_family: string;
    window_title: string;
  };
  clipboard: {
    payload_hash: string;
    payload_type: string;
    preview_text: string;
    byte_size: number;
  };
  screenshot_id: string | null;
  privacy_class: string;
  confidence: number;
  destination_app: CaptureEvent["source_app"] | null;
  plugin_context: Record<string, unknown> | null;
  workflow_id: string | null;
  parent_event_id: string | null;
  paste_mode: string | null;
  content_type: string;
  anchor: { x: number; y: number } | null;
  display: {
    title: string;
    source: string;
    preview: string;
    time: string;
  };
};

export type BubbleAction = {
  action_id: string;
  label: string;
  backend_action_id: string;
  description: string;
};

export type BubblePayload = {
  visible: boolean;
  phase: "captured" | "ready" | "error";
  anchor: { x: number; y: number } | null;
  title: string;
  subtitle: string;
  source: string;
  content_type: string;
  event_id: string;
  actions: BubbleAction[];
};

export type ContextAnalysis = {
  content_type: string;
  domain: string;
  summary: string;
  intent: string;
  entities: Array<{ name: string; type: string }>;
  source: string;
};

export type DesktopEvent =
  | { type: "copy"; event: CaptureEvent; bubble: BubblePayload }
  | { type: "paste"; event: CaptureEvent; bubble: { visible: false; reason: string } }
  | {
      type: "copy_analysis";
      event: CaptureEvent;
      context: ContextAnalysis | null;
      actions: BubbleAction[];
      bubble: BubblePayload;
      error?: string;
    }
  | { type: "action_result"; result: BackendActionResult }
  | { type: "context_block"; block: Record<string, unknown> };

export type SettingsStatus = {
  openrouter: {
    configured: boolean;
    model: string;
    analyzer_model: string;
    action_model: string;
  };
  exa: {
    configured: boolean;
    search_type: string;
    num_results: number;
  };
  capture: {
    data_dir: string;
    copy_settle_ms: number;
    clipboard_poll_ms: number;
    screenshot_mode: string;
    bubble_auto_hide_ms: number;
  };
};

declare global {
  interface Window {
    contextClip?: {
      getConfig: () => Promise<DesktopConfig>;
      showBubble: (payload: { anchor: { x: number; y: number } | null }) => void;
      hideBubble: () => void;
    };
  }
}
