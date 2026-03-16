import streamlit as st

st.set_page_config(
    page_title="Error Report Processor",
    layout="wide",
    page_icon="🔧",
)

import pandas as pd
from datetime import datetime

from config import ERROR_DESCRIPTION_MAP, ERROR_TITLE_MAP
from database import init_db, is_error_already_tracked, log_error, update_last_seen, get_all_open_errors
from s3_handler import get_file_for_error, cleanup_temp_files
from jira_handler import create_ticket, find_existing_ticket
from file_parser import parse_missing_cdf, parse_missing_images
from sheets_handler import log_to_sheet, init_sheet
from sync_status import sync_jira_to_sheet

# ── Sample data ───────────────────────────────────────────────────────────────

SAMPLE_SUMMARY = "Failed Images: 47\nMissing Images: 12\nMissing CDF: 23"

SAMPLE_ERROR_TABLE = """22
A
Disposition Error
150
89
14
2
33
B
Disposition Error
45
32
7
1
42
A
Outstanding CDF Error
78
56
21
3"""

# ── One-time initialization (cached so it only runs once per server session) ──

@st.cache_resource
def initialize_services():
    init_db()
    try:
        init_sheet()
    except Exception:
        pass  # Non-fatal — sheet init may fail when credentials aren't configured


initialize_services()


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_summary_text(text: str) -> dict:
    counts = {"FAILED_IMAGES": 0, "MISSING_IMAGES": 0, "MISSING_CDF": 0}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            if "Failed Images" in line:
                counts["FAILED_IMAGES"] = int(line.split(":")[1].strip())
            elif "Missing Images" in line:
                counts["MISSING_IMAGES"] = int(line.split(":")[1].strip())
            elif "Missing CDF" in line:
                counts["MISSING_CDF"] = int(line.split(":")[1].strip())
        except (ValueError, IndexError):
            continue
    return counts


def parse_error_table_text(text: str) -> list:
    skip_labels = {
        "PROJECT DESCRIPTION", "Vendor", "ERROR CODE", "SUB",
        "MESSAGE", "CHASES", "RECORDS", "Avg_Days", "Avg_Weeks",
        "OVERALL", "ALL", "CI",
    }
    lines = [l.strip() for l in text.strip().splitlines() if l.strip() and l.strip() not in skip_labels]

    errors = []
    i = 0
    while i < len(lines):
        try:
            error_code = lines[i]
            if not error_code.isdigit():
                i += 1
                continue
            chases = int(lines[i + 3])
            records = int(lines[i + 4])
            avg_days = int(lines[i + 5])
            avg_weeks = int(lines[i + 6])
            errors.append({
                "error_code": error_code,
                "chases": chases,
                "records": records,
                "avg_days": avg_days,
                "avg_weeks": avg_weeks,
            })
            i += 7
        except (IndexError, ValueError):
            i += 1
    return errors


# ── Session state helpers ─────────────────────────────────────────────────────

def reset_workflow():
    for key in ["stage", "report_date", "display_date", "summary_counts",
                "errors", "selected_errors", "results", "summary_ta", "error_ta"]:
        st.session_state.pop(key, None)


def _init_state(key, default):
    if key not in st.session_state:
        st.session_state[key] = default


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.header("Report Configuration")

        st.selectbox("Program", ["ACA", "MRA"], key="program")
        st.text_input(
            "Report Date (YYYYMMDD)",
            placeholder="e.g. 20260303",
            key="date_input",
        )

        st.divider()
        st.caption("Sync Jira statuses to Google Sheet before processing.")
        if st.button("🔄 Sync Jira Statuses", use_container_width=True):
            with st.spinner("Syncing..."):
                try:
                    sync_jira_to_sheet()
                    st.success("Sync complete!")
                except Exception as e:
                    st.error(f"Sync failed: {e}")

        st.divider()
        stage = st.session_state.get("stage", "input")
        if stage != "input":
            if st.button("↩ Start Over", use_container_width=True):
                reset_workflow()
                st.rerun()


# ── Tab 1: Process Report ─────────────────────────────────────────────────────

