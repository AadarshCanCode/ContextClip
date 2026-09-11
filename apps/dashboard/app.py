"""
apps/dashboard/app.py — Flask web dashboard for ContextClip.

Routes:
  GET  /                     → dashboard HTML
  GET  /api/events           → recent events (JSON)
  GET  /api/stats            → copy/paste stats (JSON)
  GET  /api/blocks           → context blocks (JSON)
  GET  /api/blocks/<id>/markdown → raw Markdown for a block
  GET  /api/context          → full LLM context JSON
  GET  /api/screenshot/<id>  → serve screenshot image
  GET  /api/graph            → event graph edges
  POST /api/clear            → clear all history
  GET  /api/health           → health check

Usage:
  from apps.dashboard.app import create_app
  flask_app = create_app(agent)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from flask import Flask, Response, jsonify, render_template, request, send_file

if TYPE_CHECKING:
    from apps.agent import ContextClipAgent

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

DASHBOARD_PORT = int(os.environ.get("CONTEXTCLIP_DASHBOARD_PORT", "5678"))


def create_app(agent: "ContextClipAgent") -> Flask:
    """
    Flask application factory.
    The agent instance is shared — the dashboard reads from it directly.
    """
    app = Flask(
        __name__,
        template_folder=str(_TEMPLATE_DIR),
        static_folder=str(_STATIC_DIR),
    )
    app._agent = agent

    # -----------------------------------------------------------------------
    # Main dashboard
    # -----------------------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html")

    # -----------------------------------------------------------------------
    # Events API
    # -----------------------------------------------------------------------

    @app.route("/api/events")
    def api_events():
        n = int(request.args.get("n", 50))
        events = agent.get_active_events(n)
        return jsonify({
            "events": [e.to_dict() for e in events],
            "count": len(events),
        })

    # -----------------------------------------------------------------------
    # Stats API
    # -----------------------------------------------------------------------

    @app.route("/api/stats")
    def api_stats():
        stats = agent.get_stats()
        stats["pending_window"] = agent._memory.pending_count()
        return jsonify(stats)

    # -----------------------------------------------------------------------
    # Context blocks API
    # -----------------------------------------------------------------------

    @app.route("/api/blocks")
    def api_blocks():
        n = int(request.args.get("n", 10))
        blocks = agent.get_context_blocks(n)
        return jsonify({
            "blocks": [b.to_dict() for b in blocks],
            "count": len(blocks),
        })

    @app.route("/api/blocks/<block_id>/markdown")
    def api_block_markdown(block_id: str):
        blocks = agent.get_context_blocks(50)
        for block in blocks:
            if block.id == block_id:
                return Response(block.markdown_payload, mimetype="text/plain; charset=utf-8")
        return Response("Block not found", status=404)

    # -----------------------------------------------------------------------
    # Full LLM context
    # -----------------------------------------------------------------------

    @app.route("/api/context")
    def api_context():
        return jsonify(agent.dump_llm_context())

    # -----------------------------------------------------------------------
    # Graph edges
    # -----------------------------------------------------------------------

    @app.route("/api/graph")
    def api_graph():
        events = agent.get_active_events(50)
        edges = agent.get_all_edges()
        return jsonify({
            "events": [e.to_dict() for e in events],
            "edges": [e.to_dict() for e in edges],
        })

    # -----------------------------------------------------------------------
    # Screenshot serving
    # -----------------------------------------------------------------------

    @app.route("/api/screenshot/<screenshot_id>")
    def api_screenshot(screenshot_id: str):
        path = agent.get_screenshot_path(screenshot_id)
        if path and Path(path).exists():
            return send_file(path, mimetype="image/png")
        # Return a placeholder 1x1 transparent PNG
        import base64
        placeholder = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )
        return Response(placeholder, mimetype="image/png")

    # -----------------------------------------------------------------------
    # Clear history
    # -----------------------------------------------------------------------

    @app.route("/api/clear", methods=["POST"])
    def api_clear():
        # For MVP: reinitialize the DB (blunt but safe for demo)
        try:
            from storage.database import initialize as init_db
            db_path = agent._event_repo._db
            conn = agent._event_repo._conn()
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM screenshots")
            conn.execute("DELETE FROM graph_edges")
            conn.execute("DELETE FROM context_blocks")
            conn.execute("DELETE FROM events_fts")
            conn.commit()
            agent._graph._copy_by_hash.clear()
            agent._graph._last_copy_event_id = None
            agent._memory._pending_event_ids = []
            return jsonify({"success": True, "message": "History cleared."})
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

    # -----------------------------------------------------------------------
    # Health check
    # -----------------------------------------------------------------------

    @app.route("/api/health")
    def api_health():
        return jsonify({
            "status": "ok",
            "agent_running": agent._running,
            "pending_window": agent._memory.pending_count(),
        })

    # -----------------------------------------------------------------------
    # App families (for connected apps panel)
    # -----------------------------------------------------------------------

    @app.route("/api/apps")
    def api_apps():
        families = agent.get_app_families()
        return jsonify({"apps": families})

    return app


def run_dashboard(agent: "ContextClipAgent", port: int = DASHBOARD_PORT) -> None:
    """Start the Flask dashboard in blocking mode (call from a thread)."""
    flask_app = create_app(agent)
    # Suppress Flask startup banner in production
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)
    flask_app.run(
        host="127.0.0.1",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )
