# Bubble Branch Merge Notes

Branch inspected: `origin/bubble`

Separate checkout folder:

```text
.branch-checkouts/bubble
```

## What The Bubble Branch Was Trying To Do

The branch was a hackathon prototype for the core ContextClip interaction:

```text
copy text
  -> detect clipboard change
  -> capture app/window/screenshot context
  -> classify copied context with an LLM
  -> show a small native desktop bubble
  -> offer context-aware actions
```

Its strongest product idea is not the exact implementation. The strongest idea is that ContextClip should appear at the moment of copy and offer a few useful actions without requiring the user to open a chatbot.

## Files In The Branch

| Branch File | Intent |
| --- | --- |
| `capture.py` | Poll clipboard changes, capture active window and screenshot, then show/update the bubble. |
| `bubble.py` | Tkinter topmost popup window with title, copied-content summary, relation hint, and up to three buttons. |
| `context_engine.py` | Gemini-backed structured classification of copied text and surrounding workspace context. |
| `action_router.py` | Deterministic Python router that maps classified content/intent to allowed action buttons. |
| `context.md` | Hackathon product and implementation notes. |

## What Was Merged

The current main codebase already has stronger capture, storage, graph, privacy, TOON, Exa, and OpenRouter structure than the branch. So the merge kept the branch's intent while adapting it to the current architecture.

Merged concepts:

- Native Tkinter contextual bubble.
- Bubble appears after copy capture.
- UI work stays on Tkinter's main thread.
- LLM or local analyzer produces semantic context.
- Python deterministically chooses allowed actions.
- Buttons dispatch actual backend actions.
- Background threads keep analysis/actions from blocking the UI.

## What Was Not Copied Directly

The branch implementation was not copied line-for-line because it conflicted with the current app direction.

Skipped or replaced:

- Gemini API was replaced with OpenRouter.
- Clipboard polling was replaced with the existing `pynput` Ctrl+C/Ctrl+V listener.
- Prototype screenshot capture was replaced with the existing event-scoped screenshot system.
- Printed action stubs were replaced with `BackendActionBroker` execution.
- Fixed bottom-right placement was replaced with cursor-anchored placement when available.
- Standalone branch data models were replaced with `core/context_engine.py`.

## New Main-Code Modules

| File | Purpose |
| --- | --- |
| `apps/bubble.py` | Native Tkinter bubble UI. |
| `apps/bubble_runtime.py` | Runs agent, bubble, analysis, and action dispatch together. |
| `core/context_engine.py` | Local semantic classification models and fallback analysis. |
| `core/action_router.py` | Deterministic bubble action routing. |
| `cloud/openrouter.py` | Shared OpenRouter client helper. |
| `cloud/clipboard_analyzer.py` | OpenRouter-backed copied-context classification. |
| `cloud/clipboard_actions.py` | OpenRouter-backed action execution for clipboard text. |

## Final Runtime Shape

```text
python main.py
  -> ContextClipBubbleApp
  -> Tkinter root
  -> ContextClipAgent.start_background()
  -> user copies text
  -> event stored in SQLite
  -> copy-time cursor position stored in event plugin_context
  -> bubble shows near cursor
  -> OpenRouter analyzer runs in background when configured
  -> local analyzer fallback runs if key/network fails
  -> core/action_router.py selects actions
  -> button click calls BackendActionBroker
```

## Action Examples

For copied errors:

```text
Help fix -> ai.help_fix_clipboard
Explain -> ai.explain_clipboard
Search refs -> references.search_clipboard
```

For copied URLs:

```text
Open link -> system.open_clipboard_url
Summarize -> ai.summarize_clipboard
Search refs -> references.search_clipboard
```

For copied emails:

```text
Summarize -> ai.summarize_clipboard
Draft reply -> ai.draft_reply
Copy context -> context.copy_markdown
```

## Safety Notes

- Restricted clipboard content is blocked before OpenRouter actions.
- Restricted clipboard content is blocked before Exa reference search.
- `.env` is ignored by git.
- `.env.example` documents the required configuration without secrets.
- The branch checkout folder is ignored by git.

## Current Status

The bubble logic is now merged into the main codebase as an active desktop runtime. The app is no longer only headless: `python main.py` starts the native bubble experience, and `python main.py --agent` remains available for headless operation.
