"""
Flask backend for Clinect - Clinical Trial Patient Matching Platform
"""

from flask import Flask, request, jsonify, render_template, session
import requests
from datetime import timedelta
import os
from dotenv import load_dotenv
import models
import trial_cache

# Load environment variables
load_dotenv()

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
        # Get or create user in database
        user = models.get_or_create_user(username)
        session['user'] = username
        session['user_id'] = user['id']
        session.permanent = True
        return jsonify({'success': True, 'username': username})

    return jsonify({'success': False, 'error': 'Username required'}), 400

@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout user"""
    session.pop('user', None)
    session.pop('user_id', None)
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
def save_medical_history_endpoint():
    """Save user's medical history"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    user_id = session['user_id']

    try:
        history = models.save_medical_history(
            user_id=user_id,
            age=data.get('age'),
            gender=data.get('gender'),
            location=data.get('location'),
            conditions=data.get('conditions'),
            medications=data.get('medications')
        )
        return jsonify({'success': True, 'data': history})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/medical-history', methods=['GET'])
def get_medical_history_endpoint():
    """Get user's medical history"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']

    try:
        history = models.get_medical_history(user_id)
        if history:
            return jsonify(history)
        return jsonify({})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# Clinical Trials Search Endpoints
# ============================================================================

@app.route('/api/trials/search', methods=['GET'])
def search_trials():
    """
    Search clinical trials via ClinicalTrials.gov API with MongoDB caching
    Query params:
    - condition: disease/condition
    - location: geographic location
    - age: patient age
    - gender: patient gender
    - status: recruitment status
    - pageSize: results per page (default 10)
    - pageToken: pagination token
    - use_cache: whether to use cache (default true)
    """
    try:
        condition = request.args.get('condition')
        location = request.args.get('location')
        status = request.args.get('status')
        use_cache = request.args.get('use_cache', 'true').lower() == 'true'

        # Try to get from cache first (if not paginating)
        if use_cache and not request.args.get('pageToken'):
            try:
                cached_results = trial_cache.search_cached_trials(
                    condition=condition,
                    location=location,
                    status=status,
                    limit=int(request.args.get('pageSize', 20))
                )

                if cached_results:
                    # Format cached results to match API response
                    formatted_studies = []
                    for cached_trial in cached_results:
                        formatted_studies.append({
                            'protocolSection': cached_trial.get('protocolSection', {})
                        })

                    return jsonify({
                        'studies': formatted_studies,
                        'totalCount': len(formatted_studies),
                        'cached': True
                    })
            except Exception as cache_error:
                print(f"Cache lookup failed: {cache_error}, falling back to API")

        # Build query parameters for API
        params = {
            'format': 'json',
            'pageSize': request.args.get('pageSize', 10)
        }

        # Build query string
        query_parts = []

        if condition:
            query_parts.append(f"AREA[ConditionSearch]{condition}")

        if location:
            query_parts.append(f"AREA[LocationSearch]{location}")

        if status:
            query_parts.append(f"AREA[RecruitmentStatus]{status}")

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

        # Cache the results in MongoDB
        if use_cache and 'studies' in data:
            for study in data['studies']:
                try:
                    trial_cache.cache_trial(study)
                except Exception as cache_error:
                    print(f"Failed to cache trial: {cache_error}")

        data['cached'] = False
        return jsonify(data)

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'API request failed: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/trials/<nct_id>', methods=['GET'])
def get_trial_details(nct_id):
    """Get detailed information about a specific trial with MongoDB caching"""
    try:
        # Check cache first
        cached_trial = trial_cache.get_cached_trial(nct_id)

        if cached_trial:
            return jsonify({
                'protocolSection': cached_trial.get('protocolSection', {}),
                'cached': True
            })

        # Not in cache, fetch from API
        response = requests.get(
            f"{CLINICAL_TRIALS_API_BASE}/studies/{nct_id}",
            params={'format': 'json'},
            timeout=10
        )
        response.raise_for_status()

        data = response.json()

        # Cache the trial
        if 'protocolSection' in data:
            try:
                trial_cache.cache_trial(data)
            except Exception as cache_error:
                print(f"Failed to cache trial {nct_id}: {cache_error}")

        data['cached'] = False
        return jsonify(data)

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'API request failed: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# Saved Trials Endpoints
# ============================================================================

@app.route('/api/saved-trials', methods=['GET'])
def get_saved_trials_endpoint():
    """Get user's saved trials"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']

    try:
        trials = models.get_saved_trials(user_id)
        # Format for frontend compatibility
        formatted_trials = [{
            'nctId': trial['nct_id'],
            'trialData': {
                'title': trial['trial_title'],
                'status': trial['trial_status'],
                'summary': trial['trial_summary']
            },
            'savedAt': trial['saved_at'].isoformat() if trial['saved_at'] else None
        } for trial in trials]
        return jsonify(formatted_trials)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/saved-trials', methods=['POST'])
def save_trial_endpoint():
    """Save a trial to user's list"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    nct_id = data.get('nctId')
    trial_data = data.get('trialData', {})

    if not nct_id:
        return jsonify({'error': 'Trial ID required'}), 400

    user_id = session['user_id']

    try:
        # Check if already saved
        if models.is_trial_saved(user_id, nct_id):
            return jsonify({'success': True, 'message': 'Trial already saved'})

        # Save to database
        models.save_trial(
            user_id=user_id,
            nct_id=nct_id,
            trial_title=trial_data.get('title'),
            trial_status=trial_data.get('status'),
            trial_summary=trial_data.get('summary')
        )

        return jsonify({'success': True, 'message': 'Trial saved'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/saved-trials/<nct_id>', methods=['DELETE'])
def unsave_trial_endpoint(nct_id):
    """Remove a trial from user's saved list"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user_id']

    try:
        success = models.delete_saved_trial(user_id, nct_id)
        if success:
            return jsonify({'success': True, 'message': 'Trial removed'})
        return jsonify({'error': 'Trial not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
