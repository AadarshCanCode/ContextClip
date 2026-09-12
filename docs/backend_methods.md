# ContextClip Backend Method Reference

This reference tracks the active desktop backend and native bubble only. Removed dashboards, tray code, and web frontend modules are intentionally excluded.

## Entry Point

| Method | Reference | Purpose |
| --- | --- | --- |
| `configure_console_io` | `main.py` | Prefers UTF-8 CLI output on Windows consoles. |
| `run_agent_only` | `main.py` | Starts the headless clipboard agent service. |
| `run_desktop_bubble` | `main.py` | Starts the native desktop bubble agent. |
| `dump_context` | `main.py` | Prints the current LLM context JSON. |
| `search_clipboard` | `main.py` | Runs Exa reference search for current clipboard text. |
| `list_actions` | `main.py` | Lists concrete backend actions available in this build. |
| `run_action` | `main.py` | Executes one concrete backend action by id. |
| `main` | `main.py` | Loads `.env`, parses CLI arguments, and dispatches backend commands. |

## Configuration

| Method | Reference | Purpose |
| --- | --- | --- |
| `load_env_file` | `core/config.py` | Loads project `.env` values into `os.environ` without overriding shell values. |
| `get_str` | `core/config.py` | Reads a string environment value. |
| `get_int` | `core/config.py` | Reads an integer environment value with a fallback. |
| `_parse_env_line` | `core/config.py` | Parses one `.env` line. |
| `_strip_inline_comment` | `core/config.py` | Removes unquoted inline comments from `.env` values. |

## Backend Actions

| Method | Reference | Purpose |
| --- | --- | --- |
| `BackendActionDescriptor.to_dict` | `core/actions.py` | Serializes an advertised backend action. |
| `BackendActionResult.to_dict` | `core/actions.py` | Serializes an action execution result. |
| `BackendActionBroker.__init__` | `core/actions.py` | Wires action ids to real agent-backed handlers. |
| `BackendActionBroker.discover` | `core/actions.py` | Returns available concrete backend actions. |
| `BackendActionBroker.execute` | `core/actions.py` | Executes a concrete backend action by id. |
| `BackendActionBroker._storage_stats` | `core/actions.py` | Reads event and app-family storage stats. |
| `BackendActionBroker._dump_llm_context` | `core/actions.py` | Dumps the active LLM context payload. |
| `BackendActionBroker._export_markdown` | `core/actions.py` | Renders the active event window as Markdown. |
| `BackendActionBroker._copy_markdown` | `core/actions.py` | Copies active context Markdown to the OS clipboard. |
| `BackendActionBroker._graph_summary` | `core/actions.py` | Reads graph edges and a text graph summary. |
| `BackendActionBroker._search_clipboard_references` | `core/actions.py` | Runs Exa clipboard reference search when configured. |
| `BackendActionBroker._ai_explain_clipboard` | `core/actions.py` | Runs the OpenRouter explain action for clipboard text. |
| `BackendActionBroker._ai_summarize_clipboard` | `core/actions.py` | Runs the OpenRouter summarize action for clipboard text. |
| `BackendActionBroker._ai_help_fix_clipboard` | `core/actions.py` | Runs the OpenRouter troubleshoot/fix action for clipboard text. |
| `BackendActionBroker._ai_extract_information` | `core/actions.py` | Runs the OpenRouter information extraction action. |
| `BackendActionBroker._ai_draft_reply` | `core/actions.py` | Runs the OpenRouter draft-reply action. |
| `BackendActionBroker._ai_adapt_code` | `core/actions.py` | Runs the OpenRouter adapt-code action. |
| `BackendActionBroker._run_ai_clipboard_action` | `core/actions.py` | Shared OpenRouter action handler. |
| `BackendActionBroker._open_clipboard_url` | `core/actions.py` | Opens a copied URL through the OS default browser. |
| `BackendActionBroker._record_clipboard_copy` | `core/actions.py` | Manually records the current clipboard as a copy event. |
| `BackendActionBroker._record_clipboard_paste` | `core/actions.py` | Manually records the current clipboard as a paste event. |
| `_optional_list` | `core/actions.py` | Normalizes optional CLI list values. |
| `_event_action_result` | `core/actions.py` | Builds a common result for capture actions. |

