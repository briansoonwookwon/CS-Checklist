from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
from datetime import datetime, timedelta
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
            # --- NEW LOGIC: Generate a fresh list based on periodicity ---
            
            # 1. Fetch Master Items and History
            master_items = fetch_master_items()
            last_completions = fetch_all_last_completions()
            
            target_date = datetime.strptime(date, '%Y-%m-%d')
            
            filtered_items = []
            
            for item in master_items:
                item_id = item.get('id')
                period_days = item.get('periodDays')
                
                # Default assumption: Item is due
                is_due = True

                # Apply Periodic Logic if a period is defined and > 0
                if period_days is not None and period_days > 0:
                    last_completion_date_str = last_completions.get(item_id)
                    
                    if last_completion_date_str:
                        last_date_dt = datetime.strptime(last_completion_date_str, '%Y-%m-%d')
                        
                        # Calculate days since last completion
                        # We use 00:00:00 normalization to ensure accurate day counts
                        delta = target_date.replace(hour=0, minute=0, second=0, microsecond=0) - \
                                last_date_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                        days_since = delta.days
                        
                        # LOGIC: If 3 day period, and 4 days passed -> Show (4 >= 3)
                        # If 3 day period, and 1 day passed -> Hide (1 < 3)
                        if days_since < period_days:
                            is_due = False
                
                if is_due:
                    filtered_items.append(item)

            return JSONResponse({
                'date': date,
                'items': filtered_items, # Return only the items that passed the filter
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
    # --- FIX 1: Corrected payload reference to 'data' and extracted note ---
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

# @app.get('/api/summary/calendar')
# async def get_calendar_summary(start_date: str, end_date: str):
#     """
#     Retrieves summary data, applying periodic recurrence logic to determine total_due items for each day.
#     """
#     try:
#         ensure_firebase()
        
#         # 1. Fetch ALL required data once
#         master_items = fetch_master_items() # Master item definitions
#         last_completions = fetch_all_last_completions() # Last completion dates
#         total_master_items = len(master_items) # Total master count for fallback
        
#         start_dt = datetime.strptime(start_date, '%Y-%m-%d')
#         end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
#         current_dt = start_dt
#         summary_data = {}
        
#         # Iterate through all days in the range
#         while current_dt <= end_dt:
#             date_str = current_dt.strftime('%Y-%m-%d')
            
#             # --- NEW LOGIC: Calculate filtered item count (total_due) ---
            
#             items_due_count = 0
            
#             for item in master_items:
#                 item_id = item.get('id')
#                 period_days = item.get('periodDays')
                
#                 # Check if the task is due for the current day based on recurrence
#                 is_due = True
                
#                 # Apply Rule 3: Periodic filter (Only if periodDays > 0)
#                 if period_days is not None and period_days > 0:
#                     last_completion_date_str = last_completions.get(item_id)
                    
#                     if last_completion_date_str:
#                         # Calculate days since last completion
#                         last_date_dt = datetime.strptime(last_completion_date_str, '%Y-%m-%d')
#                         # Use 00:00:00 time to align with the front-end's date comparison
#                         days_since = (current_dt.replace(hour=0, minute=0, second=0, microsecond=0) - last_date_dt.replace(hour=0, minute=0, second=0, microsecond=0)).days
                        
#                         # Hide task if NOT enough days have passed
#                         if days_since < period_days:
#                             is_due = False

#                 if is_due:
#                     items_due_count += 1
            
#             # --- END NEW LOGIC ---
            
#             doc_ref = db.collection('checklists').document(date_str)
#             doc = doc_ref.get()
            
#             day_summary = {
#                 'submitted': False,
#                 'total_checked': 0,
#                 'users': {},  
#                 # Set total_due to the filtered count, falling back to the full master count if calculation fails (unlikely here)
#                 'total_due': items_due_count if items_due_count > 0 else total_master_items
#             }

#             if doc.exists:
#                 data = doc.to_dict()
                
#                 if data and data.get('checked'):
#                     day_summary['submitted'] = True
#                     all_checked_items = data['checked']
                    
#                     # Calculate total checks and user counts
#                     total_checked = 0
#                     user_checks = {}
                    
#                     for item_id, user_data in all_checked_items.items():
#                         # ONLY count an item as checked if it was one of the *due* items
#                         # (This is implicitly handled by `total_checked` being a raw count 
#                         # but we can improve `total_due` by checking if the due item list was saved)

#                         for user_name, check_info in user_data.items():
#                             if check_info.get('checked'):
#                                 total_checked += 1
#                                 user_checks[user_name] = user_checks.get(user_name, 0) + 1
                    
#                     day_summary['total_checked'] = total_checked
#                     day_summary['users'] = user_checks
                
#                 # RETURNING: If a document exists, prioritize the saved `items` length
#                 # which represents the actual list of items due when the user viewed the page.
#                 # However, since you are calculating `items_due_count` dynamically for the summary,
#                 # we should use the dynamic calculation, unless we detect the document saved a specific list.
#                 # We will keep the calculated `items_due_count` as the primary `total_due`.
            
#             summary_data[date_str] = day_summary
            
#             # Move to the next day
#             current_dt += timedelta(days=1)

#         return JSONResponse({'summaryData': summary_data, 'totalMasterItems': total_master_items})
        
#     except Exception as e:
#         print(f"Error fetching calendar summary: {e}")
#         return JSONResponse({"error": str(e)}, status_code=500)

@app.get('/api/summary/calendar')
async def get_calendar_summary(start_date: str, end_date: str):
    """
    Retrieves summary data, applying periodic recurrence logic to determine total_due items for each day.
    """
    try:
        ensure_firebase()
        
        # 1. Fetch ALL required data once
        master_items = fetch_master_items() # Master item definitions
        last_completions = fetch_all_last_completions() # Last completion dates
        total_master_items = len(master_items) # Total master count for fallback
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        current_dt = start_dt
        summary_data = {}
        
        # Iterate through all days in the range
        while current_dt <= end_dt:
            date_str = current_dt.strftime('%Y-%m-%d')
            
            # --- NEW LOGIC: Calculate filtered item count (total_due) ---
            # We calculate this for every day, but we only use it if
            # there is no saved document for that day (e.g. future dates).
            
            items_due_count = 0
            
            for item in master_items:
                item_id = item.get('id')
                period_days = item.get('periodDays')
                
                # Default assumption: Item is due
                is_due = True
                
                # Apply Rule 3: Periodic filter (Only if periodDays > 0)
                if period_days is not None and period_days > 0:
                    last_completion_date_str = last_completions.get(item_id)
                    
                    if last_completion_date_str:
                        # Calculate days since last completion
                        last_date_dt = datetime.strptime(last_completion_date_str, '%Y-%m-%d')
                        
                        # Use 00:00:00 time to align with the front-end's date comparison
                        delta = current_dt.replace(hour=0, minute=0, second=0, microsecond=0) - \
                                last_date_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                        days_since = delta.days
                        
                        # Hide task if NOT enough days have passed
                        if days_since < period_days:
                            is_due = False

                if is_due:
                    items_due_count += 1
            
            # --- END NEW LOGIC ---
            
            doc_ref = db.collection('checklists').document(date_str)
            doc = doc_ref.get()
            
            day_summary = {
                'submitted': False,
                'total_checked': 0,
                'users': {},
                # Use the calculated count. 
                # Removed 'else total_master_items' because if 0 items are due, we want to show 0.
                'total_due': items_due_count
            }

            if doc.exists:
                data = doc.to_dict()
                
                # IMPORTANT: If the day has saved data, use the SAVED 'items' length.
                # This represents what was actually due/shown to the user on that day.
                if data and 'items' in data:
                    day_summary['total_due'] = len(data['items'])

                if data and data.get('checked'):
                    day_summary['submitted'] = True
                    all_checked_items = data['checked']
                    
                    # Calculate total checks and user counts
                    total_checked = 0
                    user_checks = {}
                    
                    for item_id, user_data in all_checked_items.items():
                        # Check if any user checked this item
                        is_item_checked = False
                        for user_name, check_info in user_data.items():
                            if check_info.get('checked'):
                                is_item_checked = True
                                user_checks[user_name] = user_checks.get(user_name, 0) + 1
                        
                        if is_item_checked:
                            total_checked += 1
                    
                    day_summary['total_checked'] = total_checked
                    day_summary['users'] = user_checks
            
            summary_data[date_str] = day_summary
            
            # Move to the next day
            current_dt += timedelta(days=1)

        return JSONResponse({'summaryData': summary_data, 'totalMasterItems': total_master_items})
        
    except Exception as e:
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


# Vercel serverless function handler (ASGI)
# Export an ASGI-compatible handler so Vercel can invoke this app.
# async def handler(scope, receive, send):
#     await app(scope, receive, send)


# __all__ = ['handler', 'app']
# from mangum import Mangum

# handler = Mangum(app)