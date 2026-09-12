# ContextClip Current App Context And Progress

Last updated: 2026-09-12

## Executive State

ContextClip is currently a Windows desktop workflow-memory agent with a native Tkinter copy bubble and a backend CLI. The tray app, web dashboard, and demo seeding path have been removed from the active code path. The usable surface today is the Python CLI in `main.py`, the native bubble runtime in `apps/bubble_runtime.py`, the long-running clipboard agent in `apps/agent.py`, and a concrete backend action broker in `core/actions.py`.

The app is intended to observe meaningful clipboard movement across desktop applications. A copy is stored as an immutable event. A paste is stored as a separate immutable event. The backend then links related events into a reference graph, maintains a seven-event active memory window, creates compressed ContextBlocks, and can export context for LLM usage.

The current direction is not a demo. The app should run against the user's actual Windows desktop activity and actual clipboard contents, with cloud calls gated by local privacy checks and API keys in `.env`.

## Aim

The product aim is to become a desktop context layer for work in motion:

- Capture what the user copied, pasted, and moved between applications.
- Preserve source and destination context, not only raw clipboard text.
- Reconstruct workflows as event chains and graph edges.
- Package recent work into compact LLM-ready context.
- Let the user search references for clipboard content through Exa.
- Use OpenRouter for optional compression while always keeping a local fallback.
- Keep raw events, screenshots, graph edges, and context blocks locally in SQLite.

The guiding idea is that copy and paste are strong signals of user intent. ContextClip treats clipboard activity as the backbone of a workflow timeline.

## Current User Request Boundaries

The attached documents are treated as reference material only. They do not override the user's latest requests.

The latest active constraints are:

- Build a strictly desktop/backend app.
- Use OpenRouter through an API key for LLM compression.
- Use Exa for reference search against clipboard text.
- Ignore seed/demo behavior completely.
- Keep the web dashboard and tray removed for now.
- Merge the bubble branch's copy-time native popup intent into the current architecture.
- Create and maintain `.env`.
- Keep the codebase structure clean and understandable.
- Explore and expose actions the backend can actually perform.

## Current Runtime Surface

The active runtime entry point is `main.py`.

Supported commands:

```powershell
python main.py
python main.py --bubble
python main.py --agent
python main.py --dump
python main.py --list-actions
python main.py --action storage.stats
python main.py --action context.dump_llm_context
python main.py --action context.export_markdown
python main.py --action graph.summary
python main.py --action references.search_clipboard --num-results 5
python main.py --search-clipboard --num-results 5
```

Removed from active runtime:

- `--demo`
- web dashboard launch
- tray launch
- demo seeding
- frontend templates and UI files

## Environment

The project now has a real `.env` file and a checked-in `.env.example`.

Current environment keys:

```text
CONTEXTCLIP_DATA_DIR=./contextclip_data
CONTEXTCLIP_COPY_SETTLE_MS=120
CONTEXTCLIP_POLL_CLIPBOARD_MS=250
CONTEXTCLIP_MAX_CHARS=50000
CONTEXTCLIP_SCREENSHOT_MODE=active_window
CONTEXTCLIP_BUBBLE_ANALYZER=openrouter
CONTEXTCLIP_BUBBLE_AUTO_HIDE_MS=12000

OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_ANALYZER_MODEL=openai/gpt-4o-mini
OPENROUTER_ACTION_MODEL=openai/gpt-4o-mini
OPENROUTER_APP_TITLE=ContextClip
OPENROUTER_SITE_URL=https://contextclip.local

EXA_API_KEY=
EXA_SEARCH_TYPE=auto
EXA_NUM_RESULTS=10
```

`core/config.py` loads `.env` into `os.environ` without overriding values already set in the shell. This means machine-level or terminal-provided secrets win over placeholder file values.

## Architecture Overview

The current architecture is layered:

