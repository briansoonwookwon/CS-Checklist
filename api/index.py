from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
from datetime import datetime
import json
import time
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()
# Get the project root directory (parent of 'api' folder)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_folder = os.path.join(project_root, 'static')

app = Flask(__name__, static_folder=static_folder, static_url_path='/static')
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB upload limit

# Initialize Firebase references
db = None
bucket = None


def init_firebase():
    """Initialize Firebase services if needed."""
    global db, bucket
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

        firebase_config = {}
        bucket_name = os.environ.get('FIREBASE_STORAGE_BUCKET')
        if bucket_name:
            firebase_config['storageBucket'] = bucket_name
        firebase_admin.initialize_app(cred, firebase_config or None)

    db = firestore.client()
    bucket_name = os.environ.get('FIREBASE_STORAGE_BUCKET')
    bucket = storage.bucket(bucket_name) if bucket_name else None


# Attempt to initialize on import (will warn if missing config)
try:
    init_firebase()
except Exception as e:
    print(f"Warning: Firebase initialization failed: {e}")


def convert_firestore_timestamp(timestamp):
    """Convert Firestore timestamp/datetime to ISO string."""
    if timestamp is None:
        return None
    if hasattr(timestamp, 'isoformat'):
        return timestamp.isoformat()
    return str(timestamp)


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
    global db, bucket
    if db is None or bucket is None:
        init_firebase()


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


@app.route('/api/checklist', methods=['GET'])
def get_checklist():
    """Get checklist items for a specific date."""
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    try:
        ensure_firebase()

        doc_ref = db.collection('checklists').document(date)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            return jsonify(make_json_serializable(data))
        else:
            return jsonify({
                'date': date,
                'items': [],
                'checked': {},
                'photos': {}
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/checklist', methods=['POST'])
def update_checklist():
    """Replace the checklist state for a date."""
    data = request.json or {}
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    items = data.get('items', [])
    checked = data.get('checked', {})

    try:
        ensure_firebase()

        doc_ref = db.collection('checklists').document(date)
        doc_ref.set({
            'date': date,
            'items': items,
            'checked': checked,
            'lastUpdated': firestore.SERVER_TIMESTAMP
        }, merge=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/checklist/toggle', methods=['POST'])
def toggle_check():
    """Toggle a specific checklist item for a user."""
    data = request.json or {}
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    item_id = data.get('item_id')
    user = data.get('user', 'anonymous')

    if not item_id:
        return jsonify({"error": "Missing item_id"}), 400

    try:
        ensure_firebase()

        doc_ref = db.collection('checklists').document(date)
        doc = doc_ref.get()

        if doc.exists:
            checklist_data = doc.to_dict()
            checked = checklist_data.get('checked', {})
            checklist_data.setdefault('photos', {})
        else:
            checklist_data = {
                'date': date,
                'items': [],
                'checked': {},
                'photos': {}
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
            return jsonify({"success": True, "checked": serializable_checked})
        else:
            return jsonify({"success": True, "checked": {}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/checklist/items', methods=['GET'])
def get_checklist_items():
    """Return the master checklist item definitions."""
    try:
        ensure_firebase()

        doc_ref = db.collection('config').document('checklist_items')
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return jsonify(make_json_serializable(data))
        else:
            return jsonify({"items": []})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/checklist/items', methods=['POST'])
def set_checklist_items():
    """Replace the master checklist item definitions."""
    data = request.json or {}
    items = data.get('items', [])

    try:
        ensure_firebase()

        doc_ref = db.collection('config').document('checklist_items')
        doc_ref.set({
            'items': items,
            'lastUpdated': firestore.SERVER_TIMESTAMP
        })
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/checklist/last-completions', methods=['GET'])
def get_last_completions():
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

        return jsonify({"lastCompletions": last_completions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/checklist/photo', methods=['POST'])
def upload_photo():
    """Upload a verification photo for a checklist item."""
    if 'photo' not in request.files:
        return jsonify({"error": "No photo provided"}), 400

    file = request.files['photo']
    date = request.form.get('date')
    item_id = request.form.get('item_id')
    user = request.form.get('user', 'anonymous')

    if not date or not item_id or not user:
        return jsonify({"error": "Missing required fields"}), 400

    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    if not file.mimetype or not file.mimetype.startswith('image/'):
        return jsonify({"error": "Only image uploads are allowed"}), 400

    try:
        ensure_firebase()
        if bucket is None:
            return jsonify({"error": "Photo uploads require FIREBASE_STORAGE_BUCKET to be configured"}), 500

        safe_name = secure_filename(file.filename)
        timestamp = int(time.time())
        blob_path = f"checklists/{date}/{item_id}/{timestamp}_{safe_name}"

        blob = bucket.blob(blob_path)
        blob.upload_from_file(file, content_type=file.mimetype)
        blob.make_public()

        photo_entry = {
            'url': blob.public_url,
            'path': blob_path,
            'uploadedBy': user,
            'uploadedAt': firestore.SERVER_TIMESTAMP
        }

        doc_ref = db.collection('checklists').document(date)
        doc_ref.set({
            'photos': {
                item_id: {
                    user: photo_entry
                }
            },
            'lastUpdated': firestore.SERVER_TIMESTAMP
        }, merge=True)

        updated_doc = doc_ref.get()
        photos = {}
        if updated_doc.exists:
            doc_data = updated_doc.to_dict()
            photos = make_json_serializable(doc_data.get('photos', {}))

        return jsonify({"success": True, "photos": photos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------- Static asset helpers for local dev -------- #
@app.route('/')
def index():
    """Serve the main HTML page."""
    return send_from_directory(static_folder, 'index.html')


@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static assets when running locally."""
    if filename.startswith('api/'):
        return jsonify({"error": "Not found"}), 404

    file_path = os.path.join(static_folder, filename)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(static_folder, filename)
    return jsonify({"error": "Not found"}), 404


# Vercel serverless function handler (WSGI)
# Vercel invokes Python serverless functions using the WSGI-style
# callable signature (environ, start_response). Forward the call
# directly to the Flask WSGI app so the server handles response
# headers/status correctly.
def handler(environ, start_response):
    try:
        ensure_firebase()
    except Exception as e:
        print(f"Firebase init error: {e}")

    return app(environ, start_response)


__all__ = ['handler', 'app']

