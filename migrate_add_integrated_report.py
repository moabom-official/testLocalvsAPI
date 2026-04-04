#!/usr/bin/env python
"""
Migration script to add integrated_report column to video_reports table.
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/techdb")

def main():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute('''
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'video_reports' AND column_name = 'integrated_report'
            )
        ''')
        exists = cursor.fetchone()[0]
        
        if not exists:
            print("Adding integrated_report column...")
            cursor.execute('''
                ALTER TABLE video_reports 
                ADD COLUMN integrated_report TEXT
            ''')
            conn.commit()
            print("✓ Column added successfully")
        else:
            print("✓ Column already exists")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")
        if conn:
            conn.rollback()
            conn.close()

if __name__ == "__main__":
    main()