## Bubble Action Routing

| Method | Reference | Purpose |
| --- | --- | --- |
| `get_bubble_action_ids` | `core/action_router.py` | Selects deterministic semantic bubble action ids from classified context. |
| `get_bubble_actions` | `core/action_router.py` | Returns full bubble action definitions with backend action ids. |

## Context Analysis

| Method | Reference | Purpose |
| --- | --- | --- |
| `Entity.to_dict` | `core/context_engine.py` | Serializes one extracted semantic entity. |
| `ContextResult.to_dict` | `core/context_engine.py` | Serializes one clipboard context classification. |
| `analyze_event_locally` | `core/context_engine.py` | Builds a local context result from a captured event. |
| `analyze_clipboard_locally` | `core/context_engine.py` | Classifies clipboard text with deterministic local heuristics. |
| `context_result_from_dict` | `core/context_engine.py` | Normalizes OpenRouter JSON into a `ContextResult`. |
| `_canonical_content_type` | `core/context_engine.py` | Maps backend content types to bubble routing types. |
| `_infer_intent` | `core/context_engine.py` | Infers the likely user intent from text and window context. |
| `_infer_domain` | `core/context_engine.py` | Infers the broad work domain. |
| `_make_summary` | `core/context_engine.py` | Creates a concise bubble-ready summary. |
| `_extract_entities` | `core/context_engine.py` | Extracts local URLs, errors, dates, and file names. |

## Agent Service

| Method | Reference | Purpose |
| --- | --- | --- |
| `_new_event_id` | `apps/agent.py` | Creates event IDs. |
| `_utc_now` | `apps/agent.py` | Creates UTC timestamps. |
| `_merge_capture_position` | `apps/agent.py` | Merges cursor/caret coordinates into event capture metadata. |
| `ContextClipAgent.__init__` | `apps/agent.py` | Wires storage, graph, memory, capture, privacy, and plugins. |
| `ContextClipAgent.start` | `apps/agent.py` | Starts the global clipboard listener loop. |
| `ContextClipAgent.start_background` | `apps/agent.py` | Starts the listener without taking over the main thread. |
| `ContextClipAgent.stop` | `apps/agent.py` | Stops the clipboard listener loop. |
| `ContextClipAgent._start_clipboard_polling` | `apps/agent.py` | Starts clipboard-change polling as a fallback capture path. |
| `ContextClipAgent._poll_clipboard_loop` | `apps/agent.py` | Detects changed clipboard payloads and records them as copy events. |
| `ContextClipAgent._hash_seen_clipboard` | `apps/agent.py` | Hashes normalized clipboard text for polling and suppression. |
| `ContextClipAgent.suppress_clipboard_text` | `apps/agent.py` | Suppresses app-written clipboard text so the bubble does not reopen itself. |
| `ContextClipAgent._handle_copy` | `apps/agent.py` | Captures a copy event, screenshot, plugin context, graph state, and rolling memory. |
| `ContextClipAgent._handle_paste` | `apps/agent.py` | Captures a paste event, destination screenshot, source correlation, plugin context, and graph edge. |
| `ContextClipAgent._on_context_window_ready` | `apps/agent.py` | Handles completed seven-event windows and workflow rotation. |
| `ContextClipAgent.get_active_events` | `apps/agent.py` | Returns recent active context events. |
| `ContextClipAgent.get_context_blocks` | `apps/agent.py` | Returns recent compressed context blocks. |
| `ContextClipAgent.get_stats` | `apps/agent.py` | Returns event statistics. |
| `ContextClipAgent.get_app_families` | `apps/agent.py` | Returns app usage summaries. |
| `ContextClipAgent.get_all_edges` | `apps/agent.py` | Returns graph edges. |
| `ContextClipAgent.get_screenshot_path` | `apps/agent.py` | Resolves a screenshot ID to its local path. |
| `ContextClipAgent.export_active_context_markdown` | `apps/agent.py` | Renders active events as Markdown. |
| `ContextClipAgent.copy_active_context_markdown` | `apps/agent.py` | Copies active Markdown context to the OS clipboard. |
| `ContextClipAgent.summarize_graph` | `apps/agent.py` | Returns a compact reference graph summary. |
| `ContextClipAgent.record_current_clipboard_copy` | `apps/agent.py` | Manually records current clipboard text as a copy event. |
| `ContextClipAgent.record_current_clipboard_paste` | `apps/agent.py` | Manually records current clipboard text as a paste event. |
| `ContextClipAgent.dump_llm_context` | `apps/agent.py` | Builds the active TOON/events/stats payload. |
| `ContextClipAgent.search_clipboard_references` | `apps/agent.py` | Searches current clipboard references through Exa. |
| `ContextClipAgent._new_workflow_id` | `apps/agent.py` | Creates workflow IDs. |
| `ContextClipAgent._print_copy_summary` | `apps/agent.py` | Prints a captured copy summary for backend logs. |

