// API base URL - adjust for your Vercel deployment
const API_BASE = window.location.origin + '/api';

// Get current date in YYYY-MM-DD format
function getTodayDate() {
    const today = new Date();
    // Use UTC date parts to prevent timezone issues when comparing YYYY-MM-DD strings
    return new Date(today.getTime() - (today.getTimezoneOffset() * 60000)).toISOString().split('T')[0];
}

// NEW: Function to read date from URL query parameter
function getDateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    // Check if the URL parameter 'date' exists and is a valid date string
    const dateParam = params.get('date');
    if (dateParam && dateParam.match(/^\d{4}-\d{2}-\d{2}$/)) {
        return dateParam;
    }
    return null;
}

/**
 * Formats an ISO timestamp string to a readable time (e.g., 03:30 PM).
 * @param {string} timestamp - ISO 8601 string from Firestore.
 * @returns {string} Formatted time string.
 */
function formatTime(timestamp) {
    if (!timestamp) return '';
    try {
        const date = new Date(timestamp);
        // Formats to 12-hour time with AM/PM (e.g., 03:30 PM)
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return '';
    }
}

/**
 * Escapes HTML special characters in a string.
 * @param {string} str - The string to escape.
 * @returns {string} The escaped string.
 */
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;")
               .replace(/</g, "&lt;")
               .replace(/>/g, "&gt;")
               .replace(/"/g, "&quot;")
               .replace(/'/g, "&#039;");
}


// --- Global State ---
let currentDate = getDateFromUrl() || getTodayDate();
let checklistItems = [];
let checkedItems = {};
let currentUser = '';
let photoCache = {}; // Cache to store photo URLs locally

// --- DOM Elements ---
const checklistContainer = document.getElementById('checklist-container');
const loadingSpinner = document.getElementById('loading-spinner');
const userInput = document.getElementById('user-name-input');
const checklistDateDisplay = document.getElementById('checklist-date');


// --- UI Helpers ---

function showLoading() {
    loadingSpinner.style.display = 'block';
}

function hideLoading() {
    loadingSpinner.style.display = 'none';
}

function showError(message) {
    const errorDiv = document.getElementById('error-message');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);
    }
}

// Set up the current user from local storage
document.addEventListener('DOMContentLoaded', () => {
    const storedUser = localStorage.getItem('currentUser');
    if (storedUser) {
        currentUser = storedUser;
        userInput.value = storedUser;
    }

    userInput.addEventListener('change', (e) => {
        currentUser = e.target.value.trim();
        if (currentUser) {
            localStorage.setItem('currentUser', currentUser);
        } else {
            localStorage.removeItem('currentUser');
        }
        // Re-render to update UI elements based on current user (e.g., highlighting their checks)
        renderChecklist();
    });
});

// --- API Logic ---

/**
 * Fetches the checklist state for the current date from the server.
 */
