// API base URL - adjust for your Vercel deployment
const API_BASE = window.location.origin + '/api';

// Get current date in YYYY-MM-DD format
function getTodayDate() {
    const today = new Date();
    return today.toISOString().split('T')[0];
}

// Initialize
let currentDate = getTodayDate();
let currentUser = localStorage.getItem('checklist_user') || '';
let checklistItems = [];
let checkedItems = {};
let lastCompletions = {}; // {item_id: 'YYYY-MM-DD'}
let filterProcess = 'all';
let filterEquipment = 'all';
let filterPeriod = 'all';

// DOM elements
const dateInput = document.getElementById('date-input');
const userInput = document.getElementById('user-input');
const loadingDiv = document.getElementById('loading');
const errorDiv = document.getElementById('error');
const checklistContainer = document.getElementById('checklist-container');
const checklistDiv = document.getElementById('checklist');
const totalItemsSpan = document.getElementById('total-items');
const checkedCountSpan = document.getElementById('checked-count');
const progressSpan = document.getElementById('progress');
const processFilterSelect = document.getElementById('filter-process');
const equipmentFilterSelect = document.getElementById('filter-equipment');
const periodFilterSelect = document.getElementById('filter-period');

// Set today's date
dateInput.value = currentDate;
userInput.value = currentUser;

// Event listeners
dateInput.addEventListener('change', (e) => {
    currentDate = e.target.value;
    loadChecklist();
});

userInput.addEventListener('change', (e) => {
    currentUser = e.target.value;
    localStorage.setItem('checklist_user', currentUser);
    renderChecklist();
});

processFilterSelect.addEventListener('change', (e) => {
    filterProcess = e.target.value;
    renderChecklist();
});

equipmentFilterSelect.addEventListener('change', (e) => {
    filterEquipment = e.target.value;
    renderChecklist();
});

periodFilterSelect.addEventListener('change', (e) => {
    filterPeriod = e.target.value;
    renderChecklist();
});

// Load checklist items structure
async function loadChecklistItems() {
    try {
        const response = await fetch(`${API_BASE}/checklist/items`);
        const data = await response.json();
        
        if (data.items && data.items.length > 0) {
            checklistItems = data.items;
            populateFilters();
        } else {
            // If no items, show message
            showError('No checklist items found. Please run the setup script first.');
            return false;
        }
        return true;
    } catch (error) {
        console.error('Error loading checklist items:', error);
        showError('Failed to load checklist items: ' + error.message);
        return false;
    }
}

// Load checklist for current date
async function loadChecklist() {
    showLoading();
    hideError();
    
    // First load the checklist items structure
    const itemsLoaded = await loadChecklistItems();
    if (!itemsLoaded) {
        return;
    }
    
    // Load last completion dates and current date's checklist in parallel
    try {
        const [completionsResponse, checklistResponse] = await Promise.all([
            fetch(`${API_BASE}/checklist/last-completions`),
            fetch(`${API_BASE}/checklist?date=${currentDate}`)
        ]);
        
        const completionsData = await completionsResponse.json();
        lastCompletions = completionsData.lastCompletions || {};
        
        const checklistData = await checklistResponse.json();
        checkedItems = checklistData.checked ? checklistData.checked : {};
        
        renderChecklist();
        hideLoading();
    } catch (error) {
        console.error('Error loading checklist:', error);
        showError('Failed to load checklist: ' + error.message);
        hideLoading();
    }
}

// Toggle check for an item
async function toggleCheck(itemId) {
    // Local-only toggle: mark/unmark checkedItems locally and wait for explicit submit
    if (!currentUser) {
        alert('Please enter your name first!');
        userInput.focus();
        return;
    }

    // Ensure structure exists
    if (!checkedItems[itemId]) {
        checkedItems[itemId] = {};
    }

    if (checkedItems[itemId][currentUser]) {
        // Uncheck locally
        delete checkedItems[itemId][currentUser];
        if (Object.keys(checkedItems[itemId]).length === 0) {
            delete checkedItems[itemId];
        }
    } else {
        // Check locally with an ISO timestamp (server will replace with its timestamp on submit)
        checkedItems[itemId][currentUser] = {
            timestamp: new Date().toISOString(),
            checked: true
        };
    }

    // Do NOT update lastCompletions here; only update on submit when data is persisted
    renderChecklist();
}

