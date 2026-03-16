import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from config import SHEET_ID, CREDENTIALS_FILE

# Google Sheets configuration
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Column headers
HEADERS = [
    "Date Logged",
    "Report Date",
    "Error Type",
    "New Count",
    "Jira Ticket",
    "Jira URL",
    "Status",
    "Notes"
]

def get_sheets_client():
    """Create and return a Google Sheets client.

    Credentials are resolved in priority order:
    1. st.secrets["google_credentials"]  (Streamlit Cloud / secrets.toml)
    2. Local service account JSON file    (CREDENTIALS_FILE from config)
    """
    try:
        import streamlit as st
        creds_dict = dict(st.secrets["google_credentials"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except Exception:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def get_worksheet():
    """Get the worksheet"""
    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)
    return sheet.sheet1

def init_sheet():
    """Set up headers if sheet is empty"""
    ws = get_worksheet()
    
    # Check if headers already exist
    first_row = ws.row_values(1)
    
    if not first_row:
        print("Adding headers to sheet...")
        ws.append_row(HEADERS)
        print("Headers added!")
    else:
        print("Sheet already has headers")

def log_to_sheet(report_date, error_type, new_count, jira_ticket, jira_url, status="Open", notes=""):
    """
    Log a new ticket entry to the Google Sheet
    report_date format: YYYYMMDD e.g. 20260303
    """
    try:
        ws = get_worksheet()
        
        # Format dates for display
        date_logged = datetime.now().strftime("%m/%d/%Y")
        report_date_formatted = f"{report_date[4:6]}/{report_date[6:8]}/{report_date[2:4]}"
        
        row = [
            date_logged,
            report_date_formatted,
            error_type,
            new_count,
            jira_ticket,
            jira_url,
            status,
            notes
        ]
        
        ws.append_row(row)
        print(f"Logged {error_type} to Google Sheet")
        return True
    
    except Exception as e:
        print(f"Error logging to Google Sheet: {e}")
        return False

def update_ticket_status(jira_ticket, new_status, notes=""):
    """Update the status of a ticket in the sheet"""
    try:
        ws = get_worksheet()
        
        # Find the row with this ticket
        cell = ws.find(jira_ticket)
        
        if not cell:
            print(f"Ticket {jira_ticket} not found in sheet")
            return False
        
        # Update status column (column 7)
        ws.update_cell(cell.row, 7, new_status)
        
        # Update notes if provided
        if notes:
            ws.update_cell(cell.row, 8, notes)
        
        print(f"Updated {jira_ticket} status to {new_status}")
        return True
    
    except Exception as e:
        print(f"Error updating sheet: {e}")
        return False

def get_open_entries():
    """Get all open entries from the sheet"""
    try:
        ws = get_worksheet()
        records = ws.get_all_records()
        
        open_entries = [r for r in records if r.get("Status") == "Open"]
        return open_entries
    
    except Exception as e:
        print(f"Error reading sheet: {e}")
        return []

if __name__ == "__main__":
    # Test connection and init sheet
    print("Testing Google Sheets connection...")
    
    try:
        init_sheet()
        print("Connected successfully!")
        
        # Test logging a row
        print("\nLogging a test row...")
        log_to_sheet(
            report_date="20260303",
            error_type="TEST",
            new_count=1,
            jira_ticket="COD-TEST",
            jira_url="https://datavant.atlassian.net/browse/COD-TEST",
            status="Open",
            notes="This is a test entry"
        )
        print("Test row logged - check your Google Sheet!")
        
    except Exception as e:
        print(f"Error: {e}")