## Core Contracts

| Method | Reference | Purpose |
| --- | --- | --- |
| `AppRef.to_dict` | `core/contracts.py` | Serializes app/window metadata. |
| `AppRef.from_dict` | `core/contracts.py` | Rehydrates app/window metadata from storage JSON. |
| `ClipboardPayload.compute_hash` | `core/contracts.py` | Computes the canonical payload hash. |
| `ClipboardPayload.to_dict` | `core/contracts.py` | Serializes clipboard metadata. |
| `ScreenshotRef.to_dict` | `core/contracts.py` | Serializes screenshot metadata. |
| `Event.to_dict` | `core/contracts.py` | Serializes immutable event records. |
| `Event.short_id` | `core/contracts.py` | Returns a compact event ID label. |
| `Event.time_label` | `core/contracts.py` | Formats an event timestamp as HH:MM. |
| `GraphEdge.to_dict` | `core/contracts.py` | Serializes a graph edge. |
| `ContextBlock.to_dict` | `core/contracts.py` | Serializes a seven-event context block. |

## Capture

| Method | Reference | Purpose |
| --- | --- | --- |
| `infer_app_family` | `core/capture.py` | Maps process/window metadata to app families. |
| `get_foreground_window` | `core/capture.py` | Reads the current foreground Windows app context. |
| `read_clipboard` | `core/capture.py` | Reads text from the OS clipboard. |
| `build_clipboard_payload` | `core/capture.py` | Normalizes clipboard text into a hashable payload. |
| `get_text_anchor_position` | `core/capture.py` | Reads the active caret/focused-control location for copy bubble placement, falling back to cursor position. |
| `ScreenshotCapture.__init__` | `core/capture.py` | Prepares screenshot blob storage. |
| `ScreenshotCapture.capture` | `core/capture.py` | Captures an event-scoped screenshot. |
| `ClipboardListener.__init__` | `core/capture.py` | Configures copy and paste callbacks. |
| `ClipboardListener._on_press` | `core/capture.py` | Detects Ctrl+C and Ctrl+V keypresses. |
| `ClipboardListener._on_release` | `core/capture.py` | Tracks Ctrl key release state. |
| `ClipboardListener.start` | `core/capture.py` | Starts keyboard listening. |
| `ClipboardListener.stop` | `core/capture.py` | Stops keyboard listening. |
| `get_cursor_position` | `core/capture.py` | Reads current cursor coordinates for fallback placement and paste metadata. |

## Desktop Bubble

