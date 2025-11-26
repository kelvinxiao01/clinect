// Global state
let currentUser = null;
let medicalHistory = null;

// Initialize app
document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
});

// ============================================================================
// Authentication
// ============================================================================

async function checkAuth() {
    try {
        const response = await fetch('/api/current-user');
        const data = await response.json();

        if (data.logged_in) {
            currentUser = data.username;
            showMainApp();
        } else {
            showLogin();
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        showLogin();
    }
}

async function login() {
    const username = document.getElementById('username').value.trim();

    if (!username) {
        alert('Please enter a username');
        return;
    }

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username })
        });

        const data = await response.json();

        if (data.success) {
            currentUser = data.username;
            showMainApp();
        } else {
            alert('Login failed: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Login error:', error);
        alert('Login failed');
    }
}

async function logout() {
    try {
        await fetch('/api/logout', { method: 'POST' });
        currentUser = null;
        medicalHistory = null;
        showLogin();
    } catch (error) {
        console.error('Logout error:', error);
    }
}

function showLogin() {
    document.getElementById('login-section').classList.remove('hidden');
    document.getElementById('main-section').classList.add('hidden');
}

function showMainApp() {
    document.getElementById('login-section').classList.add('hidden');
    document.getElementById('main-section').classList.remove('hidden');
    document.getElementById('current-user').textContent = currentUser;
    loadMedicalHistory();
}

// ============================================================================
// Tab Navigation
// ============================================================================

function showTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });

    document.getElementById(`${tabName}-tab`).classList.add('active');

    // Load data for specific tabs
    if (tabName === 'saved') {
        loadSavedTrials();
    }
}

// ============================================================================
// Medical History
// ============================================================================

async function loadMedicalHistory() {
    try {
        const response = await fetch('/api/medical-history');
        const data = await response.json();

        if (data && Object.keys(data).length > 0) {
            medicalHistory = data;

            // Populate form
            document.getElementById('age').value = data.age || '';
            document.getElementById('gender').value = data.gender || '';
            document.getElementById('location').value = data.location || '';
            document.getElementById('conditions').value = data.conditions || '';
            document.getElementById('medications').value = data.medications || '';
        }
    } catch (error) {
        console.error('Failed to load medical history:', error);
    }
}

async function saveMedicalHistory(event) {
    event.preventDefault();

    const data = {
        age: document.getElementById('age').value,
        gender: document.getElementById('gender').value,
        location: document.getElementById('location').value,
        conditions: document.getElementById('conditions').value,
        medications: document.getElementById('medications').value
    };

    try {
        const response = await fetch('/api/medical-history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            medicalHistory = data;
            showMessage('history-message', 'Medical history saved successfully', 'success');
        } else {
            showMessage('history-message', 'Failed to save medical history', 'error');
        }
    } catch (error) {
        console.error('Save medical history error:', error);
        showMessage('history-message', 'Failed to save medical history', 'error');
    }
}

function useMyHistory() {
    if (!medicalHistory) {
        alert('Please fill out your medical history first');
        showTab('history');
        return;
    }

    // Pre-fill search form with medical history
    const conditions = medicalHistory.conditions?.split('\n')[0] || '';
    document.getElementById('search-condition').value = conditions;
    document.getElementById('search-location').value = medicalHistory.location || '';
}

// ============================================================================
// Search Trials
// ============================================================================

async function searchTrials(event) {
    event.preventDefault();

    const condition = document.getElementById('search-condition').value.trim();
    const location = document.getElementById('search-location').value.trim();
    const status = document.getElementById('search-status').value;

    if (!condition && !location) {
        alert('Please enter at least a condition or location');
        return;
    }

    // Show loading
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('results-container').innerHTML = '';

    try {
        const params = new URLSearchParams();
        if (condition) params.append('condition', condition);
        if (location) params.append('location', location);
        if (status) params.append('status', status);
        params.append('pageSize', '20');

        const response = await fetch(`/api/trials/search?${params}`);
        const data = await response.json();

        document.getElementById('loading').classList.add('hidden');

        if (data.error) {
            document.getElementById('results-container').innerHTML =
                `<div class="empty-state">Error: ${data.error}</div>`;
            return;
        }

        displayTrials(data.studies || []);
    } catch (error) {
        console.error('Search error:', error);
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('results-container').innerHTML =
            '<div class="empty-state">Search failed. Please try again.</div>';
    }
}

