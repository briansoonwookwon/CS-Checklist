# Quick Setup Guide

## Step 1: Firebase Setup

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project
3. Enable **Firestore Database** (start in test mode for now)
4. Go to **Project Settings** > **Service Accounts**
5. Click **"Generate New Private Key"**
6. Save the downloaded JSON file

## Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 3: Configure Firebase Credentials

**Option A: Using Environment Variable (Recommended for Vercel)**
- Copy the contents of your Firebase credentials JSON file
- In Vercel, add it as `FIREBASE_CREDENTIALS` environment variable (as a JSON string)

**Option B: Using File (For Local Development)**
- Save your Firebase credentials JSON as `firebase-credentials.json` in the project root
- Add to `.gitignore` (already done)

## Step 4: Initialize Checklist from Excel

Run this command to parse your Excel file and upload to Firebase:

```bash
python scripts/parse_excel.py
```

This will:
- Read `MILS_CellTracking_CS_CheckList.xlsx`
- Expect the columns **Process, Equipment, Item, Period** (row 1 = headers)
- Upload all checklist items—including their process/equipment/period metadata—to Firebase Firestore

> **Sorting & filters:** In the UI, items are automatically ordered by Period (ascending), then Process, Equipment, and row order. The same fields power the Process / Equipment / Frequency filter bar, so keep the headers consistent.

## Step 5: Test Locally (Optional)

```bash
# Set environment variable
export FIREBASE_CREDENTIALS_PATH=firebase-credentials.json

# Run Flask
python -m flask --app api/index run
```

Visit `http://localhost:5000` to test.

## Troubleshooting

### "Firebase credentials not found"
- Make sure you've set `FIREBASE_CREDENTIALS` or `FIREBASE_CREDENTIALS_PATH`
- For Vercel, use the environment variable, not the file path

### "No checklist items found"
- Run `python scripts/parse_excel.py` to initialize the checklist
- Check that the Excel file is in the project root

### Checklist not loading in browser
- Check browser console for errors
- Verify API endpoints are working: `https://your-app.vercel.app/api/health`
- Check Firebase Firestore rules allow read/write