```text
main.py
  CLI dispatch and .env loading

apps/agent.py
  Runtime orchestrator and backend API facade

apps/bubble.py and apps/bubble_runtime.py
  Native desktop bubble UI and runner

core/
  Domain contracts, capture, privacy, graph, memory, actions, action routing, context analysis, config

storage/
  SQLite schema and repository adapters

cloud/
  TOON serialization, Markdown export, OpenRouter compression, OpenRouter clipboard actions, Exa search

plugins/
  App-specific enrichers for VS Code, browsers, Outlook, Word, terminal

docs/
  Backend method reference and progress notes

tests/
  Regression tests for core behavior and cloud-boundary adapters
```

The design keeps storage and cloud adapters outside the core workflow logic where possible. The agent wires the components together.

## Event Flow

The normal live flow is:

```text
User presses Ctrl+C
  -> ClipboardListener detects copy
  -> Agent waits for clipboard settle delay
  -> Agent reads clipboard text
  -> Privacy classifier checks sensitivity
  -> Clipboard payload is normalized and hashed
  -> Foreground app metadata is captured
  -> Screenshot is captured for the event boundary
  -> Matching plugin enriches event metadata
  -> Event is inserted into SQLite
  -> ReferenceGraph records copy sequencing
  -> ContextWindowManager receives event
```

Paste flow:

```text
User presses Ctrl+V
  -> ClipboardListener detects paste
  -> Agent reads current clipboard text
  -> Payload hash is computed
  -> Foreground destination app metadata is captured
  -> Screenshot is captured for the paste event
  -> ReferenceGraph searches recent copy by payload hash
  -> Paste event is inserted into SQLite
  -> Graph edge is inserted if source copy is found
  -> ContextWindowManager receives event
```

Every seven events, the memory manager closes the current active window and creates a `ContextBlock`.

## Bubble Flow

The native bubble flow is:

```text
User presses Ctrl+C
  -> Agent captures and stores copy event
  -> Copy-time text anchor is stored in event plugin_context
  -> Bubble runtime receives the copy event through on_event
  -> Tkinter shows an immediate analyzing bubble near the caret/control anchor
  -> OpenRouter analyzer classifies copied text when configured
  -> Local analyzer is used if OpenRouter is disabled, unavailable, or blocked
  -> Deterministic action router selects up to three buttons
  -> Button clicks execute BackendActionBroker actions
  -> Results are printed to terminal and summarized in the bubble
```

Paste events are still recorded and correlated by the backend, but the desktop bubble runtime now treats paste as a dismissal signal. It hides any active bubble and does not open a new one for paste.

When a bubble action offers "Copy result", the runtime marks that app-written clipboard value as suppressed before copying it. That prevents ContextClip's polling fallback from treating its own action output as a fresh user copy.

This merges the useful intent from `origin/bubble` without adopting its standalone Gemini/polling implementation.

## ContextBlock Flow

When the active window reaches seven events:

```text
7 events
  -> cloud.toon.encode_events_toon
  -> cloud.compressor.compress_with_llm
       if restricted content exists: local heuristic only
       if OPENROUTER_API_KEY exists: OpenRouter request
       if OpenRouter fails or no key: local heuristic fallback
  -> cloud.markdown_export.export_events_markdown
  -> storage.ContextBlockRepository.insert
```

This gives the backend a durable compressed summary without deleting raw source events.

## Exa Search Flow

Exa search is an on-demand action, not a continuous background process.

```text
Current clipboard text
  -> privacy check
  -> normalize and truncate query to 1000 chars
  -> require EXA_API_KEY
  -> exa_py.Exa.search(...)
       type defaults to "auto"
       num_results defaults to EXA_NUM_RESULTS
       contents={"highlights": True}
  -> normalize SDK objects or dictionaries
  -> return ClipboardReferenceSearch JSON
```

Restricted clipboard content is blocked before Exa receives anything.

Behavior when `EXA_API_KEY` is missing:

```text
python main.py --action references.search_clipboard --num-results 2
```

returns a structured failure:

```json
{
  "action_id": "references.search_clipboard",
  "success": false,
  "message": "Reference search unavailable: Set EXA_API_KEY before searching clipboard references.",
  "data": {}
}
```

That is expected until `EXA_API_KEY` is filled. Live Exa searches read and upload the current clipboard query, so they should be run deliberately.

