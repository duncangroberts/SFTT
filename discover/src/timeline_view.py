"""Timeline view for the Discover module."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from . import util

class TimelineView(ttk.Frame):
    """Timeline view for the Discover module."""

    def __init__(self, master: tk.Widget):
        super().__init__(master)
        self.pack(fill='both', expand=True)

        self.figure = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, self)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)

        self.ax_signal = self.figure.add_subplot(211)
        self.ax_sentiment = self.figure.add_subplot(212)

        self.refresh()

    def refresh(self):
        """Refresh the timeline view."""
        self.ax_signal.clear()
        self.ax_sentiment.clear()

        conn = util.get_db()
        df = pd.read_sql_query("SELECT * FROM trend_history", conn)
        conn.close()

        if df.empty:
            self.ax_signal.set_title("No data to display")
            self.canvas.draw()
            return

        for trend_id in df['trend_id'].unique():
            trend_df = df[df['trend_id'] == trend_id]
            self.ax_signal.plot(trend_df['run_id'], trend_df['signal'], label=f"Theme {trend_id}")
            self.ax_sentiment.plot(trend_df['run_id'], trend_df['sentiment'], label=f"Theme {trend_id}")

        self.ax_signal.set_title("Theme Signal vs. Time")
        self.ax_signal.set_ylabel("Signal")
        self.ax_signal.legend()

        self.ax_sentiment.set_title("Theme Sentiment vs. Time")
        self.ax_sentiment.set_xlabel("Run ID")
        self.ax_sentiment.set_ylabel("Sentiment")
        self.ax_sentiment.legend()

        self.figure.tight_layout()
        self.canvas.draw()
