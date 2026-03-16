from datetime import datetime
from database import init_db, is_error_already_tracked, log_error, update_last_seen
from s3_handler import get_file_for_error, cleanup_temp_files
from jira_handler import create_ticket, find_existing_ticket
from file_parser import parse_missing_cdf, parse_missing_images
from sheets_handler import log_to_sheet, init_sheet

def get_report_date():
    """Ask user for the report date and program type"""
    print("\n" + "="*50)
    print("ERROR REPORT PROCESSOR")
    print("="*50)
    
    # Get program type
    print("\nIs this an ACA or MRA report?")
    while True:
        program = input("Program (ACA/MRA): ").strip().upper()
        if program in ("ACA", "MRA"):
            break
        print("Please enter ACA or MRA")
    
    print("\nEnter the report date from the email")
    print("Format: YYYYMMDD (e.g. 20260303)")
    date_input = input("Report date: ").strip()
    
    # Validate format
    try:
        datetime.strptime(date_input, "%Y%m%d")
    except ValueError:
        print("Invalid date format! Please use YYYYMMDD")
        return get_report_date()
    
    # Format for display in tickets e.g. 3.3
    month = str(int(date_input[4:6]))
    day = str(int(date_input[6:8]))
    display_date = f"{month}.{day}"
    
    return date_input, display_date, program

def get_summary_counts():
    """Ask user to paste the summary counts from the email"""
    print("\n--- SUMMARY COUNTS FROM EMAIL ---")
    print("Copy and paste the summary counts from the email.")
    print("When done, type END on a new line and press ENTER:\n")
    
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line.strip())
    
    # Remove empty lines
    lines = [l for l in lines if l]
    
    # Default counts
    counts = {
        "FAILED_IMAGES": 0,
        "MISSING_IMAGES": 0,
        "MISSING_CDF": 0
    }
    
    for line in lines:
        try:
            if "Failed Images" in line:
                counts["FAILED_IMAGES"] = int(line.split(":")[1].strip())
            elif "Missing Images" in line:
                counts["MISSING_IMAGES"] = int(line.split(":")[1].strip())
            elif "Missing CDF" in line:
                counts["MISSING_CDF"] = int(line.split(":")[1].strip())
        except (ValueError, IndexError):
            print(f"  Could not parse line: {line}")
            continue
    
    print(f"\n  ✓ Failed Images: {counts['FAILED_IMAGES']}")
    print(f"  ✓ Missing Images: {counts['MISSING_IMAGES']}")
    print(f"  ✓ Missing CDF: {counts['MISSING_CDF']}")
    
    return counts

def get_error_table():
    """Ask user to paste the OVERALL table from the email"""
    print("\n--- OVERALL ERROR TABLE ---")
    print("Copy and paste the OVERALL table from the email.")
    print("When done, type END on a new line and press ENTER:\n")
    
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line.strip())
    
    # Remove empty lines
    lines = [l for l in lines if l]
    
    # Known header values to skip
    headers = {
        "PROJECT DESCRIPTION", "Vendor", "ERROR CODE", "SUB",
        "MESSAGE", "CHASES", "RECORDS", "Avg_Days", "Avg_Weeks",
        "OVERALL", "ALL", "CI"
    }
    
    # Filter out header/label lines
    data_lines = [l for l in lines if l not in headers]
    
    errors = []
    i = 0
    
    while i < len(data_lines):
        try:
            error_code = data_lines[i]
            if not error_code.isdigit():
                i += 1
                continue
            
            sub = data_lines[i + 1]
            message = data_lines[i + 2]
            chases = int(data_lines[i + 3])
            records = int(data_lines[i + 4])
            avg_days = int(data_lines[i + 5])
            avg_weeks = int(data_lines[i + 6])
            
            errors.append({
                "error_code": error_code,
                "chases": chases,
                "records": records,
                "avg_days": avg_days,
                "avg_weeks": avg_weeks
            })
            
            print(f"  ✓ Parsed error code {error_code} "
                  f"(chases: {chases}, avg_weeks: {avg_weeks})")
            
            i += 7
            
        except (IndexError, ValueError):
            i += 1
            continue
    
    if not errors:
        print("No errors parsed - please check the pasted content")
    else:
        print(f"\nSuccessfully parsed {len(errors)} errors")
    
    return errors

