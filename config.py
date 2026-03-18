import os
import toml

# Load .streamlit/secrets.toml directly when running outside Streamlit
_toml_secrets: dict = {}
_secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
try:
    _toml_secrets = toml.load(_secrets_path)
except Exception:
    pass


def _secret(section: str, key: str, env_var: str = "") -> str:
    """
    Read a secret in priority order:
    1. st.secrets (when running under Streamlit)
    2. .streamlit/secrets.toml (when running main.py directly)
    3. Environment variable
    """
    try:
        import streamlit as st
        return st.secrets[section][key]
    except Exception:
        pass
    try:
        return _toml_secrets[section][key]
    except (KeyError, TypeError):
        pass
    return os.environ.get(env_var, "")


# Jira Configuration
JIRA_URL = _secret("jira", "url", "JIRA_URL")
JIRA_EMAIL = _secret("jira", "email", "JIRA_EMAIL")
JIRA_API_TOKEN = _secret("jira", "api_token", "JIRA_API_TOKEN")
JIRA_PROJECT_KEY = _secret("jira", "project_key", "JIRA_PROJECT_KEY") or "COD"
JIRA_LABEL = _secret("jira", "label", "JIRA_LABEL") or "aetna"

# AWS Configuration
AWS_ACCESS_KEY_ID = _secret("aws", "access_key_id", "AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = _secret("aws", "secret_access_key", "AWS_SECRET_ACCESS_KEY")
AWS_REGION = _secret("aws", "region", "AWS_REGION") or "us-east-1"

# S3 Configuration
S3_BUCKET_NAME = _secret("aws", "bucket_name", "S3_BUCKET_NAME")
S3_FOLDER_PATH = _secret("aws", "folder_path", "S3_FOLDER_PATH")

# Google Sheets Configuration
SHEET_ID = _secret("google_sheets", "sheet_id", "GOOGLE_SHEET_ID")
CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "error-report-automation.json")

# Error code to S3 file keyword mapping
ERROR_FILE_MAP = {
    "14": "MismatchChase",
    "16": "NPI_Analysis_Detail",
    "17": "MismatchChase",
    "18": "MismatchChase",
    "22": "Disposition_Error_Analysis",
    "33": "Disposition_Error_Analysis",
    "34": "ICDAnalysis",
    "35": "ICDAnalysis",
    "42": "Outstanding_CDF_Error_Summary",
    "48": "Outstanding_CDF_Error_Summary",
    "53": "Outstanding_CDF_Error_Summary",
    "FAILED_IMAGES": "MissingImages_FullDetail",
    "MISSING_CDF": "MissingCDF",
}

# Error code to ticket title mapping
ERROR_TITLE_MAP = {
    "14": "Aetna {program} CI CDF Error Summary {date} - Error 14",
    "16": None,  # Skip - needs client discussion
    "17": "Aetna {program} CI CDF Error Summary {date} - Error 17",
    "18": "Aetna {program} CI CDF Error Summary {date} - Error 18",
    "22": "Aetna {program} CI Cumulative CDF Error Summary {date} - Error 22, 33",
    "22_only": "Aetna {program} CI Cumulative CDF Error Summary {date} - Error 22",
    "33": None,  # Handled by 22 when both present
    "33_only": "Aetna {program} CI Cumulative CDF Error Summary {date} - Error 33",
    "34": "Aetna {program} CI CDF Error Summary {date} - Error 34",
    "35": "Aetna {program} CI CDF Error Summary {date} - Error 35",
    "42": "Aetna {program} CI CDF Error Summary {date} - Error 42",
    "48": "Aetna {program} CI CDF Error Summary {date} - Error 48",
    "53": "Aetna {program} CI CDF Error Summary {date} - Error 53",
    "FAILED_IMAGES": "Aetna {program} Missing Images {date}",
    "MISSING_CDF": "Aetna {program} CI CDF Error Summary {date} | Missing CDFs",
}

# Error code to ticket description mapping
ERROR_DESCRIPTION_MAP = {
    "14": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFor error code 14 please use the attached MismatchChase file.",
    "16": None,  # Skip - needs client discussion
    "17": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFor error code 17 please use the attached MismatchChase file.",
    "18": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFor error code 18 please use the attached MismatchChase file.",
    "22": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFile with errors attached for Error codes 22 and 33.\n\nAetna reported {count_22} error 22 and {count_33} error 33 for this week.",
    "22_only": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFile with errors attached for Error code 22.\n\nAetna reported {count_22} error 22 for this week.",
    "33_only": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFile with errors attached for Error code 33.\n\nAetna reported {count_33} error 33 for this week.",
    "34": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFor error code 34 please use the attached ICDAnalysis file.",
    "35": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFor error code 35 please use the attached ICDAnalysis file.",
    "42": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFor error code 42 please use the attached Outstanding CDF Error Summary file.",
    "48": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFor error code 48 please use the attached Outstanding CDF Error Summary file.",
    "53": "Hello,\n\nAetna ACA Output File Errors to Correct.\n\nFor error code 53 please use the attached Outstanding CDF Error Summary file.",
    "FAILED_IMAGES": "Aetna has reported {count} missing images.\n\nI've uploaded the file with the information on the missing images. Please report any findings as to why these may have been reported as missing and resend as requested by Aetna.",
    "MISSING_CDF": "Hello,\n\nAetna sent the attached document with images missing CDF records.\n\nCan we please add these results to the next file?\n\nPlease let me know if that is the standard protocol.\n\nImages Missing CDF Records: {count}",
}

# Local temp folder for downloaded S3 files
TEMP_DOWNLOAD_PATH = "temp_files/"
