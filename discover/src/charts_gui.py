#!/usr/bin/env python
"""GUI for the Discover Charts tab."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import os
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from discover.src import db_manager

class ChartsTab(ttk.Frame):
    def __init__(self, parent, app_instance):
        super().__init__(parent)
        self.app = app_instance

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- Controls ---
        controls_frame = ttk.Frame(self)
        controls_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)

        self.refresh_button = ttk.Button(controls_frame, text="Refresh Charts", command=self.refresh_charts)
        self.refresh_button.pack(side=tk.LEFT)

        self.export_button = ttk.Button(controls_frame, text="Export PNG", command=self.export_png)
        self.export_button.pack(side=tk.LEFT, padx=10)

        # --- Discussion Score Chart ---
        discussion_frame = ttk.LabelFrame(self, text="Top Themes by Discussion Score")
        discussion_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.discussion_fig = Figure(figsize=(5, 4), dpi=100)
        self.discussion_ax = self.discussion_fig.add_subplot(111)
        self.discussion_canvas = FigureCanvasTkAgg(self.discussion_fig, master=discussion_frame)
        self.discussion_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- Sentiment Score Chart ---
        sentiment_frame = ttk.LabelFrame(self, text="Top Themes by Sentiment")
        sentiment_frame.grid(row=1, column=1, sticky="nsew", padx=(0, 10), pady=(0, 10))

        self.sentiment_fig = Figure(figsize=(5, 4), dpi=100)
        self.sentiment_ax = self.sentiment_fig.add_subplot(111)
        self.sentiment_canvas = FigureCanvasTkAgg(self.sentiment_fig, master=sentiment_frame)
        self.sentiment_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.after(200, self.refresh_charts)

    def export_png(self):
        """Export both charts to PNG files."""
        file_path = filedialog.asksaveasfilename(
            defaultextension='.png',
            filetypes=[('PNG Image', '*.png'), ('All Files', '*.*')],
            title='Export Discover Charts as PNG'
        )
        if not file_path:
            return
        base, _ = os.path.splitext(file_path)
        discussion_path = f"{base}_discussion.png"
        sentiment_path = f"{base}_sentiment.png"
        try:
            self.discussion_fig.savefig(discussion_path, dpi=300, facecolor=self.discussion_fig.get_facecolor())
            self.sentiment_fig.savefig(sentiment_path, dpi=300, facecolor=self.sentiment_fig.get_facecolor())
            messagebox.showinfo('Export Complete', f"Charts saved to:\n{discussion_path}\n{sentiment_path}")
        except Exception as exc:
            messagebox.showerror('Export Error', f'Failed to export charts: {exc}')


    def refresh_charts(self):
        themes = db_manager.get_top_themes(limit=10)
        if not themes:
            self._style_no_data_message(self.discussion_ax, "No theme data available.")
            self._style_no_data_message(self.sentiment_ax, "No sentiment data available.")
            self.discussion_canvas.draw()
            self.sentiment_canvas.draw()
            return

        df = pd.DataFrame(themes)

        self._plot_discussion_scores(df)
        self._plot_sentiment_scores(df)

    def _plot_discussion_scores(self, df):
        self.discussion_ax.clear()
        df_sorted = df.sort_values('discussion_score', ascending=True)

        self.discussion_ax.barh(df_sorted['name'], df_sorted['discussion_score'], color=self.app.brand_palette)
        self.discussion_ax.set_xlabel("Discussion Score")
        self.discussion_ax.set_title("Discussion Score of Top Themes")
        self._prepare_axis(self.discussion_ax, self.discussion_fig)
        self.discussion_fig.subplots_adjust(left=0.4)
        self.discussion_canvas.draw()

    def _plot_sentiment_scores(self, df):
        self.sentiment_ax.clear()
        df_sorted = df.sort_values('sentiment_score', ascending=True)
        
        colors = ['#f2545b' if x < 0 else '#5ad1a4' for x in df_sorted['sentiment_score']]

        self.sentiment_ax.barh(df_sorted['name'], df_sorted['sentiment_score'], color=colors)
        self.sentiment_ax.set_xlabel("Sentiment Score (Compound)")
        self.sentiment_ax.set_title("Sentiment of Top Themes")
        self.sentiment_ax.axvline(0, color='grey', linewidth=0.8)
        self._prepare_axis(self.sentiment_ax, self.sentiment_fig)
        self.sentiment_fig.subplots_adjust(left=0.4)
        self.sentiment_canvas.draw()

    def _prepare_axis(self, ax, fig):
        brand_colors = self.app.brand_colors
        ax.set_facecolor(brand_colors['plot_bg'])
        fig.patch.set_facecolor(brand_colors['fig_bg'])
        ax.grid(color=brand_colors['grid'], linestyle='--', linewidth=0.6, alpha=0.35)
        ax.tick_params(colors=brand_colors['muted'], labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(brand_colors['grid'])
        ax.xaxis.label.set_color(brand_colors['muted'])
        ax.yaxis.label.set_color(brand_colors['muted'])
        ax.title.set_color(brand_colors['accent_light'])

    def _style_no_data_message(self, ax, message):
        brand_colors = self.app.brand_colors
        ax.clear()
        ax.figure.patch.set_facecolor(brand_colors['fig_bg'])
        ax.set_facecolor(brand_colors['plot_bg'])
        ax.text(0.5, 0.5, message, ha='center', va='center', color=brand_colors['muted'], fontsize=11)
        ax.axis('off')

    def apply_theme(self):
        """Reapply chart styling to match the current application theme."""
        colors = getattr(self.app, 'brand_colors', {})
        for canvas in (self.discussion_canvas, self.sentiment_canvas):
            widget = canvas.get_tk_widget()
            widget.configure(background=colors.get('fig_bg', '#ffffff'), highlightthickness=0, borderwidth=0)
        # Redraw charts so axes adopt the latest colors
        self.refresh_charts()
