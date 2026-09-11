"""
main.py — ContextClip v4 entry point.

Usage:
  python main.py           → start tray + dashboard + agent (recommended)
  python main.py --agent   → agent only (no tray/dashboard)
  python main.py --demo    → inject demo events and open dashboard
  python main.py --dump    → dump current LLM context to stdout
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))


def run_tray() -> None:
    """Start the full application: tray + dashboard + agent."""
    from apps.tray import main
    main()


def run_agent_only() -> None:
    """Start only the clipboard agent (no GUI, no dashboard)."""
    from apps.agent import ContextClipAgent
    agent = ContextClipAgent()
    agent.start()


def run_demo() -> None:
    """Inject a 7-event demo scenario and open the dashboard."""
    import threading, time, webbrowser
    from apps.agent import ContextClipAgent, DATA_DIR
    from apps.dashboard.app import run_dashboard, DASHBOARD_PORT
    from demo_seed import seed_demo_events

    agent = ContextClipAgent(data_dir=DATA_DIR)
    seed_demo_events(agent)

    dashboard_thread = threading.Thread(
        target=run_dashboard,
        args=(agent,),
        daemon=True,
    )
    dashboard_thread.start()

    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{DASHBOARD_PORT}")
    print(f"[Demo] Dashboard: http://127.0.0.1:{DASHBOARD_PORT}")
    print("[Demo] Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def dump_context() -> None:
    """Dump the current LLM context JSON to stdout."""
    import json
    from apps.agent import ContextClipAgent, DATA_DIR
    agent = ContextClipAgent(data_dir=DATA_DIR)
    ctx = agent.dump_llm_context()
    print(json.dumps(ctx, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="contextclip",
        description="ContextClip v4 — Workflow memory agent",
    )
    parser.add_argument("--agent", action="store_true", help="Agent only (no tray/dashboard)")
    parser.add_argument("--demo", action="store_true", help="Inject demo events + open dashboard")
    parser.add_argument("--dump", action="store_true", help="Dump LLM context to stdout")
    args = parser.parse_args()

    if args.agent:
        run_agent_only()
    elif args.demo:
        run_demo()
    elif args.dump:
        dump_context()
    else:
        run_tray()


if __name__ == "__main__":
    main()
