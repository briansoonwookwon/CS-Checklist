from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import firebase_admin
from firebase_admin import credentials, firestore
import os
from datetime import datetime, timedelta
import json
import time

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

def fetch_master_item_count():
    """Fetches the total number of items in the master checklist."""
    try:
        # Assuming the master checklist items are stored here, same place as /checklist/items reads from
        doc_ref = db.collection('config').document('checklist_items')
        doc = doc_ref.get()
        if doc.exists and 'items' in doc.to_dict():
            return len(doc.to_dict()['items'])
        return 0
    except Exception:
        # Fallback in case of DB error
        return 0

def fetch_master_items():
    """Fetches the entire master checklist item list."""
    try:
        doc_ref = db.collection('config').document('checklist_items')
        doc = doc_ref.get()
        if doc.exists and 'items' in doc.to_dict():
            return doc.to_dict()['items']
        return []
    except Exception:
        return []

def fetch_all_last_completions():
    """Fetches the last completion date for each task across all dates (same as /api/checklist/last-completions)."""
    try:
        checklists_ref = db.collection('checklists')
        all_checklists = checklists_ref.stream()

        last_completions = {}  # {item_id: 'YYYY-MM-DD'}

        for checklist_doc in all_checklists:
            checklist_data = checklist_doc.to_dict()
            checked = checklist_data.get('checked', {})
            doc_date = checklist_doc.id

            for item_id, users_checked in checked.items():
                if users_checked:
                    if item_id not in last_completions or doc_date > last_completions[item_id]:
                        last_completions[item_id] = doc_date
        return last_completions
    except Exception:
        return {}

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
            return JSONResponse(make_json_serializable(data))
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
            'items': items,
            'checked': checked,
            'lastUpdated': firestore.SERVER_TIMESTAMP
        }, merge=True)
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post('/api/checklist/toggle')
async def toggle_check(data: dict):
    """Toggle a specific checklist item for a user and save an optional note."""
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    item_id = data.get('item_id')
    user = data.get('user', 'anonymous')
    note = data.get('note', '') 

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
            # Unchecking the item
            del checked[item_id][user]
            if not checked[item_id]:
                del checked[item_id]
        else:
            # Checking the item
            checked[item_id][user] = {
                'timestamp': firestore.SERVER_TIMESTAMP,
                'checked': True,
                # --- FIX 2: Added the 'note' field to the saved data ---
                'note': note
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
            return JSONResponse(make_json_serializable(data))
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

@app.get('/api/summary/calendar')
async def get_calendar_summary(start_date: str, end_date: str):
    """
    Retrieves summary data (who submitted, how many checked) for all dates 
    between start_date and end_date (YYYY-MM-DD), and the total master item count.
    """
    try:
        ensure_firebase()
        
        # Get the total number of tasks to use as the denominator in the summary
        master_items = fetch_master_items() # Master item definitions
        last_completions = fetch_all_last_completions() # Last completion dates
        total_master_items = fetch_master_item_count()
        
        item_period_map = {item.get('id'): item.get('periodDays') for item in master_items}

        # Convert string dates to datetime objects for comparison
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        current_dt = start_dt
        summary_data = {}
        
        # Iterate through all days in the range
        while current_dt <= end_dt:
            date_str = current_dt.strftime('%Y-%m-%d')
            doc_ref = db.collection('checklists').document(date_str)
            doc = doc_ref.get()

            items_due_count = 0
            period_due_counts = {}
            
            for item in master_items:
                item_id = item.get('id')
                period_days = item.get('periodDays', 0)
                
                # Check if the task is due for the current day based on recurrence
                is_due = True
                
                # Apply Rule 3: Periodic filter (Only if periodDays > 0)
                if period_days is not None and period_days > 0:
                    last_completion_date_str = last_completions.get(item_id)
                    
                    if last_completion_date_str:
                        # Calculate days since last completion
                        last_date_dt = datetime.strptime(last_completion_date_str, '%Y-%m-%d')
                        # Use 00:00:00 time to align with the front-end's date comparison
                        days_since = (current_dt.replace(hour=0, minute=0, second=0, microsecond=0) - last_date_dt.replace(hour=0, minute=0, second=0, microsecond=0)).days
                        
                        # Hide task if NOT enough days have passed
                        if days_since < period_days:
                            is_due = False

                if is_due:
                    items_due_count += 1
                    period_due_counts[period_days] = period_due_counts.get(period_days, 0) + 1


            day_summary = {
                'submitted': False,
                'total_checked': 0,
                'period_checks': {}, 
                'period_due_counts': period_due_counts,
            }

            if doc.exists:
                data = doc.to_dict()
                
                # Check if the document has any checked items
                if data and data.get('checked'):
                    day_summary['submitted'] = True
                    all_checked_items = data['checked']
                    
                    # Calculate total checks and user counts
                    total_checked = 0
                    period_checks = day_summary['period_checks']
                    
                    for item_id, user_data in all_checked_items.items():
                        # Determine the period for this item
                        period_days = item_period_map.get(item_id, 0) # Default to 0 for non-periodic/unknown

                        for user_name, check_info in user_data.items():
                            if check_info.get('checked'):
                                total_checked += 1
                                # Aggregate by period_days
                                period_checks[period_days] = period_checks.get(period_days, 0) + 1
                                break # Count an item check once, regardless of how many users checked it

                    day_summary['total_checked'] = total_checked
            
            for key in day_summary['period_checks']:
                # Check if the key also exists in the second dictionary
                if key in day_summary['period_due_counts']:
                    # Add the values and store the result
                    day_summary['period_due_counts'][key] = day_summary['period_checks'][key] + day_summary['period_due_counts'][key]
            
            day_summary['total_due'] = sum(day_summary['period_due_counts'].values())

            summary_data[date_str] = day_summary
            
            # Move to the next day
            current_dt += timedelta(days=1)

        # Return the summary data and the total item count
        return JSONResponse({'summaryData': summary_data, 'totalMasterItems': total_master_items})
        
    except Exception as e:
        # ... (rest of the error handling)
        print(f"Error fetching calendar summary: {e}")
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