async function loadChecklist() {
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/checklist/${currentDate}`);
        const data = await response.json();
        
        if (data.success) {
            checklistItems = data.items || [];
            checkedItems = data.checked || {};
            
            // Update the URL to include the date if it's missing (e.g., first load)
            if (!getDateFromUrl() && currentDate !== getTodayDate()) {
                 history.pushState(null, '', `?date=${currentDate}`);
            }

            // Update the displayed date
            checklistDateDisplay.textContent = currentDate === getTodayDate() ? 
                `Checklist for Today (${currentDate})` : 
                `Checklist for ${currentDate}`;

            renderChecklist();
        } else {
            throw new Error(data.error || 'Failed to load checklist');
        }
    } catch (error) {
        console.error('Error loading checklist:', error);
        showError('Failed to load checklist: ' + error.message);
    } finally {
        hideLoading();
    }
}

/**
 * Submits the complete local checklist state to the server.
 */
async function submitChecklist() {
    // Submission still requires a user name to avoid confusion in audit logs
    if (!currentUser) {
        alert('Please enter your name first before submitting the full checklist!');
        userInput.focus();
        return;
    }

    const payload = {
        date: currentDate,
        items: checklistItems,
        checked: checkedItems
    };

    try {
        showLoading();
        const response = await fetch(`${API_BASE}/checklist`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (data.success) {
            // After successful submit, reload from server to refresh last-completions
            await loadChecklist();
            alert('Checklist submitted successfully.');
        } else {
            throw new Error(data.error || 'Submit failed');
        }
    } catch (error) {
        console.error('Error submitting checklist:', error);
        showError('Failed to submit checklist: ' + error.message);
    } finally {
        hideLoading();
    }
}


/**
 * Sends a toggle request to the server and updates the local state.
 * @param {string} itemId 
 */
async function toggleCheck(itemId) {
    if (!currentUser) {
        alert('Please enter your name first.');
        userInput.focus();
        return;
    }

    // Capture the note from the hidden input field before the toggle
    const noteInput = document.getElementById(`note-input-${itemId}`);
    const note = noteInput ? noteInput.value : '';

    const payload = {
        date: currentDate,
        item_id: itemId,
        user: currentUser,
        note: note // Include the note in the toggle request
    };

    try {
        showLoading();
        const response = await fetch(`${API_BASE}/checklist/toggle`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (data.success) {
            // Update local state with the new 'checked' map returned by the server
            checkedItems = data.checked;
            renderChecklist();

            // The note box should be hidden if unchecked, or shown if checked and a note exists
            if (data.checked[itemId] && data.checked[itemId][currentUser]) {
                // Item is now checked, make sure the note box is visible if a note was entered
                const noteInput = document.getElementById(`note-input-${itemId}`);
                const saveBtn = document.getElementById(`save-note-btn-${itemId}`);
                if (noteInput.value.trim() !== '') {
                    noteInput.style.display = 'block';
                    saveBtn.style.display = 'inline-block';
                }
            } else {
                // Item is now unchecked, clear and hide the note box and button
                const noteInput = document.getElementById(`note-input-${itemId}`);
                if (noteInput) {
                    noteInput.value = ''; // Clear the note
                }
                toggleNoteBox(itemId, true); // Force close
            }

        } else {
            throw new Error(data.error || 'Toggle failed');
        }
    } catch (error) {
        console.error('Error toggling checklist item:', error);
        showError('Failed to toggle item: ' + error.message);
    } finally {
        hideLoading();
    }
}

/**
 * Saves the photo upload file to the server.
 * @param {string} itemId 
 * @param {File} file 
 */
async function savePhotoUpload(itemId, file) {
    if (!currentUser) {
        alert('Please enter your name first before uploading a photo.');
        userInput.focus();
        return;
    }

    // Check if the item is actually checked by the current user before uploading
    if (!checkedItems[itemId] || !checkedItems[itemId][currentUser]) {
        alert('You must check the item first before uploading a photo.');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('date', currentDate);
    formData.append('user', currentUser);

    try {
        showLoading();
        const response = await fetch(`${API_BASE}/upload/${itemId}`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (data.success) {
            // Update the photo cache and re-render the list
            if (!photoCache[itemId]) photoCache[itemId] = {};
            if (!photoCache[itemId][currentUser]) photoCache[itemId][currentUser] = {};
            
            photoCache[itemId][currentUser].photoUrl = data.photoUrl;
            
            // Re-render to show the new photo button/link
            renderChecklist();
            alert('Photo uploaded successfully!');

        } else {
            throw new Error(data.error || 'Photo upload failed');
        }

    } catch (error) {
        console.error('Error uploading photo:', error);
        showError('Failed to upload photo: ' + error.message);
    } finally {
        hideLoading();
    }
}


// --- Rendering Logic ---

/**
 * Renders the checklist to the DOM.
 */
function renderChecklist() {
    if (!checklistContainer) return;

    if (checklistItems.length === 0) {
        checklistContainer.innerHTML = '<p>No checklist items found for this date.</p>';
        return;
    }

    // Render each checklist item
    checklistContainer.innerHTML = checklistItems.map(item => {
        const itemCheckData = checkedItems[item.id] || {};
        const isChecked = Object.keys(itemCheckData).length > 0;
        const currentUserCheckData = itemCheckData[currentUser];
        
        let checkedByHtml = '';
        const checkedEntries = Object.entries(itemCheckData);

        if (checkedEntries.length > 0) {
            checkedByHtml = checkedEntries.map(([user, data]) => {
                const timeStr = formatTime(data.timestamp); 
                
                // --- MODIFIED: ADDED NOTE DISPLAY HERE ---
                const noteDisplay = data.note ? `<span class="note-display"> (Note: ${escapeHtml(data.note)})</span>` : '';
                
                return `
                    <span class="checked-by">
                        ${escapeHtml(user)} ${timeStr}${noteDisplay}
                    </span>
                `;
            }).join(', '); // Join multiple checkers with a comma and space
        }

        // Photo Button Logic
        const photoUrl = currentUserCheckData ? currentUserCheckData.photoUrl : null;
        const photoBtnText = photoUrl ? 'View/Change Photo' : 'Upload Photo';
        const photoBtnStyle = photoUrl ? 'background-color: #28a745; color: white;' : '';

        // Note Logic
        const existingNote = currentUserCheckData ? (currentUserCheckData.note || '') : '';
        const noteInputId = `note-input-${item.id}`;
        const hasNote = existingNote.trim() !== '';
        
        // Note box is visible if a note exists or if the user is typing/has typed one
        const noteDisplay = (hasNote || (currentUserCheckData && !currentUserCheckData.checked)) ? 'block' : 'none';

        // Variables for the new Save Note Button
        const canSave = (checkedItems[item.id] && checkedItems[item.id][currentUser]);
        const saveBtnId = `save-note-btn-${item.id}`;
        const saveBtnDisplay = (noteDisplay === 'block' && canSave) ? 'inline-block' : 'none';


        return `
            <div class="checklist-item ${isChecked ? 'checked' : ''}" onclick="toggleCheck('${item.id}')">
                <div class="checkbox"></div>
                <div class="item-content">
                    <div class="item-title">${escapeHtml(item.name)}</div>
                    ${isChecked ? `<div class="checked-info">${checkedByHtml}</div>` : ''}
                    
                    <div class="item-actions" onclick="event.stopPropagation();">
                        <button 
                            type="button"
                            class="action-btn"
                            style="${photoBtnStyle} margin-right: 8px;"
                            onclick="triggerPhotoUpload('${item.id}')"
                        >
                            ${photoBtnText}
                        </button>

                        <button 
                            type="button"
                            class="action-btn"
                            onclick="toggleNoteBox('${item.id}')"
                        >
                            ${noteBtnText}
                        </button>

                        <textarea 
                            id="${noteInputId}" 
                            class="item-note-input" 
                            rows="3" 
                            style="display: ${noteDisplay};" 
                            placeholder="Type your notes here..."
                            onblur="updateItemNote('${item.id}', this.value)"
                            onclick="event.stopPropagation();"
                        >${escapeHtml(existingNote)}</textarea>
                        
                        <button
                            id="${saveBtnId}"
                            type="button"
                            class="action-btn save-note-btn"
                            style="display: ${saveBtnDisplay}; margin-top: 5px; background-color: #007bff; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;"
                            onclick="saveNoteOnly('${item.id}')"
                        >
                            💾 Save Note
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}


