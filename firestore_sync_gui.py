import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import sqlite3
from google.cloud import firestore
import os

class FirestoreSyncTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.log_queue = queue.Queue()

        # UI Elements
        sync_button = ttk.Button(self, text="Sync to Firestore", command=self.start_sync)
        sync_button.pack(pady=10)

        self.log_text = tk.Text(self, height=20, width=80)
        self.log_text.pack(pady=10, fill="both", expand=True)

        self.after(100, self.process_log_queue)

    def log(self, message):
        self.log_queue.put(message)

    def process_log_queue(self):
        while not self.log_queue.empty():
            message = self.log_queue.get_nowait()
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
        self.after(100, self.process_log_queue)

    def start_sync(self):
        if not os.path.exists("serviceAccountKey.json"):
            messagebox.showerror("Error", "serviceAccountKey.json not found. Please follow the setup instructions.")
            return

        self.log("Starting Firestore sync...")
        threading.Thread(target=self.perform_sync, daemon=True).start()

    def perform_sync(self):
        try:
            # Initialize Firestore client
            db = firestore.Client.from_service_account_json("serviceAccountKey.json")
            self.log("Firestore client initialized.")

            # Sync tracker_data.sqlite
            self.sync_table(db, 'tracker_data.sqlite', 'monthly_sentiment', ['tech_id', 'month'])

            # Sync discover.sqlite
            discover_db_path = os.path.join('discover', 'db', 'discover.sqlite')
            self.sync_table(db, discover_db_path, 'themes', ['id'])
            self.sync_table(db, discover_db_path, 'stories', ['id'])
            self.sync_table(db, discover_db_path, 'theme_stories', ['theme_id', 'story_id'])

            self.log("Firestore sync completed successfully.")
            messagebox.showinfo("Success", "Firestore sync completed successfully.")

        except Exception as e:
            self.log(f"An error occurred during Firestore sync: {e}")
            messagebox.showerror("Error", f"An error occurred during Firestore sync: {e}")

    def sync_table(self, firestore_db, db_path, table_name, primary_key_cols):
        self.log(f"Syncing table: {table_name} from {db_path}")
        if not os.path.exists(db_path):
            self.log(f"Database file not found: {db_path}")
            return

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        conn.close()

        collection_ref = firestore_db.collection(table_name)
        for row in rows:
            doc_id = "_".join(str(row[col]) for col in primary_key_cols)
            doc_ref = collection_ref.document(doc_id)
            data = dict(row)
            # Convert binary data to bytes if necessary
            for key, value in data.items():
                if isinstance(value, bytes):
                    data[key] = value.hex() # Store blobs as hex strings
            doc_ref.set(data)

        self.log(f"Synced {len(rows)} documents to '{table_name}' collection.")