| Method | Reference | Purpose |
| --- | --- | --- |
| `ContextBubble.__init__` | `apps/bubble.py` | Creates a native Tkinter bubble controller. |
| `ContextBubble.show` | `apps/bubble.py` | Shows or updates the bubble near a screen anchor. |
| `ContextBubble.hide` | `apps/bubble.py` | Dismisses the active bubble. |
| `ContextBubble._fade_in` | `apps/bubble.py` | Animates the bubble into view. |
| `ContextBubble._position` | `apps/bubble.py` | Clamps bubble placement to the visible screen. |
| `ContextClipBubbleApp.__init__` | `apps/bubble_runtime.py` | Wires Tkinter, the agent, and backend action broker. |
| `ContextClipBubbleApp.start` | `apps/bubble_runtime.py` | Starts listener and Tkinter main loop. |
| `ContextClipBubbleApp.stop` | `apps/bubble_runtime.py` | Stops agent and closes the bubble runtime. |
| `ContextClipBubbleApp._on_event` | `apps/bubble_runtime.py` | Queues copy events for UI-thread handling and hides the bubble on paste events. |
| `ContextClipBubbleApp._drain_queue` | `apps/bubble_runtime.py` | Moves event, hide, analysis, and action results onto the UI thread. |
| `ContextClipBubbleApp._show_analyzing` | `apps/bubble_runtime.py` | Shows immediate feedback after copy capture. |
| `ContextClipBubbleApp._analyze_in_background` | `apps/bubble_runtime.py` | Runs OpenRouter or local analysis off the UI thread. |
| `ContextClipBubbleApp._show_analysis` | `apps/bubble_runtime.py` | Displays routed action buttons in the bubble. |
| `ContextClipBubbleApp._run_action_async` | `apps/bubble_runtime.py` | Runs clicked backend actions in a worker thread. |
| `ContextClipBubbleApp._show_action_result` | `apps/bubble_runtime.py` | Displays the action result and optional copy-result button. |
| `ContextClipBubbleApp._copy_result_text` | `apps/bubble_runtime.py` | Copies action output without reopening the bubble from polling. |
| `_anchor_from_event` | `apps/bubble_runtime.py` | Reads event anchor/cursor metadata for placement. |
| `_result_text` | `apps/bubble_runtime.py` | Extracts display text from action results. |

## Privacy

| Method | Reference | Purpose |
| --- | --- | --- |
| `classify_content` | `core/privacy.py` | Classifies clipboard content type. |
| `detect_privacy_class` | `core/privacy.py` | Detects restricted or public content. |
| `AppExclusionPolicy.__init__` | `core/privacy.py` | Builds app/process exclusion policy. |
| `AppExclusionPolicy.is_excluded` | `core/privacy.py` | Checks whether capture should be blocked. |
| `normalize_text` | `core/privacy.py` | Normalizes whitespace for previews and hashes. |
| `safe_preview` | `core/privacy.py` | Creates bounded display-safe previews. |

## Reference Graph

| Method | Reference | Purpose |
| --- | --- | --- |
| `_new_edge_id` | `core/graph.py` | Creates graph edge IDs. |
| `_time_proximity_score` | `core/graph.py` | Scores event closeness by time. |
| `_entity_overlap_score` | `core/graph.py` | Scores overlap between event previews. |
| `_app_transition_score` | `core/graph.py` | Scores app-to-app workflow transitions. |
| `compute_workflow_score` | `core/graph.py` | Combines weighted workflow signals. |
| `ReferenceGraph.__init__` | `core/graph.py` | Wires event and edge repositories. |
| `ReferenceGraph.record_copy` | `core/graph.py` | Caches copies and adds sequence edges. |
| `ReferenceGraph.correlate_paste` | `core/graph.py` | Backward-compatible paste correlation entry. |
| `ReferenceGraph.find_source_for_paste` | `core/graph.py` | Finds a copy source without writing edges. |
| `ReferenceGraph.record_paste` | `core/graph.py` | Adds the persisted paste graph edge. |
| `ReferenceGraph.add_edge` | `core/graph.py` | Adds an explicit graph edge. |
| `ReferenceGraph._add_edge` | `core/graph.py` | Persists a graph edge. |
| `ReferenceGraph.get_neighbors` | `core/graph.py` | Reads neighboring edges for an event. |
| `ReferenceGraph.get_workflow_events` | `core/graph.py` | Reads events by workflow ID. |
| `ReferenceGraph.get_all_edges` | `core/graph.py` | Reads all graph edges. |
| `ReferenceGraph.summarize` | `core/graph.py` | Returns a human-readable graph summary. |

