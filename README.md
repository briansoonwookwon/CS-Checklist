# CS Checklist - Daily Tracking Web App

A web-based checklist application for tracking daily tasks. Built with Python (FastAPI), Firebase, and deployed on Vercel.

## Features

- 📋 Daily checklist tracking with progress stats
- 👥 Multi-user support (each user can mark their own checks)
- 📅 Date-based tracking
- 🔎 Filter tasks by process, equipment, or frequency
- 🔁 Automatic sorting by process, equipment, and frequency (period)
- 💾 Firebase (Firestore + Storage) for persistent storage
- ☁️ Deployable on Vercel

## Setup Instructions

### 1. Prerequisites

- Python 3.10+
- Firebase project
- Vercel account (free tier works)

### 2. Firebase Setup

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or use an existing one
3. Enable Firestore Database
4. Go to Project Settings > Service Accounts
6. Click "Generate New Private Key" to download your service account JSON file
7. Save this file as `firebase-credentials.json` in the project root (or use environment variable)

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Initialize Checklist from Excel

Run the script to parse your Excel file and upload the checklist structure to Firebase:

```bash
python scripts/parse_excel.py
```

This will:
- Read `CS_CheckList.xlsx`
- Extract checklist items using the four-column schema (Process, Equipment, Item, Period)
- Upload them to Firebase Firestore

No need to do this again unless there is a change in the checklist.

### 5. Local Development

```bash
uv run uvicorn api.index:app --reload
```

Then visit `http://localhost:8000` in your browser.

### 6. Deploy to Vercel

Set environment variables in Vercel Dashboard:
  - Go to your project settings
  - Add environment variables:
    - `FIREBASE_CREDENTIALS`: Your Firebase credentials as a JSON string (recommended for Vercel)
    - Or `FIREBASE_CREDENTIALS_PATH`: Path to credentials file (if using file upload)

## Project Structure

```
.
├── api/
│   └── index.py          # FastAPI API endpoints
├── scripts/
│   └── parse_excel.py    # Excel parser and Firebase initializer
├── static/
│   ├── index.html        # Main HTML page
│   ├── app.js            
│   ├── summary.html      # Summary HTML page
│   ├── summary.js
│   └── styles.css        # Styling
├── requirements.txt      # Python dependencies
├── .gitignore
├── pyproject.toml  
├── vercel.json          # Vercel configuration
├── uv.lock
├── SETUP.md
└── README.md            # This file
```

## Usage

1. Open the web app
2. Enter your name (saved in browser localStorage)
3. Select a date
4. Click on checklist items to mark them as checked/unchecked
5. Use the filters (Process / Equipment / Frequency) to focus on a subset of tasks
6. Use "Upload Photo" on any task to attach evidence (images only, max 10 MB)
7. Each user's checks and photos are tracked separately

## License

MIT


