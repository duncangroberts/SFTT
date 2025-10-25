#!/usr/bin/env python
"""GUI for the Discover tab."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue
import subprocess
import os

from discover.src import pipeline, db_manager

class DiscoverTab(ttk.Frame):
    def __init__(self, parent, app_instance):
        super().__init__(parent)
        self.app = app_instance
        self.log_queue = queue.Queue()
        self.llm_server_process = None
        self.pipeline_running = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self, style='BrandNotebook.TNotebook')
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # --- Themes tab ---
        themes_tab = ttk.Frame(self.notebook)
        themes_tab.grid_rowconfigure(1, weight=3)
        themes_tab.grid_rowconfigure(2, weight=2)
        themes_tab.grid_rowconfigure(3, weight=2)
        themes_tab.grid_rowconfigure(4, weight=1)
        themes_tab.grid_columnconfigure(0, weight=1)
        self.notebook.add(themes_tab, text="Themes")

        theme_controls = ttk.Frame(themes_tab)
        theme_controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        self.refresh_button = ttk.Button(theme_controls, text="Refresh Themes", command=self.refresh_themes)
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10))

        self.purge_button = ttk.Button(theme_controls, text="Purge Discover DB", command=self.purge_database)
        self.purge_button.pack(side=tk.LEFT, padx=(0, 10))

        tree_frame = ttk.LabelFrame(themes_tab, text="Top Themes")
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        columns = ("name", "score", "sentiment", "score_trend", "sentiment_trend")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", style='Brand.Treeview')
        self.tree.heading("name", text="Theme")
        self.tree.heading("score", text="Discussion Score")
        self.tree.heading("sentiment", text="Sentiment")
        self.tree.heading("score_trend", text="Discussion Trend")
        self.tree.heading("sentiment_trend", text="Sentiment Trend")
        self.tree.column("name", anchor="w", stretch=True)
        self.tree.column("score", anchor="center", width=120)
        self.tree.column("sentiment", anchor="center", width=110)
        self.tree.column("score_trend", anchor="center", width=140)
        self.tree.column("sentiment_trend", anchor="center", width=140)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_theme_select)

        flatlined_frame = ttk.LabelFrame(themes_tab, text="Flatlined Themes")
        flatlined_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        flatlined_frame.grid_rowconfigure(0, weight=1)
        flatlined_frame.grid_columnconfigure(0, weight=1)

        self.flatlined_tree = ttk.Treeview(flatlined_frame, columns=columns, show="headings", style='Brand.Treeview')
        self.flatlined_tree.heading("name", text="Theme")
        self.flatlined_tree.heading("score", text="Discussion Score")
        self.flatlined_tree.heading("sentiment", text="Sentiment")
        self.flatlined_tree.heading("score_trend", text="Discussion Trend")
        self.flatlined_tree.heading("sentiment_trend", text="Sentiment Trend")
        self.flatlined_tree.column("name", anchor="w", stretch=True)
        self.flatlined_tree.column("score", anchor="center", width=120)
        self.flatlined_tree.column("sentiment", anchor="center", width=110)
        self.flatlined_tree.column("score_trend", anchor="center", width=140)
        self.flatlined_tree.column("sentiment_trend", anchor="center", width=140)
        self.flatlined_tree.pack(fill="both", expand=True)
        self.flatlined_tree.bind("<<TreeviewSelect>>", self.on_theme_select)

        coma_frame = ttk.LabelFrame(themes_tab, text="Coma Themes")
        coma_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        coma_frame.grid_rowconfigure(0, weight=1)
        coma_frame.grid_columnconfigure(0, weight=1)

        self.coma_tree = ttk.Treeview(coma_frame, columns=columns, show="headings", style='Brand.Treeview')
        self.coma_tree.heading("name", text="Theme")
        self.coma_tree.heading("score", text="Discussion Score")
        self.coma_tree.heading("sentiment", text="Sentiment")
        self.coma_tree.heading("score_trend", text="Discussion Trend")
        self.coma_tree.heading("sentiment_trend", text="Sentiment Trend")
        self.coma_tree.column("name", anchor="w", stretch=True)
        self.coma_tree.column("score", anchor="center", width=120)
        self.coma_tree.column("sentiment", anchor="center", width=110)
        self.coma_tree.column("score_trend", anchor="center", width=140)
        self.coma_tree.column("sentiment_trend", anchor="center", width=140)
        self.coma_tree.pack(fill="both", expand=True)
        self.coma_tree.bind("<<TreeviewSelect>>", self.on_theme_select)

        story_frame = ttk.LabelFrame(themes_tab, text="Stories for Theme")
        story_frame.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 10))
        story_frame.grid_rowconfigure(0, weight=1)
        story_frame.grid_columnconfigure(0, weight=1)

        self.story_text = tk.Text(story_frame, wrap="word", state="disabled", height=8)
        self.story_text.pack(fill="both", expand=True, pady=5, padx=5)

        # --- Run Discovery tab ---
        run_tab = ttk.Frame(self.notebook)
        run_tab.grid_rowconfigure(1, weight=1)
        run_tab.grid_columnconfigure(0, weight=1)
        self.notebook.add(run_tab, text="Run Discovery")

        run_controls = ttk.Frame(run_tab)
        run_controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        self.run_button = ttk.Button(run_controls, text="Run Discovery Pipeline", command=self.run_pipeline)
        self.run_button.pack(side=tk.LEFT, padx=(0, 10))

        self.export_logs_button = ttk.Button(run_controls, text="Export Logs", command=self.export_logs)
        self.export_logs_button.pack(side=tk.LEFT)

        log_frame = ttk.LabelFrame(run_tab, text="Logs")
        log_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", height=12)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

        # --- LLM Server tab ---
        server_tab = ttk.Frame(self.notebook)
        server_tab.grid_columnconfigure(0, weight=1)
        server_tab.grid_rowconfigure(0, weight=1)
        self.notebook.add(server_tab, text="LLM Server")

        server_frame = ttk.LabelFrame(server_tab, text="Server Control")
        server_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        model_row = ttk.Frame(server_frame)
        model_row.pack(fill="x", pady=(0, 10))
        ttk.Label(model_row, text="Model:").pack(side=tk.LEFT, padx=(0, 5))
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model_var, width=40)
        self.model_combo.pack(side=tk.LEFT, fill="x", expand=True)
        self.populate_model_dropdown()

        status_row = ttk.Frame(server_frame)
        status_row.pack(fill="x", pady=(0, 10))
        ttk.Label(status_row, text="Status:").pack(side=tk.LEFT, padx=(0, 5))
        self.llm_status_var = tk.StringVar(value="Not Running")
        self.llm_status_label = ttk.Label(status_row, textvariable=self.llm_status_var)
        self.llm_status_label.pack(side=tk.LEFT)

        button_row = ttk.Frame(server_frame)
        button_row.pack(fill="x")
        self.start_llm_button = ttk.Button(button_row, text="Start Server", command=self.start_llm_server)
        self.start_llm_button.pack(side=tk.LEFT, padx=(0, 10))
        self.stop_llm_button = ttk.Button(button_row, text="Stop Server", command=self.stop_llm_server, state="disabled")
        self.stop_llm_button.pack(side=tk.LEFT)

        self.after(100, self.process_log_queue)
        self.refresh_themes()
        self.update_run_button_state()
        self.apply_theme()

    def log(self, message):
        self.log_queue.put(message)

    def process_log_queue(self):
        while not self.log_queue.empty():
            message = self.log_queue.get()
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.config(state="disabled")
            self.log_text.see(tk.END)
        self.after(100, self.process_log_queue)

    def llm_is_running(self):
        return self.llm_server_process is not None and self.llm_server_process.poll() is None

    def update_run_button_state(self):
        if not hasattr(self, "run_button"):
            return
        if self.pipeline_running or not self.llm_is_running():
            self.run_button.config(state="disabled")
        else:
            self.run_button.config(state="normal")

    def _current_colors(self):
        colors = getattr(self.app, 'brand_colors', None)
        if colors:
            return colors
        # Fallback palette mirroring light theme defaults
        return {
            'bg': '#d9d9d9',
            'panel': '#f0f0f0',
            'fig_bg': '#ffffff',
            'text': '#1f1f1f',
            'accent': '#2f5597',
            'grid': '#b5b5b5'
        }

    def apply_theme(self):
        colors = dict(self._current_colors())
        try:
            self.notebook.configure(style='BrandNotebook.TNotebook')
        except tk.TclError:
            pass
        try:
            self.tree.configure(style='Brand.Treeview')
        except tk.TclError:
            pass
        self.tree.tag_configure('theme-row', foreground=colors.get('text', '#000000'))
        fig_bg = colors.get('fig_bg', '#ffffff')
        text_color = colors.get('text', '#000000')
        text_kwargs = {
            'bg': fig_bg,
            'fg': text_color,
            'insertbackground': colors.get('accent', '#2f5597')
        }
        highlight_color = colors.get('grid', text_color)
        selection_bg = colors.get('accent', '#2f5597')
        if str(fig_bg).lower() in ('#000000', '#000', '#111111'):
            selection_fg = text_color
        else:
            selection_fg = fig_bg
        for widget in (getattr(self, 'story_text', None), getattr(self, 'log_text', None)):
            if widget is not None:
                widget.configure(**text_kwargs,
                                 selectbackground=selection_bg,
                                 selectforeground=selection_fg,
                                 highlightthickness=1,
                                 highlightbackground=highlight_color,
                                 highlightcolor=highlight_color,
                                 relief='flat',
                                 borderwidth=0)

    def run_pipeline(self):
        if not self.llm_is_running():
            messagebox.showwarning("LLM Server Required", "Start the LLM server before running the discovery pipeline.")
            self.log("Cannot run discovery pipeline because the LLM server is not running.")
            self.update_run_button_state()
            return
        if self.pipeline_running:
            return
        self.pipeline_running = True
        self.update_run_button_state()
        self.log("Starting discovery pipeline in background...")
        threading.Thread(target=self._run_pipeline_worker, daemon=True).start()

    def _run_pipeline_worker(self):
        import sys
        original_stdout = sys.stdout
        sys.stdout = self
        try:
            pipeline.run_discovery_pipeline()
            self.log("Pipeline finished.")
        except Exception as e:
            self.log(f"Pipeline failed: {e}")
            messagebox.showerror("Pipeline Error", str(e))
        finally:
            sys.stdout = original_stdout
            self.after(0, self._on_pipeline_finished)

    def _on_pipeline_finished(self):
        self.pipeline_running = False
        self.update_run_button_state()
        self.refresh_themes()

    def write(self, message):
        self.log(message.strip())

    def flush(self):
        pass

    def refresh_themes(self):
        tree_widgets = [self.tree, self.flatlined_tree, self.coma_tree]
        for widget in tree_widgets:
            if widget:
                for item in widget.get_children():
                    widget.delete(item)
        try:
            db_manager.cleanup_theme_story_links()
        except Exception as exc:
            self.log(f"Failed to clean theme links: {exc}")
        active_themes = db_manager.get_top_themes()
        flatlined_themes = db_manager.get_top_flatlined_themes(limit=10)
        coma_themes = db_manager.get_top_coma_themes(limit=10)
        self._populate_theme_tree(self.tree, active_themes)
        self._populate_theme_tree(self.flatlined_tree, flatlined_themes)
        self._populate_theme_tree(self.coma_tree, coma_themes)

    def _populate_theme_tree(self, tree_widget, themes):
        if tree_widget is None:
            return
        for theme in themes:
            sentiment = theme.get("sentiment_score")
            sentiment_display = f"{sentiment:.2f}" if sentiment is not None else "0.00"
            tree_widget.insert(
                "",
                tk.END,
                iid=str(theme["id"]),
                values=(
                    theme["name"],
                    theme["discussion_score"],
                    sentiment_display,
                    theme.get("discussion_score_trend"),
                    theme.get("sentiment_score_trend")
                ),
                tags=("theme-row",)
            )

    def _clear_other_tree_selections(self, active_tree):
        for tree_widget in (self.tree, self.flatlined_tree, self.coma_tree):
            if tree_widget is None or tree_widget is active_tree:
                continue
            for item in tree_widget.selection():
                tree_widget.selection_remove(item)

    def populate_model_dropdown(self):
        try:
            models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'models'))
            if os.path.exists(models_dir):
                gguf_files = [f for f in os.listdir(models_dir) if f.endswith('.gguf')]
                if gguf_files:
                    self.model_combo['values'] = gguf_files
                    self.model_combo.set(gguf_files[0])
                else:
                    self.model_combo.set("No GGUF models found in /models")
            else:
                self.model_combo.set("/models directory not found")
        except Exception as e:
            self.log(f"Error finding models: {e}")
            self.model_combo.set("Error finding models")

    def on_theme_select(self, event):
        tree_widget = getattr(event, "widget", None)
        if tree_widget not in (self.tree, self.flatlined_tree, self.coma_tree):
            return
        selection = tree_widget.selection()
        if not selection:
            return
        self._clear_other_tree_selections(tree_widget)
        item_id = selection[0]
        try:
            theme_id = int(item_id)
        except (TypeError, ValueError):
            self.log(f"Unexpected theme identifier: {item_id}")
            return
        theme = db_manager.get_theme_by_id(theme_id)
        if not theme:
            return
        stories = db_manager.get_stories_for_theme(theme_id)
        self.story_text.config(state="normal")
        self.story_text.delete("1.0", tk.END)
        if not stories:
            self.story_text.insert(tk.END, "No stories found for this theme.")
        else:
            for story in stories:
                self.story_text.insert(tk.END, f"{story['title']}\n{story['url']}\n\n")
        self.story_text.config(state="disabled")

    def purge_database(self):
        if messagebox.askyesno("Confirm Purge", "Are you sure you want to delete all data from the Discover database?"):
            try:
                db_manager.purge_discover_database()
                self.log("Discover database purged successfully.")
                self.refresh_themes()
            except Exception as e:
                self.log(f"Error during Discover DB purge: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    def export_logs(self):
        log_content = self.log_text.get("1.0", tk.END)
        if not log_content.strip():
            messagebox.showinfo("Export Logs", "There is no log content to export.")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                messagebox.showinfo("Export Successful", f"Logs successfully saved to {file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to save logs: {e}")

    def start_llm_server(self):
        self.log("Starting LLM server...")
        try:
            selected_model_file = self.model_var.get()
            if not selected_model_file or not selected_model_file.endswith('.gguf'):
                messagebox.showerror("Model Error", "Please select a valid GGUF model from the dropdown.")
                self.update_run_button_state()
                return

            server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'llama.cpp', 'llama-server.exe'))
            model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'models', selected_model_file))
            
            self.log(f"Server path: {server_path}")
            self.log(f"Model path: {model_path}")
            
            if not os.path.exists(server_path):
                self.log("Error: llama-server.exe not found!")
                messagebox.showerror("Server Error", f"Server executable not found at {server_path}")
                self.update_run_button_state()
                return
            
            if not os.path.exists(model_path):
                self.log(f"Error: Model file not found at {model_path}")
                messagebox.showerror("Server Error", f"Model file not found at {model_path}")
                self.update_run_button_state()
                return

            command = [server_path, "-m", model_path, "-c", "4096"]
            self.log(f"Running command: {' '.join(command)}")

            self.llm_server_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            threading.Thread(target=self._monitor_llm_server, daemon=True).start()

            self.start_llm_button.config(state="disabled")
            self.stop_llm_button.config(state="normal")
            self.llm_status_var.set("Running")
        except Exception as e:
            self.log(f"Failed to start LLM server: {e}")
            messagebox.showerror("Server Error", f"Failed to start LLM server: {e}")
        finally:
            self.update_run_button_state()

    def _monitor_llm_server(self):
        if self.llm_server_process and self.llm_server_process.stdout:
            for line in iter(self.llm_server_process.stdout.readline, ''):
                self.log(f"[LLM Server] {line.strip()}")
        self.after(0, self.stop_llm_server)

    def stop_llm_server(self):
        if self.llm_server_process:
            self.log("Stopping LLM server...")
            self.llm_server_process.terminate()
            self.llm_server_process.wait()
            self.llm_server_process = None
            self.log("LLM server stopped.")
        
        self.start_llm_button.config(state="normal")
        self.stop_llm_button.config(state="disabled")
        self.llm_status_var.set("Not Running")
        self.update_run_button_state()