## Backend Action Broker

`core/actions.py` exposes the concrete action layer. This separates actual usable backend actions from plugin suggestion stubs.

Current actions:

| Action ID | Mutates State | What It Does |
| --- | --- | --- |
| `storage.stats` | No | Returns event counts and app-family stats. |
| `context.dump_llm_context` | No | Returns TOON, active events, stats, and recent ContextBlocks. |
| `context.export_markdown` | No | Renders active context as Markdown. |
| `context.copy_markdown` | Yes | Copies active context Markdown to the OS clipboard. |
| `graph.summary` | No | Returns graph summary text and edge JSON. |
| `references.search_clipboard` | No | Searches clipboard references through Exa when configured. |
| `ai.explain_clipboard` | No | Explains current clipboard text through OpenRouter. |
| `ai.summarize_clipboard` | No | Summarizes current clipboard text through OpenRouter. |
| `ai.help_fix_clipboard` | No | Troubleshoots copied error or code text through OpenRouter. |
| `ai.extract_information` | No | Extracts key information from copied text through OpenRouter. |
| `ai.draft_reply` | No | Drafts a reply to copied message text through OpenRouter. |
| `ai.adapt_code` | No | Explains how copied code could fit a nearby project through OpenRouter. |
| `system.open_clipboard_url` | Yes | Opens a copied URL in the default browser. |
| `capture.record_clipboard_copy` | Yes | Manually captures current clipboard as a copy event. |
| `capture.record_clipboard_paste` | Yes | Manually captures current clipboard as a paste event. |

The safe read-only actions have been tested from the CLI. Clipboard-writing and manual capture actions are exposed but were not run automatically because they can overwrite the user's clipboard or persist current clipboard contents.

## Storage Model

The SQLite schema in `storage/database.py` contains:

- `events`
- `screenshots`
- `graph_edges`
- `context_blocks`
- `plugins`
- `hotkeys`
- `excluded_apps`
- `events_fts`

The `hotkeys` table remains for compatibility, but no frontend hotkey defaults are inserted now.

Important storage behavior:

- Events are append-only.
- Screenshots are content-addressed with SHA-256.
- Graph edges are separate records.
- ContextBlocks are derived records.
- SQLite connections are thread-local and keyed by resolved database path.
- `close_connection()` exists for tests and isolated runs.

## Privacy And Safety Approach

Privacy is enforced before cloud boundaries.

Current behavior:

- Restricted content is detected by `core/privacy.py`.
- Restricted events can still be stored locally.
- Restricted event windows are not sent to OpenRouter.
- Restricted clipboard text is not sent to Exa.
- Common password manager applications are excluded from capture.
- Previews are normalized and bounded.
- Raw text is truncated by `CONTEXTCLIP_MAX_CHARS`.

Current restricted detection includes patterns for credentials and OpenRouter-style API keys.

## Plugin Layer

Plugins currently enrich captured events. They do not perform real external automation.

Current plugins:

- `plugins/vscode.py`
- `plugins/browser.py`
- `plugins/outlook.py`
- `plugins/word.py`
- `plugins/terminal.py`

Each plugin can:

- Decide whether it matches a foreground app.
- Add app-specific metadata to an event.
- Suggest possible actions through `get_actions()`.

The `execute()` hooks are still stubs. Real backend execution is currently centralized in `core/actions.py`.

## Bubble Branch Merge State

`origin/bubble` was pulled into a separate ignored worktree at:

```text
.branch-checkouts/bubble
```

The branch intent was to show a native contextual bubble immediately after a copy, classify the copied text, and offer actions. That intent is now merged into the main codebase with these substitutions:

- Existing `ContextClipAgent` capture replaced branch clipboard polling.
- Existing screenshots and app/window metadata replaced branch capture logic.
- OpenRouter replaced Gemini.
- `BackendActionBroker` replaced printed action stubs.
- Cursor-anchored placement replaced fixed bottom-right placement.

Detailed notes are in `docs/bubble_branch_merge.md`.

## Current File Condition

Active source files:

