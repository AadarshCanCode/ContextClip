# ContextClip v4

> **Information in motion. Workflows in action.**

ContextClip is a Windows workflow memory agent whose trigger surface is the clipboard. It observes information moving between applications and reconstructs the workflow around that movement — not just what was copied, but *why* and *where*.

---

## What it does

- **Every Ctrl+C** → records what moved, where it came from, a screenshot, and the content type (error, code, URL, email, meeting…)
- **Every Ctrl+V** → records the destination, a second screenshot, then links the two events in the Reference Graph
- **Every 7 events** → compressed into a portable Context Block (Markdown + TOON payload for LLM input)
- **Dashboard** → shows your live workflow, app connections, and compressed context blocks
- **Plugins** → VS Code, Browser, Outlook, Teams, Word, Terminal — each adds app-specific context and suggested actions

---

## Architecture

```
┌────────────────────────────────────────────────────┐
│            ContextClip Dashboard (Flask)           │
│              http://127.0.0.1:5678                 │
└─────────────────────┬──────────────────────────────┘
                      │ reads from
┌─────────────────────▼──────────────────────────────┐
│               ContextClip Agent                    │
│  Clipboard  ─►  Event  ─►  Graph  ─►  Memory       │
│  Listener       Capture     Edges     7-event ctx  │
│                   │                      │         │
│             Screenshot            ContextBlock     │
│             Capture               (TOON+Markdown)  │
└─────────────────────┬──────────────────────────────┘
                      │
         ┌────────────▼────────────┐
         │   SQLite (events.db)    │
         │   events / screenshots  │
         │   graph_edges           │
         │   context_blocks        │
         └─────────────────────────┘

Plugins sit on top of core event store (never own storage):
  plugins/vscode.py  plugins/browser.py  plugins/outlook.py
  plugins/word.py    plugins/terminal.py
```

---

## Installation

```bash
# 1. Clone / open the project
cd contextclip

# 2. Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Usage

### Full app (recommended) — tray + dashboard + agent

```bash
python main.py
```

This starts:
- System tray icon (right-click for menu)
- Dashboard at http://127.0.0.1:5678 (auto-opens)
- Clipboard agent (global Ctrl+C / Ctrl+V monitoring)

### Agent only (no GUI)

```bash
python main.py --agent
```

### Demo mode (seed 7-event scenario + open dashboard)

```bash
python main.py --demo
```

Injects the Golden Demo Scenario from the spec:
`VS Code → Browser → Word → Terminal → ContextBlock-001`

### Dump LLM context to stdout

```bash
python main.py --dump
```

### Legacy single-file runner

```bash
python contextclip.py
```

---

## Dashboard

Open http://127.0.0.1:5678 after starting the app.

| Section | Description |
|---|---|
| Stats bar | Copies today, pastes today, workflow length, connected apps |
| App grid | Connected apps with live status |
| Recent Context | Last 50 events with type badges, previews, screenshots |
| Context Blocks | Compressed 7-event windows — copy as Markdown |
| Context Bubble | Appears when a new event arrives — shows AI actions |

**Keyboard shortcuts:**
- `Ctrl+1` — Summarize active context
- `Ctrl+2` — Explain
- `Ctrl+3` — Create (draft/task/reply)
- `Ctrl+4` — Translate
- `Ctrl+/` — More actions

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CONTEXTCLIP_DATA_DIR` | `./contextclip_data` | Where to store events, screenshots, database |
| `CONTEXTCLIP_SCREENSHOT_MODE` | `active_window` | `active_window` or `full_screen` |
| `CONTEXTCLIP_COPY_SETTLE_MS` | `120` | Milliseconds to wait after Ctrl+C for clipboard to settle |
| `CONTEXTCLIP_DASHBOARD_PORT` | `5678` | Flask dashboard port |
| `OPENAI_API_KEY` | _(unset)_ | Set to enable LLM-powered context compression |

---

## Project Structure

