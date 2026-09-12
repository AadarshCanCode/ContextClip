"""
main.py - ContextClip v4 backend entry point.

Usage:
  python main.py                    -> run clipboard agent service
  python main.py --agent            -> run clipboard agent service
  python main.py --dump             -> dump current LLM context JSON
  python main.py --list-actions     -> list concrete backend actions
  python main.py --action ACTION_ID -> run one concrete backend action
  python main.py --search-clipboard -> search clipboard references with Exa
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from core.config import get_int, load_env_file


def configure_console_io() -> None:
    """Prefer UTF-8 CLI output on Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def run_agent_only() -> None:
    """Start the clipboard agent service with no frontend."""
    from apps.agent import ContextClipAgent

    agent = ContextClipAgent()
    agent.start()


def dump_context() -> None:
    """Print the current LLM context JSON to stdout and exit."""
    from apps.agent import ContextClipAgent, DATA_DIR

    agent = ContextClipAgent(data_dir=DATA_DIR)
    ctx = agent.dump_llm_context()
    print(json.dumps(ctx, indent=2, ensure_ascii=False))


def search_clipboard(args: argparse.Namespace) -> None:
    """Search current clipboard text through Exa and print normalized JSON."""
    from apps.agent import ContextClipAgent, DATA_DIR
    from cloud.exa_search import ExaSearchError

    agent = ContextClipAgent(data_dir=DATA_DIR)
    try:
        result = agent.search_clipboard_references(
            search_type=args.search_type,
            num_results=args.num_results,
            include_domains=args.include_domain,
            exclude_domains=args.exclude_domain,
            max_age_hours=args.max_age_hours,
        )
    except ExaSearchError as exc:
        print(f"[Exa] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


def list_actions() -> None:
    """Print concrete backend actions available in this build."""
    from apps.agent import ContextClipAgent, DATA_DIR
    from core.actions import BackendActionBroker

    agent = ContextClipAgent(data_dir=DATA_DIR)
    broker = BackendActionBroker(agent)
    actions = [action.to_dict() for action in broker.discover()]
    print(json.dumps(actions, indent=2, ensure_ascii=False))


def run_action(args: argparse.Namespace) -> None:
    """Execute a concrete backend action and print normalized JSON."""
    from apps.agent import ContextClipAgent, DATA_DIR
    from core.actions import BackendActionBroker, BackendActionError

    agent = ContextClipAgent(data_dir=DATA_DIR)
    broker = BackendActionBroker(agent)
    try:
        result = broker.execute(
            args.action,
            search_type=args.search_type,
            num_results=args.num_results,
            include_domains=args.include_domain,
            exclude_domains=args.exclude_domain,
            max_age_hours=args.max_age_hours,
        )
    except BackendActionError as exc:
        print(f"[Action] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    if not result.success:
        raise SystemExit(2)


def main() -> None:
    configure_console_io()
    load_env_file(_ROOT / ".env")

    parser = argparse.ArgumentParser(
        prog="contextclip",
        description="ContextClip v4 backend workflow memory agent",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Run clipboard agent service",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="Dump current LLM context JSON to stdout",
    )
    parser.add_argument(
        "--list-actions",
        action="store_true",
        help="List concrete backend actions available in this build",
    )
    parser.add_argument(
        "--action",
        help="Run a concrete backend action by id",
    )
    parser.add_argument(
        "--search-clipboard",
        action="store_true",
        help="Search web references for the current clipboard using Exa",
    )
    parser.add_argument(
        "--search-type",
        default=os.environ.get("EXA_SEARCH_TYPE", "auto"),
        choices=["auto", "fast", "instant", "deep-lite", "deep", "deep-reasoning"],
        help="Exa search type for --search-clipboard or references.search_clipboard",
    )
    parser.add_argument(
        "--num-results",
        type=int,
        default=get_int("EXA_NUM_RESULTS", 10),
        help="Number of Exa results to return",
    )
    parser.add_argument(
        "--include-domain",
        action="append",
        help="Restrict Exa results to a domain; repeat for multiple domains",
    )
    parser.add_argument(
        "--exclude-domain",
        action="append",
        help="Exclude an Exa result domain; repeat for multiple domains",
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        help="Exa contents freshness cap; 0 forces livecrawl, -1 cache only",
    )
    args = parser.parse_args()

    if args.dump:
        dump_context()
    elif args.list_actions:
        list_actions()
    elif args.action:
        run_action(args)
    elif args.search_clipboard:
        search_clipboard(args)
    else:
        run_agent_only()


if __name__ == "__main__":
    main()
