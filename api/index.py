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
            # Use cert as dictionary if running serverless/containerized
            cred = credentials.Certificate(cred_dict)
        else:
            cred_path = os.environ.get('FIREBASE_CREDENTIALS_PATH', 'firebase-credentials.json')
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
            else:
                raise Exception("Firebase credentials not found. Set FIREBASE_CREDENTIALS or FIREBASE_CREDENTIALS_PATH")
        firebase_admin.initialize_app(cred)

@app.on_event("startup")
def on_startup():
    init_firebase()

# -------- API Endpoints -------- #

# Endpoint for submitting the full checklist
@app.post('/api/checklist')
async def submit_checklist(data: dict):
    """
    Submits the complete checklist state for a given date.
    This replaces the entire document, usually called via a 'Submit' button.
    """
    try:
        if not db:
            init_firebase()

        date = data.get('date')
        if not date:
            raise HTTPException(status_code=400, detail="Date is required.")

        doc_ref = db.collection('checklists').document(date)
        
        # Merge True is critical here to ensure photo and other fields persist
        # if the client-side payload doesn't include them, though the current
        # client logic sends the full state.
        doc_ref.set(data, merge=True)

        return JSONResponse({'success': True})
    except Exception as e:
        print(f"Error submitting checklist: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Endpoint for toggling a single item (atomic update)
@app.post('/api/checklist/toggle')
async def toggle_check(data: dict):
    """
    Toggles the checked status of a single item for a given user.
    This is called when a user clicks a checkbox.
    """
    try:
        if not db:
            init_firebase()

        date = data.get('date')
        item_id = data.get('item_id')
        user = data.get('user')
        note = data.get('note', '')  # Note is passed with the toggle
        
        if not all([date, item_id, user]):
            raise HTTPException(status_code=400, detail="Date, item_id, and user are required.")

        doc_ref = db.collection('checklists').document(date)
        doc = doc_ref.get()
        
        # Get existing data or initialize
        if doc.exists:
            checklist_data = doc.to_dict()
        else:
            # If the checklist doesn't exist yet, we can't toggle an item.
            # This should ideally be preceded by a GET /api/checklist/date.
            # For simplicity, we'll initialize the base structure needed for the toggle.
            checklist_data = {
                'date': date,
                'items': [], # Master items list should be loaded on /api/checklist/date
                'checked': {}
            }
        
        checked = checklist_data.get('checked', {})
        
        if item_id in checked and user in checked[item_id]:
            # Item is currently checked by this user, so uncheck it
            del checked[item_id][user]
            
            # If no one else has checked it, remove the item_id entirely
            if not checked[item_id]:
                del checked[item_id]
        else:
            # Item is not checked by this user, so check it
            if item_id not in checked:
                checked[item_id] = {}
                
            # Checking the item
            checked[item_id][user] = {
                'timestamp': firestore.SERVER_TIMESTAMP,
                'checked': True,
                # --- FIX 2: Added the 'note' field to the saved data ---
                'note': note
            }
            
        # Update the checked map
        checklist_data['checked'] = checked
        
        # Update Firestore document with the modified 'checked' map.
        # We only need to merge the 'checked' field to avoid overwriting the 'items' list
        # which represents the master checklist for the day.
        doc_ref.set({'checked': checked}, merge=True)

        return JSONResponse({'success': True, 'checked': checked})
    except Exception as e:
        print(f"Error toggling checklist item: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Endpoint for photo upload
@app.post("/api/upload/{item_id}")
async def upload_photo(item_id: str, file: UploadFile = File(...), date: str = Form(...), user: str = Form(...)):
    """Handles image upload for a specific checklist item."""
    try:
        if not firebase_admin._apps:
            init_firebase()

        bucket = storage.bucket()
        
        # Create a unique filename: date/itemId_user_timestamp.ext
        file_extension = file.filename.split('.')[-1]
        timestamp = int(time.time() * 1000)
        blob_name = f"{date}/{item_id}_{user}_{timestamp}.{file_extension}"
        
        blob = bucket.blob(blob_name)
        
        # Upload the file stream
        # Read the file content and upload
        file_content = await file.read()
        blob.upload_from_string(file_content, content_type=file.content_type)
        
        # Make the file publicly viewable
        blob.make_public()
        photo_url = blob.public_url

        # Update the Firestore document with the photo URL
        doc_ref = db.collection('checklists').document(date)
        
        # Use a dot-notation key to set the photo URL specifically for the item and user
        field_path = f"checked.{item_id}.{user}.photoUrl"
        doc_ref.set({field_path: photo_url}, merge=True)
        
        return JSONResponse({"success": True, "photoUrl": photo_url})

    except Exception as e:
        print(f"Error uploading photo: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Endpoint for fetching a checklist for a specific date (and creating one if it doesn't exist)
@app.get('/api/checklist/{date}')
async def get_checklist(date: str):
    """Fetches the checklist for a given date."""
    try:
        if not db:
            init_firebase()

        # 1. Fetch the master checklist items
        master_doc_ref = db.collection('master').document('checklist')
        master_doc = master_doc_ref.get()
        if not master_doc.exists:
            # Fallback or error if master list is missing
            master_items = []
        else:
            master_items = master_doc.to_dict().get('items', [])
            
        # Add 'id' field if missing (for client-side keys)
        for i, item in enumerate(master_items):
            if 'id' not in item:
                item['id'] = f'item{i+1}'

        # 2. Fetch the checked status for the requested date
        doc_ref = db.collection('checklists').document(date)
        doc = doc_ref.get()

        if doc.exists:
            checklist_data = doc.to_dict()
            # Ensure the master list is used, checked data is merged
            checked = checklist_data.get('checked', {})
            # Use the master items, not the potentially stale list in the date doc
            items = master_items 
        else:
            # Checklist for the date doesn't exist yet, return master list with no checks
            items = master_items
            checked = {}

        return JSONResponse({
            'date': date,
            'items': items,
            'checked': checked,
            'success': True
        })

    except Exception as e:
        print(f"Error fetching checklist: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# Endpoint for fetching calendar summary data
@app.get('/api/summary')
async def get_summary():
    """Fetches summary of checklist completion status for the last 30 days."""
    try:
        if not db:
            init_firebase()

        summary_data = {}
        today = datetime.now()
        
        # 1. Fetch the master checklist items count
        master_doc_ref = db.collection('master').document('checklist')
        master_doc = master_doc_ref.get()
        total_master_items = len(master_doc.to_dict().get('items', [])) if master_doc.exists else 0
        
        # 2. Iterate through the last 30 days
        for i in range(30):
            date_dt = today - timedelta(days=i)
            date_str = date_dt.strftime('%Y-%m-%d')
            
            doc_ref = db.collection('checklists').document(date_str)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                checked_count = sum(
                    len(item_checks) 
                    for item_checks in data.get('checked', {}).values()
                )
                
                # Check if every master item has at least one check
                unique_items_checked = len(data.get('checked', {}))
                is_complete = (total_master_items > 0 and unique_items_checked >= total_master_items)

                summary_data[date_str] = {
                    'checked_count': checked_count,
                    'is_complete': is_complete
                }
            else:
                # No data for this date
                summary_data[date_str] = {
                    'checked_count': 0,
                    'is_complete': False
                }
        
        # Return the summary data and the total item count
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
