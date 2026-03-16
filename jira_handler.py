from jira import JIRA
from config import (
    JIRA_URL,
    JIRA_EMAIL,
    JIRA_API_TOKEN,
    JIRA_PROJECT_KEY,
    JIRA_LABEL,
    ERROR_TITLE_MAP,
    ERROR_DESCRIPTION_MAP
)

def get_jira_client():
    """Create and return a Jira client"""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    return JIRA(
        server=JIRA_URL,
        basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        options={
            'server': JIRA_URL,
            'verify': False,
            'check_update': False
        }
    )

def get_open_tickets():
    """Get all open tickets in the project"""
    jira = get_jira_client()
    
    issues = jira.search_issues(
        f'project={JIRA_PROJECT_KEY} AND status not in ("Done", "Canceled") AND labels = "{JIRA_LABEL}"',
        maxResults=50
    )
    
    return issues

def find_existing_ticket(error_code):
    """
    Check if an open ticket already exists for this error code
    Returns ticket key if found, None if not
    """
    jira = get_jira_client()
    
    if error_code not in ERROR_TITLE_MAP:
        return None
    
    if ERROR_TITLE_MAP[error_code] is None:
        return None
    
    # Search for open tickets with matching summary and label
    search_term = ERROR_TITLE_MAP[error_code].split("{")[0].strip()
    
    issues = jira.search_issues(
        f'project={JIRA_PROJECT_KEY} '
        f'AND status not in ("Done", "Canceled") '
        f'AND labels = "{JIRA_LABEL}" '
        f'AND summary ~ "{search_term}"',
        maxResults=5
    )
    
    if issues:
        print(f"Found existing ticket for error {error_code}: {issues[0].key}")
        return issues[0].key
    
    return None

def create_ticket(error_code, count, report_date, local_file_path=None,
                  count_22=None, count_33=None, program="ACA"):
    """
    Create a Jira ticket for a given error code
    Returns the created ticket key and url or None if failed
    """
    jira = get_jira_client()
    
    if error_code not in ERROR_TITLE_MAP:
        print(f"No ticket template found for error code {error_code}")
        return None, None
    
    if ERROR_TITLE_MAP[error_code] is None:
        print(f"Error code {error_code} is set to skip")
        return None, None
    
    # Format title
    title = ERROR_TITLE_MAP[error_code].format(
        count=count,
        date=report_date,
        program=program
    )
    
    # Format description - handle combo 22/33 case
    if error_code == "22" and count_22 is not None and count_33 is not None:
        description = ERROR_DESCRIPTION_MAP[error_code].format(
            count_22=count_22,
            count_33=count_33
        )
    elif error_code == "22_only" and count_22 is not None:
        description = ERROR_DESCRIPTION_MAP[error_code].format(
            count_22=count_22
        )
    elif error_code == "33_only" and count_33 is not None:
        description = ERROR_DESCRIPTION_MAP[error_code].format(
            count_33=count_33
        )
    else:
        description = ERROR_DESCRIPTION_MAP[error_code].format(
            count=count,
            date=report_date
        )
    
    # Build ticket fields
    issue_dict = {
        'project': {'key': JIRA_PROJECT_KEY},
        'summary': title,
        'description': description,
        'issuetype': {'name': 'Task'},
        'labels': [JIRA_LABEL]
    }
    
    try:
        # Create the ticket
        print(f"Creating Jira ticket for error {error_code}...")
        new_issue = jira.create_issue(fields=issue_dict)
        print(f"Created ticket: {new_issue.key}")
        
        # Attach the file if provided
        if local_file_path:
            print(f"Attaching file to {new_issue.key}...")
            with open(local_file_path, 'rb') as f:
                jira.add_attachment(
                    issue=new_issue.key,
                    attachment=f,
                    filename=local_file_path.split('/')[-1]
                )
            print(f"File attached successfully!")
        
        # Return ticket key and URL
        ticket_url = f"{JIRA_URL}browse/{new_issue.key}"
        return new_issue.key, ticket_url
    
    except Exception as e:
        print(f"Error creating ticket for {error_code}: {e}")
        return None, None

if __name__ == "__main__":
    # Test - check Jira connection and list open tickets
    print("Testing Jira connection...")
    
    try:
        jira = get_jira_client()
        print("Connected to Jira successfully!")
        
        print(f"\nChecking for open tickets in {JIRA_PROJECT_KEY}...")
        tickets = get_open_tickets()
        
        if tickets:
            print(f"Found {len(tickets)} open tickets:")
            for ticket in tickets:
                print(f"  {ticket.key}: {ticket.fields.summary}")
        else:
            print("No open tickets found")
            
    except Exception as e:
        print(f"Error connecting to Jira: {e}")