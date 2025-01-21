#!/usr/bin/env python3

import os
import csv
import sqlite3
from datetime import datetime

# Adjust if your DB or table is in a different location/name:
DB_PATH = "../data/bot_messages.db"
TABLE_NAME = "bot_messages"

def main():
    # Create output directory if needed
    out_dir = "exports"
    os.makedirs(out_dir, exist_ok=True)

    # Build a timestamped filename
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_filename = f"all_messages_{timestamp_str}.csv"
    out_path = os.path.join(out_dir, out_filename)

    try:
        # Connect to the SQLite DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Query all messages from the table (sorted by timestamp ascending)
        query = f"""
            SELECT 
                id,
                bot_localpart,
                room_id,
                event_id,
                sender,
                timestamp,
                body
            FROM {TABLE_NAME}
            ORDER BY timestamp ASC
        """
        rows = cursor.execute(query).fetchall()
        
        # Write rows to CSV
        with open(out_path, mode="w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            # Write a header row:
            writer.writerow(["id", 
                             "bot_localpart", 
                             "room_id", 
                             "event_id", 
                             "sender", 
                             "timestamp", 
                             "body"])
            # Write all data rows
            for row in rows:
                writer.writerow(row)
        
        print(f"Exported {len(rows)} messages to '{out_path}'.")
    
    except Exception as e:
        print(f"Error exporting messages: {e}")
    
    finally:
        # Always close the DB connection
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
