# Keap to Google Drive Migration Tool

This tool migrates files from Keap (Infusionsoft) to Google Drive, organizing them by contact email address.

## Prerequisites

- Python 3.7 or higher
- A Keap (Infusionsoft) account with API access
- A Google Cloud Project with the Google Drive API enabled
- A Google Shared Drive to store the migrated files

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd b2b-keap-files
```

2. Create and activate a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
# Using requirements.txt (recommended)
pip install -r requirements.txt

# Or install packages individually
pip install python-dotenv google-api-python-client google-auth-httplib2 google-auth-oauthlib requests
```

### Dependency Management

This project uses `requirements.txt` for dependency management. To update the requirements file with your current environment:

```bash
pip freeze > requirements.txt
```

To install dependencies in a new environment:
```bash
pip install -r requirements.txt
```

### Virtual Environment

The virtual environment (`venv/`) is not committed to the repository. Each developer should create their own virtual environment. This ensures:
- Consistent dependency versions across all environments
- Isolation from system Python packages
- Clean development environment

## Keap API Setup

1. Log in to your Keap account at https://app.infusionsoft.com

2. Generate an API Key:
   - Go to Admin → API & OAuth
   - Click "Add New API Key"
   - Give it a name (e.g., "File Migration")
   - Select the necessary scopes (at minimum: `files.read`)
   - Copy the generated API Key

3. Generate an Access Token:
   - Go to Admin → API & OAuth
   - Click "Add New OAuth Connection"
   - Select "OAuth 2.0"
   - Give it a name (e.g., "File Migration")
   - Select the necessary scopes (at minimum: `files.read`)
   - Click "Generate Access Token"
   - Copy the generated Access Token

4. Find your Application Name:
   - Go to Admin → API & OAuth
   - Look for "Application Name" or check the URL when logged in
   - It's usually something like "nw206" or similar

## Google Drive Setup

1. Create a Google Cloud Project:
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Click "New Project"
   - Give it a name (e.g., "Keap File Migration")
   - Click "Create"

2. Enable the Google Drive API:
   - In your project, go to "APIs & Services" → "Library"
   - Search for "Google Drive API"
   - Click "Enable"

3. Create a Service Account:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "Service Account"
   - Fill in the service account details
   - Click "Create and Continue"
   - For Role, select "Project" → "Editor"
   - Click "Continue" and "Done"

4. Generate Service Account Key:
   - In the Service Accounts list, click on your new service account
   - Go to the "Keys" tab
   - Click "Add Key" → "Create New Key"
   - Choose JSON format
   - Click "Create"
   - Save the downloaded JSON file securely

5. Set up Google Shared Drive:
   - Go to [Google Drive](https://drive.google.com)
   - Click "New" → "Shared Drive"
   - Name it (e.g., "Keap Files")
   - Click "Create"
   - Share the drive with your service account email (found in the service account JSON file)
   - Give it "Editor" access
   - Copy the Shared Drive ID from the URL (it's the long string after /folders/)

6. Create Parent Folder:
   - In your Shared Drive, create a new folder (e.g., "Keap Migrated Files")
   - Copy the folder ID from the URL (it's the long string after /folders/)

## Configuration

1. Create your environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:
```env
# Keap API Configuration
KEAP_ACCESS_TOKEN=your_access_token_here
KEAP_API_KEY=your_api_key_here
KEAP_APP_NAME=your_app_name_here

# Google Drive Configuration
GOOGLE_SERVICE_ACCOUNT_FILE=path_to_your_service_account_file.json
PARENT_FOLDER_ID=your_parent_folder_id
SHARED_DRIVE_ID=your_shared_drive_id

# Optional Configuration
DRY_RUN=false
```

3. Place your Google service account JSON file in the project directory and update the path in `.env`

## Usage

1. Test the configuration (optional):
```bash
# Set DRY_RUN=true in .env first
python migration.py
```

2. Run the migration:
```bash
# Set DRY_RUN=false in .env
python migration.py
```

The script will:
1. Fetch all contacts from Keap
2. Create folders for each contact in Google Drive
3. Download and upload files for each contact
4. Provide progress updates and error logging

## Logs

Logs are stored in the `temp/migration_[timestamp].log` file and also output to the console. The logs include:
- Contact processing progress
- File download and upload status
- Any errors or issues encountered
- Final summary of successful uploads, failures, and skipped files

Note: The `temp` directory is automatically created when the script runs and is excluded from version control.

## Troubleshooting

Common issues and solutions:

1. **403 Forbidden Errors**:
   - Verify your Keap API key and access token are correct
   - Check that your service account has proper access to the Shared Drive
   - Ensure the Google Drive API is enabled in your project

2. **File Upload Failures**:
   - Check your internet connection
   - Verify you have enough storage space in Google Drive
   - Check the logs for specific error messages

3. **Missing Files**:
   - Verify the contact has files in Keap
   - Check the logs for any skipped files
   - Ensure the file permissions are correct in Keap

## Security

- Never commit the `.env` file or service account JSON files to version control
- Keep your API keys and tokens secure
- Use the `.env.example` file as a template for required variables
- Regularly rotate your API keys and tokens
- Use the principle of least privilege when setting up service account permissions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Your chosen license] 