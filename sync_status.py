from jira import JIRA
from sheets_handler import get_worksheet
from jira_handler import get_jira_client

def sync_jira_to_sheet():
    """
    Check all open tickets in Google Sheet against Jira
    and update their status
    """
    print("\nSyncing Jira statuses to Google Sheet...")
    
    try:
        jira = get_jira_client()
        ws = get_worksheet()
        records = ws.get_all_records()
        
        updated_count = 0
        
        for i, record in enumerate(records):
            ticket = record.get("Jira Ticket")
            current_status = record.get("Status")
            
            # Skip empty rows or already closed tickets
            if not ticket or current_status in ("Done", "Canceled"):
                continue
            
            try:
                # Get current status from Jira
                issue = jira.issue(ticket)
                jira_status = issue.fields.status.name
                
                # Row number in sheet (add 2 - 1 for header, 1 for zero index)
                row_num = i + 2
                
                # Update if status has changed
                if jira_status != current_status:
                    ws.update_cell(row_num, 7, jira_status)
                    print(f"  Updated {ticket}: {current_status} → {jira_status}")
                    updated_count += 1
                else:
                    print(f"  {ticket}: no change ({current_status})")
                    
            except Exception as e:
                print(f"  Error checking {ticket}: {e}")
                continue
        
        if updated_count == 0:
            print("All tickets already up to date!")
        else:
            print(f"\nUpdated {updated_count} ticket(s)")
            
    except Exception as e:
        print(f"Error syncing: {e}")

if __name__ == "__main__":
    sync_jira_to_sheet()