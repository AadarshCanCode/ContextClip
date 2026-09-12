# ContextClip v4 Backend

ContextClip is a Windows desktop workflow-memory agent built around copy and paste events. Every copy is one immutable event, every paste is a separate immutable event, and each event can carry window metadata, payload metadata, screenshot references, graph links, and plugin context.

The active desktop surface is a native Tkinter copy bubble. The web dashboard and tray app are removed from the active code path.

## What It Does

- Records Ctrl+C as Copy events with source app metadata and event-scoped screenshots.
- Records Ctrl+V as Paste events with destination metadata, a separate screenshot, and a graph edge when a source copy can be correlated.
- Keeps the latest seven events as the active context window.
- Creates derived ContextBlocks after every seven events without deleting raw events.
- Serializes LLM-bound event windows as TOON and user exports as Markdown.
- Uses OpenRouter for optional seven-event compression.
- Uses Exa Search for optional clipboard reference search.
- Shows a native desktop bubble near the copy location with routed actions.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Environment

Create or edit `.env` in the project root. It is loaded automatically by the CLI and backend modules:

```powershell
OPENROUTER_API_KEY=your-openrouter-key
EXA_API_KEY=your-exa-key
```

OpenRouter powers optional context compression. Exa powers clipboard reference search. Without `OPENROUTER_API_KEY`, ContextClip falls back to local heuristic compression. Without `EXA_API_KEY`, clipboard reference search is unavailable, but capture and local storage still work.

Use `.env.example` as the reproducible template.

## Commands

Run the native desktop bubble agent:

```powershell
python main.py
```

Run the headless clipboard agent:

```powershell
python main.py --agent
```

List concrete backend actions:

```powershell
python main.py --list-actions
```

Run one backend action:

```powershell
python main.py --action storage.stats
python main.py --action context.dump_llm_context
python main.py --action graph.summary
python main.py --action references.search_clipboard --num-results 5
```

Dump the active LLM context payload:

```powershell
python main.py --dump
```

Search web references for the current clipboard text through Exa:

```powershell
python main.py --search-clipboard
```

Useful Exa options:

```powershell
python main.py --search-clipboard --search-type auto --num-results 5
python main.py --search-clipboard --include-domain docs.docker.com
python main.py --search-clipboard --max-age-hours 24
```

The Exa integration uses the Search API with `type="auto"` by default and `contents={"highlights": True}` for token-efficient agent workflows.

## Data And Privacy

Local runtime data is written under `contextclip_data/` by default. Override it with:

```powershell
$env:CONTEXTCLIP_DATA_DIR = "C:\path\to\data"
```

Screenshots are captured only at copy or paste event boundaries. Restricted clipboard content is recorded locally but blocked from OpenRouter compression and Exa reference search. Default exclusions include common password managers.

## Project Structure

```text
main.py                  backend CLI entry point
apps/agent.py            clipboard agent and backend API facade
apps/bubble.py           native Tkinter context bubble
apps/bubble_runtime.py   desktop bubble app runner
core/                    config, actions, action routing, context analysis, contracts, capture, graph, memory, privacy
storage/                 SQLite schema and repositories
cloud/                   TOON, Markdown export, OpenRouter, Exa search, clipboard analysis/actions
plugins/                 plugin SDK and starter app plugins
docs/backend_methods.md  backend method reference
tests/                   backend regression tests
```
