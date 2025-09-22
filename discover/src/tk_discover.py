"Focused Tkinter UI for the Discover tab (Hacker News trends)."
from __future__ import annotations

import sqlite3
import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox, ttk

import numpy as np

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from . import util
from .run_once import RunConfig, run as run_pipeline


from .timeline_view import TimelineView

class DiscoverUI(ttk.Frame):
    """Compact Discover UI dedicated to Hacker News trend signals."""

    def __init__(self, master: tk.Widget):
        super().__init__(master)
        self.pack(fill='both', expand=True)

        self.running = False
        self._run_thread: threading.Thread | None = None
        self._run_observer_prev = None
        self._stage_observer_prev = None
        self._run_observer_cb = None
        self._stage_observer_cb = None
        self._active_run_id: int | None = None

        self._trend_records: dict[int, dict[str, object]] = {}
        self._trend_details: dict[int, list[dict[str, object]]] = {}

        self.since_var = tk.StringVar(value='7')
        self.embed_var = tk.StringVar(value='C:/Users/dunca/Desktop/SFTT/models/all-MiniLM-L6-v2')
        self.status_var = tk.StringVar(value='Idle')

        # Main notebook for splitting UI
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)

        dashboard_frame = ttk.Frame(self.notebook)
        run_log_frame = ttk.Frame(self.notebook)
        timeline_frame = ttk.Frame(self.notebook)

        self.notebook.add(dashboard_frame, text='Dashboard')
        self.notebook.add(run_log_frame, text='Run & Log')
        self.notebook.add(timeline_frame, text='Timeline')

        # Build UI components into their respective frames
        self._build_dashboard_ui(dashboard_frame)
        self._build_run_log_ui(run_log_frame)
        self.timeline_view = TimelineView(timeline_frame)

        self._ensure_db_ready()
        self._register_host_hooks()
        self.bind('<Destroy>', self._on_destroy)
        self.after(400, self.refresh_all)

    # ------------------------------------------------------------------ UI builders

    def _build_dashboard_ui(self, parent: ttk.Frame):
        self._build_signal_chart(parent)
        self._build_trend_section(parent)

    def _build_run_log_ui(self, parent: ttk.Frame):
        self._build_controls(parent)
        
        log_container = ttk.LabelFrame(parent, text="Real-time Log")
        log_container.pack(fill='both', expand=True, padx=12, pady=(10, 0))
        self.log_text = tk.Text(log_container, height=15, wrap='word', relief='flat', state='disabled')
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)

        self._build_run_history(parent)

    def _build_controls(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent)
        controls.pack(fill='x', padx=12, pady=8)

        # Load config
        self.config = util.load_config()
        self.comment_weight_var = tk.StringVar(value=self.config.get('comment_weight', 0.6))
        self.sim_threshold_var = tk.StringVar(value=self.config.get('sim_threshold', 0.78))
        self.stale_decay_factor_var = tk.StringVar(value=self.config.get('stale_decay_factor', 0.9))
        self.sentiment_weight_var = tk.StringVar(value=self.config.get('sentiment_weight', 0.5))

        # UI elements
        ttk.Label(controls, text='Lookback: 30 days').pack(side='left', padx=(4, 12))

        ttk.Label(controls, text='Embedding model:').pack(side='left')
        ttk.Entry(controls, textvariable=self.embed_var, width=32).pack(side='left', padx=(4, 12))

        self.run_button = ttk.Button(controls, text='Run Discover', command=self._on_run_clicked)
        self.run_button.pack(side='left', padx=(12, 0))
        self.stop_button = ttk.Button(controls, text='Stop', command=self._on_stop_clicked, state='disabled')
        self.stop_button.pack(side='left', padx=(6, 0))

        ttk.Label(controls, textvariable=self.status_var).pack(side='right')
        self.purge_button = ttk.Button(controls, text='Purge DB', command=self._confirm_purge)
        self.purge_button.pack(side='right', padx=(0, 8))

        # Config settings
        config_frame = ttk.LabelFrame(parent, text="Configuration")
        config_frame.pack(fill='x', padx=12, pady=8)

        ttk.Label(config_frame, text="Comment Weight:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(config_frame, textvariable=self.comment_weight_var).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Sim Threshold:").grid(row=0, column=2, padx=5, pady=5)
        ttk.Entry(config_frame, textvariable=self.sim_threshold_var).grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(config_frame, text="Stale Decay Factor:").grid(row=1, column=0, padx=5, pady=5)
        ttk.Entry(config_frame, textvariable=self.stale_decay_factor_var).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Sentiment Weight:").grid(row=1, column=2, padx=5, pady=5)
        ttk.Entry(config_frame, textvariable=self.sentiment_weight_var).grid(row=1, column=3, padx=5, pady=5)

        save_button = ttk.Button(config_frame, text="Save Config", command=self._save_config)
        save_button.grid(row=2, column=3, padx=5, pady=5, sticky='e')

    def _save_config(self):
        self.config['comment_weight'] = float(self.comment_weight_var.get())
        self.config['sim_threshold'] = float(self.sim_threshold_var.get())
        self.config['stale_decay_factor'] = float(self.stale_decay_factor_var.get())
        self.config['sentiment_weight'] = float(self.sentiment_weight_var.get())
        util.save_config(self.config)
        messagebox.showinfo("Config Saved", "Configuration saved successfully.")

    def _build_signal_chart(self, parent: ttk.Frame) -> None:
        chart_frame = ttk.Frame(parent)
        chart_frame.pack(fill='x', padx=12, pady=(0, 8))

        self.signal_fig = Figure(figsize=(6, 2.8), dpi=100)
        self.signal_ax = self.signal_fig.add_subplot(111)
        self.signal_canvas = FigureCanvasTkAgg(self.signal_fig, master=chart_frame)
        self.signal_canvas.get_tk_widget().pack(fill='both', expand=True)

    def _build_trend_section(self, parent: ttk.Frame) -> None:
        container = ttk.Frame(parent)
        container.pack(fill='both', expand=True, padx=12, pady=(0, 8))

        left = ttk.Frame(container)
        left.pack(side='left', fill='both', expand=True)

        right = ttk.LabelFrame(container, text='Hot terms')
        right.pack(side='right', fill='y', padx=(12, 0))

        columns = ('label', 'source', 'signal', 'delta', 'stories', 'comments', 'novelty', 'persistence')
        self.trend_tree = ttk.Treeview(left, columns=columns, show='headings', height=8)
        self.trend_tree.heading('label', text='Theme')
        self.trend_tree.heading('source', text='Source')
        self.trend_tree.heading('signal', text='Signal')
        self.trend_tree.heading('delta', text='? prev')
        self.trend_tree.heading('stories', text='Items')
        self.trend_tree.heading('comments', text='Interactions')
        self.trend_tree.heading('novelty', text='Novelty')
        self.trend_tree.heading('persistence', text='Persistence')
        self.trend_tree.column('label', width=220, anchor='w')
        self.trend_tree.column('source', width=100, anchor='w')
        self.trend_tree.column('signal', width=80, anchor='e')
        self.trend_tree.column('delta', width=80, anchor='e')
        self.trend_tree.column('stories', width=70, anchor='center')
        self.trend_tree.column('comments', width=90, anchor='center')
        self.trend_tree.column('novelty', width=80, anchor='center')
        self.trend_tree.column('persistence', width=100, anchor='center')
        self.trend_tree.pack(fill='x', expand=False, side='top')
        self.trend_tree.bind('<<TreeviewSelect>>', self._on_trend_selected)

        detail_frame = ttk.Frame(left)
        detail_frame.pack(fill='both', expand=True, pady=(8, 0))

        self.item_tree = ttk.Treeview(
            detail_frame,
            columns=('title', 'metric1', 'metric2', 'age'),
            show='headings',
            height=6,
        )
        self.item_tree.heading('title', text='Item')
        self.item_tree.heading('metric1', text='Metric 1')
        self.item_tree.heading('metric2', text='Metric 2')
        self.item_tree.heading('age', text='Age')
        self.item_tree.column('title', width=360, anchor='w')
        self.item_tree.column('metric1', width=70, anchor='center')
        self.item_tree.column('metric2', width=90, anchor='center')
        self.item_tree.column('age', width=110, anchor='center')
        self.item_tree.pack(fill='x', expand=False, side='top')

        self.discovery_text = tk.Text(detail_frame, height=6, wrap='word')
        self.discovery_text.configure(state='disabled')
        self.discovery_text.pack(fill='both', expand=True, pady=(6, 0))

        hot_columns = ('term', 'ratio', 'score', 'delta')
        self.hot_terms_tree = ttk.Treeview(right, columns=hot_columns, show='headings', height=12)
        self.hot_terms_tree.heading('term', text='Term')
        self.hot_terms_tree.heading('ratio', text='Surge x')
        self.hot_terms_tree.heading('score', text='Score')
        self.hot_terms_tree.heading('delta', text='? score')
        self.hot_terms_tree.column('term', width=140, anchor='w')
        self.hot_terms_tree.column('ratio', width=70, anchor='e')
        self.hot_terms_tree.column('score', width=70, anchor='e')
        self.hot_terms_tree.column('delta', width=80, anchor='e')
        self.hot_terms_tree.pack(fill='y', expand=False, padx=6, pady=6)

    def _build_run_history(self, parent: ttk.Frame) -> None:
        run_frame = ttk.LabelFrame(parent, text='Recent runs')
        run_frame.pack(fill='x', padx=12, pady=(0, 12))

        columns = ('started', 'status', 'message')
        self.run_tree = ttk.Treeview(run_frame, columns=columns, show='headings', height=5)
        self.run_tree.heading('started', text='Started')
        self.run_tree.heading('status', text='Status')
        self.run_tree.heading('message', text='Summary')
        self.run_tree.column('started', width=160)
        self.run_tree.column('status', width=90)
        self.run_tree.column('message', width=420)
        self.run_tree.pack(fill='x', expand=True, padx=6, pady=6)

    def _log_message(self, msg: str):
        if not hasattr(self, 'log_text') or not self.log_text.winfo_exists():
            return
        self.log_text.configure(state='normal')
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')

    # ------------------------------------------------------------------ actions

    def _on_stop_clicked(self) -> None:
        if not self.running:
            return
        self.status_var.set('Cancelling...')
        self._log_message("Cancellation requested by user.")
        self.stop_button.configure(state='disabled')
        util.cancel_current_run()

    def _on_run_clicked(self) -> None:
        if self.running:
            return
        config = RunConfig(
            since_arg='30d',
            since_days=30,
            embed_model=self.embed_var.get(),
        )

        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')
        self._log_message(f"Starting run with lookback=30d, model={self.embed_var.get()}")

        self._install_observers()
        util.reset_cancel_event()

        self.running = True
        self.run_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.purge_button.configure(state='disabled')
        self.status_var.set('Starting...')

        thread = threading.Thread(target=self._run_pipeline_thread, args=(config,), daemon=True)
        self._run_thread = thread
        thread.start()

    def _run_pipeline_thread(self, config: RunConfig) -> None:
        try:
            results = run_pipeline(config)
        except util.CancelledError:
            self.after(0, self._handle_run_cancelled)
            return
        except Exception as exc:  # pragma: no cover - UI thread
            self.after(0, self._handle_run_error, exc)
            return
        self.after(0, self._handle_run_success, results)

    # ------------------------------------------------------------------ observer plumbing

    def _install_observers(self) -> None:
        def run_cb(event: dict[str, object]) -> None:
            self.after(0, self._handle_run_event_ui, event)

        def stage_cb(event: dict[str, object]) -> None:
            self.after(0, self._handle_stage_event_ui, event)

        self._run_observer_cb = run_cb
        self._stage_observer_cb = stage_cb
        self._run_observer_prev = util.set_run_observer(run_cb)
        self._stage_observer_prev = util.set_stage_observer(stage_cb)

    def _remove_observers(self) -> None:
        util.set_run_observer(self._run_observer_prev)
        util.set_stage_observer(self._stage_observer_prev)
        self._run_observer_prev = None
        self._stage_observer_prev = None
        self._run_observer_cb = None
        self._stage_observer_cb = None
        self._active_run_id = None

    def _handle_run_event_ui(self, event: dict[str, object]) -> None:
        run_id = event.get('run_id')
        if run_id is None:
            return
        try:
            run_id_int = int(run_id)
        except (TypeError, ValueError):
            return
        event_type = event.get('event')
        if event_type == 'run_start':
            self._active_run_id = run_id_int
            self.status_var.set('Running...')
            self._log_message(f"Run {run_id_int} started.")
        elif event_type == 'run_end':
            self.status_var.set('Idle')
            self._active_run_id = None
            self._log_message(f"Run {run_id} finished. Status: {event.get('status')}. Message: {event.get('message')}")
            self.refresh_all()

    def _handle_stage_event_ui(self, event: dict[str, object]) -> None:
        stage = str(event.get('stage') or '')
        detail = str(event.get('detail') or '')
        status = str(event.get('status') or 'running')
        msg = f"[{stage}] {status}: {detail}"
        self._log_message(msg)
        if stage:
            stage_name = stage.replace('_', ' ').title()
            self.status_var.set(f"{stage_name} {detail}")

    # ------------------------------------------------------------------ run lifecycle handlers

    def _handle_run_cancelled(self) -> None:
        self._remove_observers()
        self.running = False
        self._run_thread = None
        self.run_button.configure(state='normal')
        self.stop_button.configure(state='disabled')
        self.purge_button.configure(state='normal')
        self.status_var.set('Cancelled')
        self._log_message("Run was cancelled.")
        self.refresh_all()

    def _handle_run_success(self, results: dict[str, object]) -> None:
        self._remove_observers()
        self.running = False
        self._run_thread = None
        self.run_button.configure(state='normal')
        self.stop_button.configure(state='disabled')
        self.purge_button.configure(state='normal')
        self.status_var.set('Completed')
        self._log_message(f"Run completed successfully. Results: {results}")
        self.refresh_all()

    def _handle_run_error(self, exc: Exception) -> None:
        self._remove_observers()
        self.running = False
        self._run_thread = None
        self.run_button.configure(state='normal')
        self.stop_button.configure(state='disabled')
        self.purge_button.configure(state='normal')
        self.status_var.set('Error')
        self._log_message(f"Run failed with error: {exc}")
        messagebox.showerror('Discover run failed', str(exc))

    # ------------------------------------------------------------------ refresh helpers

    def refresh_all(self) -> None:
        self._refresh_trends()
        self._refresh_hot_terms()
        self._refresh_run_history()

    def _refresh_trends(self) -> None:
        conn = util.get_db()
        try:
            rows = conn.execute(
                """
                SELECT
                    tc.trend_id,
                    tc.canonical_label,
                    tc.canonical_terms,
                    tc.latest_signal,
                    tc.latest_delta,
                    tc.latest_story_count,
                    tc.latest_comment_count,
                    tc.novelty,
                    tc.persistence,
                    tc.fingerprint,
                    SUM(CASE WHEN tcm.obj_type = 'story' THEN 1 ELSE 0 END) as hn_count
                FROM trend_clusters tc
                LEFT JOIN trend_cluster_members tcm ON tc.trend_id = tcm.trend_id
                WHERE tc.active = 1
                GROUP BY tc.trend_id
                ORDER BY tc.latest_signal DESC
                LIMIT 20
                """
            ).fetchall()

            self._trend_records = {}
            self._trend_details = {}
            self.trend_tree.delete(*self.trend_tree.get_children())

            top_scores: list[float] = []
            top_labels: list[str] = []
            top_ids: list[int] = []

            for row in rows:
                trend_id = int(row['trend_id'])
                self._trend_records[trend_id] = dict(row)
                
                source_parts = []
                hn_count = int(row['hn_count'] or 0)
                if hn_count > 0:
                    source_parts.append(f"HN: {hn_count}")
                source_str = ', '.join(source_parts)

                self.trend_tree.insert(
                    '',
                    tk.END,
                    iid=str(trend_id),
                    values=(
                        row['canonical_label'],
                        source_str,
                        f"{float(row['latest_signal'] or 0):.1f}",
                        f"{float(row['latest_delta'] or 0):+.1f}",
                        int(row['latest_story_count'] or 0),
                        int(row['latest_comment_count'] or 0),
                        f"{float(row['novelty'] or 0):.2f}",
                        f"{float(row['persistence'] or 0):.2f}",
                    ),
                )
                top_ids.append(trend_id)
                top_scores.append(float(row['latest_signal'] or 0.0))
                top_labels.append(str(row['canonical_label'] or row['fingerprint'] or trend_id))

            self._render_signal_chart(top_labels[:5], top_scores[:5])

            if top_ids:
                first = str(top_ids[0])
                self.trend_tree.selection_set(first)
                self.trend_tree.focus(first)
                self._populate_trend_details(top_ids[0], conn)
            else:
                self.item_tree.delete(*self.item_tree.get_children())
                self.discovery_text.configure(state='normal')
                self.discovery_text.delete('1.0', tk.END)
                self.discovery_text.insert(tk.END, 'Run the pipeline to surface new themes.')
                self.discovery_text.configure(state='disabled')
        finally:
            conn.close()

    def _render_signal_chart(self, labels: list[str], scores: list[float]) -> None:
        self.signal_ax.clear()
        if not scores:
            self.signal_ax.set_title('No trends yet - run the pipeline')
            self.signal_ax.set_xticks([])
            self.signal_ax.set_yticks([])
            self.signal_canvas.draw_idle()
            return

        y_pos = np.arange(len(scores))
        bars = self.signal_ax.barh(y_pos, scores, color='#4F6BED')
        self.signal_ax.set_yticks(y_pos)
        self.signal_ax.set_yticklabels(labels)
        self.signal_ax.invert_yaxis()
        self.signal_ax.set_xlabel('Signal strength')
        self.signal_ax.set_title('Top emerging themes')
        for bar, value in zip(bars, scores):
            self.signal_ax.text(value + 0.2, bar.get_y() + bar.get_height() / 2, f"{value:.1f}", va='center')
        self.signal_fig.tight_layout()
        self.signal_canvas.draw_idle()

    def _refresh_hot_terms(self) -> None:
        conn = util.get_db()
        try:
            rows = conn.execute(
                """
                SELECT term, current_score, baseline_score, surge_ratio, surge_delta
                FROM term_surge_snapshots
                WHERE run_id = (
                    SELECT run_id FROM term_surge_snapshots ORDER BY run_id DESC LIMIT 1
                )
                ORDER BY surge_ratio DESC
                LIMIT 20
                """
            ).fetchall()
        finally:
            conn.close()

        self.hot_terms_tree.delete(*self.hot_terms_tree.get_children())
        if not rows:
            self.hot_terms_tree.insert('', tk.END, values=('-', '-', '-', '-'))
            return
        for row in rows:
            term = row['term']
            ratio = float(row['surge_ratio'] or 0.0)
            score = float(row['current_score'] or 0.0)
            delta = float(row['surge_delta'] or 0.0)
            self.hot_terms_tree.insert(
                '',
                tk.END,
                values=(
                    term,
                    f"{ratio:.2f}",
                    f"{score:.1f}",
                    f"{delta:+.1f}",
                ),
            )

    def _signal_delta(self, conn: sqlite3.Connection, trend_id: int) -> float | None:
        rows = conn.execute(
            """
            SELECT signal
            FROM trend_snapshots
            WHERE trend_id = ?
            ORDER BY snapshot_id DESC
            LIMIT 2
            """,
            (trend_id,),
        ).fetchall()
        if len(rows) < 2:
            return None
        return float(rows[0]['signal']) - float(rows[1]['signal'])

    def _populate_trend_details(self, trend_id: int | None, conn: sqlite3.Connection | None = None) -> None:
        self.item_tree.delete(*self.item_tree.get_children())
        self.discovery_text.configure(state='normal')
        self.discovery_text.delete('1.0', tk.END)

        if trend_id is None:
            self.discovery_text.insert(tk.END, 'Select a trend to inspect its constituent items.')
            self.discovery_text.configure(state='disabled')
            return

        close_conn = False
        if conn is None:
            conn = util.get_db()
            close_conn = True
        
        try:
            members = conn.execute(
                "SELECT obj_type, obj_id FROM trend_cluster_members WHERE trend_id = ?", (trend_id,)
            ).fetchall()

            details = []
            for member in members:
                if member['obj_type'] == 'story':
                    row = conn.execute("SELECT id, title, score, descendants, time, url FROM stories WHERE id = ?", (member['obj_id'],)).fetchone()
                    if not row: continue
                    age = self._format_age(int(row['time'] or 0))
                    self.item_tree.heading('metric1', text='Score')
                    self.item_tree.heading('metric2', text='Comments')
                    self.item_tree.insert('', tk.END, values=(row['title'], row['score'], row['descendants'], age))
                    details.append(dict(row))

            self._trend_details[trend_id] = details

            record = self._trend_records.get(trend_id, {})
            summary = record.get('llm_summary') or record.get('canonical_label') or 'Trend'
            summary_lines = [
                summary,
                '',
                f"Signal: {float(record.get('latest_signal', 0)):.1f}",
                f"Items in cluster: {len(details)}",
                f"Novelty: {float(record.get('novelty', 0)):.2f}  |  Persistence: {float(record.get('persistence', 0)):.2f}",
            ]
            self.discovery_text.insert(tk.END, '\n'.join(summary_lines))

            if details:
                self.discovery_text.insert(tk.END, '\n\nRepresentative Items:\n')
                for detail_item in details[:5]:
                    if 'title' in detail_item:  # Story
                        self.discovery_text.insert(tk.END, f"- {detail_item['title']}\n")

        finally:
            if close_conn:
                conn.close()
            self.discovery_text.configure(state='disabled')

    def _refresh_run_history(self) -> None:
        if not hasattr(self, 'run_tree'): return
        conn = util.get_db()
        try:
            rows = conn.execute(
                """
                SELECT id, started_at, finished_at, status, message
                FROM run_logs
                ORDER BY id DESC
                LIMIT 12
                """
            ).fetchall()
            self.run_tree.delete(*self.run_tree.get_children())
            for row in rows:
                stamp = row['finished_at'] or row['started_at']
                self.run_tree.insert(
                    '',
                    tk.END,
                    values=(stamp or '-', row['status'], row['message'] or ''),
                )
        finally:
            conn.close()

    # ------------------------------------------------------------------ misc helpers

    def _format_age(self, ts_unix: int) -> str:
        if ts_unix <= 0:
            return 'unknown'
        dt = datetime.fromtimestamp(ts_unix, tz=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days > 1:
            return f"{days} days ago"
        hours = delta.seconds // 3600
        if hours:
            return f"{hours}h ago"
        minutes = (delta.seconds // 60) % 60
        return f"{minutes}m ago"

    def _confirm_purge(self) -> None:
        if self.running:
            messagebox.showwarning('Busy', 'Wait for the current run to finish before purging.')
            return
        if not messagebox.askyesno('Purge Discover data', 'This will delete trend history. Continue?'):
            return
        self._purge_database()

    def _purge_database(self) -> None:
        db_path = util.DB_PATH
        wal_path = db_path.with_name(db_path.name + '-wal')
        shm_path = db_path.with_name(db_path.name + '-shm')
        errors = []
        for path in (db_path, wal_path, shm_path):
            try:
                if path.exists():
                    path.unlink()
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        if errors:
            messagebox.showerror('Purge failed', 'Unable to remove database files:\n' + '\n'.join(errors))
        else:
            messagebox.showinfo('Discover', 'Database removed. A fresh run will recreate it.')
            self._ensure_db_ready()
            self.refresh_all()

    def _ensure_db_ready(self) -> None:
        conn = util.get_db()
        try:
            util.ensure_schema(conn)
            util.ensure_views(conn)
        finally:
            conn.close()

    def _register_host_hooks(self) -> None:
        host = getattr(self.master, 'master', None)
        if host is None:
            return
        try:
            setattr(host, 'discovery_tree', self.item_tree)
            if hasattr(host, '_on_discovery_select'):
                self.trend_tree.bind('<<TreeviewSelect>>', host._on_discovery_select)
        except Exception:
            pass
        try:
            setattr(host, 'discovery_text', self.discovery_text)
            if hasattr(host, '_clear_discovery_detail'):
                host._clear_discovery_detail()
        except Exception:
            pass

    def _on_trend_selected(self, _event=None) -> None:
        selection = self.trend_tree.selection()
        if not selection:
            self._populate_trend_details(None)
            return
        trend_id = int(selection[0])
        self._populate_trend_details(trend_id)

    def _on_destroy(self, _event=None) -> None:
        self._remove_observers()


__all__ = ['DiscoverUI']