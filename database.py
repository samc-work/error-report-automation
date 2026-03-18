import sqlite3
import os

DB_PATH = "error_tracker.db"

def init_db():
    """Create the database and tables if they don't exist"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_code TEXT NOT NULL,
            jira_ticket_id TEXT NOT NULL,
            jira_ticket_url TEXT,
            first_seen_date TEXT NOT NULL,
            last_seen_date TEXT NOT NULL,
            report_date TEXT NOT NULL,
            chase_count INTEGER,
            record_count INTEGER,
            avg_days INTEGER,
            avg_weeks INTEGER,
            status TEXT DEFAULT 'open',
            notes TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")

def is_error_already_tracked(error_code, report_date, date_specific=False):
    """
    Check if an error code already has an open ticket.
    If date_specific=True, only matches entries for this exact report date
    (used for per-week errors like MISSING_CDF and FAILED_IMAGES).
    Returns the jira ticket id if found, None if not.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if date_specific:
        cursor.execute("""
            SELECT jira_ticket_id
            FROM tracked_errors
            WHERE error_code = ?
            AND report_date = ?
            AND status = 'open'
        """, (error_code, report_date))
    else:
        cursor.execute("""
            SELECT jira_ticket_id
            FROM tracked_errors
            WHERE error_code = ?
            AND status = 'open'
        """, (error_code,))

    result = cursor.fetchone()
    conn.close()

    if result:
        return result[0]
    return None

def log_error(error_code, jira_ticket_id, jira_ticket_url, report_date, 
              chase_count, record_count, avg_days, avg_weeks):
    """Log a newly created ticket to the database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO tracked_errors (
            error_code,
            jira_ticket_id,
            jira_ticket_url,
            first_seen_date,
            last_seen_date,
            report_date,
            chase_count,
            record_count,
            avg_days,
            avg_weeks,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
    """, (
        error_code,
        jira_ticket_id,
        jira_ticket_url,
        report_date,
        report_date,
        report_date,
        chase_count,
        record_count,
        avg_days,
        avg_weeks
    ))
    
    conn.commit()
    conn.close()
    print(f"Logged error {error_code} with ticket {jira_ticket_id}")

def update_last_seen(error_code, report_date):
    """Update the last seen date for an existing tracked error"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE tracked_errors 
        SET last_seen_date = ?
        WHERE error_code = ?
        AND status = 'open'
    """, (report_date, error_code))
    
    conn.commit()
    conn.close()

def close_error(error_code):
    """Mark an error as closed when the ticket is resolved"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE tracked_errors 
        SET status = 'closed'
        WHERE error_code = ?
        AND status = 'open'
    """, (error_code,))
    
    conn.commit()
    conn.close()
    print(f"Closed tracking for error {error_code}")

def get_all_open_errors():
    """Get all currently open/tracked errors - useful for review"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            error_code,
            jira_ticket_id,
            jira_ticket_url,
            first_seen_date,
            last_seen_date,
            chase_count,
            avg_weeks,
            status
        FROM tracked_errors 
        WHERE status = 'open'
        ORDER BY first_seen_date DESC
    """)
    
    results = cursor.fetchall()
    conn.close()
    return results

if __name__ == "__main__":
    init_db()