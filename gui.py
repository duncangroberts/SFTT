import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue
import sqlite3
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
import ui_run_controller
import ingest
import db as database
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd
import discovery_llm
from discover.src.discover_gui import DiscoverTab
from discover.src.charts_gui import ChartsTab
from firestore_sync_gui import FirestoreSyncTab
from llm_client import LlamaCppClient, LLMClientError

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Big Bob's Bombhole | Short Fuse Research")
        self.geometry("1100x800")
        self.export_max_edge_px = 2560
        self.export_default_dpi = 300
        self.quadrant_has_data = False
        self.comment_has_data = False
        self.traj_has_data = False
        self.trend_has_data = False
        self.discovery_running = False
        self.discovery_results: dict[str, object] | None = None
        self.discovery_theme_rows: dict[str, dict[str, object]] = {}
        self.llm_prompt_text: tk.Text | None = None

        self.theme_configs = {
            'dark': {
                'bg': '#000000',
                'panel': '#111111',
                'fig_bg': '#000000',
                'plot_bg': '#000000',
                'accent': '#ff6b35',
                'accent_light': '#ffa351',
                'secondary': '#1f1f1f',
                'text': '#f5f7fa',
                'muted': '#b0b7c3',
                'grid': '#2a2a2a'
            },
            'light': {
                'bg': '#d9d9d9',
                'panel': '#f0f0f0',
                'fig_bg': '#ffffff',
                'plot_bg': '#ffffff',
                'accent': '#2f5597',
                'accent_light': '#3f6fb5',
                'secondary': '#c5c5c5',
                'text': '#1f1f1f',
                'muted': '#4f4f4f',
                'grid': '#b5b5b5'
            }
        }
        self.current_theme = 'dark'
        self.brand_palette = ['#ff6b35', '#f7c843', '#3ab4f2', '#f2545b', '#b353ff', '#5ad1a4']
        self.brand_colors = dict(self.theme_configs[self.current_theme])
        self.dark_mode_var = tk.BooleanVar(value=True)
        self.logo_image: tk.PhotoImage | None = None
        self._configure_brand_styles()
        self._load_brand_logo()
        self._build_brand_header()

        # Thread-safe logging queue and task state
        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._task_thread: threading.Thread | None = None
        self._running: bool = False

        self.module_notebook = ttk.Notebook(self, style='BrandNotebook.TNotebook')
        self.module_notebook.pack(pady=10, padx=10, fill="both", expand=True)

        tech_module = ttk.Frame(self.module_notebook)
        tech_module.grid_rowconfigure(0, weight=1)
        tech_module.grid_columnconfigure(0, weight=1)
        self.module_notebook.add(tech_module, text="Technology Trends")

        self.tech_notebook = ttk.Notebook(tech_module, style='BrandNotebook.TNotebook')
        self.tech_notebook.pack(fill="both", expand=True, padx=5, pady=5)

        discover_module = ttk.Frame(self.module_notebook)
        discover_module.grid_rowconfigure(0, weight=1)
        discover_module.grid_columnconfigure(0, weight=1)
        self.module_notebook.add(discover_module, text="Discover")

        self.discover_notebook = ttk.Notebook(discover_module, style='BrandNotebook.TNotebook')
        self.discover_notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Firestore Sync Tab
        sync_module = ttk.Frame(self.module_notebook)
        sync_module.grid_rowconfigure(0, weight=1)
        sync_module.grid_columnconfigure(0, weight=1)
        self.module_notebook.add(sync_module, text="Firestore Sync")
        firestore_sync_tab = FirestoreSyncTab(sync_module, self)
        firestore_sync_tab.pack(fill="both", expand=True, padx=5, pady=5)

        # Technology Trends sub-tabs
        self.create_run_view(self.tech_notebook)
        self.create_db_view(self.tech_notebook)
        self.create_analyst_view(self.tech_notebook)
        self.create_quadrant_view(self.tech_notebook)
        self.create_config_view(self.tech_notebook)
        self.create_comment_volume_view(self.tech_notebook)
        self.create_trajectories_view(self.tech_notebook)
        self.create_trends_view(self.tech_notebook)

        # Discover sub-tabs
        self.create_discovery_view(self.discover_notebook)
        self.create_discover_charts_view(self.discover_notebook)

        # Log startup environment details after UI is ready
        try:
            self.after(200, self.log_startup_info)
            self.after(100, self._drain_log_queue)
        except Exception:
            pass

    def _configure_brand_styles(self):
        self.configure(bg=self.brand_colors['bg'])
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass

        panel = self.brand_colors['panel']
        text_color = self.brand_colors['text']
        accent = self.brand_colors['accent']
        muted = self.brand_colors['muted']
        fig_bg = self.brand_colors['fig_bg']

        style.configure('.', background=panel, foreground=text_color, font=('Segoe UI', 10))
        style.configure('BrandHeader.TFrame', background=self.brand_colors['bg'])
        style.configure('BrandHeader.TLabel', background=self.brand_colors['bg'])
        style.configure('BrandHeaderTitle.TLabel', background=self.brand_colors['bg'], foreground=self.brand_colors['accent_light'], font=('Segoe UI Semibold', 20))
        style.configure('BrandHeaderSubtitle.TLabel', background=self.brand_colors['bg'], foreground=muted, font=('Segoe UI', 11))
        style.configure('BrandNotebook.TNotebook', background=self.brand_colors['bg'], borderwidth=0)
        style.configure('TNotebook', background=self.brand_colors['bg'])
        style.configure('TNotebook.Tab', background=panel, foreground=muted, padding=[12, 6])
        style.map('TNotebook.Tab', background=[('selected', accent)], foreground=[('selected', text_color)])
        style.configure('Brand.Treeview', background=panel, foreground=text_color, fieldbackground=panel, rowheight=24, borderwidth=0)
        style.configure('Treeview.Heading', background=self.brand_colors['secondary'], foreground=text_color, relief='flat')
        style.map('Brand.Treeview', background=[('selected', self.brand_colors['accent_light'])], foreground=[('selected', self.brand_colors['bg'])])
        style.configure('TLabel', background=panel, foreground=text_color)
        style.configure('TFrame', background=panel)
        style.configure('TLabelframe', background=panel, foreground=text_color)
        style.configure('TLabelframe.Label', background=panel, foreground=text_color)
        style.configure('TButton', background=accent, foreground=self.brand_colors['bg'], borderwidth=0)
        style.map('TButton', background=[('active', self.brand_colors['accent_light'])], foreground=[('active', self.brand_colors['bg'])])
        style.configure('TCombobox', fieldbackground=fig_bg, background=fig_bg, foreground=text_color)
        style.map('TCombobox', fieldbackground=[('readonly', fig_bg)], foreground=[('readonly', text_color)])
        style.configure('TSpinbox', fieldbackground=fig_bg, foreground=text_color, background=fig_bg)
        style.configure('TEntry', fieldbackground=fig_bg, foreground=text_color, insertcolor=text_color)
        style.map('TEntry', fieldbackground=[('disabled', panel)], foreground=[('disabled', muted)])
        style.configure('Brand.Horizontal.TProgressbar', background=accent, troughcolor=fig_bg, borderwidth=0)
        style.configure('ThemeToggle.TCheckbutton', background=self.brand_colors['bg'], foreground=text_color)
        style.map('ThemeToggle.TCheckbutton', background=[('active', panel)], foreground=[('active', text_color)])

    def _update_custom_widget_colors(self):
        if hasattr(self, 'log_text'):
            self.log_text.configure(bg=self.brand_colors['fig_bg'], fg=self.brand_colors['text'], insertbackground=self.brand_colors['accent'])
        if hasattr(self, 'theme_toggle'):
            self.theme_toggle.configure(style='ThemeToggle.TCheckbutton')
        if hasattr(self, 'discovery_text') and self.discovery_text is not None:
            self.discovery_text.configure(bg=self.brand_colors['fig_bg'], fg=self.brand_colors['text'], insertbackground=self.brand_colors['accent'])

    def _refresh_plots_after_theme_change(self):
        if hasattr(self, 'fig'):
            self.update_quadrant_plot()
        if hasattr(self, 'comment_fig'):
            self.update_comment_volume_plot()
        if hasattr(self, 'traj_fig'):
            self.update_trajectories_plot()
        if hasattr(self, 'trend_fig'):
            self.update_trends_plot()

    def _apply_theme(self, theme_name: str):
        theme_key = (theme_name or '').lower()
        if theme_key not in self.theme_configs:
            return
        self.current_theme = theme_key
        self.brand_colors = dict(self.theme_configs[theme_key])
        self.dark_mode_var.set(self.current_theme == 'dark')
        self._configure_brand_styles()
        self._update_custom_widget_colors()
        for notebook in (getattr(self, 'module_notebook', None), getattr(self, 'tech_notebook', None), getattr(self, 'discover_notebook', None)):
            if notebook is not None:
                try:
                    notebook.configure(style='BrandNotebook.TNotebook')
                except tk.TclError:
                    pass
        self._refresh_plots_after_theme_change()
        if hasattr(self, 'discover_tab') and self.discover_tab is not None:
            self.discover_tab.apply_theme()
        if hasattr(self, 'discover_charts_tab') and self.discover_charts_tab is not None:
            self.discover_charts_tab.apply_theme()

    def _toggle_theme(self):
        requested_theme = 'dark' if self.dark_mode_var.get() else 'light'
        self._apply_theme(requested_theme)

    def _load_brand_logo(self):
        logo_path = Path('assets/short_fuse_logo.png')
        if not logo_path.exists():
            self.logo_image = None
            return
        try:
            img = tk.PhotoImage(file=str(logo_path))
            max_width = 200
            if img.width() > max_width:
                ratio = max(1, img.width() // max_width)
                img = img.subsample(ratio, ratio)
            self.logo_image = img
        except Exception:
            self.logo_image = None

    def _build_brand_header(self):
        header = ttk.Frame(self, style='BrandHeader.TFrame')
        header.pack(fill='x', padx=14, pady=(12, 4))
        if self.logo_image is not None:
            logo_label = ttk.Label(header, image=self.logo_image, style='BrandHeader.TLabel')
            logo_label.pack(side=tk.LEFT, padx=(0, 12))
        title_frame = ttk.Frame(header, style='BrandHeader.TFrame')
        title_frame.pack(side=tk.LEFT, fill='x', expand=True)
        ttk.Label(title_frame, text="Big Bob's Bombhole", style='BrandHeaderTitle.TLabel').pack(anchor='w')
        ttk.Label(title_frame, text='Short Fuse Research - Emerging Technology Intelligence Dashboard', style='BrandHeaderSubtitle.TLabel').pack(anchor='w')
        toggle_frame = ttk.Frame(header, style='BrandHeader.TFrame')
        toggle_frame.pack(side=tk.RIGHT, padx=(8, 0))
        self.theme_toggle = ttk.Checkbutton(toggle_frame, text='Dark Mode', style='ThemeToggle.TCheckbutton', variable=self.dark_mode_var, command=self._toggle_theme)
        self.theme_toggle.pack(anchor='e')

    def _prepare_axis(self, ax, fig, *, grid=True):
        ax.axis('on')
        ax.set_facecolor(self.brand_colors['plot_bg'])
        fig.patch.set_facecolor(self.brand_colors['fig_bg'])
        if grid:
            ax.grid(color=self.brand_colors['grid'], linestyle='--', linewidth=0.6, alpha=0.35)
        else:
            ax.grid(False)
        ax.tick_params(colors=self.brand_colors['muted'], labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(self.brand_colors['grid'])
        ax.xaxis.label.set_color(self.brand_colors['muted'])
        ax.yaxis.label.set_color(self.brand_colors['muted'])

    def _style_no_data_message(self, ax, message):
        ax.figure.patch.set_facecolor(self.brand_colors['fig_bg'])
        ax.set_facecolor(self.brand_colors['plot_bg'])
        ax.text(0.5, 0.5, message, ha='center', va='center', color=self.brand_colors['muted'], fontsize=11)
        ax.axis('off')

    def create_run_view(self, notebook):
        run_frame = ttk.Frame(notebook)
        notebook.add(run_frame, text="Run")

        run_month_frame = ttk.Frame(run_frame)
        run_month_frame.pack(pady=10, fill="x")
        ttk.Label(run_month_frame, text="Run Selected Month (YYYY-MM):").pack(side=tk.LEFT, padx=5)
        self.run_month_entry = ttk.Entry(run_month_frame, width=10)
        try:
            last_month = (datetime.utcnow().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        except Exception:
            last_month = "2025-01"
        self.run_month_entry.insert(0, last_month)
        self.run_month_entry.pack(side=tk.LEFT)
        self.run_month_button = ttk.Button(run_month_frame, text="Run Month", command=self.run_selected_month)
        self.run_month_button.pack(side=tk.LEFT, padx=5)

        self.purge_button = ttk.Button(
            run_frame,
            text="Purge Database",
            command=self.purge_database
        )
        self.purge_button.pack(pady=10)

        self.progress = ttk.Progressbar(run_frame, orient="horizontal", mode="determinate", length=500, style='Brand.Horizontal.TProgressbar')
        self.progress.pack(pady=5, fill="x")
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(run_frame, textvariable=self.status_var).pack(anchor="w")

        self.log_text = tk.Text(run_frame, height=20, width=80, relief='flat', highlightthickness=0)
        self.log_text.configure(bg=self.brand_colors['fig_bg'], fg=self.brand_colors['text'], insertbackground=self.brand_colors['accent'])
        self.log_text.pack(pady=10, fill='both', expand=True)

    def _set_running(self, running: bool):
        self._running = running
        state = ("disabled" if running else "normal")
        for btn in [self.run_month_button, self.purge_button]:
            try:
                btn.configure(state=state)
            except Exception:
                pass

    def _set_status(self, text: str):
        try:
            self.status_var.set(text)
        except Exception:
            pass

    def _set_progress(self, value=None, maximum=None, mode=None):
        def do():
            try:
                if mode:
                    self.progress.configure(mode=mode)
                if maximum is not None:
                    self.progress.configure(maximum=maximum)
                if value is not None:
                    self.progress.configure(value=value)
            except Exception:
                pass
        self.after(0, do)

    def _progress_start(self, interval=10):
        self.after(0, lambda: self.progress.start(interval))

    def _progress_stop(self):
        self.after(0, self.progress.stop)

    def run_initial_load(self):
        if self._running:
            return
        self.log("Running initial 3-year data load...")
        self._set_running(True)
        self._set_progress(0, 36, mode="determinate")
        self._set_status("Initial load in progress...")

        def worker():
            import pandas as _pd
            try:
                today = datetime.today()
                for i in range(36):
                    month_date = today - _pd.DateOffset(months=i)
                    target_month = month_date.strftime("%Y-%m")
                    self.log(f"[Init] Running month {i+1}/36: {target_month}")
                    ui_run_controller.run_month_update(target_month, logger=self.log)
                    self._set_progress(i + 1)
                self.log("Initial data load completed successfully.")
            except Exception as e:
                self.log(f"Error during initial data load: {e}")
                try:
                    messagebox.showerror("Error", f"An error occurred: {e}")
                except Exception:
                    pass
            finally:
                self._set_running(False)
                self._set_status("Idle")
                try:
                    self.refresh_db_view()
                    self.populate_analyst_combos()
                    self.populate_quadrant_combos()
                    self.populate_comment_months()
                except Exception:
                    pass

        self._task_thread = threading.Thread(target=worker, daemon=True)
        self._task_thread.start()

    def run_monthly_update(self):
        if self._running:
            return
        self.log("Running last month's update...")
        self._set_running(True)
        self._set_progress(0, 100, mode="indeterminate")
        self._progress_start(10)
        self._set_status("Monthly update in progress...")

        def worker():
            try:
                ui_run_controller.run_monthly_update(logger=self.log)
                self.log("Monthly update completed successfully.")
            except Exception as e:
                self.log(f"Error during monthly update: {e}")
                try:
                    messagebox.showerror("Error", f"An error occurred: {e}")
                except Exception:
                    pass
            finally:
                self._progress_stop()
                self._set_running(False)
                self._set_status("Idle")
                try:
                    self.refresh_db_view()
                    self.populate_analyst_combos()
                    self.populate_quadrant_combos()
                    self.populate_comment_months()
                except Exception:
                    pass

        self._task_thread = threading.Thread(target=worker, daemon=True)
        self._task_thread.start()

    def run_selected_month(self):
        month_str = self.run_month_entry.get().strip()
        if not month_str:
            messagebox.showerror("Error", "Please enter a month in YYYY-MM format.")
            return
        try:
            datetime.strptime(month_str, "%Y-%m")
        except ValueError:
            messagebox.showerror("Error", "Invalid month format. Use YYYY-MM.")
            return
        self.log(f"Running update for {month_str}...")
        if self._running:
            return
        self._set_running(True)
        self._set_progress(0, 100, mode="indeterminate")
        self._progress_start(10)
        self._set_status(f"Update for {month_str} in progress...")

        def worker():
            try:
                ui_run_controller.run_month_update(month_str, logger=self.log)
                self.log("Selected month update completed successfully.")
            except Exception as e:
                self.log(f"Error during selected month update: {e}")
                try:
                    messagebox.showerror("Error", f"An error occurred: {e}")
                except Exception:
                    pass
            finally:
                self._progress_stop()
                self._set_running(False)
                self._set_status("Idle")
                try:
                    self.refresh_db_view()
                    self.populate_analyst_combos()
                    self.populate_quadrant_combos()
                    self.populate_comment_months()
                except Exception:
                    pass

        self._task_thread = threading.Thread(target=worker, daemon=True)
        self._task_thread.start()

    def run_specific_day(self):
        day_str = self.one_day_entry.get().strip()
        if not day_str:
            messagebox.showerror("Error", "Please enter a date in YYYY-MM-DD format.")
            return
        try:
            datetime.strptime(day_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD.")
            return
        self.log(f"Running one-day update for {day_str}...")
        if self._running:
            return
        self._set_running(True)
        self._set_progress(0, 100, mode="indeterminate")
        self._progress_start(10)
        self._set_status(f"One-day update for {day_str}...")

        def worker():
            try:
                ui_run_controller.run_one_day(day_str, upsert=True, logger=self.log)
                self.log("One-day update completed successfully.")
            except Exception as e:
                self.log(f"Error during one-day update: {e}")
                try:
                    messagebox.showerror("Error", f"An error occurred: {e}")
                except Exception:
                    pass
            finally:
                self._progress_stop()
                self._set_running(False)
                self._set_status("Idle")
                try:
                    self.refresh_db_view()
                except Exception:
                    pass

        self._task_thread = threading.Thread(target=worker, daemon=True)
        self._task_thread.start()

    def purge_database(self):
        if messagebox.askyesno("Confirm Purge", "Are you sure you want to delete all data from the database?"):
            try:
                ingest.purge_database()
                self.log("Database purged successfully.")
                self.refresh_db_view()
            except Exception as e:
                self.log(f"Error during database purge: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    def log(self, message):
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            self._log_queue.put(f"[{ts}] {message}")
        except Exception:
            # Fallback directly to widget (main thread)
            self.log_text.insert(tk.END, str(message) + "\n")
            self.log_text.see(tk.END)

    def _drain_log_queue(self):
        try:
            while not self._log_queue.empty():
                msg = self._log_queue.get_nowait()
                self.log_text.insert(tk.END, msg + "\n")
                self.log_text.see(tk.END)
        except Exception:
            pass
        finally:
            # keep polling
            try:
                self.after(150, self._drain_log_queue)
            except Exception:
                pass

    def log_startup_info(self):
        try:
            self.log("Startup: collecting environment info...")
            # Python executable and version
            self.log(f"Python: exe={sys.executable}")
            self.log(f"Python: version={sys.version.split()[0]}")
            # Key packages
            try:
                from importlib.metadata import version, PackageNotFoundError  # Py>=3.8
            except Exception:
                try:
                    from importlib_metadata import version, PackageNotFoundError  # backport
                except Exception:
                    version = None
                    PackageNotFoundError = Exception
            for pkg in ["requests", "pandas", "numpy", "matplotlib", "vaderSentiment"]:
                try:
                    v = version(pkg) if version else None
                    self.log(f"Pkg: {pkg}={v if v else 'unknown'}")
                except PackageNotFoundError:
                    self.log(f"Pkg: {pkg}=not installed")
                except Exception:
                    self.log(f"Pkg: {pkg}=unknown")
            try:
                client = LlamaCppClient()
                self.log(f"LLM server: url={client.base_url} model={client.model} style={client.api_style}")
            except LLMClientError as exc:
                self.log(f"LLM server connection issue: {exc}")
            except Exception as exc:
                self.log(f"LLM client init failed: {exc}")
            model_dir = Path('models')
            if model_dir.exists():
                models = sorted(p.name for p in model_dir.iterdir() if p.is_file())
                if models:
                    self.log(f"Models directory: {model_dir} ({len(models)} files)")
                else:
                    self.log(f"Models directory: {model_dir} (empty)")
            else:
                self.log('Models directory not found.')
            # Attempt direct import of VADER and show module path
            try:
                from vaderSentiment import vaderSentiment as _vs
                self.log(f"VADER: module={getattr(_vs, '__file__', 'unknown')}")
                try:
                    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer as _SIA
                    self.log("VADER: SentimentIntensityAnalyzer import OK")
                except Exception as e:
                    self.log(f"VADER: analyzer import failed: {e}")
            except Exception as e:
                self.log(f"VADER: import failed: {e}")
            # Show a couple sys.path entries
            try:
                self.log("sys.path (first 3):")
                for p in sys.path[:3]:
                    self.log(f"  - {p}")
            except Exception:
                pass
            # Database path
            self.log(f"DB: path={database.DATABASE_FILE}")
        except Exception as e:
            try:
                self.log(f"Startup info error: {e}")
            except Exception:
                pass

    def create_db_view(self, notebook):
        db_frame = ttk.Frame(notebook)
        notebook.add(db_frame, text="Database")

        tree_container = ttk.Frame(db_frame)
        tree_container.pack(fill="both", expand=True)

        self.db_tree = ttk.Treeview(tree_container, style='Brand.Treeview')
        self.db_tree.pack(pady=10, padx=10, fill="both", expand=True)

        refresh_button = ttk.Button(
            db_frame,
            text="Refresh",
            command=self.refresh_db_view
        )
        refresh_button.pack(pady=10)

        dedupe_button = ttk.Button(
            db_frame,
            text="Deduplicate Rows",
            command=self.dedupe_db
        )
        dedupe_button.pack(pady=5)

        # Populate on startup
        self.refresh_db_view()


    def refresh_db_view(self):
        for i in self.db_tree.get_children():
            self.db_tree.delete(i)

        conn = sqlite3.connect(database.DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM monthly_sentiment")
        rows = cursor.fetchall()
        conn.close()

        self.db_tree["columns"] = [
            "tech_id", "tech_name", "month",
            "average_tone",
            "hn_avg_compound", "hn_comment_count",
            "analyst_lit_score", "analyst_whimsy_score",
            "run_at"
        ]
        self.db_tree.column("#0", width=0, stretch=tk.NO)
        for col in self.db_tree["columns"]:
            self.db_tree.column(col, anchor=tk.W, width=100)
            self.db_tree.heading(col, text=col, anchor=tk.W)

        for row in rows:
            self.db_tree.insert("", tk.END, values=row)

    def dedupe_db(self):
        try:
            database.deduplicate_monthly_sentiment()
            self.log("DB: deduplicated rows (kept latest run_at per tech/month)")
            self.refresh_db_view()
        except Exception as e:
            self.log(f"DB dedupe error: {e}")
            messagebox.showerror("Error", f"Deduplication failed: {e}")

    def create_analyst_view(self, notebook):
        analyst_frame = ttk.Frame(notebook)
        notebook.add(analyst_frame, text="Analyst Scores")

        # Month selector
        top = ttk.Frame(analyst_frame)
        top.pack(fill="x", pady=5)
        ttk.Label(top, text="Month:").pack(side=tk.LEFT, padx=5)
        self.analyst_month_combo = ttk.Combobox(top, width=10, state="normal")
        self.analyst_month_combo.pack(side=tk.LEFT)
        self.analyst_month_combo.bind("<<ComboboxSelected>>", self.on_select_analyst_month)
        ttk.Label(top, text="(YYYY-MM)").pack(side=tk.LEFT, padx=5)

        # Grid for all technologies
        self.analyst_grid = ttk.Frame(analyst_frame)
        self.analyst_grid.pack(fill="both", expand=True, padx=10, pady=10)

        header = ttk.Frame(self.analyst_grid)
        header.pack(fill="x")
        ttk.Label(header, text="Technology", width=30).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Literature (-1..1)", width=20).grid(row=0, column=1)
        ttk.Label(header, text="Whimsy (-1..1)", width=20).grid(row=0, column=2)

        self.analyst_rows_frame = ttk.Frame(self.analyst_grid)
        self.analyst_rows_frame.pack(fill="both", expand=True)
        self.analyst_entries = {}  # tech_id -> {name, lit_entry, whimsy_entry}

        # Save all button
        save_all = ttk.Button(analyst_frame, text="Save All", command=self.save_all_analyst_scores)
        save_all.pack(pady=10)

        self.populate_analyst_combos()

    def _fetch_distinct_months(self) -> list[str]:
        conn = sqlite3.connect(database.DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT month FROM monthly_sentiment ORDER BY month DESC")
        months = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()
        return months

    def populate_analyst_combos(self):
        months = self._fetch_distinct_months()
        self.analyst_month_combo['values'] = months
        # If no months yet, default to last completed month
        if months:
            selected = self.analyst_month_combo.get().strip() or months[0]
        else:
            try:
                selected = (datetime.utcnow().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            except Exception:
                selected = "2025-01"
        self.analyst_month_combo.set(selected)
        self.build_analyst_grid(selected)

    def on_select_analyst_month(self, event=None):
        month = self.analyst_month_combo.get()
        if month:
            self.build_analyst_grid(month)

    def build_analyst_grid(self, month: str):
        # Clear existing rows
        for w in self.analyst_rows_frame.winfo_children():
            w.destroy()
        self.analyst_entries.clear()

        config = ui_run_controller.load_config()
        # Load existing scores from DB
        conn = sqlite3.connect(database.DATABASE_FILE)
        cur = conn.cursor()
        cur.execute("SELECT tech_id, analyst_lit_score, analyst_whimsy_score FROM monthly_sentiment WHERE month = ?", (month,))
        existing = {tid: (lit or 0.0, whimsy or 0.0) for tid, lit, whimsy in cur.fetchall()}
        conn.close()

        for i, tech in enumerate(config.get('technologies', []), start=1):
            tid = tech['id']
            tname = tech['name']
            ttk.Label(self.analyst_rows_frame, text=tname, width=30).grid(row=i, column=0, sticky="w", padx=2, pady=2)
            lit_e = ttk.Entry(self.analyst_rows_frame, width=8)
            whim_e = ttk.Entry(self.analyst_rows_frame, width=8)
            # Pre-fill raw -1..1 values
            lit0, whim0 = existing.get(tid, (0.0, 0.0))
            try:
                lit_e.insert(0, f"{float(lit0):.2f}")
                whim_e.insert(0, f"{float(whim0):.2f}")
            except Exception:
                pass
            lit_e.grid(row=i, column=1, padx=2)
            whim_e.grid(row=i, column=2, padx=2)
            self.analyst_entries[tid] = {"name": tname, "lit": lit_e, "whim": whim_e}

    def save_all_analyst_scores(self):
        month = self.analyst_month_combo.get()
        if not month:
            messagebox.showerror("Error", "Please select a month.")
            return
        # Validate month format
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError:
            messagebox.showerror("Error", "Invalid month format. Use YYYY-MM.")
            return

        # Validate and collect
        updates = []  # (tech_id, tech_name, lit_f, whim_f) where -1..1
        for tid, info in self.analyst_entries.items():
            tname = info["name"]
            try:
                lit_f = float(info["lit"].get())
                whim_f = float(info["whim"].get())
                if not (-1.0 <= lit_f <= 1.0 and -1.0 <= whim_f <= 1.0):
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Error", f"Scores for {tname} must be decimal numbers between -1 and 1.")
                return
            updates.append((tid, tname, lit_f, whim_f))

        # Apply to DB
        conn = sqlite3.connect(database.DATABASE_FILE)
        cur = conn.cursor()
        for tid, tname, lit_f, whim_f in updates:
            cur.execute(
                """
                UPDATE monthly_sentiment
                SET analyst_lit_score = ?, analyst_whimsy_score = ?
                WHERE tech_id = ? AND month = ?
                """,
                (lit_f, whim_f, tid, month)
            )
            if cur.rowcount == 0:
                run_at = datetime.now().isoformat()
                cur.execute(
                    """
                    REPLACE INTO monthly_sentiment (
                        tech_id, tech_name, month,
                        analyst_lit_score, analyst_whimsy_score,
                        average_tone, hn_avg_compound, hn_comment_count,
                        run_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tid, tname, month, lit_f, whim_f, None, None, 0, run_at)
                )
        conn.commit()
        conn.close()

        messagebox.showinfo("Saved", "All scores saved.")
        self.refresh_db_view()
        # Ensure month appears in combos if newly created
        try:
            months = list(self.analyst_month_combo['values'])
            if month not in months:
                months.insert(0, month)
                self.analyst_month_combo['values'] = months
        except Exception:
            pass
        try:
            if self.quadrant_month_combo.get() == month:
                self.update_quadrant_plot()
        except Exception:
            pass

    def create_quadrant_view(self, notebook):
        quadrant_frame = ttk.Frame(notebook)
        notebook.add(quadrant_frame, text="Quadrant")

        # Month Selector
        ttk.Label(quadrant_frame, text="Month:").pack(pady=5)
        self.quadrant_month_combo = ttk.Combobox(quadrant_frame)
        self.quadrant_month_combo.pack(pady=5)
        self.quadrant_month_combo.bind("<<ComboboxSelected>>", self.update_quadrant_plot)

        # Plot
        self.fig = Figure(figsize=(8, 8), facecolor=self.brand_colors['fig_bg'])
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(self.brand_colors['plot_bg'])
        self.canvas = FigureCanvasTkAgg(self.fig, master=quadrant_frame)
        self.canvas.get_tk_widget().pack(pady=10, fill="both", expand=True)

        # Export Buttons
        export_frame = ttk.Frame(quadrant_frame)
        export_frame.pack(pady=10)
        ttk.Button(export_frame, text="Export PNG", command=self.export_png).pack(side=tk.LEFT, padx=5)
        ttk.Button(export_frame, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(export_frame, text="Export JSON", command=self.export_json).pack(side=tk.LEFT, padx=5)

        self.populate_quadrant_combos()

    def populate_quadrant_combos(self):
        months = self._fetch_distinct_months()
        self.quadrant_month_combo['values'] = months

    # ----------------------------
    # Configuration View (sources, technologies, subterms)
    # ----------------------------
    def create_config_view(self, notebook):
        cfg_frame = ttk.Frame(notebook)
        notebook.add(cfg_frame, text="Configuration")

        self.config_data = ui_run_controller.load_config()

        # Sources editor
        # Sources (domains) removed; timelinetone now uses sourcelang:eng globally.

        # Technologies editor
        techs_frame = ttk.LabelFrame(cfg_frame, text="Technologies")
        techs_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=10, pady=10)

        left = ttk.Frame(techs_frame)
        left.pack(side=tk.LEFT, fill="y", padx=5)
        ttk.Label(left, text="List").pack(anchor="w")
        self.tech_list = tk.Listbox(left, height=12, exportselection=False)
        self.tech_list.pack(fill="y", expand=False)
        self.tech_list.bind("<<ListboxSelect>>", self.on_select_tech)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=5)
        ttk.Button(btns, text="Add Tech", command=self.add_tech).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Remove Tech", command=self.remove_tech).pack(side=tk.LEFT, padx=2)

        right = ttk.Frame(techs_frame)
        right.pack(side=tk.LEFT, fill="both", expand=True, padx=5)
        form = ttk.Frame(right)
        form.pack(fill="x", pady=5)
        ttk.Label(form, text="ID:").grid(row=0, column=0, sticky="w")
        self.tech_id_entry = ttk.Entry(form)
        self.tech_id_entry.grid(row=0, column=1, sticky="ew")
        ttk.Label(form, text="Name:").grid(row=1, column=0, sticky="w")
        self.tech_name_entry = ttk.Entry(form)
        self.tech_name_entry.grid(row=1, column=1, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(right, text="Subterms (patterns)").pack(anchor="w")
        patterns_frame = ttk.Frame(right)
        patterns_frame.pack(fill="both", expand=True)
        self.patterns_list = tk.Listbox(patterns_frame, height=8, selectmode=tk.EXTENDED, exportselection=False)
        self.patterns_list.pack(side=tk.LEFT, fill="both", expand=True)
        pat_btns = ttk.Frame(patterns_frame)
        pat_btns.pack(side=tk.LEFT, fill="y", padx=5)
        self.pattern_entry = ttk.Entry(pat_btns)
        self.pattern_entry.pack(fill="x", pady=2)
        ttk.Button(pat_btns, text="Add", command=self.add_pattern).pack(fill="x", pady=2)
        ttk.Button(pat_btns, text="Remove Selected", command=self.remove_pattern).pack(fill="x", pady=2)

        save_frame = ttk.Frame(cfg_frame)
        save_frame.pack(side=tk.BOTTOM, fill="x", padx=10, pady=10)
        ttk.Button(save_frame, text="Save Configuration", command=self.save_configuration).pack(side=tk.RIGHT)

        # populate tech list
        self.refresh_tech_list()

    def refresh_tech_list(self):
        self.tech_list.delete(0, tk.END)
        for tech in self.config_data.get('technologies', []):
            self.tech_list.insert(tk.END, tech.get('name', tech.get('id', 'unknown')))
        # clear detail panel
        self.tech_id_entry.delete(0, tk.END)
        self.tech_name_entry.delete(0, tk.END)
        self.patterns_list.delete(0, tk.END)
        self.pattern_entry.delete(0, tk.END)

    def current_tech_index(self):
        sel = self.tech_list.curselection()
        return sel[0] if sel else None

    def on_select_tech(self, event=None):
        idx = self.current_tech_index()
        if idx is None:
            return
        tech = self.config_data['technologies'][idx]
        self.tech_id_entry.delete(0, tk.END)
        self.tech_id_entry.insert(0, tech.get('id', ''))
        self.tech_name_entry.delete(0, tk.END)
        self.tech_name_entry.insert(0, tech.get('name', ''))
        self.patterns_list.delete(0, tk.END)
        for p in tech.get('patterns', []):
            self.patterns_list.insert(tk.END, p)

    def add_tech(self):
        new = {"id": "new-tech", "name": "New Technology", "patterns": []}
        self.config_data.setdefault('technologies', []).append(new)
        self.refresh_tech_list()
        self.tech_list.selection_clear(0, tk.END)
        self.tech_list.selection_set(tk.END)
        self.on_select_tech()

    def remove_tech(self):
        idx = self.current_tech_index()
        if idx is None:
            return
        try:
            tech = self.config_data['technologies'][idx]
            name = tech.get('name', tech.get('id', 'tech'))
        except Exception:
            name = 'tech'
        if not messagebox.askyesno("Confirm", f"Remove {name}?"):
            return
        try:
            del self.config_data['technologies'][idx]
        except Exception:
            return
        # Persist immediately so removal sticks across restarts
        try:
            ui_run_controller.save_config(self.config_data)
        except Exception:
            pass
        self.refresh_tech_list()
        # Update other views that depend on config
        try:
            self.populate_analyst_combos()
            self.populate_quadrant_combos()
        except Exception:
            pass

    def add_pattern(self):
        idx = self.current_tech_index()
        if idx is None:
            messagebox.showerror("Error", "Select a technology first.")
            return
        val = self.pattern_entry.get().strip()
        if not val:
            return
        self.config_data['technologies'][idx].setdefault('patterns', []).append(val)
        self.patterns_list.insert(tk.END, val)
        self.pattern_entry.delete(0, tk.END)

    def remove_pattern(self):
        idx = self.current_tech_index()
        if idx is None:
            messagebox.showerror("Error", "Select a technology first.")
            return
        sel = self.patterns_list.curselection()
        if not sel:
            messagebox.showinfo("Info", "Select one or more subterms to remove.")
            return
        # Normalize indices to ints and remove from end to start
        to_remove = sorted([int(i) for i in sel], reverse=True)
        try:
            pats = self.config_data['technologies'][idx].setdefault('patterns', [])
        except Exception:
            pats = []
        for i in to_remove:
            if 0 <= i < len(pats):
                try:
                    del pats[i]
                except Exception:
                    pass
            try:
                self.patterns_list.delete(i)
            except Exception:
                pass
        # Persist immediately so user sees effect reliably
        try:
            ui_run_controller.save_config(self.config_data)
        except Exception:
            pass

    # Sources management removed.

    def save_configuration(self):
        # persist any edits in the detail form back to the model
        idx = self.current_tech_index()
        if idx is not None:
            self.config_data['technologies'][idx]['id'] = self.tech_id_entry.get().strip()
            self.config_data['technologies'][idx]['name'] = self.tech_name_entry.get().strip()
            # patterns list already in sync

        ui_run_controller.save_config(self.config_data)
        if idx is not None:
            display = self.config_data['technologies'][idx].get('name') or self.config_data['technologies'][idx].get('id', 'unknown')
            self.tech_list.delete(idx)
            self.tech_list.insert(idx, display)
            self.tech_list.selection_clear(0, tk.END)
            self.tech_list.selection_set(idx)
        messagebox.showinfo("Saved", "Configuration saved to config.json")
        # refresh dependent combos in other views
        self.populate_analyst_combos()
        self.populate_quadrant_combos()

    def update_quadrant_plot(self, event=None):
        month = self.quadrant_month_combo.get()
        self.quadrant_has_data = False
        if not month:
            return

        conn = sqlite3.connect(database.DATABASE_FILE)
        df = pd.read_sql_query(f"SELECT * FROM monthly_sentiment WHERE month = '{month}'", conn)
        conn.close()

        self.ax.clear()
        if df.empty:
            self._style_no_data_message(self.ax, "No data for this month")
            self.canvas.draw()
            return

        # Compute from raw fields
        df['average_tone'] = pd.to_numeric(df['average_tone'], errors='coerce').fillna(0.0)
        df['hn_avg_compound'] = pd.to_numeric(df['hn_avg_compound'], errors='coerce').fillna(0.0)
        df['analyst_lit_score'] = pd.to_numeric(df['analyst_lit_score'], errors='coerce').fillna(0.0)
        df['analyst_whimsy_score'] = pd.to_numeric(df['analyst_whimsy_score'], errors='coerce').fillna(0.0)
        df['momentum_val'] = df['average_tone'] + df['analyst_lit_score'] + df['analyst_whimsy_score']
        df['conviction_val'] = df['hn_avg_compound'] + df['analyst_lit_score'] + df['analyst_whimsy_score']

        self._prepare_axis(self.ax, self.fig, grid=False)
        self.ax.set_xlabel('Momentum', color=self.brand_colors['muted'])
        self.ax.set_ylabel('Conviction', color=self.brand_colors['muted'])
        self.ax.set_title(f"Technology Quadrant - {month}", color=self.brand_colors['accent_light'])

        x_vals = df['momentum_val'].astype(float)
        y_vals = df['conviction_val'].astype(float)
        x_min, x_max = x_vals.min(), x_vals.max()
        y_min, y_max = y_vals.min(), y_vals.max()
        if abs(x_max - x_min) < 1e-6:
            x_min -= 1
            x_max += 1
        if abs(y_max - y_min) < 1e-6:
            y_min -= 1
            y_max += 1
        x_pad = (x_max - x_min) * 0.1
        y_pad = (y_max - y_min) * 0.1
        self.ax.set_xlim(x_min - x_pad, x_max + x_pad)
        self.ax.set_ylim(y_min - y_pad, y_max + y_pad)

        x_mid = (x_min + x_max) / 2
        y_mid = (y_min + y_max) / 2
        self.ax.axvline(x_mid, color=self.brand_colors['grid'], linewidth=0.8, linestyle='--', alpha=0.5)
        self.ax.axhline(y_mid, color=self.brand_colors['grid'], linewidth=0.8, linestyle='--', alpha=0.5)

        for idx, row in enumerate(df.itertuples()):
            x = float(row.momentum_val)
            y = float(row.conviction_val)
            color = self.brand_palette[idx % len(self.brand_palette)]
            self.ax.scatter(x, y, s=100, color=color, edgecolor=self.brand_colors['bg'], linewidths=1.2, zorder=3)
            self.ax.text(x + x_pad * 0.05, y + y_pad * 0.05, row.tech_name, color=self.brand_colors['text'], fontsize=9, fontweight='bold')

        self.quadrant_has_data = True
        self.canvas.draw()

    def create_comment_volume_view(self, notebook):
        volume_frame = ttk.Frame(notebook)
        notebook.add(volume_frame, text="Comment Volume")

        ctrl = ttk.Frame(volume_frame)
        ctrl.pack(fill="x", padx=10, pady=5)
        ttk.Label(ctrl, text="Month:").pack(side=tk.LEFT)
        self.comment_month_combo = ttk.Combobox(ctrl, width=10, state="normal")
        self.comment_month_combo.pack(side=tk.LEFT, padx=5)
        self.comment_month_combo.bind("<<ComboboxSelected>>", self.update_comment_volume_plot)
        ttk.Button(ctrl, text="Render", command=self.update_comment_volume_plot).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Export PNG", command=self.export_comment_png).pack(side=tk.LEFT, padx=5)

        self.comment_fig = Figure(figsize=(6, 4), facecolor=self.brand_colors['fig_bg'])
        self.comment_ax = self.comment_fig.add_subplot(111)
        self.comment_ax.set_facecolor(self.brand_colors['plot_bg'])
        self.comment_canvas = FigureCanvasTkAgg(self.comment_fig, master=volume_frame)
        self.comment_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        self.populate_comment_months()

    def populate_comment_months(self):
        months = self._fetch_distinct_months()
        self.comment_month_combo['values'] = months
        if months:
            current = self.comment_month_combo.get().strip()
            if current not in months:
                current = months[0]
            self.comment_month_combo.set(current)
        else:
            self.comment_month_combo.set('')
        self.update_comment_volume_plot()

    def update_comment_volume_plot(self, event=None):
        month = (self.comment_month_combo.get() or '').strip()
        self.comment_has_data = False
        self.comment_ax.clear()
        self.comment_fig.patch.set_facecolor(self.brand_colors['fig_bg'])
        if not month:
            self.comment_ax.set_title("Hacker News Comment Share", color=self.brand_colors['accent_light'])
            self._style_no_data_message(self.comment_ax, "Select a month to view comment distribution")
            self.comment_canvas.draw()
            return

        conn = sqlite3.connect(database.DATABASE_FILE)
        try:
            df = pd.read_sql_query(
                "SELECT tech_name, hn_comment_count FROM monthly_sentiment WHERE month = ?",
                conn,
                params=(month,)
            )
        finally:
            conn.close()

        if df.empty:
            self.comment_ax.set_title(f"Hacker News Comment Share - {month}", color=self.brand_colors['accent_light'])
            self._style_no_data_message(self.comment_ax, "No comment data")
            self.comment_canvas.draw()
            return

        df['hn_comment_count'] = pd.to_numeric(df['hn_comment_count'], errors='coerce').fillna(0.0)
        df = df[df['hn_comment_count'] > 0]
        total = float(df['hn_comment_count'].sum())
        if total <= 0 or df.empty:
            self.comment_ax.set_title(f"Hacker News Comment Share - {month}", color=self.brand_colors['accent_light'])
            self._style_no_data_message(self.comment_ax, "No comments recorded")
            self.comment_canvas.draw()
            return

        self.comment_ax.axis('on')
        self.comment_ax.set_facecolor(self.brand_colors['plot_bg'])
        self.comment_ax.set_title(f"Hacker News Comment Share - {month}", color=self.brand_colors['accent_light'])

        def _autopct(pct):
            count = int(round(pct * total / 100)) if total else 0
            return f"{pct:.1f}%\n({count})"

        colors = [self.brand_palette[i % len(self.brand_palette)] for i in range(len(df))]
        self.comment_ax.pie(
            df['hn_comment_count'],
            labels=df['tech_name'],
            autopct=_autopct,
            colors=colors,
            textprops={'color': self.brand_colors['text'], 'fontsize': 10, 'fontweight': 'bold'},
            wedgeprops={'linewidth': 1.2, 'edgecolor': self.brand_colors['bg']}
        )
        self.comment_ax.axis('equal')
        self.comment_has_data = True
        self.comment_canvas.draw()


    def create_trajectories_view(self, notebook):
        traj_frame = ttk.Frame(notebook)
        notebook.add(traj_frame, text="Trajectories")

        ctrl = ttk.Frame(traj_frame)
        ctrl.pack(fill="x", padx=10, pady=5)
        ttk.Label(ctrl, text="Months (history):").pack(side=tk.LEFT)
        self.traj_months_var = tk.IntVar(value=6)
        ttk.Spinbox(ctrl, from_=3, to=24, width=5, textvariable=self.traj_months_var).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Render", command=self.update_trajectories_plot).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Export PNG", command=self.export_trajectories_png).pack(side=tk.LEFT, padx=5)

        self.traj_fig = Figure(figsize=(6, 4), facecolor=self.brand_colors['fig_bg'])
        self.traj_ax = self.traj_fig.add_subplot(111)
        self.traj_ax.set_facecolor(self.brand_colors['plot_bg'])
        self.traj_canvas = FigureCanvasTkAgg(self.traj_fig, master=traj_frame)
        self.traj_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        self.update_trajectories_plot()

    def update_trajectories_plot(self):
        try:
            months_back = int(self.traj_months_var.get())
        except Exception:
            months_back = 6

        self.traj_has_data = False
        # Build month list: last N months including last completed month
        try:
            last_month = (datetime.utcnow().replace(day=1) - timedelta(days=1))
        except Exception:
            last_month = datetime.utcnow()
        month_list = [(last_month - pd.DateOffset(months=i)).strftime("%Y-%m") for i in reversed(range(months_back))]

        conn = sqlite3.connect(database.DATABASE_FILE)
        df = pd.read_sql_query("SELECT * FROM monthly_sentiment", conn)
        conn.close()
        if df.empty:
            self.traj_ax.clear()
            self.traj_ax.set_title("Trajectories", color=self.brand_colors['accent_light'])
            self._style_no_data_message(self.traj_ax, "No data available")
            self.traj_canvas.draw()
            return

        # Prepare values (raw-only model)
        df['average_tone'] = pd.to_numeric(df.get('average_tone'), errors='coerce').fillna(0.0)
        df['hn_avg_compound'] = pd.to_numeric(df.get('hn_avg_compound'), errors='coerce').fillna(0.0)
        df['analyst_lit_score'] = pd.to_numeric(df.get('analyst_lit_score'), errors='coerce').fillna(0.0)
        df['analyst_whimsy_score'] = pd.to_numeric(df.get('analyst_whimsy_score'), errors='coerce').fillna(0.0)
        df['conviction_0_100'] = df['hn_avg_compound'] + df['analyst_lit_score'] + df['analyst_whimsy_score']
        df['momentum_0_100'] = df['average_tone'] + df['analyst_lit_score'] + df['analyst_whimsy_score']

        focus_df = df[df['month'].isin(month_list)].copy()
        if focus_df.empty:
            self.traj_ax.clear()
            self.traj_ax.set_title(f"Trajectories (last {months_back} months)", color=self.brand_colors['accent_light'])
            self._style_no_data_message(self.traj_ax, "No data for selected range")
            self.traj_canvas.draw()
            return

        self.traj_ax.clear()
        self._prepare_axis(self.traj_ax, self.traj_fig)
        self.traj_ax.set_xlabel("Momentum", color=self.brand_colors['muted'])
        self.traj_ax.set_ylabel("Conviction", color=self.brand_colors['muted'])
        self.traj_ax.set_title(f"Trajectories (last {months_back} months)", color=self.brand_colors['accent_light'])

        x_vals = focus_df['momentum_0_100'].astype(float)
        y_vals = focus_df['conviction_0_100'].astype(float)
        x_min, x_max = x_vals.min(), x_vals.max()
        y_min, y_max = y_vals.min(), y_vals.max()
        if abs(x_max - x_min) < 1e-6:
            x_min -= 1
            x_max += 1
        if abs(y_max - y_min) < 1e-6:
            y_min -= 1
            y_max += 1
        x_pad = (x_max - x_min) * 0.1
        y_pad = (y_max - y_min) * 0.1
        self.traj_ax.set_xlim(x_min - x_pad, x_max + x_pad)
        self.traj_ax.set_ylim(y_min - y_pad, y_max + y_pad)

        for idx, (tech_id, g) in enumerate(focus_df.groupby('tech_id')):
            g = g.sort_values('month')
            x = g['momentum_0_100'].astype(float).tolist()
            y = g['conviction_0_100'].astype(float).tolist()
            if not x or not y:
                continue
            name = g['tech_name'].iloc[0] if not g.empty else tech_id
            color = self.brand_palette[idx % len(self.brand_palette)]
            point_count = len(x)
            size_min, size_max = 36.0, 180.0
            if point_count > 1:
                size_scale = [(size_min + (size_max - size_min) * (i / (point_count - 1))) for i in range(point_count)]
            else:
                size_scale = [size_max]
            for seg_idx in range(max(point_count - 1, 0)):
                frac = (seg_idx + 1) / (point_count - 1) if point_count > 1 else 1.0
                line_width = 1.2 + (3.6 - 1.2) * frac
                line_alpha = 0.55 + 0.35 * frac
                self.traj_ax.plot(
                    x[seg_idx:seg_idx + 2],
                    y[seg_idx:seg_idx + 2],
                    color=color,
                    linewidth=line_width,
                    alpha=line_alpha,
                    zorder=2
                )
            self.traj_ax.scatter(
                x,
                y,
                s=size_scale,
                color=color,
                edgecolor=self.brand_colors['bg'],
                linewidths=1.1,
                alpha=0.9,
                zorder=3,
                label=name
            )
            self.traj_ax.text(
                x[-1] + x_pad * 0.03,
                y[-1] + y_pad * 0.03,
                name,
                color=self.brand_colors['text'],
                fontsize=9,
                fontweight='bold'
            )

        legend = self.traj_ax.legend(loc='upper left', frameon=True, fontsize=9)
        if legend is not None:
            legend.get_frame().set_facecolor(self.brand_colors['fig_bg'])
            legend.get_frame().set_edgecolor(self.brand_colors['grid'])
            for text_item in legend.get_texts():
                text_item.set_color(self.brand_colors['text'])
        self.traj_has_data = True
        self.traj_canvas.draw()

    def create_trends_view(self, notebook):
        trends_frame = ttk.Frame(notebook)
        notebook.add(trends_frame, text="Trends")

        ctrl = ttk.Frame(trends_frame)
        ctrl.pack(fill="x", padx=10, pady=5)
        ttk.Label(ctrl, text="Months (history):").pack(side=tk.LEFT)
        self.trend_months_var = tk.IntVar(value=12)
        ttk.Spinbox(ctrl, from_=3, to=36, width=5, textvariable=self.trend_months_var).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Render", command=self.update_trends_plot).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Export PNG", command=self.export_trends_png).pack(side=tk.LEFT, padx=5)

        self.trend_fig = Figure(figsize=(6,4), facecolor=self.brand_colors['fig_bg'])
        self.trend_ax = self.trend_fig.add_subplot(111)
        self.trend_ax.set_facecolor(self.brand_colors['plot_bg'])
        self.trend_canvas = FigureCanvasTkAgg(self.trend_fig, master=trends_frame)
        self.trend_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        self.update_trends_plot()

    def update_trends_plot(self):
        try:
            months_back = int(self.trend_months_var.get())
        except Exception:
            months_back = 12
        self.trend_has_data = False
        try:
            last_month = (datetime.utcnow().replace(day=1) - timedelta(days=1))
        except Exception:
            last_month = datetime.utcnow()
        month_list = [(last_month - pd.DateOffset(months=i)).strftime("%Y-%m") for i in reversed(range(months_back))]

        conn = sqlite3.connect(database.DATABASE_FILE)
        df = pd.read_sql_query("SELECT tech_id, tech_name, month, average_tone, hn_avg_compound, analyst_lit_score, analyst_whimsy_score FROM monthly_sentiment", conn)
        conn.close()

        self.trend_ax.clear()
        self._prepare_axis(self.trend_ax, self.trend_fig)
        self.trend_ax.set_xlabel("Month", color=self.brand_colors['muted'])
        self.trend_ax.set_ylabel("Momentum (tone + analyst)", color=self.brand_colors['muted'])
        self.trend_ax.set_title(f"Momentum Trend (last {months_back} months)", color=self.brand_colors['accent_light'])

        if df.empty:
            self._style_no_data_message(self.trend_ax, "No data available")
            self.trend_canvas.draw()
            return
        df = df[df['month'].isin(month_list)]
        if df.empty:
            self._style_no_data_message(self.trend_ax, "No data for selected range")
            self.trend_canvas.draw()
            return
        for col in ['average_tone','hn_avg_compound','analyst_lit_score','analyst_whimsy_score']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        df['momentum'] = df['average_tone'] + df['analyst_lit_score'] + df['analyst_whimsy_score']
        for idx, (tech_id, g) in enumerate(df.groupby('tech_id')):
            g = g.sort_values('month')
            xs = g['month'].tolist()
            ys = g['momentum'].astype(float).tolist()
            if not xs or not ys:
                continue
            name = g['tech_name'].iloc[0] if not g.empty else tech_id
            color = self.brand_palette[idx % len(self.brand_palette)]
            self.trend_ax.plot(xs, ys, marker='o', linewidth=2, color=color, label=name)
        legend = self.trend_ax.legend(loc='best', frameon=True, fontsize=9)
        if legend is not None:
            legend.get_frame().set_facecolor(self.brand_colors['fig_bg'])
            legend.get_frame().set_edgecolor(self.brand_colors['grid'])
            for text_item in legend.get_texts():
                text_item.set_color(self.brand_colors['text'])
        self.trend_has_data = True
        self.trend_canvas.draw()



    def create_discovery_view(self, notebook):
        discovery_frame = ttk.Frame(notebook)
        notebook.add(discovery_frame, text="Discover")
        try:
            self.discover_tab = DiscoverTab(discovery_frame, self)
            self.discover_tab.pack(fill="both", expand=True)
        except Exception as exc:
            self.discover_tab = None
            fallback = ttk.Frame(discovery_frame)
            fallback.pack(fill="both", expand=True, padx=20, pady=20)
            ttk.Label(
                fallback,
                text=f"Discover module unavailable: {exc}",
                justify='center',
                anchor='center'
            ).pack(fill='both', expand=True)

    def run_theme_discovery(self):
        messagebox.showinfo("Discover", "Use the Discover tab controls to run the new pipeline.")
    def _end_discovery_run(self):
        self.discovery_running = False
        self.discovery_status_var.set("Idle")

    def _populate_discovery_results(self, result: dict[str, object]):
        themes = result.get("themes") or []
        self.discovery_results = result
        summary_bits = [
            f"{len(themes)} themes",
            f"{result.get('stories_in_prompt', 0)} stories analysed",
            f"last {result.get('days_back', '?')} days",
            f"min {result.get('min_points', 0)} pts",
        ]
        self.discovery_summary_var.set(' | '.join(summary_bits))
        self.discovery_theme_rows.clear()
        for item in self.discovery_tree.get_children():
            self.discovery_tree.delete(item)
        for idx, theme in enumerate(themes, start=1):
            title = str(theme.get("title") or f"Theme {idx}")
            confidence = str(theme.get("confidence") or "").title() or "-"
            strength = str(theme.get("signal_strength") or "").title() or "-"
            signals = theme.get("signals") or []
            story_refs = theme.get("story_refs") or []
            signals_count = len([s for s in signals if isinstance(s, dict)]) or len(story_refs)
            summary_text = str(theme.get("summary") or theme.get("why_it_matters") or "")
            summary_display = self._shorten_text(summary_text, 160)
            item_id = self.discovery_tree.insert(
                "",
                tk.END,
                values=(
                    title,
                    confidence,
                    strength,
                    f"{signals_count}",
                    summary_display,
                ),
            )
            self.discovery_theme_rows[item_id] = theme
        if themes:
            first = self.discovery_tree.get_children()[0]
            self.discovery_tree.selection_set(first)
            self.discovery_tree.focus(first)
            self._on_discovery_select()
        else:
            self._clear_discovery_detail()
            self.discovery_summary_var.set(
                "No themes were produced. Try lowering the min points or expanding the window."
            )

    def _on_discovery_select(self, event=None):
        selection = self.discovery_tree.selection()
        if not selection:
            self._clear_discovery_detail()
            return
        item_id = selection[0]
        theme = self.discovery_theme_rows.get(item_id)
        if not theme:
            self._clear_discovery_detail()
            return
        self._show_discovery_theme(theme)

    def _shorten_text(self, text: str, limit: int = 180) -> str:
        if not text:
            return ""
        text = text.strip()
        if len(text) <= limit:
            return text
        truncated = text[: limit - 3].rsplit(" ", 1)[0]
        return f"{truncated}..."

    def _show_discovery_theme(self, theme: dict[str, object]):
        title = str(theme.get("title") or "")
        summary = str(theme.get("summary") or "").strip()
        why = str(theme.get("why_it_matters") or "").strip()
        confidence = str(theme.get("confidence") or "-").title()
        strength = str(theme.get("signal_strength") or "-").title()
        watch_actions = [
            action.strip()
            for action in (theme.get("watch_actions") or [])
            if isinstance(action, str) and action.strip()
        ]
        domains = [
            domain.strip()
            for domain in (theme.get("domains") or [])
            if isinstance(domain, str) and domain.strip()
        ]
        lines = [
            f"Theme: {title}",
            f"Confidence: {confidence} | Signal strength: {strength}",
        ]
        if domains:
            lines.append(f"Domains: {', '.join(domains)}")
        if summary:
            lines.append("")
            lines.append("Summary:")
            lines.append(summary)
        if why and why != summary:
            lines.append("")
            lines.append("Why it matters:")
            lines.append(why)
        if watch_actions:
            lines.append("")
            lines.append("Watch actions:")
            for action in watch_actions:
                lines.append(f"- {action}")
        signals = theme.get("signals") or []
        story_refs = theme.get("story_refs") or []
        story_lookup = {
            str(story.get("id")): story
            for story in story_refs
            if isinstance(story, dict)
        }
        if signals:
            lines.append("")
            lines.append("Signals:")
            for sig in signals:
                if not isinstance(sig, dict):
                    continue
                story_id = str(sig.get("story_id") or "")
                story = story_lookup.get(story_id)
                headline = sig.get("headline") or (story.get("title") if story else "")
                if story_id:
                    lines.append(f"- [{story_id}] {headline}")
                else:
                    lines.append(f"- {headline}")
                insight = str(sig.get("insight") or "").strip()
                if insight:
                    lines.append(f"  Insight: {insight}")
                if story:
                    lines.append(
                        f"  Points: {story.get('points', 0)} | Comments: {story.get('comments', 0)} | {story.get('created_at', '')}"
                    )
                    url = story.get("url") or story.get("discussion_url")
                    if url:
                        lines.append(f"  {url}")
                lines.append("")
        elif story_refs:
            lines.append("")
            lines.append("Signals:")
            for story in story_refs:
                lines.append(f"- [{story.get('id')}] {story.get('title')}")
                lines.append(
                    f"  Points: {story.get('points', 0)} | Comments: {story.get('comments', 0)} | {story.get('created_at', '')}"
                )
                url = story.get("url") or story.get("discussion_url")
                if url:
                    lines.append(f"  {url}")
                lines.append("")
        text = "\n".join(line for line in lines if line).strip()
        if not text:
            text = "No additional details available for this theme."
        self.discovery_text.configure(state="normal")
        self.discovery_text.delete("1.0", tk.END)
        self.discovery_text.insert(tk.END, text)
        self.discovery_text.configure(state="disabled")

    def _clear_discovery_detail(self):
        if not hasattr(self, "discovery_text"):
            return
        self.discovery_text.configure(state="normal")
        self.discovery_text.delete("1.0", tk.END)
        self.discovery_text.insert(
            tk.END,
            "Run discovery to generate LLM-backed themes, then select a row to see supporting signals.",
        )
        self.discovery_text.configure(state="disabled")

    def create_llm_settings_view(self, notebook):
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="LLM Prompt")

        ttk.Label(
            settings_frame,
            text="Edit the system prompt used for Discover runs. Keep the {max_themes} placeholder and use double braces {{ }} for literal braces."
        ).pack(anchor="w", padx=10, pady=(8, 2))
        prompt_path = discovery_llm.get_system_prompt_path()
        ttk.Label(settings_frame, text=f"Prompt file: {prompt_path}").pack(anchor="w", padx=10, pady=(0, 6))

        text_frame = ttk.Frame(settings_frame)
        text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.llm_prompt_text = tk.Text(text_frame, height=20, wrap="word")
        self.llm_prompt_text.pack(fill="both", expand=True)
        self._load_llm_prompt_template()
        self._update_custom_widget_colors()

        button_row = ttk.Frame(settings_frame)
        button_row.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(button_row, text="Save", command=self._save_llm_prompt_template).pack(side=tk.LEFT)
        ttk.Button(
            button_row,
            text="Reset to Default",
            command=self._reset_llm_prompt_template,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(button_row, text="Reload", command=self._load_llm_prompt_template).pack(side=tk.LEFT, padx=(8, 0))

    def _load_llm_prompt_template(self):
        if self.llm_prompt_text is None:
            return
        try:
            template = discovery_llm.get_system_prompt_template()
        except Exception as exc:  # pragma: no cover - defensive
            self.log(f"Failed to load system prompt template: {exc}")
            template = discovery_llm.get_default_system_prompt_template()
        self.llm_prompt_text.configure(state="normal")
        self.llm_prompt_text.delete("1.0", tk.END)
        self.llm_prompt_text.insert(tk.END, template)
        self.llm_prompt_text.edit_reset()
        self.llm_prompt_text.configure(state="normal")

    def _save_llm_prompt_template(self):
        if self.llm_prompt_text is None:
            return
        content = self.llm_prompt_text.get("1.0", tk.END).rstrip()
        try:
            discovery_llm.save_system_prompt_template(content)
            messagebox.showinfo("Saved", "System prompt updated.")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save system prompt: {exc}")

    def _reset_llm_prompt_template(self):
        default = discovery_llm.get_default_system_prompt_template()
        try:
            discovery_llm.save_system_prompt_template(default)
            self._load_llm_prompt_template()
            messagebox.showinfo("Reset", "System prompt reset to default.")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to reset system prompt: {exc}")

    def _save_figure_png(self, figure, default_name):
        file_path = filedialog.asksaveasfilename(
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")]
        )
        if not file_path:
            return
        width_in, height_in = figure.get_size_inches()
        max_dim_in = max(width_in, height_in, 1e-6)
        dpi_cap = self.export_max_edge_px / max_dim_in
        dpi = min(self.export_default_dpi, dpi_cap)
        if dpi_cap >= 72:
            dpi = max(dpi, 72)
        dpi = max(dpi, 1)
        figure.savefig(
            file_path,
            dpi=dpi,
            facecolor=figure.get_facecolor(),
            bbox_inches='tight'
        )
        messagebox.showinfo("Success", f"Chart saved to {file_path}")

    def export_png(self):
        month = self.quadrant_month_combo.get()
        if not month:
            messagebox.showerror("Error", "Please select a month.")
            return
        if not self.quadrant_has_data:
            self.update_quadrant_plot()
        if not self.quadrant_has_data:
            messagebox.showerror("Error", "No quadrant data is available to export.")
            return
        safe_month = month.replace('/', '-')
        self._save_figure_png(self.fig, f"quadrant_{safe_month}.png")

    def export_comment_png(self):
        month = (self.comment_month_combo.get() or '').strip()
        if not month:
            messagebox.showerror("Error", "Please select a month.")
            return
        if not self.comment_has_data:
            self.update_comment_volume_plot()
        if not self.comment_has_data:
            messagebox.showerror("Error", "No comment volume data is available to export.")
            return
        safe_month = month.replace('/', '-')
        self._save_figure_png(self.comment_fig, f"hn_comments_{safe_month}.png")

    def export_trajectories_png(self):
        if not self.traj_has_data:
            self.update_trajectories_plot()
        if not self.traj_has_data:
            messagebox.showerror("Error", "No trajectories data is available to export.")
            return
        try:
            months_back = int(self.traj_months_var.get())
        except Exception:
            months_back = 6
        safe_suffix = f"last_{months_back}_months" if months_back else "trajectories"
        self._save_figure_png(self.traj_fig, f"trajectories_{safe_suffix}.png")

    def export_trends_png(self):
        if not self.trend_has_data:
            self.update_trends_plot()
        if not self.trend_has_data:
            messagebox.showerror("Error", "No trend data is available to export.")
            return
        try:
            months_back = int(self.trend_months_var.get())
        except Exception:
            months_back = 12
        safe_suffix = f"last_{months_back}_months" if months_back else "trends"
        self._save_figure_png(self.trend_fig, f"momentum_trends_{safe_suffix}.png")

    def export_csv(self):
        month = self.quadrant_month_combo.get()
        if not month:
            messagebox.showerror("Error", "Please select a month.")
            return

        conn = sqlite3.connect(database.DATABASE_FILE)
        df = pd.read_sql_query(f"SELECT tech_name, average_tone, hn_avg_compound, analyst_lit_score, analyst_whimsy_score FROM monthly_sentiment WHERE month = '{month}'", conn)
        conn.close()

        for col in ['average_tone','hn_avg_compound','analyst_lit_score','analyst_whimsy_score']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        df['momentum'] = df['average_tone'] + df['analyst_lit_score'] + df['analyst_whimsy_score']
        df['conviction'] = df['hn_avg_compound'] + df['analyst_lit_score'] + df['analyst_whimsy_score']
        df = df[['tech_name', 'momentum', 'conviction']]

        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV File", "*.csv")])
        if file_path:
            df.to_csv(file_path, index=False)
            messagebox.showinfo("Success", f"Data saved to {file_path}")

    def export_json(self):
        month = self.quadrant_month_combo.get()
        if not month:
            messagebox.showerror("Error", "Please select a month.")
            return

        conn = sqlite3.connect(database.DATABASE_FILE)
        df = pd.read_sql_query(f"SELECT tech_name, average_tone, hn_avg_compound, analyst_lit_score, analyst_whimsy_score FROM monthly_sentiment WHERE month = '{month}'", conn)
        conn.close()

        for col in ['average_tone','hn_avg_compound','analyst_lit_score','analyst_whimsy_score']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        df['momentum'] = df['average_tone'] + df['analyst_lit_score'] + df['analyst_whimsy_score']
        df['conviction'] = df['hn_avg_compound'] + df['analyst_lit_score'] + df['analyst_whimsy_score']
        df = df[['tech_name', 'momentum', 'conviction']]

        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON File", "*.json")])
        if file_path:
            df.to_json(file_path, orient="records")
            messagebox.showinfo("Success", f"Data saved to {file_path}")

    def create_discover_charts_view(self, notebook):
        charts_frame = ttk.Frame(notebook)
        notebook.add(charts_frame, text="Discover Charts")
        try:
            self.discover_charts_tab = ChartsTab(charts_frame, self)
            self.discover_charts_tab.pack(fill="both", expand=True)
            self.discover_charts_tab.apply_theme()
        except Exception as e:
            self.discover_charts_tab = None
            ttk.Label(charts_frame, text=f"Error loading Discover Charts: {e}").pack(pady=20, padx=20)
