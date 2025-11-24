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

### 6. Local Development

```bash
uv run uvicorn api.index:app --reload
```

Then visit `http://localhost:8000` in your browser.

### 7. Deploy to Vercel

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

## API Endpoints

- `GET /api/checklist?date=YYYY-MM-DD` - Get checklist for a date
- `POST /api/checklist` - Update checklist
- `POST /api/checklist/toggle` - Toggle a checklist item
- `POST /api/checklist/photo` - Upload a photo for a checklist item
- `GET /api/checklist/items` - Get checklist items structure
- `POST /api/checklist/items` - Set checklist items structure
- `GET /api/checklist/last-completions` - Get last completion date for each task across all dates

## Usage

1. Open the web app
2. Enter your name (saved in browser localStorage)
3. Select a date
4. Click on checklist items to mark them as checked/unchecked
5. Use the filters (Process / Equipment / Frequency) to focus on a subset of tasks
6. Use "Upload Photo" on any task to attach evidence (images only, max 10 MB)
7. Each user's checks and photos are tracked separately

## Customization

### Modify Checklist Structure

Edit `scripts/parse_excel.py` to adjust how the Excel file is parsed based on your specific format.

### Styling

Edit `static/styles.css` to customize the appearance.

### Firebase Security Rules

Make sure to set up proper Firestore security rules in Firebase Console:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /checklists/{date} {
      allow read: if true;
      allow write: if true;
      // For production, add proper authentication rules
    }
    match /config/{document} {
      allow read: if true;
      allow write: if false; // Only allow writes from admin
    }
  }
}
```

For Firebase Storage, start with permissive rules while testing, then tighten access:

```javascript
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /{allPaths=**} {
      allow read, write: if request.time < timestamp.date(2025, 12, 31); // TODO: lock down
    }
  }
}
```

## Troubleshooting

### Firebase Connection Issues

- Verify your `firebase-credentials.json` file is correct
- Check that Firestore **and Storage** are enabled in your Firebase project
- Ensure environment variables are set correctly in Vercel

### Checklist Not Loading

- Run `scripts/parse_excel.py` to initialize the checklist structure
- Check browser console for errors
- Verify API endpoints are accessible

### Photo Upload Issues

- Confirm `FIREBASE_STORAGE_BUCKET` matches your Firebase Storage bucket name
- Ensure Firebase Storage rules allow uploads (see example above)
- Check that uploads are below the 10 MB limit
- Verify the Vercel project has the Storage env var set in all environments

### Vercel Deployment Issues

- Ensure `vercel.json` is in the root directory
- Check that Python runtime is supported (Vercel uses Python 3.9 by default)
- Verify all environment variables are set in Vercel dashboard

## License

MIT


