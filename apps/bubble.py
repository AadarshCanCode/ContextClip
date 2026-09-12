"""
apps/bubble.py - native Tkinter context bubble.

The bubble is intentionally small and desktop-native. It is not a frontend
framework or dashboard; it is a contextual overlay attached to copy events.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional, Sequence, Tuple

from core.config import get_int, load_env_file


load_env_file()


BubbleAction = tuple[str, Callable[[], None]]


class ContextBubble:
    WIDTH = 420
    HEIGHT = 246
    MARGIN = 18

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.window: Optional[tk.Toplevel] = None
        self.hide_job: Optional[str] = None
        self.visible = False
        self.auto_hide_ms = get_int("CONTEXTCLIP_BUBBLE_AUTO_HIDE_MS", 12000)

    def show(
        self,
        title: str,
        subtitle: str,
        detail: str,
        actions: Optional[Sequence[BubbleAction]] = None,
        relation: Optional[str] = None,
        anchor: Optional[Tuple[int, int]] = None,
    ) -> None:
        """Show or update the context bubble near the supplied screen anchor."""
        self.hide()
        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.0)
        self.window.configure(bg="#0b1020")

        x, y = self._position(anchor)
        self.window.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        frame = tk.Frame(self.window, bg="#111827", padx=18, pady=15)
        frame.pack(fill="both", expand=True)

        header = tk.Frame(frame, bg="#111827")
        header.pack(fill="x")

        logo = tk.Label(
            header,
            text="CC",
            bg="#4f46e5",
            fg="#ffffff",
            width=4,
            font=("Segoe UI", 9, "bold"),
        )
        logo.pack(side="left")

        brand = tk.Frame(header, bg="#111827")
        brand.pack(side="left", padx=(10, 0), fill="x", expand=True)
        tk.Label(
            brand,
            text="ContextClip",
            bg="#111827",
            fg="#f8fafc",
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).pack(fill="x")
        tk.Label(
            brand,
            text="copy context agent",
            bg="#111827",
            fg="#64748b",
            anchor="w",
            font=("Segoe UI", 8),
        ).pack(fill="x")

        close = tk.Button(
            header,
            text="x",
            command=self.hide,
            bg="#111827",
            fg="#94a3b8",
            activebackground="#1f2937",
            activeforeground="#ffffff",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
        )
        close.pack(side="right")

        tk.Label(
            frame,
            text=title,
            bg="#111827",
            fg="#a5b4fc",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(fill="x", pady=(18, 5))

        tk.Label(
            frame,
            text=subtitle or "Something was copied",
            bg="#111827",
            fg="#f8fafc",
            anchor="w",
            justify="left",
            wraplength=self.WIDTH - 42,
            font=("Segoe UI", 12, "bold"),
        ).pack(fill="x")

        tk.Label(
            frame,
            text=detail,
            bg="#111827",
            fg="#94a3b8",
            anchor="w",
            justify="left",
            wraplength=self.WIDTH - 42,
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(6, 0))

        if relation:
            tk.Label(
                frame,
                text=relation,
                bg="#111827",
                fg="#86efac",
                anchor="w",
                justify="left",
                wraplength=self.WIDTH - 42,
                font=("Segoe UI", 9),
            ).pack(fill="x", pady=(8, 0))

        action_frame = tk.Frame(frame, bg="#111827")
        action_frame.pack(fill="x", side="bottom", pady=(14, 0))

        for label, callback in list(actions or [])[:3]:
            button = tk.Button(
                action_frame,
                text=label,
                command=callback,
                bg="#1f2937",
                fg="#e5e7eb",
                activebackground="#374151",
                activeforeground="#ffffff",
                borderwidth=1,
                relief="solid",
                highlightthickness=0,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )
            button.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.window.deiconify()
        self.window.update_idletasks()
        self.visible = True
        self._fade_in()
        if self.auto_hide_ms > 0:
            self.hide_job = self.root.after(self.auto_hide_ms, self.hide)

    def hide(self) -> None:
        if self.hide_job is not None:
            try:
                self.root.after_cancel(self.hide_job)
            except tk.TclError:
                pass
            self.hide_job = None

        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        self.window = None
        self.visible = False

    def _fade_in(self) -> None:
        if self.window is None:
            return
        try:
            alpha = float(self.window.attributes("-alpha"))
            if alpha >= 0.98:
                self.window.attributes("-alpha", 1.0)
                return
            self.window.attributes("-alpha", min(1.0, alpha + 0.12))
            self.root.after(15, self._fade_in)
        except tk.TclError:
            pass

    def _position(self, anchor: Optional[Tuple[int, int]]) -> Tuple[int, int]:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        if anchor is None:
            anchor = (screen_width - self.WIDTH - self.MARGIN, screen_height - self.HEIGHT - 64)

        x = anchor[0] + 18
        y = anchor[1] + 18
        if x + self.WIDTH + self.MARGIN > screen_width:
            x = max(self.MARGIN, anchor[0] - self.WIDTH - 18)
        if y + self.HEIGHT + self.MARGIN > screen_height:
            y = max(self.MARGIN, anchor[1] - self.HEIGHT - 18)

        x = max(self.MARGIN, min(x, screen_width - self.WIDTH - self.MARGIN))
        y = max(self.MARGIN, min(y, screen_height - self.HEIGHT - self.MARGIN))
        return x, y