def render_process_tab():
    _init_state("stage", "input")

    stage = st.session_state.stage
    stages = ["Input", "Review", "Done"]
    idx = {"input": 0, "review": 1, "done": 2}.get(stage, 0)

    cols = st.columns(3)
    for i, (col, label) in enumerate(zip(cols, stages)):
        with col:
            if i < idx:
                st.success(f"✓ {label}")
            elif i == idx:
                st.info(f"● {label}")
            else:
                st.caption(f"○ {label}")

    st.divider()

    if stage == "input":
        render_input_stage()
    elif stage == "review":
        render_review_stage()
    elif stage == "done":
        render_done_stage()


def render_input_stage():
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Summary Counts")
        st.caption("Paste the summary section from the error report email.")
        if st.button("Load sample", key="btn_sample_summary"):
            st.session_state["summary_ta"] = SAMPLE_SUMMARY
        st.text_area(
            "Summary counts",
            height=160,
            placeholder="Failed Images: 47\nMissing Images: 12\nMissing CDF: 23",
            label_visibility="collapsed",
            key="summary_ta",
        )

    with col2:
        st.subheader("Overall Error Table")
        st.caption("Paste the OVERALL table from the error report email.")
        if st.button("Load sample", key="btn_sample_errors"):
            st.session_state["error_ta"] = SAMPLE_ERROR_TABLE
        st.text_area(
            "Error table",
            height=160,
            placeholder="22\nA\nDisposition Error\n150\n89\n14\n2",
            label_visibility="collapsed",
            key="error_ta",
        )

    if st.button("Parse & Review →", type="primary", use_container_width=True):
        date_input = st.session_state.get("date_input", "").strip()
        if not date_input:
            st.error("Please enter a report date in the sidebar.")
            return
        try:
            datetime.strptime(date_input, "%Y%m%d")
        except ValueError:
            st.error("Invalid date format. Use YYYYMMDD (e.g. 20260303).")
            return

        summary_text = st.session_state.get("summary_ta", "")
        error_text = st.session_state.get("error_ta", "")

        summary_counts = parse_summary_text(summary_text)
        errors = parse_error_table_text(error_text)

        if all(v == 0 for v in summary_counts.values()) and not errors:
            st.error("No data could be parsed. Please check your input.")
            return

        month = str(int(date_input[4:6]))
        day = str(int(date_input[6:8]))
        st.session_state.report_date = date_input
        st.session_state.display_date = f"{month}.{day}"
        st.session_state.summary_counts = summary_counts
        st.session_state.errors = errors
        st.session_state.selected_errors = {}
        st.session_state.stage = "review"
        st.rerun()