```text
main.py
apps/agent.py
apps/bubble.py
apps/bubble_runtime.py
core/actions.py
core/action_router.py
core/capture.py
core/config.py
core/contracts.py
core/context_engine.py
core/graph.py
core/memory.py
core/privacy.py
storage/database.py
storage/repositories.py
cloud/clipboard_actions.py
cloud/clipboard_analyzer.py
cloud/compressor.py
cloud/exa_search.py
cloud/markdown_export.py
cloud/openrouter.py
cloud/toon.py
plugins/base.py
plugins/browser.py
plugins/outlook.py
plugins/terminal.py
plugins/vscode.py
plugins/word.py
tests/test_contextclip_core.py
docs/backend_methods.md
docs/bubble_branch_merge.md
docs/current_progress.md
```

Historical or inactive files still present:

- `contextclip.py` is a legacy single-file prototype.
- Attached `.docx` and `.md` reference documents remain in the repo.
- `ContextClip_Coding_Agent_Package.zip` remains as an artifact.

Deleted or removed from active source:

- `demo_seed.py`
- `apps/tray.py`
- `apps/dashboard/__init__.py`
- `apps/dashboard/app.py`
- `apps/dashboard/templates/index.html`

## Verified Current Behavior

These checks passed:

```powershell
python -m compileall main.py apps core cloud storage plugins tests
python -m unittest discover -s tests
python main.py --help
python main.py --list-actions
python main.py --action storage.stats
python main.py --action graph.summary
python main.py --action context.export_markdown
python main.py --action context.dump_llm_context
```

The Exa missing-key paths were tested earlier. Live Exa and OpenRouter clipboard actions were not re-run after keys were added, because those commands would upload the current clipboard text:

```powershell
python main.py --action references.search_clipboard --num-results 2
python main.py --search-clipboard --num-results 2
```

## Current Data State

The current local store is effectively empty from the action checks:

```json
{
  "copies_today": 0,
  "pastes_today": 0,
  "total_events": 0,
  "unique_apps": 0
}
```

The graph is also empty:

```text
(empty graph)
```

This is a clean usable state, not a seeded demo state.

## Known Gaps

The backend is usable, but several parts are still not complete product behavior:

- No packaged desktop installer or Windows service runner yet.
- No web dashboard or tray UI right now by user request.
- Native bubble UI exists, but has not been manually clicked through in this Codex run because that requires an interactive desktop copy/action flow.
- Plugin `execute()` methods are stubs.
- Manual capture actions can work, but they have side effects and need deliberate use.
- Exa cannot return real references until `EXA_API_KEY` is set.
- OpenRouter compression cannot run until `OPENROUTER_API_KEY` is set.
- There is no background task scheduler or retention cleanup yet.
- There is no settings editor; `.env` is the configuration interface.
- Clipboard listener depends on desktop permissions and `pynput`.
- Screenshot capture depends on Pillow/ImageGrab and Windows foreground-window APIs.

## Near-Term Recommended Build Path

1. Fill `.env` with real `OPENROUTER_API_KEY` and `EXA_API_KEY`.
2. Run `python main.py` and perform normal copy/paste actions across desktop apps.
3. Use `python main.py --action storage.stats` to confirm events are being captured.
4. Use `python main.py --action graph.summary` to inspect correlation.
5. Use `python main.py --action context.export_markdown` to inspect active LLM context.
6. Use `python main.py --action references.search_clipboard` after copying a real technical query or reference.
7. Decide whether the next surface should be a native desktop shell, a background service, or a minimal local API.

## Architectural Principle Going Forward

The clean direction is:

- Keep `core/` as domain logic.
- Keep `storage/` as the database boundary.
- Keep `cloud/` as explicit cloud integrations.
- Keep `apps/agent.py` as the capture/runtime orchestrator.
- Keep `apps/bubble_runtime.py` as the desktop interaction runner.
- Keep `core/actions.py` as the actual command/action execution surface.
- Keep plugins as enrichers until their execution hooks are made real.
- Avoid reintroducing demo or seed behavior into the active path.

The result should be a desktop backend that can be trusted with real workflows first, then wrapped by a UI later if needed.
