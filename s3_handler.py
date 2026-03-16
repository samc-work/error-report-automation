import boto3
import os
import certifi
import urllib3
from config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    S3_BUCKET_NAME,
    S3_FOLDER_PATH,
    ERROR_FILE_MAP,
    TEMP_DOWNLOAD_PATH
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_s3_client():
    """Create and return an S3 client"""
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    
    return boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        verify=False
    )

def list_bucket_files(report_date=None):
    """List files in the bucket, optionally filtered by date"""
    s3 = get_s3_client()
    
    try:
        # Build prefix to narrow down results
        if report_date:
            prefix = f"{S3_FOLDER_PATH}CI_ACA_PY2025_{report_date}"
        else:
            prefix = S3_FOLDER_PATH
        
        response = s3.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=prefix
        )
        
        if 'Contents' not in response:
            print("No files found in bucket")
            return []
        
        files = [obj['Key'] for obj in response['Contents']]
        return files
    
    except Exception as e:
        print(f"Error listing bucket: {e}")
        return []

def find_file_for_error(error_code, report_date):
    """
    Find the correct S3 file for a given error code and report date
    report_date format: YYYYMMDD e.g. 20260303
    """
    if error_code not in ERROR_FILE_MAP:
        print(f"No file mapping found for error code {error_code}")
        return None
    
    file_keyword = ERROR_FILE_MAP[error_code]
    files = list_bucket_files(report_date=report_date)
    
    # Look for file matching both the keyword and the report date
    matching_files = [
        f for f in files
        if file_keyword in f and report_date in f
    ]
    
    if not matching_files:
        print(f"No file found for error {error_code} with date {report_date}")
        return None
    
    # Return the first match
    return matching_files[0]

def download_file(s3_key):
    """
    Download a file from S3 to local temp folder
    Returns the local file path
    """
    s3 = get_s3_client()
    
    # Create temp folder if it doesnt exist
    os.makedirs(TEMP_DOWNLOAD_PATH, exist_ok=True)
    
    # Get just the filename from the full s3 key
    filename = os.path.basename(s3_key)
    local_path = os.path.join(TEMP_DOWNLOAD_PATH, filename)
    
    try:
        print(f"Downloading {filename} from S3...")
        s3.download_file(S3_BUCKET_NAME, s3_key, local_path)
        print(f"Downloaded successfully to {local_path}")
        return local_path
    
    except Exception as e:
        print(f"Error downloading {s3_key}: {e}")
        return None

def get_file_for_error(error_code, report_date):
    """
    Main function - finds and downloads the correct file for an error
    Returns local file path or None if not found
    """
    s3_key = find_file_for_error(error_code, report_date)
    
    if not s3_key:
        return None
    
    return download_file(s3_key)

def cleanup_temp_files():
    """Delete all files in temp folder after tickets are created"""
    if not os.path.exists(TEMP_DOWNLOAD_PATH):
        return
    
    for filename in os.listdir(TEMP_DOWNLOAD_PATH):
        file_path = os.path.join(TEMP_DOWNLOAD_PATH, filename)
        try:
            os.remove(file_path)
            print(f"Cleaned up {filename}")
        except Exception as e:
            print(f"Error cleaning up {filename}: {e}")

if __name__ == "__main__":
    test_date = "20260303"
    print(f"Listing files for date {test_date}...")
    files = list_bucket_files(report_date=test_date)
    
    if files:
        print(f"\nFound {len(files)} files:")
        for f in files:
            print(f"  {f}")
    else:
        print("No files found or connection failed")