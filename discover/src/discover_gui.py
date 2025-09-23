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

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1) # Allow log viewer to expand

        # --- Controls ---
        controls_frame = ttk.Frame(self)
        controls_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)

        self.run_button = ttk.Button(controls_frame, text="Run Discovery Pipeline", command=self.run_pipeline)
        self.run_button.pack(side=tk.LEFT, padx=(0, 10))

        self.refresh_button = ttk.Button(controls_frame, text="Refresh Themes", command=self.refresh_themes)
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10))

        self.purge_button = ttk.Button(controls_frame, text="Purge Discover DB", command=self.purge_database)
        self.purge_button.pack(side=tk.LEFT, padx=(0, 10))

        self.export_logs_button = ttk.Button(controls_frame, text="Export Logs", command=self.export_logs)
        self.export_logs_button.pack(side=tk.LEFT)
        
        # --- LLM Server Controls ---
        llm_frame = ttk.LabelFrame(controls_frame, text="LLM Server")
        llm_frame.pack(side=tk.RIGHT, padx=(20, 0))

        # Model selection dropdown
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(llm_frame, textvariable=self.model_var, width=40)
        self.model_combo.pack(side=tk.LEFT, padx=5)
        self.populate_model_dropdown()

        self.llm_status_var = tk.StringVar(value="Not Running")
        self.llm_status_label = ttk.Label(llm_frame, textvariable=self.llm_status_var)
        self.llm_status_label.pack(side=tk.LEFT, padx=5)

        self.start_llm_button = ttk.Button(llm_frame, text="Start Server", command=self.start_llm_server)
        self.start_llm_button.pack(side=tk.LEFT, padx=5)

        self.stop_llm_button = ttk.Button(llm_frame, text="Stop Server", command=self.stop_llm_server, state="disabled")
        self.stop_llm_button.pack(side=tk.LEFT, padx=5)

        # --- Main content area (Themes and Logs) ---
        main_frame = ttk.Frame(self)
        main_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)

        # --- Themes Treeview ---
        tree_frame = ttk.LabelFrame(main_frame, text="Top Themes")
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(0, 10))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, columns=("score", "sentiment", "score_trend", "sentiment_trend"), show="headings")
        self.tree.heading("score", text="Discussion Score")
        self.tree.heading("sentiment", text="Sentiment")
        self.tree.heading("score_trend", text="Discussion Trend")
        self.tree.heading("sentiment_trend", text="Sentiment Trend")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_theme_select)

        # --- Log Viewer ---
        log_frame = ttk.LabelFrame(main_frame, text="Logs")
        log_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=(0, 10))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", height=10)
        self.log_text.pack(fill="both", expand=True)

        # --- Story Details ---
        story_frame = ttk.LabelFrame(self, text="Stories for Theme")
        story_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        story_frame.grid_rowconfigure(0, weight=1)
        story_frame.grid_columnconfigure(0, weight=1)

        self.story_text = tk.Text(story_frame, wrap="word", state="disabled", height=8)
        self.story_text.pack(fill="both", expand=True, pady=5, padx=5)

        self.after(100, self.process_log_queue)
        self.refresh_themes()

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

    def run_pipeline(self):
        self.run_button.config(state="disabled")
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
            self.run_button.config(state="normal")
            self.after(0, self.refresh_themes)
    
    def write(self, message):
        self.log(message.strip())

    def flush(self):
        pass

    def refresh_themes(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        themes = db_manager.get_top_themes()
        for theme in themes:
            self.tree.insert("", tk.END, text=theme["name"], values=(
                theme["discussion_score"],
                f"{theme['sentiment_score']:.2f}",
                theme["discussion_score_trend"],
                theme["sentiment_score_trend"]
            ))

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
        selection = self.tree.selection()
        if not selection:
            return
        item = self.tree.item(selection[0])
        theme_name = item['text']
        theme = db_manager.get_theme_by_name(theme_name)
        if not theme:
            return
        stories = db_manager.get_stories_for_theme(theme['id'])
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
                return

            server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'llama.cpp', 'llama-server.exe'))
            model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'models', selected_model_file))
            
            self.log(f"Server path: {server_path}")
            self.log(f"Model path: {model_path}")
            
            if not os.path.exists(server_path):
                self.log("Error: llama-server.exe not found!")
                messagebox.showerror("Server Error", f"Server executable not found at {server_path}")
                return
            
            if not os.path.exists(model_path):
                self.log(f"Error: Model file not found at {model_path}")
                messagebox.showerror("Server Error", f"Model file not found at {model_path}")
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
