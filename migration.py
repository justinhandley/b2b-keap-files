import requests
import json
import io
import time
import xmlrpc.client
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# --- CONFIG ---
KEAP_ACCESS_TOKEN = os.getenv('KEAP_ACCESS_TOKEN')
KEAP_API_KEY = os.getenv('KEAP_API_KEY')
KEAP_APP_NAME = os.getenv('KEAP_APP_NAME')
KEAP_API_URL = 'https://api.infusionsoft.com/crm/rest/v1'
KEAP_XMLRPC_URL = f'https://api.infusionsoft.com/crm/xmlrpc/v1/{KEAP_APP_NAME}'

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
PARENT_FOLDER_ID = os.getenv('PARENT_FOLDER_ID')
SHARED_DRIVE_ID = os.getenv('SHARED_DRIVE_ID')

SCOPES = ['https://www.googleapis.com/auth/drive']

DRY_RUN = os.getenv('DRY_RUN', 'false').lower() == 'true'

# Validate required environment variables
required_vars = [
    'KEAP_ACCESS_TOKEN',
    'KEAP_API_KEY',
    'KEAP_APP_NAME',
    'GOOGLE_SERVICE_ACCOUNT_FILE',
    'PARENT_FOLDER_ID',
    'SHARED_DRIVE_ID'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# --- Logging Setup ---
# Create temp directory if it doesn't exist
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

# Set up logging with temp directory
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(TEMP_DIR, f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Reduce noise from other loggers
logging.getLogger('googleapiclient.discovery').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
logging.getLogger('google.auth.transport.requests').setLevel(logging.WARNING)

# --- Google Drive Setup ---
credentials = service_account.Credentials.from_service_account_file(
    GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# --- XML-RPC Setup ---
class BearerAuthTransport(xmlrpc.client.SafeTransport):
    def __init__(self, token, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = token
        self._verbose = False  # Disable verbose logging

    def send_headers(self, connection, headers):
        connection.putheader('Authorization', f'Bearer {self.token}')
        connection.putheader('Content-Type', 'text/xml')
        connection.putheader('Accept', '*/*')
        connection.putheader('User-Agent', 'Python XML-RPC Client')
        super().send_headers(connection, headers)

xmlrpc_server = xmlrpc.client.ServerProxy(
    KEAP_XMLRPC_URL,
    transport=BearerAuthTransport(KEAP_ACCESS_TOKEN),
    verbose=False  # Disable verbose logging
)

# --- Utility functions ---
def retry_request(func, *args, retries=3, delay=2, **kwargs):
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except (requests.RequestException, HttpError, xmlrpc.client.Fault) as e:
            logger.error(f"Error on attempt {attempt + 1}/{retries}: {str(e)}")
            if attempt < retries - 1:
                wait_time = delay * (2 ** attempt)
                logger.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                logger.error("Max retries exceeded")
                raise
    raise Exception("Max retries exceeded")

def get_keap_headers():
    return {"Authorization": f"Bearer {KEAP_ACCESS_TOKEN}"}

def get_keap_contacts():
    logger.info("Fetching Keap contacts...")
    url = f"{KEAP_API_URL}/contacts?limit=1000"
    headers = get_keap_headers()
    contacts = []
    total_contacts = 0

    while url:
        try:
            response = retry_request(requests.get, url, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.error(f"Error fetching contacts: {response.text}")
                break

            data = response.json()
            new_contacts = data.get('contacts', [])
            
            if not new_contacts:
                logger.info("No new contacts found in this batch, stopping pagination")
                break
                
            contacts.extend(new_contacts)
            total_contacts += len(new_contacts)
            url = data.get('next')
            logger.info(f"Total contacts fetched: {total_contacts}")

        except Exception as e:
            logger.error(f"Error during contact fetching: {str(e)}")
            break

    return contacts

def get_keap_files(contact_id):
    logger.info(f"Fetching files for contact {contact_id}")
    url = f"{KEAP_API_URL}/files?contactId={contact_id}"
    headers = get_keap_headers()
    
    try:
        response = retry_request(requests.get, url, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Error fetching files for contact {contact_id}: {response.text}")
            return []

        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and 'files' in data:
            return data['files']
        return []
    except Exception as e:
        logger.error(f"Error fetching files for contact {contact_id}: {str(e)}")
        return []

def get_or_create_contact_folder(contact_email):
    logger.info(f"Checking/creating folder for {contact_email}")
    query = f"name='{contact_email}' and '{PARENT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    
    try:
        results = retry_request(
            drive_service.files().list(
                q=query,
                corpora='drive',
                driveId=SHARED_DRIVE_ID,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                fields="files(id, name)"
            ).execute
        )
        files = results.get('files', [])
        if files:
            logger.info(f"Found existing folder for {contact_email}")
            return files[0]['id']

        if DRY_RUN:
            logger.info(f"DRY-RUN: Would create folder for {contact_email}")
            return "dry-run-folder-id"

        file_metadata = {
            'name': contact_email,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [PARENT_FOLDER_ID]
        }
        folder = retry_request(
            drive_service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute
        )
        logger.info(f"Created folder for {contact_email}")
        return folder.get('id')
    except Exception as e:
        logger.error(f"Error creating folder for {contact_email}: {str(e)}")
        raise

def file_already_uploaded(folder_id, file_name):
    if DRY_RUN:
        logger.info(f"DRY-RUN: Would check if {file_name} exists in {folder_id}")
        return False

    query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
    try:
        results = retry_request(
            drive_service.files().list(
                q=query,
                corpora='drive',
                driveId=SHARED_DRIVE_ID,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                fields="files(id, name)"
            ).execute
        )
        return len(results.get('files', [])) > 0
    except Exception as e:
        logger.error(f"Error checking if file exists: {str(e)}")
        return False

def upload_file_to_drive(folder_id, keap_file):
    """Upload a file to Google Drive with progress tracking and retry logic."""
    file_id = keap_file.get('id')
    file_name = keap_file.get('file_name')

    if not file_id or not file_name:
        logger.error(f"Invalid file entry: {keap_file}")
        return

    if file_already_uploaded(folder_id, file_name):
        logger.info(f"File {file_name} already exists. Skipping.")
        return

    if DRY_RUN:
        logger.info(f"DRY-RUN: Would download and upload {file_name} to {folder_id}")
        return

    try:
        # --- Download file via XML-RPC ---
        logger.info(f"Downloading {file_name}...")
        file_data = retry_request(
            xmlrpc_server.FileService.getFile,
            KEAP_API_KEY,
            int(file_id)
        )

        if not file_data:
            logger.error(f"File {file_name} returned no data.")
            return

        # Convert base64 string to bytes if needed
        if isinstance(file_data, str):
            try:
                import base64
                file_data = base64.b64decode(file_data)
                logger.info(f"Successfully decoded {file_name} (size: {len(file_data)/1024:.2f} KB)")
            except Exception as e:
                logger.error(f"Error decoding base64 data for {file_name}: {str(e)}")
                return

        # Create a temporary file to store the data
        temp_file_path = os.path.join(TEMP_DIR, file_name)
        with open(temp_file_path, 'wb') as f:
            f.write(file_data)

        # --- Upload to Drive with progress tracking ---
        logger.info(f"Uploading {file_name} to Google Drive...")
        max_retries = 3
        retry_delay = 5  # seconds

        for attempt in range(max_retries):
            try:
                file_metadata = {
                    'name': file_name,
                    'parents': [folder_id]
                }

                # Create media file upload object
                media = MediaFileUpload(
                    temp_file_path,
                    mimetype='application/octet-stream',
                    resumable=True
                )

                # Create upload request
                request = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id',
                    supportsAllDrives=True
                )

                # Track upload progress
                response = None
                last_progress = -1
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        if progress != last_progress:  # Only log when progress changes
                            logger.info(f"Upload progress for {file_name}: {progress}%")
                            last_progress = progress

                file_id = response.get('id')
                if file_id:
                    logger.info(f"Successfully uploaded {file_name} (Drive ID: {file_id})")
                    # Clean up temporary file
                    os.remove(temp_file_path)
                    return file_id
                else:
                    raise Exception("No file ID returned from upload")

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Upload attempt {attempt + 1} failed for {file_name}: {str(e)}")
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to upload {file_name} after {max_retries} attempts: {str(e)}")
                    raise

    except Exception as e:
        logger.error(f"Error processing file {file_name}: {str(e)}")
        # Clean up temporary file if it exists
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

def main():
    logger.info("Starting migration process")
    start_time = time.time()
    
    try:
        contacts = get_keap_contacts()
        total_contacts = len(contacts)
        logger.info(f"Found {total_contacts} contacts to process")
        
        successful_uploads = 0
        failed_uploads = 0
        skipped_files = 0
        
        for index, contact in enumerate(contacts, 1):
            contact_id = contact['id']
            email = contact.get('email_addresses', [{}])[0].get('email')

            if not email:
                logger.warning(f"Skipping contact {contact_id} (no email)")
                continue

            logger.info(f"Processing contact {index}/{total_contacts}: {email}")
            files = get_keap_files(contact_id)
            
            if not files:
                logger.info(f"No files for {email}")
                continue

            folder_id = get_or_create_contact_folder(email)
            logger.info(f"Processing {len(files)} files for {email}")

            for file_index, keap_file in enumerate(files, 1):
                logger.info(f"Processing file {file_index}/{len(files)} for {email}")
                try:
                    upload_file_to_drive(folder_id, keap_file)
                    successful_uploads += 1
                except Exception as e:
                    failed_uploads += 1
                    logger.error(f"Failed to process file: {str(e)}")

        end_time = time.time()
        duration = end_time - start_time
        logger.info(f"Migration completed in {duration:.2f} seconds")
        logger.info(f"Summary: {successful_uploads} files uploaded, {failed_uploads} failed, {skipped_files} skipped")
        
    except Exception as e:
        logger.error(f"Fatal error during migration: {str(e)}")
        raise

if __name__ == '__main__':
    main()