def confirm_ticket(error_code, count, display_date, avg_weeks=None, description=None):
    """
    Show the user what ticket is about to be created and ask for confirmation
    Returns True if user confirms, False if user skips
    """
    print("\n" + "-"*40)
    print("TICKET TO BE CREATED:")
    print(f"  Error Type : {error_code}")
    print(f"  Count      : {count}")
    print(f"  Date       : {display_date}")
    if avg_weeks is not None:
        print(f"  Avg Weeks  : {avg_weeks}")
    if description:
        print(f"  Description: {description}")
    print("-"*40)
    
    while True:
        response = input("Create this ticket? (y/n): ").strip().lower()
        if response == 'y':
            return True
        elif response == 'n':
            print("Skipping this ticket.")
            return False
        else:
            print("Please enter y or n")

def process_summary_errors(summary_counts, report_date, display_date, program):
    """Process failed images and missing CDF from summary section"""
    results = []
    
    for error_type, total_count in summary_counts.items():
        if total_count == 0:
            print(f"\nSkipping {error_type} - count is 0")
            continue
        
        if error_type == "MISSING_IMAGES":
            print(f"\nSkipping MISSING_IMAGES - no ticket needed")
            continue
        
        print(f"\nProcessing {error_type} (total count: {total_count})...")
        
        # Check if already tracked in database
        existing_ticket = is_error_already_tracked(error_type, report_date)
        if existing_ticket:
            print(f"  Already tracked - ticket {existing_ticket} exists. Updating last seen date.")
            update_last_seen(error_type, report_date)
            results.append({
                "error_type": error_type,
                "status": "already_tracked",
                "ticket": existing_ticket
            })
            continue
        
        # Check Jira directly
        jira_ticket = find_existing_ticket(error_type)
        if jira_ticket:
            print(f"  Found existing Jira ticket {jira_ticket}. Skipping.")
            results.append({
                "error_type": error_type,
                "status": "already_tracked",
                "ticket": jira_ticket
            })
            continue
        
        # Download file from S3 and get accurate new count
        local_file = get_file_for_error(error_type, report_date)
        new_count = total_count  # fallback to total if parsing fails
        
        if local_file:
            if error_type == "MISSING_CDF":
                new_count = parse_missing_cdf(local_file, report_date)
            elif error_type == "FAILED_IMAGES":
                new_count = parse_missing_images(local_file)
        
        if new_count == 0:
            print(f"  No new {error_type} this week - skipping")
            continue
        
        # Build description and title
        from config import ERROR_DESCRIPTION_MAP, ERROR_TITLE_MAP
        description = ERROR_DESCRIPTION_MAP[error_type].format(count=new_count)
        title = ERROR_TITLE_MAP[error_type].format(
            count=new_count,
            date=display_date,
            program=program
        )
        
        # Ask for confirmation
        confirmed = confirm_ticket(error_type, new_count, display_date, description=description)
        if not confirmed:
            results.append({
                "error_type": error_type,
                "status": "skipped_by_user",
                "ticket": None
            })
            continue
        
        # Create ticket
        ticket_key, ticket_url = create_ticket(
            error_code=error_type,
            count=new_count,
            report_date=display_date,
            local_file_path=local_file,
            program=program
        )
        
        if ticket_key:
            log_error(
                error_code=error_type,
                jira_ticket_id=ticket_key,
                jira_ticket_url=ticket_url,
                report_date=report_date,
                chase_count=0,
                record_count=new_count,
                avg_days=0,
                avg_weeks=0
            )
            log_to_sheet(
                report_date=report_date,
                error_type=error_type,
                new_count=new_count,
                jira_ticket=ticket_key,
                jira_url=ticket_url
            )
            results.append({
                "error_type": error_type,
                "status": "created",
                "ticket": ticket_key,
                "url": ticket_url
            })
    
    return results