// --- Action Handlers ---

/**
 * Updates the local checklist state when a note is typed, ensuring it's ready to be saved on next action.
 * @param {string} itemId 
 * @param {string} note 
 */
function updateItemNote(itemId, note) {
    if (!currentUser) return;

    // Check if the item is already checked by the current user
    if (checkedItems[itemId] && checkedItems[itemId][currentUser]) {
        // Item is checked: update the note field in the local state
        // This is purely a LOCAL state update. The save happens via saveNoteOnly or toggleCheck.
        checkedItems[itemId][currentUser].note = note;
    } 
    // If the item is not checked, we won't save the note until the user checks the item.
    // The note will still be in the textarea for the next toggle action.
}

/**
 * Triggers the file upload dialog and handles the photo upload process.
 * @param {string} itemId 
 */
function triggerPhotoUpload(itemId) {
    const photoUrl = checkedItems[itemId] && checkedItems[itemId][currentUser] ? checkedItems[itemId][currentUser].photoUrl : null;
    
    // If a photo exists, offer to view it first
    if (photoUrl) {
        if (confirm('A photo already exists. Do you want to view it? (Cancel to upload a new one)')) {
            window.open(photoUrl, '_blank');
            return;
        }
    }

    // Create an invisible file input element
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (file) {
            await savePhotoUpload(itemId, file);
        }
    };
    
    // Open the file dialog
    input.click();
}