## Memory And Context Blocks

| Method | Reference | Purpose |
| --- | --- | --- |
| `ContextWindowManager.__init__` | `core/memory.py` | Configures rolling seven-event memory. |
| `ContextWindowManager._load_block_counter` | `core/memory.py` | Determines the next context block number. |
| `ContextWindowManager.push` | `core/memory.py` | Adds an event to the active seven-event window. |
| `ContextWindowManager._close_window` | `core/memory.py` | Compresses and stores a completed seven-event window. |
| `ContextWindowManager.get_active_events` | `core/memory.py` | Returns the latest active events. |
| `ContextWindowManager.get_context_blocks` | `core/memory.py` | Returns recent context blocks. |
| `ContextWindowManager.pending_count` | `core/memory.py` | Returns current window fill count. |
| `_build_context_block` | `core/memory.py` | Legacy heuristic block builder kept for internal compatibility. |
| `_infer_goal` | `core/memory.py` | Infers a one-line workflow goal. |
| `_extract_entities` | `core/memory.py` | Extracts URLs, error codes, and identifiers. |
| `_infer_questions` | `core/memory.py` | Infers unresolved questions. |
| `_build_narrative` | `core/memory.py` | Builds a compact event narrative. |

## Cloud Compression And Serialization

| Method | Reference | Purpose |
| --- | --- | --- |
| `compress_with_llm` | `cloud/compressor.py` | Compresses a context window through OpenRouter or heuristic fallback. |
| `_openrouter_compress` | `cloud/compressor.py` | Calls OpenRouter using the OpenAI-compatible client. |
| `_heuristic_compress` | `cloud/compressor.py` | Creates a local context block when cloud compression is unavailable. |
| `_build_block` | `cloud/compressor.py` | Builds the final `ContextBlock` object. |
| `openrouter_model` | `cloud/openrouter.py` | Resolves model settings for OpenRouter calls. |
| `build_openrouter_client` | `cloud/openrouter.py` | Builds the OpenAI-compatible OpenRouter client. |
| `analyze_event_context` | `cloud/clipboard_analyzer.py` | Classifies captured copy events for bubble routing. |
| `analyze_clipboard_with_openrouter` | `cloud/clipboard_analyzer.py` | Uses OpenRouter to classify clipboard text and window context. |
| `run_clipboard_ai_action` | `cloud/clipboard_actions.py` | Runs OpenRouter actions against current clipboard text. |
| `open_clipboard_url` | `cloud/clipboard_actions.py` | Opens a copied URL in the default browser. |
| `_short_time` | `cloud/toon.py` | Formats TOON timestamps. |
| `_short_app` | `cloud/toon.py` | Compacts app family labels for TOON. |
| `_short_hash` | `cloud/toon.py` | Compacts payload hashes. |
| `encode_events_toon` | `cloud/toon.py` | Serializes events at the LLM boundary. |
| `decode_toon` | `cloud/toon.py` | Parses a TOON payload back to dictionaries. |
| `_icon` | `cloud/markdown_export.py` | Maps app family names to Markdown icons. |
| `_fmt_time` | `cloud/markdown_export.py` | Formats Markdown timestamps. |
| `export_events_markdown` | `cloud/markdown_export.py` | Creates user-copyable Markdown for events or blocks. |
| `export_workflow_markdown` | `cloud/markdown_export.py` | Merges multiple blocks into a workflow Markdown export. |

## Exa Clipboard Reference Search