def process_error_table(errors, report_date, display_date, program):
    """Process errors from the OVERALL error table"""
    results = []
    
    # Check if both 22 and 33 are present
    error_codes = [e["error_code"] for e in errors]
    has_22 = "22" in error_codes
    has_33 = "33" in error_codes
    combo_22_33 = has_22 and has_33
    error_33_handled = False
    
    for error in errors:
        error_code = error["error_code"]
        avg_weeks = error["avg_weeks"]
        
        # Skip error 16 - needs client discussion
        if error_code == "16":
            print(f"\nSkipping error 16 - needs client discussion")
            results.append({
                "error_code": error_code,
                "status": "skipped_by_design",
                "ticket": None
            })
            continue
        
        # Skip 33 if already handled as part of combo
        if error_code == "33" and error_33_handled:
            print(f"\nError 33 already handled in combo ticket - skipping")
            continue
        
        print(f"\nProcessing error code {error_code} (avg_weeks: {avg_weeks})...")
        
        # Check if already tracked in database
        existing_ticket = is_error_already_tracked(error_code, report_date)
        if existing_ticket:
            print(f"  Already tracked - ticket {existing_ticket} exists. Updating last seen date.")
            update_last_seen(error_code, report_date)
            results.append({
                "error_code": error_code,
                "status": "already_tracked",
                "ticket": existing_ticket
            })
            continue
        
        # If avg_weeks > 0 check Jira directly
        if avg_weeks > 0:
            jira_ticket = find_existing_ticket(error_code)
            if jira_ticket:
                print(f"  Found existing Jira ticket {jira_ticket}. Skipping.")
                results.append({
                    "error_code": error_code,
                    "status": "already_tracked",
                    "ticket": jira_ticket
                })
                continue
        
        # Download file from S3
        local_file = get_file_for_error(error_code, report_date)
        
        # Build title and description based on combo or single
        from config import ERROR_DESCRIPTION_MAP, ERROR_TITLE_MAP
        
        if error_code == "22" and combo_22_33:
            count_22 = next(e["chases"] for e in errors if e["error_code"] == "22")
            count_33 = next(e["chases"] for e in errors if e["error_code"] == "33")
            description = ERROR_DESCRIPTION_MAP["22"].format(
                count_22=count_22,
                count_33=count_33
            )
            title = ERROR_TITLE_MAP["22"].format(
                date=display_date,
                program=program
            )
            count = count_22 + count_33
            error_33_handled = True
            
            confirmed = confirm_ticket(
                error_code="22 & 33",
                count=count,
                display_date=display_date,
                avg_weeks=avg_weeks,
                description=description
            )
            if not confirmed:
                results.append({
                    "error_code": error_code,
                    "status": "skipped_by_user",
                    "ticket": None
                })
                continue
            
            ticket_key, ticket_url = create_ticket(
                error_code="22",
                count=count,
                report_date=display_date,
                local_file_path=local_file,
                count_22=count_22,
                count_33=count_33,
                program=program
            )

        elif error_code == "22" and not combo_22_33:
            count_22 = error["chases"]
            description = ERROR_DESCRIPTION_MAP["22_only"].format(count_22=count_22)
            title = ERROR_TITLE_MAP["22_only"].format(
                date=display_date,
                program=program
            )
            count = count_22
            
            confirmed = confirm_ticket(
                error_code="22",
                count=count,
                display_date=display_date,
                avg_weeks=avg_weeks,
                description=description
            )
            if not confirmed:
                results.append({
                    "error_code": error_code,
                    "status": "skipped_by_user",
                    "ticket": None
                })
                continue
            
            ticket_key, ticket_url = create_ticket(
                error_code="22_only",
                count=count,
                report_date=display_date,
                local_file_path=local_file,
                count_22=count_22,
                program=program
            )

        elif error_code == "33" and not combo_22_33:
            count_33 = error["chases"]
            description = ERROR_DESCRIPTION_MAP["33_only"].format(count_33=count_33)
            title = ERROR_TITLE_MAP["33_only"].format(
                date=display_date,
                program=program
            )
            count = count_33
            
            confirmed = confirm_ticket(
                error_code="33",
                count=count,
                display_date=display_date,
                avg_weeks=avg_weeks,
                description=description
            )
            if not confirmed:
                results.append({
                    "error_code": error_code,
                    "status": "skipped_by_user",
                    "ticket": None
                })
                continue
            
            ticket_key, ticket_url = create_ticket(
                error_code="33_only",
                count=count,
                report_date=display_date,
                local_file_path=local_file,
                count_33=count_33,
                program=program
            )

        else:
            count = error["chases"]
            description = ERROR_DESCRIPTION_MAP.get(
                error_code,
                f"Hello,\n\nAetna {program} Output File Errors to Correct.\n\nError {error_code} reported with {count} chases. Please see attached file."
            )
            if description:
                description = description.format(count=count) if "{count}" in description else description
            
            confirmed = confirm_ticket(
                error_code=error_code,
                count=count,
                display_date=display_date,
                avg_weeks=avg_weeks,
                description=description
            )
            if not confirmed:
                results.append({
                    "error_code": error_code,
                    "status": "skipped_by_user",
                    "ticket": None
                })
                continue
            
            ticket_key, ticket_url = create_ticket(
                error_code=error_code,
                count=count,
                report_date=display_date,
                local_file_path=local_file,
                program=program
            )
        
        if ticket_key:
            log_error(
                error_code=error_code,
                jira_ticket_id=ticket_key,
                jira_ticket_url=ticket_url,
                report_date=report_date,
                chase_count=error["chases"],
                record_count=error["records"],
                avg_days=error["avg_days"],
                avg_weeks=avg_weeks
            )
            log_to_sheet(
                report_date=report_date,
                error_type=f"Error 22 & 33" if combo_22_33 else f"Error {error_code}",
                new_count=count,
                jira_ticket=ticket_key,
                jira_url=ticket_url
            )
            results.append({
                "error_code": error_code,
                "status": "created",
                "ticket": ticket_key,
                "url": ticket_url
            })
    
    return results

