"""
Flask backend for Clinect - Clinical Trial Patient Matching Platform
"""

from flask import Flask, request, jsonify, render_template, session
import requests
from datetime import timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ClinicalTrials.gov API Configuration
CLINICAL_TRIALS_API_BASE = "https://clinicaltrials.gov/api/v2"

# ============================================================================
# Authentication Endpoints (Dummy Auth)
# ============================================================================

@app.route('/api/login', methods=['POST'])
def login():
    """Dummy login - accepts any username/password"""
    data = request.json
    username = data.get('username')

    if username:
        session['user'] = username
        session.permanent = True
        return jsonify({'success': True, 'username': username})

    return jsonify({'success': False, 'error': 'Username required'}), 400

@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout user"""
    session.pop('user', None)
    return jsonify({'success': True})

@app.route('/api/current-user', methods=['GET'])
def current_user():
    """Get current logged-in user"""
    user = session.get('user')
    if user:
        return jsonify({'logged_in': True, 'username': user})
    return jsonify({'logged_in': False})

# ============================================================================
# Medical History Endpoints
# ============================================================================

@app.route('/api/medical-history', methods=['POST'])
def save_medical_history():
    """Save user's medical history"""
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    # TODO: Save to PostgreSQL
    # For now, store in session
    session['medical_history'] = data

    return jsonify({'success': True, 'data': data})

@app.route('/api/medical-history', methods=['GET'])
def get_medical_history():
    """Get user's medical history"""
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    history = session.get('medical_history', {})
    return jsonify(history)

# ============================================================================
# Clinical Trials Search Endpoints
# ============================================================================

@app.route('/api/trials/search', methods=['GET'])
def search_trials():
    """
    Search clinical trials via ClinicalTrials.gov API
    Query params:
    - condition: disease/condition
    - location: geographic location
    - age: patient age
    - gender: patient gender
    - status: recruitment status
    - pageSize: results per page (default 10)
    - pageToken: pagination token
    """
    try:
        # Build query parameters
        params = {
            'format': 'json',
            'pageSize': request.args.get('pageSize', 10)
        }

        # Build query string
        query_parts = []

        if request.args.get('condition'):
            query_parts.append(f"AREA[ConditionSearch]{request.args.get('condition')}")

        if request.args.get('location'):
            query_parts.append(f"AREA[LocationSearch]{request.args.get('location')}")

        if request.args.get('status'):
            query_parts.append(f"AREA[RecruitmentStatus]{request.args.get('status')}")

        if query_parts:
            params['query.term'] = ' AND '.join(query_parts)

        if request.args.get('pageToken'):
            params['pageToken'] = request.args.get('pageToken')

        # Call ClinicalTrials.gov API
        response = requests.get(
            f"{CLINICAL_TRIALS_API_BASE}/studies",
            params=params,
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        return jsonify(data)

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'API request failed: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/trials/<nct_id>', methods=['GET'])
def get_trial_details(nct_id):
    """Get detailed information about a specific trial"""
    try:
        response = requests.get(
            f"{CLINICAL_TRIALS_API_BASE}/studies/{nct_id}",
            params={'format': 'json'},
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        return jsonify(data)

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'API request failed: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# Saved Trials Endpoints
# ============================================================================

@app.route('/api/saved-trials', methods=['GET'])
def get_saved_trials():
    """Get user's saved trials"""
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    # TODO: Fetch from PostgreSQL
    saved_trials = session.get('saved_trials', [])
    return jsonify(saved_trials)

@app.route('/api/saved-trials', methods=['POST'])
def save_trial():
    """Save a trial to user's list"""
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    nct_id = data.get('nctId')
    trial_data = data.get('trialData', {})

    if not nct_id:
        return jsonify({'error': 'Trial ID required'}), 400

    # TODO: Save to PostgreSQL
    saved_trials = session.get('saved_trials', [])

    # Check if already saved
    if any(trial.get('nctId') == nct_id for trial in saved_trials):
        return jsonify({'success': True, 'message': 'Trial already saved'})

    saved_trials.append({
        'nctId': nct_id,
        'trialData': trial_data,
        'savedAt': None  # TODO: Add timestamp
    })

    session['saved_trials'] = saved_trials

    return jsonify({'success': True, 'message': 'Trial saved'})

@app.route('/api/saved-trials/<nct_id>', methods=['DELETE'])
def unsave_trial(nct_id):
    """Remove a trial from user's saved list"""
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    # TODO: Delete from PostgreSQL
    saved_trials = session.get('saved_trials', [])
    saved_trials = [trial for trial in saved_trials if trial.get('nctId') != nct_id]
    session['saved_trials'] = saved_trials

    return jsonify({'success': True, 'message': 'Trial removed'})

# ============================================================================
# Frontend Routes
# ============================================================================

@app.route('/')
def index():
    """Serve main application page"""
    return render_template('index.html')

# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