| Method | Reference | Purpose |
| --- | --- | --- |
| `ExaReferenceResult.to_dict` | `cloud/exa_search.py` | Serializes one Exa reference result. |
| `ClipboardReferenceSearch.to_dict` | `cloud/exa_search.py` | Serializes the full Exa search response. |
| `ExaReferenceSearch.__init__` | `cloud/exa_search.py` | Configures the Exa client or test client. |
| `ExaReferenceSearch._build_client` | `cloud/exa_search.py` | Builds the `exa_py.Exa` client from `EXA_API_KEY`. |
| `ExaReferenceSearch.search_text` | `cloud/exa_search.py` | Searches references for clipboard text with highlights. |
| `search_clipboard_references` | `cloud/exa_search.py` | Reads current clipboard text and searches Exa. |
| `_query_from_clipboard_text` | `cloud/exa_search.py` | Normalizes and bounds clipboard query text. |
| `_normalize_result` | `cloud/exa_search.py` | Converts SDK result objects or dicts to local result records. |
| `_response_cost` | `cloud/exa_search.py` | Extracts Exa request cost if provided. |
| `_get` | `cloud/exa_search.py` | Reads object or dictionary fields. |

## Storage

| Method | Reference | Purpose |
| --- | --- | --- |
| `get_connection` | `storage/database.py` | Opens a path-keyed thread-local SQLite connection. |
| `close_connection` | `storage/database.py` | Closes the thread-local SQLite connection. |
| `initialize` | `storage/database.py` | Applies schema without inserting frontend command data. |
| `_utc_now` | `storage/repositories.py` | Creates storage timestamps. |
| `_new_id` | `storage/repositories.py` | Creates repository IDs. |
| `EventRepository.__init__` | `storage/repositories.py` | Stores the database path. |
| `EventRepository._conn` | `storage/repositories.py` | Reads the active SQLite connection. |
| `EventRepository.next_seq` | `storage/repositories.py` | Computes the next event sequence number. |
| `EventRepository.insert` | `storage/repositories.py` | Persists an immutable event. |
| `EventRepository.get_by_id` | `storage/repositories.py` | Reads an event by ID. |
| `EventRepository.get_recent` | `storage/repositories.py` | Reads recent events. |
| `EventRepository.get_last_n` | `storage/repositories.py` | Reads the latest N events. |
| `EventRepository.find_recent_copy_by_hash` | `storage/repositories.py` | Finds a copy event by payload hash. |
| `EventRepository.get_by_workflow` | `storage/repositories.py` | Reads events in one workflow. |
| `EventRepository.get_stats` | `storage/repositories.py` | Computes event statistics. |
| `EventRepository.search_fts` | `storage/repositories.py` | Searches event previews with SQLite FTS5. |
| `EventRepository.get_app_families` | `storage/repositories.py` | Summarizes app activity. |
| `EventRepository._row_to_event` | `storage/repositories.py` | Converts a database row to an `Event`. |
| `ScreenshotRepository.__init__` | `storage/repositories.py` | Stores the database path. |
| `ScreenshotRepository._conn` | `storage/repositories.py` | Reads the active SQLite connection. |
| `ScreenshotRepository.insert` | `storage/repositories.py` | Persists screenshot metadata. |
| `ScreenshotRepository.get_by_id` | `storage/repositories.py` | Reads screenshot metadata by ID. |
| `ScreenshotRepository.get_by_hash` | `storage/repositories.py` | Reads screenshot metadata by image hash. |
| `GraphEdgeRepository.__init__` | `storage/repositories.py` | Stores the database path. |
| `GraphEdgeRepository._conn` | `storage/repositories.py` | Reads the active SQLite connection. |
| `GraphEdgeRepository.insert` | `storage/repositories.py` | Persists a graph edge. |
| `GraphEdgeRepository.get_neighbors` | `storage/repositories.py` | Reads edge neighbors for an event. |
| `GraphEdgeRepository.get_all` | `storage/repositories.py` | Reads all graph edges. |
| `GraphEdgeRepository._row_to_edge` | `storage/repositories.py` | Converts a database row to a `GraphEdge`. |
| `ContextBlockRepository.__init__` | `storage/repositories.py` | Stores the database path. |
| `ContextBlockRepository._conn` | `storage/repositories.py` | Reads the active SQLite connection. |
| `ContextBlockRepository.insert` | `storage/repositories.py` | Persists a context block. |
| `ContextBlockRepository.get_all` | `storage/repositories.py` | Reads all context blocks. |
| `ContextBlockRepository.get_latest` | `storage/repositories.py` | Reads recent context blocks. |
| `ContextBlockRepository._row_to_block` | `storage/repositories.py` | Converts a database row to a `ContextBlock`. |