function displayTrials(studies) {
    const container = document.getElementById('results-container');

    if (!studies || studies.length === 0) {
        container.innerHTML = '<div class="empty-state">No trials found</div>';
        return;
    }

    container.innerHTML = studies.map(study => {
        const protocol = study.protocolSection || {};
        const identification = protocol.identificationModule || {};
        const status = protocol.statusModule || {};
        const description = protocol.descriptionModule || {};

        const nctId = identification.nctId || 'N/A';
        const title = identification.briefTitle || identification.officialTitle || 'No title';
        const recruitmentStatus = status.overallStatus || 'Unknown';
        const briefSummary = description.briefSummary || 'No summary available';

        return `
            <div class="trial-card" data-nct-id="${nctId}">
                <h3>${title}</h3>
                <div class="trial-id">ID: ${nctId}</div>
                <div class="trial-status">${recruitmentStatus}</div>
                <div class="trial-details">
                    ${briefSummary.substring(0, 300)}${briefSummary.length > 300 ? '...' : ''}
                </div>
                <div class="trial-actions">
                    <button class="btn-save" onclick="saveTrial('${nctId}', this)">Save Trial</button>
                    <button class="btn-details" onclick="viewTrialDetails('${nctId}')">View Details</button>
                </div>
            </div>
        `;
    }).join('');
}

async function viewTrialDetails(nctId) {
    try {
        const response = await fetch(`/api/trials/${nctId}`);
        const data = await response.json();

        if (data.error) {
            alert('Failed to load trial details');
            return;
        }

        // For MVP, just show in alert. Later can create modal.
        const protocol = data.protocolSection || {};
        const identification = protocol.identificationModule || {};
        const description = protocol.descriptionModule || {};
        const eligibility = protocol.eligibilityModule || {};

        let details = `Trial: ${identification.briefTitle}\n\n`;
        details += `ID: ${identification.nctId}\n\n`;
        details += `Summary: ${description.briefSummary || 'N/A'}\n\n`;
        details += `Eligibility: ${eligibility.eligibilityCriteria || 'N/A'}`;

        alert(details);
    } catch (error) {
        console.error('Failed to load trial details:', error);
        alert('Failed to load trial details');
    }
}

// ============================================================================
// Saved Trials
// ============================================================================

async function saveTrial(nctId, buttonElement) {
    try {
        const trialCard = buttonElement.closest('.trial-card');
        const title = trialCard.querySelector('h3').textContent;
        const status = trialCard.querySelector('.trial-status').textContent;
        const summary = trialCard.querySelector('.trial-details').textContent;

        const response = await fetch('/api/saved-trials', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nctId: nctId,
                trialData: { title, status, summary }
            })
        });

        const data = await response.json();

        if (data.success) {
            buttonElement.textContent = 'Saved!';
            buttonElement.disabled = true;
            setTimeout(() => {
                buttonElement.textContent = 'Save Trial';
                buttonElement.disabled = false;
            }, 2000);
        }
    } catch (error) {
        console.error('Save trial error:', error);
        alert('Failed to save trial');
    }
}

async function loadSavedTrials() {
    try {
        const response = await fetch('/api/saved-trials');
        const trials = await response.json();

        const container = document.getElementById('saved-trials-container');

        if (!trials || trials.length === 0) {
            container.innerHTML = '<div class="empty-state">No saved trials yet</div>';
            return;
        }

        container.innerHTML = trials.map(trial => {
            const { nctId, trialData } = trial;
            return `
                <div class="trial-card">
                    <h3>${trialData.title || 'No title'}</h3>
                    <div class="trial-id">ID: ${nctId}</div>
                    <div class="trial-status">${trialData.status || 'Unknown'}</div>
                    <div class="trial-details">${trialData.summary || 'No summary'}</div>
                    <div class="trial-actions">
                        <button class="btn-unsave" onclick="unsaveTrial('${nctId}')">Remove</button>
                        <button class="btn-details" onclick="viewTrialDetails('${nctId}')">View Details</button>
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Load saved trials error:', error);
    }
}

async function unsaveTrial(nctId) {
    if (!confirm('Remove this trial from your saved list?')) {
        return;
    }

    try {
        const response = await fetch(`/api/saved-trials/${nctId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            loadSavedTrials();
        }
    } catch (error) {
        console.error('Unsave trial error:', error);
        alert('Failed to remove trial');
    }
}

// ============================================================================
// Utilities
// ============================================================================

function showMessage(elementId, message, type) {
    const element = document.getElementById(elementId);
    element.textContent = message;
    element.className = `message ${type}`;
    element.style.display = 'block';

    setTimeout(() => {
        element.style.display = 'none';
    }, 3000);
}