```
contextclip/
├── main.py                  ← Entry point
├── demo_seed.py             ← Golden Demo Scenario seeder
├── contextclip.py           ← Legacy single-file prototype
├── requirements.txt
│
├── core/                    ← Domain logic (no UI, no storage deps)
│   ├── contracts.py         ← Event, Screenshot, ContextBlock types
│   ├── capture.py           ← Clipboard + screenshot capture
│   ├── privacy.py           ← Content classification + app exclusion
│   ├── graph.py             ← ReferenceGraph + workflow scoring
│   └── memory.py            ← ReferenceStack + 7-event context window
│
├── storage/
│   ├── database.py          ← SQLite schema + migrations
│   └── repositories.py      ← Repository pattern over SQLite
│
├── cloud/
│   ├── toon.py              ← TOON serializer (LLM boundary)
│   ├── compressor.py        ← 7-event → ContextBlock (LLM or heuristic)
│   └── markdown_export.py   ← User-copyable Markdown export
│
├── plugins/
│   ├── base.py              ← IContextClipPlugin interface
│   ├── vscode.py            ← VS Code plugin
│   ├── browser.py           ← Browser plugin
│   ├── outlook.py           ← Outlook plugin
│   ├── word.py              ← Word plugin
│   └── terminal.py          ← Terminal plugin
│
└── apps/
    ├── agent.py             ← ContextClipAgent (orchestrator)
    ├── tray.py              ← System tray (pystray)
    └── dashboard/
        ├── app.py           ← Flask app + API routes
        └── templates/
            └── index.html   ← Dashboard UI
```

---

## Data Model

```
Event (immutable)
  id, seq, type (copy|paste), timestamp_utc
  source_app (AppRef), clipboard (payload + hash + preview)
  screenshot_id, privacy_class, content_type
  workflow_id, parent_event_id

GraphEdge
  from_event_id --[relation]--> to_event_id
  relations: copied_from | pasted_into | searched_for |
             derived_from | solves | same_thread | follows

ContextBlock (derived — never deletes raw events)
  7 event IDs, workflow_id, title, one_line_goal
  narrative, entities, open_questions, app_transitions
  toon_payload, markdown_payload
```

---

## Context Block Markdown Example

```markdown
## ContextClip Context Block 001
**Workflow:** w_debug_api
**Events:** 1–7
**Apps:** 💻 vs_code → 🌐 browser_edge → 📝 word → ⬛ terminal

### Goal
Resolve: ERR_CONNECTION_REFUSED 10.0.0.42:8080

### Timeline
1. **Copy** | 💻 vs_code | `2025-09-12 10:02 UTC`
   > ERR_CONNECTION_REFUSED 10.0.0.42:8080...

2. **Paste** | 🌐 browser_edge | `2025-09-12 10:03 UTC`
   > ERR_CONNECTION_REFUSED 10.0.0.42:8080...
...

### Open Questions
- Was the search query resolved?
- Did the fix work?
```

---

## TOON Payload (LLM boundary)

```toon
window[7]{id,type,time,app,target,summary,hash}:
  evt_a1b2,copy,10:02,VSCode,server.py,ERR_CONNECTION_REFUSED,sha256:aa1b2c3d
  evt_c3d4,paste,10:03,Edge,Search,ERR_CONNECTION_REFUSED,sha256:aa1b2c3d
  evt_e5f6,copy,10:04,Edge,Docker Docs,ECONNREFUSED means port,sha256:bb3c4d5e
  ...
workflow:
  id:w_debug_api
  goal:resolve:ERR_CONNECTION_REFUSED 10.0.0.42:8080
  links[6]:evt_a1b2->evt_c3d4,...
```

---

## Privacy & Security

- **Excluded apps**: Add process names to exclude from capture (password managers excluded by default)
- **Sensitive detection**: Detects API keys, passwords, credentials → marks as `RESTRICTED`; blocks cloud upload
- **Screenshot policy**: Event-scoped only — no continuous recording
- **Cloud upload**: Off by default. Set `OPENAI_API_KEY` to enable LLM compression (content stays local unless you opt in)
- **Retention**: Default 30 days (configurable)

---

## Roadmap

| Phase | Status |
|---|---|
| Phase 0: Repository bootstrap | ✅ Done |
| Phase 1: Clipboard + screenshots | ✅ Done |
| Phase 2: Paste + graph | ✅ Done |
| Phase 3: Dashboard UI | ✅ Done |
| Phase 4: TOON + cloud compressor | ✅ Done |
| Phase 5: Plugins + demo | ✅ Done (stubs) |
| Plugin IPC (named pipes) | 🔜 Future |
| WinUI 3 native shell | 🔜 Future |
| Browser extension | 🔜 Future |
| VS Code extension | 🔜 Future |

---

*Built following ContextClip v4 Implementation Specification.*