## Plugins

| Method | Reference | Purpose |
| --- | --- | --- |
| `IContextClipPlugin.manifest` | `plugins/base.py` | Defines plugin identity and capabilities. |
| `IContextClipPlugin.enrich` | `plugins/base.py` | Adds app-specific event context. |
| `IContextClipPlugin.get_actions` | `plugins/base.py` | Lists possible plugin actions. |
| `IContextClipPlugin.execute` | `plugins/base.py` | Plugin execution hook; current plugins are enrichers, not the action broker. |
| `IContextClipPlugin.health` | `plugins/base.py` | Reports basic plugin health. |
| `IContextClipPlugin.matches` | `plugins/base.py` | Checks whether a plugin applies to an app. |
| `BrowserPlugin.manifest` | `plugins/browser.py` | Defines browser plugin metadata. |
| `BrowserPlugin.matches` | `plugins/browser.py` | Matches Chromium, Edge, and Firefox families. |
| `BrowserPlugin.enrich` | `plugins/browser.py` | Extracts URL/search/page context from browser events. |
| `BrowserPlugin.get_actions` | `plugins/browser.py` | Lists browser-adjacent suggestions. |
| `BrowserPlugin.execute` | `plugins/browser.py` | Stub hook retained for future browser automation. |
| `OutlookPlugin.manifest` | `plugins/outlook.py` | Defines Outlook plugin metadata. |
| `OutlookPlugin.enrich` | `plugins/outlook.py` | Extracts meeting/email hints. |
| `OutlookPlugin.get_actions` | `plugins/outlook.py` | Lists Outlook-adjacent suggestions. |
| `OutlookPlugin.execute` | `plugins/outlook.py` | Stub hook retained for future Outlook automation. |
| `TerminalPlugin.manifest` | `plugins/terminal.py` | Defines terminal plugin metadata. |
| `TerminalPlugin.enrich` | `plugins/terminal.py` | Detects terminal commands and errors. |
| `TerminalPlugin.get_actions` | `plugins/terminal.py` | Lists terminal-adjacent suggestions. |
| `TerminalPlugin.execute` | `plugins/terminal.py` | Stub hook retained for future terminal automation. |
| `VSCodePlugin.manifest` | `plugins/vscode.py` | Defines VS Code plugin metadata. |
| `VSCodePlugin.enrich` | `plugins/vscode.py` | Extracts active file/language/code/error hints. |
| `VSCodePlugin._suggest_actions` | `plugins/vscode.py` | Selects VS Code action suggestions. |
| `VSCodePlugin.get_actions` | `plugins/vscode.py` | Lists VS Code-adjacent suggestions. |
| `VSCodePlugin.execute` | `plugins/vscode.py` | Stub hook retained for future VS Code automation. |
| `WordPlugin.manifest` | `plugins/word.py` | Defines Word plugin metadata. |
| `WordPlugin.enrich` | `plugins/word.py` | Extracts document and selection context. |
| `WordPlugin.get_actions` | `plugins/word.py` | Lists Word-adjacent suggestions. |
| `WordPlugin.execute` | `plugins/word.py` | Stub hook retained for future Word automation. |

## Excluded From Active Backend

`contextclip.py` remains a legacy prototype. The web dashboard and tray surfaces are not part of the active CLI path.