// Submit the entire checklist (persist checked items and photos) for the current date
async function submitChecklist() {
    if (!currentUser) {
        alert('Please enter your name first!');
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

// Photo upload feature removed. Photo-related functions and UI were deleted.

// Render checklist
function renderChecklist() {
    if (checklistItems.length === 0) {
        checklistDiv.innerHTML = '<p style="text-align: center; padding: 40px; color: #666;">No checklist items available.</p>';
        return;
    }
    
    // Sort items by period, process, equipment, then fallback to order
    const sortedItems = [...checklistItems].sort((a, b) => {
        const periodA = a.periodDays != null ? a.periodDays : Number.MAX_SAFE_INTEGER;
        const periodB = b.periodDays != null ? b.periodDays : Number.MAX_SAFE_INTEGER;
        if (periodA !== periodB) return periodA - periodB;

        const processA = (a.process || '').toLowerCase();
        const processB = (b.process || '').toLowerCase();
        if (processA !== processB) return processA.localeCompare(processB);

        const equipmentA = (a.equipment || '').toLowerCase();
        const equipmentB = (b.equipment || '').toLowerCase();
        if (equipmentA !== equipmentB) return equipmentA.localeCompare(equipmentB);

        return (a.order || 0) - (b.order || 0);
    });

    const filteredItems = sortedItems.filter(item => {
        // Manual filter matches
        const processMatches = filterProcess === 'all' || (item.process || item.category || 'General') === filterProcess;
        const equipmentMatches = filterEquipment === 'all' || (item.equipment || 'General') === filterEquipment;
        const periodValue = item.periodDays != null ? String(item.periodDays) : 'custom';
        const periodMatches = filterPeriod === 'all' || periodValue === filterPeriod;
        
        // Period-based auto-filtering: show task if enough days have passed since last completion
        const periodDays = item.periodDays;
        if (periodDays != null && periodDays > 0) {
            const lastCompletionDate = lastCompletions[item.id];
            if (lastCompletionDate) {
                // Calculate days since last completion
                const lastDate = new Date(lastCompletionDate + 'T00:00:00');
                const today = new Date(currentDate + 'T00:00:00');
                const daysSince = Math.floor((today - lastDate) / (1000 * 60 * 60 * 24));
                
                // Show task only if days since last completion >= period days
                if (daysSince < periodDays) {
                    return false; // Hide task - not enough days have passed
                }
            }
            // If never completed, show it (needs to be done)
        }
        
        return processMatches && equipmentMatches && periodMatches;
    });
    
    if (filteredItems.length === 0) {
        checklistDiv.innerHTML = '<p style="text-align: center; padding: 40px; color: #666;">No items match the selected filters.</p>';
        updateStats([]);
        return;
    }

    checklistDiv.innerHTML = filteredItems.map(item => {
        const isChecked = checkedItems[item.id] && checkedItems[item.id][currentUser];
        const checkedBy = checkedItems[item.id] ? Object.keys(checkedItems[item.id]) : [];
        const processLabel = item.process || item.category || 'General';
        const equipmentLabel = item.equipment || 'N/A';
        const taskLabel = item.item || item.text || 'Task';
        const periodDays = item.periodDays || null;
        const periodLabel = formatPeriodLabel(periodDays);
        
        return `
            <div class="checklist-item ${isChecked ? 'checked' : ''}" onclick="toggleCheck('${item.id}')">
                <div class="checkbox"></div>
                <div class="item-content">
                    <div class="item-text">${escapeHtml(taskLabel)}</div>
                    <div class="item-tags">
                        <span class="tag tag-process">${escapeHtml(processLabel)}</span>
                        <span class="tag tag-equipment">${escapeHtml(equipmentLabel)}</span>
                        <span class="tag tag-period">${escapeHtml(periodLabel)}</span>
                    </div>
                    ${checkedBy.length > 0 ? `
                        <div class="item-meta">
                            Checked by: ${checkedBy.map(u => `<span class="checked-by">${escapeHtml(u)}</span>`).join('')}
                        </div>
                    ` : ''}
                    <div class="item-actions" onclick="event.stopPropagation();">
                        <!-- Photo upload removed -->
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    updateStats(filteredItems);
}

// Update statistics
function updateStats(visibleItems) {
    const total = visibleItems.length;
    const checked = visibleItems.filter(item =>
        checkedItems[item.id] && checkedItems[item.id][currentUser]
    ).length;
    const progress = total > 0 ? Math.round((checked / total) * 100) : 0;
    
    totalItemsSpan.textContent = total;
    checkedCountSpan.textContent = checked;
    progressSpan.textContent = progress + '%';
}

// Utility functions
function showLoading() {
    loadingDiv.style.display = 'block';
    checklistContainer.style.display = 'none';
    errorDiv.style.display = 'none';
}

function hideLoading() {
    loadingDiv.style.display = 'none';
    checklistContainer.style.display = 'block';
}

function showError(message) {
    errorDiv.style.display = 'block';
    document.getElementById('error-message').textContent = message;
    checklistContainer.style.display = 'none';
}

function hideError() {
    errorDiv.style.display = 'none';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatPeriodLabel(periodDays) {
    if (!periodDays || Number.isNaN(periodDays)) {
        return 'As needed';
    }
    if (periodDays === 1) {
        return 'Daily';
    }
    if (periodDays === 7) {
        return 'Weekly';
    }
    if (periodDays === 30) {
        return 'Monthly';
    }
    return `Every ${periodDays} days`;
}

function populateFilters() {
    const processSet = new Set();
    const equipmentSet = new Set();
    const periodSet = new Set();

    checklistItems.forEach(item => {
        processSet.add(item.process || item.category || 'General');
        equipmentSet.add(item.equipment || 'General');
        const periodValue = item.periodDays != null ? String(item.periodDays) : 'custom';
        periodSet.add(periodValue);
    });

    fillSelect(processFilterSelect, Array.from(processSet).sort(), 'All processes');
    fillSelect(equipmentFilterSelect, Array.from(equipmentSet).sort(), 'All equipment');

    const periodOptions = Array.from(periodSet).sort((a, b) => {
        const numA = a === 'custom' ? Number.MAX_SAFE_INTEGER : parseInt(a, 10);
        const numB = b === 'custom' ? Number.MAX_SAFE_INTEGER : parseInt(b, 10);
        return numA - numB;
    });
    fillSelect(periodFilterSelect, periodOptions, 'All frequencies', value => {
        if (value === 'custom') {
            return 'Custom';
        }
        return formatPeriodLabel(parseInt(value, 10));
    });
}

function fillSelect(selectElement, values, defaultLabel, formatter) {
    const currentValue = selectElement.value || 'all';
    selectElement.innerHTML = `<option value="all">${defaultLabel}</option>`;
    values.forEach(value => {
        const label = formatter ? formatter(value) : value;
        selectElement.innerHTML += `<option value="${value}">${escapeHtml(label)}</option>`;
    });

    if ([...selectElement.options].some(opt => opt.value === currentValue)) {
        selectElement.value = currentValue;
    } else {
        selectElement.value = 'all';
    }
}

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
});

// Load checklist on page load
loadChecklist();


