from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
from datetime import datetime
import json
import time
# from dotenv import load_dotenv

# load_dotenv()

# Get the project root directory (parent of 'api' folder)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_folder = os.path.join(project_root, 'static')

app = FastAPI()

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (local dev)
if os.path.isdir(static_folder):
    app.mount('/static', StaticFiles(directory=static_folder), name='static')

# Initialize Firebase references
db = None

def init_firebase():
    """Initialize Firebase services if needed."""
    global db
    if not firebase_admin._apps:
        cred_path = os.environ.get('FIREBASE_CREDENTIALS')
        if cred_path:
            cred_dict = json.loads(cred_path)
            cred = credentials.Certificate(cred_dict)
        else:
            cred_path = os.environ.get('FIREBASE_CREDENTIALS_PATH', 'firebase-credentials.json')
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
            else:
                raise Exception("Firebase credentials not found. Set FIREBASE_CREDENTIALS or FIREBASE_CREDENTIALS_PATH")
        # Initialize the Firebase app using the constructed credentials
        firebase_admin.initialize_app(cred)

    db = firestore.client()

# Attempt to initialize on import (will warn if missing config)
try:
    init_firebase()
except Exception as e:
    print(f"Warning: Firebase initialization failed: {e}")


def make_json_serializable(data):
    """Recursively convert Firestore data to JSON-serializable format."""
    if isinstance(data, dict):
        return {k: make_json_serializable(v) for k, v in data.items()}
    if isinstance(data, list):
        return [make_json_serializable(item) for item in data]
    if hasattr(data, 'isoformat'):
        return data.isoformat()
    return data


def ensure_firebase():
    """Ensure Firebase services are ready before handling a request."""
    global db
    if db is None:
        init_firebase()


@app.get('/api/health')
async def health():
    return JSONResponse({"status": "ok"})


@app.get('/api/checklist')
async def get_checklist(date: str | None = None):
    """Get checklist items for a specific date."""
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')

    try:
        ensure_firebase()

        doc_ref = db.collection('checklists').document(date)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            return JSONResponse(make_json_serializable{
                **data,
                "checked": make_json_serializable(data.get('checked', {}))
            })
        else:
            return JSONResponse({
                'date': date,
                'items': [],
                'checked': {}
            })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post('/api/checklist')
async def update_checklist(payload: dict):
    """Replace the checklist state for a date."""
    date = payload.get('date', datetime.now().strftime('%Y-%m-%d'))
    items = payload.get('items', [])
    checked = payload.get('checked', {})

    try:
        ensure_firebase()

        doc_ref = db.collection('checklists').document(date)
        doc_ref.set({
            'date': date,
            'checked': checked,
            'lastUpdated': firestore.SERVER_TIMESTAMP
        }, merge=True)
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post('/api/checklist/toggle')
async def toggle_check(data: dict):
    """Toggle a specific checklist item for a user."""
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    item_id = data.get('item_id')
    user = data.get('user', 'anonymous')

    if not item_id:
        raise HTTPException(status_code=400, detail="Missing item_id")

    try:
        ensure_firebase()

        doc_ref = db.collection('checklists').document(date)
        doc = doc_ref.get()

        if doc.exists:
            checklist_data = doc.to_dict()
            checked = checklist_data.get('checked', {})
        else:
            checklist_data = {
                'date': date,
                'items': [],
                'checked': {}
            }
            checked = {}

        if item_id not in checked:
            checked[item_id] = {}

        if user in checked[item_id]:
            del checked[item_id][user]
            if not checked[item_id]:
                del checked[item_id]
        else:
            checked[item_id][user] = {
                'timestamp': firestore.SERVER_TIMESTAMP,
                'checked': True
            }

        checklist_data['checked'] = checked
        checklist_data['lastUpdated'] = firestore.SERVER_TIMESTAMP
        doc_ref.set(checklist_data)

        updated_doc = doc_ref.get()
        if updated_doc.exists:
            updated_data = updated_doc.to_dict()
            serializable_checked = make_json_serializable(updated_data.get('checked', {}))
            return JSONResponse({"success": True, "checked": serializable_checked})
        else:
            return JSONResponse({"success": True, "checked": {}})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get('/api/checklist/items')
async def get_checklist_items():
    """Return the master checklist item definitions."""
    try:
        ensure_firebase()

        doc_ref = db.collection('config').document('checklist_items')
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return JSONResponse(make_json_serializable{
                **data,
                "checked": make_json_serializable(data.get('checked', {}))
            })
        else:
            return JSONResponse({"items": []})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post('/api/checklist/items')
async def set_checklist_items(payload: dict):
    """Replace the master checklist item definitions."""
    items = payload.get('items', [])

    try:
        ensure_firebase()

        doc_ref = db.collection('config').document('checklist_items')
        doc_ref.set({
            'items': items,
            'lastUpdated': firestore.SERVER_TIMESTAMP
        })
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get('/api/checklist/last-completions')
async def get_last_completions():
    """Get the last completion date for each task across all dates."""
    try:
        ensure_firebase()

        # Query all checklist documents
        checklists_ref = db.collection('checklists')
        all_checklists = checklists_ref.stream()

        # Track last completion date for each item_id
        last_completions = {}  # {item_id: 'YYYY-MM-DD'}

        for checklist_doc in all_checklists:
            checklist_data = checklist_doc.to_dict()
            checked = checklist_data.get('checked', {})
            doc_date = checklist_doc.id  # Document ID is the date

            # For each item that was checked, track the most recent date
            for item_id, users_checked in checked.items():
                if users_checked:  # If any user checked it
                    # Check if this date is more recent than what we have
                    if item_id not in last_completions:
                        last_completions[item_id] = doc_date
                    else:
                        # Compare dates (YYYY-MM-DD format is sortable)
                        if doc_date > last_completions[item_id]:
                            last_completions[item_id] = doc_date

        return JSONResponse({"lastCompletions": last_completions})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# -------- Static asset helpers for local dev -------- #
@app.get('/')
async def index():
    """Serve the main HTML page."""
    index_path = os.path.join(static_folder, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.get('/{filename:path}')
async def serve_static(filename: str):
    """Serve static assets when running locally."""
    # Avoid serving API routes here
    if filename.startswith('api/'):
        return JSONResponse({"error": "Not found"}, status_code=404)

    file_path = os.path.join(static_folder, filename)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    return JSONResponse({"error": "Not found"}, status_code=404)


# Vercel serverless function handler (ASGI)
# Export an ASGI-compatible handler so Vercel can invoke this app.
# async def handler(scope, receive, send):
#     await app(scope, receive, send)


# __all__ = ['handler', 'app']
# from mangum import Mangum

# handler = Mangum(app)