def print_summary(summary_results, error_results):
    """Print a summary of what was done"""
    print("\n" + "="*50)
    print("PROCESSING COMPLETE - SUMMARY")
    print("="*50)
    
    all_results = summary_results + error_results
    
    created = [r for r in all_results if r["status"] == "created"]
    skipped = [r for r in all_results if r["status"] == "already_tracked"]
    skipped_by_user = [r for r in all_results if r["status"] == "skipped_by_user"]
    skipped_by_design = [r for r in all_results if r["status"] == "skipped_by_design"]
    
    if created:
        print(f"\n✓ Created {len(created)} new tickets:")
        for r in created:
            key = r.get("error_code") or r.get("error_type")
            print(f"  - {key}: {r['ticket']} ({r.get('url', '')})")
    
    if skipped:
        print(f"\n→ Skipped {len(skipped)} already tracked errors:")
        for r in skipped:
            key = r.get("error_code") or r.get("error_type")
            print(f"  - {key}: {r['ticket']}")
    
    if skipped_by_user:
        print(f"\n✗ Skipped {len(skipped_by_user)} errors by user choice:")
        for r in skipped_by_user:
            key = r.get("error_code") or r.get("error_type")
            print(f"  - {key}")
    
    if skipped_by_design:
        print(f"\n⚠ Skipped {len(skipped_by_design)} errors by design:")
        for r in skipped_by_design:
            key = r.get("error_code") or r.get("error_type")
            print(f"  - {key}")
    
    if not all_results:
        print("\nNo errors to process!")

def main():
    # Initialize database and sheet
    init_db()
    init_sheet()
    
    # Auto sync Jira statuses before processing
    from sync_status import sync_jira_to_sheet
    print("\nSyncing ticket statuses before processing...")
    sync_jira_to_sheet()
    
    # Get report date and program type
    report_date, display_date, program = get_report_date()
    
    # Get summary counts
    summary_counts = get_summary_counts()
    
    # Get error table entries
    errors = get_error_table()
    
    # Process everything
    print("\n--- PROCESSING ERRORS ---")
    
    summary_results = process_summary_errors(
        summary_counts, report_date, display_date, program
    )
    
    error_results = process_error_table(
        errors, report_date, display_date, program
    )
    
    # Print summary
    print_summary(summary_results, error_results)
    
    # Cleanup temp files
    print("\nCleaning up temp files...")
    cleanup_temp_files()
    
    print("\nDone!")

if __name__ == "__main__":
    main()