
import tkinter as tk
from tkinter import ttk
import sqlite3
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from discover.src import util as discover_util

class QuadrantView(ttk.Frame):
    def __init__(self, master: tk.Widget, brand_colors: dict):
        super().__init__(master)
        self.brand_colors = brand_colors
        self.has_data = False

        # --- UI Layout ---
        controls = ttk.Frame(self)
        controls.pack(fill='x', padx=10, pady=5)

        ttk.Button(controls, text="Refresh Data", command=self.update_plot).pack(side=tk.LEFT)

        self.fig = Figure(figsize=(8, 8), facecolor=self.brand_colors['fig_bg'])
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(pady=10, padx=10, fill="both", expand=True)

        self.after(200, self.update_plot)

    def _prepare_axis(self):
        self.ax.clear()
        self.ax.set_facecolor(self.brand_colors['plot_bg'])
        self.fig.patch.set_facecolor(self.brand_colors['fig_bg'])
        self.ax.grid(color=self.brand_colors['grid'], linestyle='--', linewidth=0.6, alpha=0.35)
        self.ax.tick_params(colors=self.brand_colors['muted'], labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_color(self.brand_colors['grid'])
        self.ax.xaxis.label.set_color(self.brand_colors['muted'])
        self.ax.yaxis.label.set_color(self.brand_colors['muted'])

    def _style_no_data_message(self, message):
        self._prepare_axis()
        self.ax.text(0.5, 0.5, message, ha='center', va='center', color=self.brand_colors['muted'], fontsize=11)
        self.ax.axis('off')
        self.canvas.draw()

    def update_plot(self):
        try:
            conn = discover_util.get_db()
            df = pd.read_sql_query(
                """SELECT canonical_label, latest_signal, latest_delta
                   FROM trend_clusters
                   WHERE active = 1""",
                conn
            )
            conn.close()
        except Exception as e:
            self._style_no_data_message(f"Failed to load trend data:\n{e}")
            return

        if df.empty:
            self._style_no_data_message("No active trends found. Run the Discover pipeline first.")
            return

        df['latest_signal'] = pd.to_numeric(df['latest_signal'], errors='coerce').fillna(0.0)
        df['latest_delta'] = pd.to_numeric(df['latest_delta'], errors='coerce').fillna(0.0)

        self._prepare_axis()

        x_vals = df['latest_delta']
        y_vals = df['latest_signal']

        x_mid = x_vals.median()
        y_mid = y_vals.median()

        self.ax.axvline(x_mid, color=self.brand_colors['grid'], linewidth=1.2, linestyle='--', alpha=0.7)
        self.ax.axhline(y_mid, color=self.brand_colors['grid'], linewidth=1.2, linestyle='--', alpha=0.7)

        self.ax.set_xlabel('Velocity (Signal Change)')
        self.ax.set_ylabel('Signal (Discussion Volume)')
        self.ax.set_title('Trend Quadrant', color=self.brand_colors['accent_light'], fontsize=16)

        # Quadrant labels
        lims = self.ax.axis()
        self.ax.text(lims[1], lims[3], 'Leading', ha='right', va='top', fontsize=12, color=self.brand_colors['accent_light'], alpha=0.8)
        self.ax.text(lims[0], lims[3], 'Established', ha='left', va='top', fontsize=12, color=self.brand_colors['muted'], alpha=0.8)
        self.ax.text(lims[1], lims[2], 'Emerging', ha='right', va='bottom', fontsize=12, color=self.brand_colors['accent_light'], alpha=0.8)
        self.ax.text(lims[0], lims[2], 'Niche', ha='left', va='bottom', fontsize=12, color=self.brand_colors['muted'], alpha=0.8)

        # Scatter plot
        sizes = (y_vals / y_vals.max() * 250) + 40 # Scale point size by signal
        self.ax.scatter(x_vals, y_vals, s=sizes, alpha=0.7, edgecolors=self.brand_colors['bg'], c=self.brand_colors['accent'])

        # Add labels
        for i, txt in enumerate(df['canonical_label']):
            self.ax.annotate(txt, (x_vals[i], y_vals[i]), textcoords="offset points", xytext=(5,5), ha='left', fontsize=8, color=self.brand_colors['text'])

        self.has_data = True
        self.canvas.draw()
