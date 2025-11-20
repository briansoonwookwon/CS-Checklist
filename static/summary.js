// API base URL - adjust for your Vercel deployment
const API_BASE = window.location.origin + '/api';

// DOM Elements
const calendarGrid = document.getElementById('calendar-grid');
const calendarHeader = document.getElementById('calendar-header');
const monthYearSpan = document.getElementById('current-month-year');
const prevButton = document.getElementById('prev-month');
const nextButton = document.getElementById('next-month');

// State
let currentViewDate = new Date(); // Tracks the month currently being viewed
let masterItems = []; // Stores the full master checklist items
let lastCompletions = {}; // Stores last completion dates {item_id: 'YYYY-MM-DD'}
// totalMasterItems is now replaced by dynamic calculation

// --- Utility Functions ---

/**
 * Formats a Date object to YYYY-MM-DD string.
 * @param {Date} date 
 * @returns {string}
 */
function formatDate(date) {
    // Uses local date components to avoid UTC/timezone confusion in a calendar view
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/**
 * Gets today's date in YYYY-MM-DD format for comparison.
 * @returns {string}
 */
function getTodayDate() {
    const today = new Date();
    return new Date(today.getTime() - (today.getTimezoneOffset() * 60000)).toISOString().split('T')[0];
}

/**
 * Calculates the start and end date (YYYY-MM-DD) for the month being viewed.
 * @param {Date} dateInMonth 
 * @returns {{startDate: string, endDate: string}}
 */
function getStartAndEndDate(dateInMonth) {
    const year = dateInMonth.getFullYear();
    const month = dateInMonth.getMonth();

    // Start of the month (YYYY-MM-01)
    const startDate = new Date(year, month, 1);

    // End of the month (Last day of the month)
    const endDate = new Date(year, month + 1, 0);

    return {
        startDate: formatDate(startDate),
        endDate: formatDate(endDate)
    };
}

/**
 * Calculates the total number of items DUE on a given date by applying
 * the same periodic filtering logic found in app.js.
 * @param {string} dateStr YYYY-MM-DD date being checked.
 * @param {Array} masterItems Full list of checklist items.
 * @param {Object} completionsDict Dictionary of last completion dates {itemId: dateStr}.
 * @returns {number} Count of items that are due on that date.
 */
function getItemsDueForDate(dateStr, masterItems, completionsDict) {
    const actualTodayStr = getTodayDate();
    const dateToCheck = new Date(dateStr + 'T00:00:00');

    return masterItems.filter(item => {
        // Rule: If viewing a past date, all items are considered 'due' for the denominator
        if (dateStr < actualTodayStr) { 
             return true; 
        }

        // Rule: If viewing today/future, apply periodic filtering (Rule 3)
        const periodDays = item.periodDays;
        
        // Non-periodic items (periodDays null or <= 0) are always due
        if (periodDays == null || periodDays <= 0) {
            return true;
        }
        
        const lastCompletionDate = completionsDict[item.id];
        
        if (lastCompletionDate) {
            const lastDate = new Date(lastCompletionDate + 'T00:00:00');
            const daysSince = Math.floor((dateToCheck - lastDate) / (1000 * 60 * 60 * 24));
            
            // Hide task if NOT enough days have passed (i.e., NOT due)
            if (daysSince < periodDays) {
                return false; 
            }
        }
        
        // If it passed all checks, it's due.
        return true;
    }).length;
}

// --- Fetching Data ---

// New function to fetch master items and completions once
async function fetchMasterData() {
    if (masterItems.length > 0) return; // Load only once

    try {
        // 1. Fetch full checklist item structure
        const itemsResponse = await fetch(`${API_BASE}/checklist/items`);
        const itemsData = await itemsResponse.json();
        masterItems = itemsData.items || [];
        
        // 2. Fetch last completion dates
        const completionsResponse = await fetch(`${API_BASE}/checklist/last-completions`);
        const completionsData = await completionsResponse.json();
        lastCompletions = completionsData.lastCompletions || {};
    } catch (error) {
         console.error('Error fetching master data:', error);
         calendarGrid.innerHTML = `<p style="text-align: center; color: red;">Failed to load master data: ${error.message}</p>`;
         // Re-throw to stop further loading
         throw new Error('Failed to load master checklist and completion data.');
    }
}

async function fetchSummaryData(date) {
    const { startDate, endDate } = getStartAndEndDate(date);
    
    try {
        // NOTE: The backend still returns totalMasterItems, but we ignore it now.
        const response = await fetch(`${API_BASE}/summary/calendar?start_date=${startDate}&end_date=${endDate}`);
        
        if (!response.ok) {
             throw new Error(`API error: ${response.statusText}`);
        }
        
        const data = await response.json();
        // We only need data.summaryData now
        return data.summaryData || {}; 
    } catch (error) {
        console.error('Error fetching calendar summary:', error);
        calendarGrid.innerHTML = `<p style="text-align: center; color: red;">Failed to load data: ${error.message}</p>`;
        return {};
    }
}

// --- Rendering Logic ---

function renderHeader() {
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    calendarHeader.className = 'calendar-header';
    calendarHeader.innerHTML = days.map(day => `<div>${day}</div>`).join('');
}

/**
 * Renders the calendar grid and populates cells with summary data.
 * @param {Object} summaryData - Data keyed by date string (YYYY-MM-DD).
 * @param {Array} masterItems - Full list of checklist items.
 * @param {Object} completionsDict - Dictionary of last completion dates.
 */
function renderCalendar(summaryData, masterItems, completionsDict) {
    calendarGrid.innerHTML = '';
    calendarGrid.className = 'calendar-grid';

    const year = currentViewDate.getFullYear();
    const month = currentViewDate.getMonth();

    // Set Month/Year display
    monthYearSpan.textContent = currentViewDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

    // 1. Determine the first day of the month and the day of the week
    const firstDayOfMonth = new Date(year, month, 1);
    const startingDayOfWeek = firstDayOfMonth.getDay(); 

    // 2. Determine the last day of the month
    const lastDayOfMonth = new Date(year, month + 1, 0).getDate();

    // 3. Add padding (empty) cells for days before the 1st
    for (let i = 0; i < startingDayOfWeek; i++) {
        calendarGrid.innerHTML += '<div class="calendar-day empty"></div>';
    }

    const actualToday = getTodayDate(); // Get today for comparison

    // 4. Render days
    for (let day = 1; day <= lastDayOfMonth; day++) {
        const date = new Date(year, month, day);
        const dateStr = formatDate(date);
        const dayData = summaryData[dateStr];
        
        let content = `<div class="day-number">${day}</div>`;
        let dayClass = 'calendar-day';

        // --- DYNAMICALLY CALCULATE TOTAL DUE ITEMS ---
        const totalItemsCount = getItemsDueForDate(dateStr, masterItems, completionsDict);
        // --- END DYNAMIC CALCULATION ---
        
        // Logic to determine if the day should be a link
        // A day is clickable if it has data OR is today/future
        const isClickable = !!dayData || dateStr >= actualToday;
        
        let elementTag = isClickable ? 'a' : 'div';
        const linkAttribute = isClickable ? `href="index.html?date=${dateStr}"` : '';

        if (dayData) {
            dayClass += ' has-data';
            
            let statusText;
            let statusClass;
            const checkedCount = dayData.total_checked;

            if (totalItemsCount === 0) {
                // If 0 items were due, mark as N/A or fully checked if 0 checks
                statusText = 'N/A';
                statusClass = 'checked';
                dayClass += ' submitted';
            } else if (checkedCount === 0) { 
                // Case 1: Nothing checked (Incomplete)
                statusText = '❌ Incomplete';
                statusClass = 'incomplete';
                dayClass += ' is-incomplete'; 
            } else if (checkedCount >= totalItemsCount) {
                // Case 2: All items checked
                statusText = '✅ Checked';
                statusClass = 'checked';
                dayClass += ' submitted'; 
            } else {
                // Case 3: Some items checked, but not all (Ongoing)
                statusText = '⚠️ Ongoing';
                statusClass = 'ongoing';
            }
            
            // Generate user summary list using the correct total count
            const userSummaries = Object.entries(dayData.users)
                .map(([user, count]) => `<li>${user}: ${count} / ${totalItemsCount} checked</li>`)
                .join('');
            

            content += `
                <div class="summary-details">
                    <p class="status ${statusClass}">${statusText}</p>
                    <ul class="user-list">${userSummaries}</ul>
                </div>
            `;
        }

        // Add today class
        if (dateStr === actualToday) {
            dayClass += ' today';
        }

        // Use the determined elementTag and attributes
        calendarGrid.innerHTML += `<${elementTag} ${linkAttribute} class="${dayClass}">${content}</${elementTag}>`;
    }
}

// --- Main Control Flow ---

async function initCalendar() {
    renderHeader();
    await loadCalendarForMonth(currentViewDate);
}

async function loadCalendarForMonth(date) {
    try {
        await fetchMasterData(); // Ensure master data is loaded once
    } catch (error) {
        return; // Stop execution if master data failed
    }
    
    // Now fetch the summary data
    const summaryData = await fetchSummaryData(date);
    
    // Pass summaryData, masterItems, and lastCompletions to renderCalendar
    renderCalendar(summaryData, masterItems, lastCompletions);
}

// Event handlers for navigation
prevButton.addEventListener('click', async () => {
    currentViewDate.setMonth(currentViewDate.getMonth() - 1);
    await loadCalendarForMonth(currentViewDate);
});

nextButton.addEventListener('click', async () => {
    currentViewDate.setMonth(currentViewDate.getMonth() + 1);
    await loadCalendarForMonth(currentViewDate);
});

document.addEventListener('DOMContentLoaded', () => {
    const returnBtn = document.getElementById('return-btn');
    if (returnBtn) {
        returnBtn.addEventListener('click', () => {
            // Redirect the user to the index page
            window.location.href = 'index.html';
        });
    }
});

// Run initialization
initCalendar();