function toggleNoteBox(itemId, forceClose = false) {
    const noteBox = document.getElementById(`note-input-${itemId}`);
    const saveBtn = document.getElementById(`save-note-btn-${itemId}`); // Get the new button
    
    if (!noteBox || !saveBtn) return; // Check if elements exist

    // Force close or if currently visible
    if (forceClose || noteBox.style.display === 'block') {
        // Hide
        noteBox.style.display = 'none';
        saveBtn.style.display = 'none';
    } else {
        // Show
        noteBox.style.display = 'block';
        
        // Only show the save button if the item is checked by the current user
        const canSave = (checkedItems[itemId] && checkedItems[itemId][currentUser]);
        if(canSave) {
            saveBtn.style.display = 'inline-block'; // Show the button next to the box
        }

        noteBox.focus(); // Automatically focus cursor in the box
    }
}

/**
 * Saves the note associated with an item immediately by submitting the checklist state.
 * @param {string} itemId 
 */
async function saveNoteOnly(itemId) {
    if (!currentUser) {
        alert('Please enter your name first before saving a note.');
        userInput.focus();
        return;
    }

    // Ensure the latest note value from the textarea is in the local state
    const noteInput = document.getElementById(`note-input-${itemId}`);
    if (noteInput) {
        updateItemNote(itemId, noteInput.value);
    }
    
    // Check if the item is actually checked by the current user before saving
    if (!checkedItems[itemId] || !checkedItems[itemId][currentUser]) {
        alert('You must check the item first before saving a standalone note.');
        return;
    }

    // Call submitChecklist, which sends the entire local state, including the note
    await submitChecklist();
    
    // Hide the note box after saving, but not the button (toggleNoteBox handles both)
    toggleNoteBox(itemId, true); 
}

// Make it global
window.saveNoteOnly = saveNoteOnly;

// Make it global
window.toggleNoteBox = toggleNoteBox;

// Expose to window so HTML onclick works
window.triggerPhotoUpload = triggerPhotoUpload;

// Make toggleCheck available globally
window.toggleCheck = toggleCheck;

// Wire submit button
document.addEventListener('DOMContentLoaded', () => {
    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) {
        submitBtn.addEventListener('click', (e) => {
            e.preventDefault();
            submitChecklist();
        });
    }

    const summaryNavBtn = document.getElementById('summary-btn');
    if (summaryNavBtn) {
        summaryNavBtn.addEventListener('click', () => {
            // Redirect the user to the summary page
            window.location.href = `/summary.html`;
        });
    }

    // Handle date navigation
    const prevDayBtn = document.getElementById('prev-day-btn');
    const nextDayBtn = document.getElementById('next-day-btn');

    function navigateDate(days) {
        try {
            const current = new Date(currentDate);
            current.setDate(current.getDate() + days);
            
            // Format to YYYY-MM-DD
            const newDate = new Date(current.getTime() - (current.getTimezoneOffset() * 60000)).toISOString().split('T')[0];
            
            // Update the URL and reload
            window.location.href = `?date=${newDate}`;

        } catch (e) {
            console.error("Date navigation error:", e);
        }
    }

    if (prevDayBtn) {
        prevDayBtn.addEventListener('click', () => navigateDate(-1));
    }
    if (nextDayBtn) {
        nextDayBtn.addEventListener('click', () => navigateDate(1));
    }
    
    // Initial load
    loadChecklist();
});