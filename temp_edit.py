from pathlib import Path
path = Path('discover/src/charts_gui.py')
text = path.read_text()
if "def export_png" in text:
    raise SystemExit('export_png already defined')
text = text.replace('from tkinter import ttk\n', 'from tkinter import ttk, filedialog, messagebox\n')
text = text.replace('import pandas as pd\n', 'import pandas as pd\nimport os\n')
text = text.replace('        self.refresh_button = ttk.Button(controls_frame, text="Refresh Charts", command=self.refresh_charts)\n        self.refresh_button.pack(side=tk.LEFT)\n\n', '        self.refresh_button = ttk.Button(controls_frame, text="Refresh Charts", command=self.refresh_charts)\n        self.refresh_button.pack(side=tk.LEFT)\n\n        self.export_button = ttk.Button(controls_frame, text="Export PNG", command=self.export_png)\n        self.export_button.pack(side=tk.LEFT, padx=10)\n\n')
text = text.replace('\n    def refresh_charts(self):\n', '\n    def refresh_charts(self):\n')
insert_str = "\n    def export_png(self):\n        \"\"\"Export both charts to PNG files.\"\"\"\n        file_path = filedialog.asksaveasfilename(\n            defaultextension='.png',\n            filetypes=[('PNG Image', '*.png'), ('All Files', '*.*')],\n            title='Export Discover Charts as PNG'\n        )\n        if not file_path:\n            return\n        base, _ = os.path.splitext(file_path)\n        discussion_path = f"{base}_discussion.png"\n        sentiment_path = f"{base}_sentiment.png"\n        try:\n            self.discussion_fig.savefig(discussion_path, dpi=300, facecolor=self.discussion_fig.get_facecolor())\n            self.sentiment_fig.savefig(sentiment_path, dpi=300, facecolor=self.sentiment_fig.get_facecolor())\n            messagebox.showinfo('Export Complete', f'Charts saved to:\n{discussion_path}\n{sentiment_path}')\n        except Exception as exc:\n            messagebox.showerror('Export Error', f'Failed to export charts: {exc}')\n\n'
idx = text.rfind('\n    def apply_theme')
if idx == -1:
    raise SystemExit('apply_theme not found')
text = text[:idx] + insert_str + text[idx:]
path.write_text(text)