def render_review_stage():
    display_date = st.session_state.display_date
    program = st.session_state.program
    counts = st.session_state.summary_counts
    errors = st.session_state.errors

    st.subheader(f"{program} Report — {display_date}")

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Failed Images", counts.get("FAILED_IMAGES", 0))
    col2.metric("Missing Images", counts.get("MISSING_IMAGES", 0))
    col3.metric("Missing CDF", counts.get("MISSING_CDF", 0))

    st.divider()

    # Summary error checkboxes
    st.subheader("Summary Errors")
    st.caption("Uncheck any errors you want to skip.")
    sel = st.session_state.selected_errors

    for error_type, count in counts.items():
        if count == 0:
            continue
        if error_type == "MISSING_IMAGES":
            st.info(f"MISSING_IMAGES ({count}) — skipped automatically (no ticket needed)")
            continue
        key = f"summary_{error_type}"
        sel[key] = st.checkbox(
            f"{error_type}: **{count}** records",
            value=sel.get(key, True),
            key=f"chk_{key}",
        )

    # Error table checkboxes
    if errors:
        st.subheader("Error Table")
        df = pd.DataFrame(errors).rename(columns={
            "error_code": "Error Code",
            "chases": "Chases",
            "records": "Records",
            "avg_days": "Avg Days",
            "avg_weeks": "Avg Weeks",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.caption("Uncheck any errors you want to skip.")
        for i, error in enumerate(errors):
            code = error["error_code"]
            if code == "16":
                st.warning(f"Error 16 — skipped by design (needs client discussion)")
                continue
            key = f"error_{code}_{i}"
            label = (
                f"Error **{code}**: {error['chases']} chases, "
                f"{error['records']} records, avg {error['avg_weeks']} wk(s)"
            )
            sel[key] = st.checkbox(label, value=sel.get(key, True), key=f"chk_{key}")

    col_back, col_go = st.columns([1, 4])
    with col_back:
        if st.button("← Back"):
            st.session_state.stage = "input"
            st.rerun()
    with col_go:
        if st.button("Process Selected →", type="primary", use_container_width=True):
            results = run_processing()
            st.session_state.results = results
            st.session_state.stage = "done"
            st.rerun()


def run_processing() -> list:
    """Execute all ticket creation and logging. Returns list of result dicts."""
    program = st.session_state.program
    report_date = st.session_state.report_date
    display_date = st.session_state.display_date
    counts = st.session_state.summary_counts
    errors = st.session_state.errors
    selected = st.session_state.selected_errors
    results = []

    with st.status("Processing errors...", expanded=True) as status:

        # ── Summary errors ────────────────────────────────────────────────────
        for error_type, total_count in counts.items():
            if total_count == 0:
                continue
            if error_type == "MISSING_IMAGES":
                continue

            key = f"summary_{error_type}"
            if not selected.get(key, True):
                st.write(f"⏭ Skipped {error_type} (user choice)")
                results.append({"label": error_type, "status": "skipped_by_user", "ticket": None})
                continue

            st.write(f"Processing **{error_type}**...")
            try:
                existing = is_error_already_tracked(error_type, report_date)
                if existing:
                    update_last_seen(error_type, report_date)
                    st.write(f"  → Already tracked: {existing}")
                    results.append({"label": error_type, "status": "already_tracked", "ticket": existing})
                    continue

                jira_ticket = find_existing_ticket(error_type)
                if jira_ticket:
                    st.write(f"  → Jira ticket found: {jira_ticket}")
                    results.append({"label": error_type, "status": "already_tracked", "ticket": jira_ticket})
                    continue

                local_file = get_file_for_error(error_type, report_date)
                new_count = total_count
                if local_file:
                    if error_type == "MISSING_CDF":
                        new_count = parse_missing_cdf(local_file, report_date)
                    elif error_type == "FAILED_IMAGES":
                        new_count = parse_missing_images(local_file)

                if new_count == 0:
                    st.write(f"  → No new records this week, skipping")
                    continue

                ticket_key, ticket_url = create_ticket(
                    error_code=error_type,
                    count=new_count,
                    report_date=display_date,
                    local_file_path=local_file,
                    program=program,
                )
                if ticket_key:
                    log_error(
                        error_code=error_type, jira_ticket_id=ticket_key,
                        jira_ticket_url=ticket_url, report_date=report_date,
                        chase_count=0, record_count=new_count, avg_days=0, avg_weeks=0,
                    )
                    log_to_sheet(
                        report_date=report_date, error_type=error_type,
                        new_count=new_count, jira_ticket=ticket_key, jira_url=ticket_url,
                    )
                    st.write(f"  ✅ Created [{ticket_key}]({ticket_url})")
                    results.append({"label": error_type, "status": "created", "ticket": ticket_key, "url": ticket_url})
                else:
                    st.write(f"  ❌ Ticket creation failed")
                    results.append({"label": error_type, "status": "error", "ticket": None})

            except Exception as e:
                st.write(f"  ❌ {error_type}: {e}")
                results.append({"label": error_type, "status": "error", "ticket": None, "error": str(e)})

        # ── Error table ───────────────────────────────────────────────────────
        if errors:
            error_codes = [e["error_code"] for e in errors]
            combo_22_33 = "22" in error_codes and "33" in error_codes
            error_33_handled = False

            for i, error in enumerate(errors):
                code = error["error_code"]
                avg_weeks = error["avg_weeks"]

                if code == "16":
                    results.append({"label": f"Error {code}", "status": "skipped_by_design", "ticket": None})
                    continue

                if code == "33" and error_33_handled:
                    continue

                key = f"error_{code}_{i}"
                if not selected.get(key, True):
                    st.write(f"⏭ Skipped Error {code} (user choice)")
                    results.append({"label": f"Error {code}", "status": "skipped_by_user", "ticket": None})
                    continue

                st.write(f"Processing **Error {code}**...")
                try:
                    existing = is_error_already_tracked(code, report_date)
                    if existing:
                        update_last_seen(code, report_date)
                        st.write(f"  → Already tracked: {existing}")
                        results.append({"label": f"Error {code}", "status": "already_tracked", "ticket": existing})
                        continue

                    if avg_weeks > 0:
                        jira_ticket = find_existing_ticket(code)
                        if jira_ticket:
                            st.write(f"  → Jira ticket found: {jira_ticket}")
                            results.append({"label": f"Error {code}", "status": "already_tracked", "ticket": jira_ticket})
                            continue

                    local_file = get_file_for_error(code, report_date)

                    if code == "22" and combo_22_33:
                        count_22 = next(e["chases"] for e in errors if e["error_code"] == "22")
                        count_33 = next(e["chases"] for e in errors if e["error_code"] == "33")
                        count = count_22 + count_33
                        error_33_handled = True
                        ticket_label = "Error 22 & 33"
                        ticket_key, ticket_url = create_ticket(
                            error_code="22", count=count, report_date=display_date,
                            local_file_path=local_file, count_22=count_22, count_33=count_33, program=program,
                        )
                    elif code == "22":
                        count = error["chases"]
                        ticket_label = "Error 22"
                        ticket_key, ticket_url = create_ticket(
                            error_code="22_only", count=count, report_date=display_date,
                            local_file_path=local_file, count_22=count, program=program,
                        )
                    elif code == "33":
                        count = error["chases"]
                        ticket_label = "Error 33"
                        ticket_key, ticket_url = create_ticket(
                            error_code="33_only", count=count, report_date=display_date,
                            local_file_path=local_file, count_33=count, program=program,
                        )
                    else:
                        count = error["chases"]
                        ticket_label = f"Error {code}"
                        ticket_key, ticket_url = create_ticket(
                            error_code=code, count=count, report_date=display_date,
                            local_file_path=local_file, program=program,
                        )

                    if ticket_key:
                        log_error(
                            error_code=code, jira_ticket_id=ticket_key,
                            jira_ticket_url=ticket_url, report_date=report_date,
                            chase_count=error["chases"], record_count=error["records"],
                            avg_days=error["avg_days"], avg_weeks=avg_weeks,
                        )
                        log_to_sheet(
                            report_date=report_date, error_type=ticket_label,
                            new_count=count, jira_ticket=ticket_key, jira_url=ticket_url,
                        )
                        st.write(f"  ✅ Created [{ticket_key}]({ticket_url})")
                        results.append({
                            "label": ticket_label, "status": "created",
                            "ticket": ticket_key, "url": ticket_url,
                        })
                    else:
                        st.write(f"  ❌ Ticket creation failed")
                        results.append({"label": ticket_label, "status": "error", "ticket": None})

                except Exception as e:
                    st.write(f"  ❌ Error {code}: {e}")
                    results.append({"label": f"Error {code}", "status": "error", "ticket": None, "error": str(e)})

        cleanup_temp_files()
        status.update(label="Done!", state="complete")

    return results


def render_done_stage():
    results = st.session_state.get("results", [])
    created = [r for r in results if r["status"] == "created"]
    already_tracked = [r for r in results if r["status"] == "already_tracked"]
    skipped_user = [r for r in results if r["status"] == "skipped_by_user"]
    skipped_design = [r for r in results if r["status"] == "skipped_by_design"]
    errored = [r for r in results if r["status"] == "error"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tickets Created", len(created))
    col2.metric("Already Tracked", len(already_tracked))
    col3.metric("Skipped", len(skipped_user) + len(skipped_design))
    col4.metric("Errors", len(errored), delta=None if not errored else f"{len(errored)} failed", delta_color="inverse")

    if created:
        st.subheader("New Tickets Created")
        rows = [{"Error": r["label"], "Ticket": r["ticket"], "URL": r.get("url", "")} for r in created]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if already_tracked:
        with st.expander(f"Already tracked ({len(already_tracked)})"):
            rows = [{"Error": r["label"], "Ticket": r["ticket"]} for r in already_tracked]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if errored:
        with st.expander(f"Failed ({len(errored)})", expanded=True):
            for r in errored:
                st.error(f"{r['label']}: {r.get('error', 'unknown error')}")

    st.success("Processing complete!")

    if st.button("Process Another Report", type="primary"):
        reset_workflow()
        st.rerun()


# ── Tab 2: View Tracker ───────────────────────────────────────────────────────

def render_tracker_tab():
    st.subheader("Open Error Tracker")
    st.caption("All errors currently tracked with open Jira tickets.")

    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.rerun()

    try:
        rows = get_all_open_errors()
    except Exception as e:
        st.error(f"Could not load tracker: {e}")
        rows = []

    if rows:
        df = pd.DataFrame(rows, columns=[
            "Error Code", "Jira Ticket", "Jira URL",
            "First Seen", "Last Seen", "Chases", "Avg Weeks", "Status",
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No open errors currently tracked in the local database.")

        try:
            sample_df = pd.read_csv("sample_data.csv")
            st.caption("Showing sample_data.csv as a demo:")
            st.dataframe(sample_df, use_container_width=True, hide_index=True)
        except FileNotFoundError:
            pass


# ── Tab 3: Settings ───────────────────────────────────────────────────────────

def render_settings_tab():
    st.subheader("Required Secrets")
    st.write("Create `.streamlit/secrets.toml` with the following structure:")

    st.code("""
[jira]
url            = "https://your-org.atlassian.net/"
email          = "your@email.com"
api_token      = "your-jira-api-token"
project_key    = "COD"
label          = "aetna"

[aws]
access_key_id     = "AKIA..."
secret_access_key = "your-secret-key"
region            = "us-east-1"
bucket_name       = "your-s3-bucket"
folder_path       = "production/toYourFolder/"

[google_sheets]
sheet_id = "your-google-sheet-id"

# Paste the full contents of your service account JSON here:
[google_credentials]
type                        = "service_account"
project_id                  = "your-gcp-project"
private_key_id              = "key-id"
private_key                 = "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"
client_email                = "your-sa@project.iam.gserviceaccount.com"
client_id                   = "..."
auth_uri                    = "https://accounts.google.com/o/oauth2/auth"
token_uri                   = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url        = "https://www.googleapis.com/robot/v1/metadata/x509/your-sa%40project.iam.gserviceaccount.com"
""", language="toml")

    st.info(
        "Alternatively, place your service account key file as "
        "`error-report-automation.json` in the project root. "
        "The `[google_credentials]` section in secrets.toml takes precedence."
    )

    st.divider()
    st.subheader("Connection Status")
    col1, col2, col3 = st.columns(3)

    with col1:
        try:
            from jira_handler import get_jira_client
            get_jira_client()
            st.success("✅ Jira")
        except Exception as e:
            st.error(f"❌ Jira\n\n`{str(e)[:120]}`")

    with col2:
        try:
            from s3_handler import get_s3_client
            get_s3_client()
            st.success("✅ AWS / S3")
        except Exception as e:
            st.error(f"❌ AWS / S3\n\n`{str(e)[:120]}`")

    with col3:
        try:
            from sheets_handler import get_sheets_client
            get_sheets_client()
            st.success("✅ Google Sheets")
        except Exception as e:
            st.error(f"❌ Google Sheets\n\n`{str(e)[:120]}`")


# ── Entry point ───────────────────────────────────────────────────────────────

render_sidebar()

st.title("🔧 Error Report Processor")
st.caption(
    "Paste your weekly Aetna error report email data, review the parsed errors, "
    "and automatically create Jira tickets and log results to Google Sheets."
)

tab1, tab2, tab3 = st.tabs(["📋 Process Report", "📊 View Tracker", "⚙️ Settings"])

with tab1:
    render_process_tab()

with tab2:
    render_tracker_tab()

with tab3:
    render_settings_tab()
