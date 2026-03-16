# Error Report Processor

A Streamlit app that converts weekly Aetna error report emails into Jira tickets and Google Sheet log entries — replacing a manual, CLI-driven workflow with a point-and-click web UI.

## What it does

1. **Input** — paste the summary counts and OVERALL error table from the weekly email
2. **Review** — see all parsed errors in a table; uncheck any you want to skip
3. **Process** — for each selected error the app:
   - checks the local SQLite database and Jira for existing open tickets
   - downloads the relevant support file from S3
   - creates a Jira ticket with the file attached
   - logs the result to Google Sheets
4. **Summary** — see all created tickets at a glance

Additional features:
- **View Tracker** tab — browse all currently open errors from the local database
- **Sync Jira Statuses** — pull the latest Jira status for every tracked ticket back into the Google Sheet
- **Settings** tab — verify connection status for Jira, AWS, and Google Sheets

---

## Quick start (local)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure secrets

Copy the template and fill in your credentials:

```bash
cp .streamlit/secrets.toml .streamlit/secrets.toml.bak   # keep a blank copy
# edit .streamlit/secrets.toml with your real values
```

See the **Secrets reference** section below for all required fields.

Alternatively, export the same values as environment variables (useful for CI):

```
JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY, JIRA_LABEL
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET_NAME, S3_FOLDER_PATH
GOOGLE_SHEET_ID
```

For Google Sheets authentication you also need either:
- `error-report-automation.json` (service account key file) in the project root, **or**
- the `[google_credentials]` section filled out in `secrets.toml`

### 3. Run

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Demo mode

Click **Load sample** in either input field to pre-fill with synthetic data. Parsing and the review step work without any credentials. Actual ticket creation requires Jira / AWS / Google Sheets to be configured.

---

## Secrets reference

```toml
# .streamlit/secrets.toml

[jira]
url         = "https://your-org.atlassian.net/"
email       = "you@yourcompany.com"
api_token   = "your-jira-api-token"   # Account Settings → Security → API tokens
project_key = "COD"
label       = "aetna"

[aws]
access_key_id     = "AKIA..."
secret_access_key = "..."
region            = "us-east-1"
bucket_name       = "your-s3-bucket"
folder_path       = "production/toYourFolder/"

[google_sheets]
sheet_id = "the-id-from-the-sheet-url"

[google_credentials]   # paste contents of your service account JSON
type          = "service_account"
project_id    = "..."
private_key   = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email  = "sa@project.iam.gserviceaccount.com"
# ... (see .streamlit/secrets.toml for all fields)
```

---

## Deploying to Streamlit Community Cloud

1. Push this repo to GitHub (**do not commit** `secrets.toml` or `error-report-automation.json`)
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app
3. Set **Main file path** to `app.py`
4. Paste the contents of your `secrets.toml` into the **Secrets** panel
5. Deploy

---

## Project structure

```
.
├── app.py                        # Streamlit entry point
├── config.py                     # Credentials loader (st.secrets → env vars)
├── database.py                   # SQLite tracker
├── jira_handler.py               # Jira ticket creation / lookup
├── s3_handler.py                 # S3 file download
├── sheets_handler.py             # Google Sheets logging
├── file_parser.py                # Excel file parsers (MissingCDF, MissingImages)
├── sync_status.py                # Jira → Sheet status sync
├── sample_data.csv               # Synthetic demo data
├── requirements.txt
└── .streamlit/
    └── secrets.toml              # Credentials template (fill in, never commit)
```
