"""
Flask backend for Clinect - Clinical Trial Patient Matching Platform
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
import requests
from datetime import timedelta
import os
from dotenv import load_dotenv
import models
import trial_cache
import firebase_admin
from firebase_admin import credentials, auth

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Enable CORS for frontend
CORS(app, origins=['http://localhost:3000', 'https://clinect-fe.vercel.app'], supports_credentials=True)

# Initialize Firebase Admin SDK
firebase_service_account_path = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH', 'firebase-service-account.json')
if os.path.exists(firebase_service_account_path):
    cred = credentials.Certificate(firebase_service_account_path)
    firebase_admin.initialize_app(cred)
    print(f"✅ Firebase Admin SDK initialized with {firebase_service_account_path}")
else:
    print(f"⚠️  Warning: Firebase service account file not found at {firebase_service_account_path}")
    print("   Firebase authentication will not work until you add the service account file.")

# ClinicalTrials.gov API Configuration
CLINICAL_TRIALS_API_BASE = "https://clinicaltrials.gov/api/v2"

# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.route('/api/firebase-login', methods=['POST'])
def firebase_login():
    """
    Verify Firebase ID token and create session
    Frontend sends Firebase ID token after user authenticates
    """
    data = request.json
    id_token = data.get('idToken')

    if not id_token:
        return jsonify({'success': False, 'error': 'ID token required'}), 400

    try:
        # Verify the Firebase ID token
        decoded_token = auth.verify_id_token(id_token)
        firebase_uid = decoded_token['uid']
        email = decoded_token.get('email')  # May be None for anonymous users

        # Get or create user in your database using Firebase UID
        user = models.get_or_create_user_by_firebase_uid(
            firebase_uid=firebase_uid,
            email=email
        )

        # Create session (your existing session logic)
        session['user'] = email or f'anonymous_{firebase_uid[:8]}'
        session['user_id'] = user['id']
        session['firebase_uid'] = firebase_uid
        session.permanent = True

        return jsonify({
            'success': True,
            'email': email,
            'firebase_uid': firebase_uid
        })

    except auth.InvalidIdTokenError:
        return jsonify({'success': False, 'error': 'Invalid ID token'}), 401
    except auth.ExpiredIdTokenError:
        return jsonify({'success': False, 'error': 'Expired ID token'}), 401
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """Legacy login - accepts any username/password (for backwards compatibility)"""
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
    session.pop('firebase_uid', None)
    return jsonify({'success': True})

@app.route('/api/current-user', methods=['GET'])
def current_user():
    """Get current logged-in user"""
    user = session.get('user')
    firebase_uid = session.get('firebase_uid')

    if user:
        return jsonify({
            'logged_in': True,
            'username': user,  # For backwards compatibility
            'email': user if '@' in str(user) else None,
            'firebase_uid': firebase_uid
        })
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
# Main
# ============================================================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
