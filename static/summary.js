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
let totalMasterItems = 0; // NEW: Global variable to store total item count

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

// --- Fetching Data ---
async function fetchSummaryData(date) {
    const { startDate, endDate } = getStartAndEndDate(date);
    
    try {
        const response = await fetch(`${API_BASE}/summary/calendar?start_date=${startDate}&end_date=${endDate}`);
        
        if (!response.ok) {
             throw new Error(`API error: ${response.statusText}`);
        }
        
        const data = await response.json();
        // Returns {summaryData: {...}, totalMasterItems: N}
        return data; 
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
 * @param {number} totalItemsCount - The total number of master checklist items.
 */
function renderCalendar(summaryData, totalItemsCount) { // UPDATED SIGNATURE
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

    // 4. Render days
    for (let day = 1; day <= lastDayOfMonth; day++) {
        const date = new Date(year, month, day);
        const dateStr = formatDate(date);
        const dayData = summaryData[dateStr];
        
        let content = `<div class="day-number">${day}</div>`;
        let dayClass = 'calendar-day';
        let elementTag = 'div'; // Default for empty days

        if (dayData || dateStr >= getTodayDate()) {
            // Only make current/future/data-filled days links
            elementTag = 'a';
            dayClass += ' clickable';
        }
        
        if (dayData) {
            dayClass += ' has-data';
            
            // ... (rest of existing logic for summary-details remains here) ...
            // The userSummaries and content concatenation should remain unchanged
            const userSummaries = Object.entries(dayData.users)
                .map(([user, count]) => `<li>${user}: ${count} / ${totalItemsCount} checked</li>`)
                .join('');
                
            if (dayData.submitted) {
                dayClass += ' submitted';
            }

            content += `
                <div class="summary-details">
                    <p class="status">${dayData.submitted ? '✅ Submitted' : '❌ Incomplete'}</p>
                    <ul class="user-list">${userSummaries}</ul>
                </div>
            `;
        }

        const linkAttribute = (elementTag === 'a') ? `href="index.html?date=${dateStr}"` : '';

        calendarGrid.innerHTML += `<${elementTag} ${linkAttribute} class="${dayClass}">${content}</${elementTag}>`;
    }
}

// --- Main Control Flow ---

async function initCalendar() {
    renderHeader();
    await loadCalendarForMonth(currentViewDate);
}

async function loadCalendarForMonth(date) {
    const responseData = await fetchSummaryData(date);
    // NEW: Extract data from the response structure
    const summaryData = responseData.summaryData || {};
    totalMasterItems = responseData.totalMasterItems || 0; // Update global state
    
    renderCalendar(summaryData, totalMasterItems); // UPDATED CALL
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