"""
Flask backend for Clinect - Clinical Trial Patient Matching Platform
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
import requests
from datetime import timedelta, datetime
import os
from dotenv import load_dotenv
import models
import trial_cache
import firebase_admin
from firebase_admin import credentials, auth
import graph_models
from google import genai
from google.genai import types
from functools import wraps
from time import time

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

# Initialize Gemini API Client
gemini_api_key = os.environ.get('GEMINI_API_KEY')
if gemini_api_key:
    genai_client = genai.Client(api_key=gemini_api_key)
    print(f"✅ Gemini API initialized with model: {os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')}")
else:
    genai_client = None
    print("⚠️  Warning: GEMINI_API_KEY not found in environment variables")
    print("   Chat endpoint will not work without a valid API key.")

# ============================================================================
# Chat & LLM Configuration
# ============================================================================

# Rate limiting storage (in-memory, use Redis in production)
chat_rate_limits = {}

# System prompt for the chat assistant
SYSTEM_PROMPT = """You are a compassionate clinical trial matching assistant helping patients find relevant medical studies.

Your job:
1. Greet users warmly and ask about their medical conditions
2. Gather: conditions, location, age, gender (ask ONE at a time)
3. When you have enough information (at least conditions), use the smart_match_trials function
4. Explain results in plain English, highlighting match scores and why trials are relevant
5. Answer follow-up questions about specific trials

Guidelines:
- Be empathetic and supportive
- Use medical terminology accurately but explain complex terms
- Ask ONE question at a time (don't overwhelm users)
- Match scores: +10 per condition match, +5 for location proximity
- If user mentions symptoms, ask clarifying questions to identify conditions

Example conversation flow:
User: "I have diabetes"
You: "I understand you're looking for trials related to diabetes. To find the best matches, may I ask your location? This helps me find trials near you."
User: "Boston"
You: "Thank you! One more quick question - what's your age? Some trials have age requirements."
User: "45"
You: [Call smart_match_trials with conditions=["diabetes"], location="Boston", age=45]
You: "Great! I found 8 clinical trials for diabetes in the Boston area. Here are the top matches..."

Important reminders:
- Never provide medical advice
- Always encourage users to consult their doctor
- Clarify that you're helping find trials, not recommending treatment
- If unsure about a medical term, ask for clarification
"""

def smart_match_trials_tool(conditions: list[str], location: str | None = None, age: int | None = None, gender: str | None = None, maxDistance: int = 50) -> dict:
    """Search for clinical trials using graph-based matching.

    Call this when you have gathered enough information from the user (at minimum: conditions).
    Returns trials with match scores.

    Args:
        conditions: Medical conditions to match (e.g., ['diabetes', 'hypertension'])
        location: User's location (city, state, or country)
        age: User's age in years
        gender: User's gender (MALE, FEMALE, or ALL)
        maxDistance: Maximum distance in miles (default: 50)

    Returns:
        Dictionary with matches, totalMatches, and method fields
    """
    return call_smart_match_internal({
        'conditions': conditions,
        'location': location,
        'age': age,
        'gender': gender,
        'maxDistance': maxDistance
    })

def rate_limit_chat(max_requests=10, window_seconds=60):
    """Limit chat requests per user to prevent abuse"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id', 'anonymous')
            current_time = time()

            if user_id not in chat_rate_limits:
                chat_rate_limits[user_id] = []

            # Remove old timestamps outside the window
            chat_rate_limits[user_id] = [
                t for t in chat_rate_limits[user_id]
                if current_time - t < window_seconds
            ]

            if len(chat_rate_limits[user_id]) >= max_requests:
                return jsonify({
                    'success': False,
                    'error': 'Rate limit exceeded. Please wait a moment.',
                    'assistantMessage': 'I need to take a quick break. Please try again in a minute.'
                }), 429

            chat_rate_limits[user_id].append(current_time)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def call_smart_match_internal(criteria):
    """
    Internal wrapper for smart match logic
    Reuses existing Neo4j graph matching code
    """
    # Parse conditions (may be list or comma-separated string)
    conditions = criteria.get('conditions', [])
    if isinstance(conditions, str):
        conditions = [c.strip() for c in conditions.split(',')]

    location = criteria.get('location')
    age = criteria.get('age')
    gender = criteria.get('gender')
    max_distance = criteria.get('maxDistance', 50)

    # Step 1: Try Neo4j graph matching
    results = graph_models.find_matching_trials(
        conditions=conditions,
        location_id=location,
        status='RECRUITING',
        max_distance_km=max_distance,
        limit=20
    )

    # Step 2: If Neo4j found results, return them
    if len(results) > 0:
        return {
            'success': True,
            'matches': results,
            'totalMatches': len(results),
            'method': 'graph'
        }

    # Step 3: FALLBACK - Search ClinicalTrials.gov API
    print(f"No graph results for {conditions}, falling back to ClinicalTrials.gov API...")

    # Build API query
    query_parts = []
    if conditions:
        condition_query = ' OR '.join(conditions)
        query_parts.append(f"AREA[ConditionSearch]{condition_query}")
    if location:
        query_parts.append(f"AREA[LocationSearch]{location}")

    params = {
        'format': 'json',
        'pageSize': 20,
        'filter.overallStatus': 'RECRUITING'
    }

    if query_parts:
        params['query.term'] = ' AND '.join(query_parts)

    try:
        response = requests.get(
            f"{CLINICAL_TRIALS_API_BASE}/studies",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        api_data = response.json()

        # Cache results (auto-syncs to Neo4j)
        if 'studies' in api_data:
            for study in api_data['studies']:
                try:
                    trial_cache.cache_trial(study)
                except Exception as cache_error:
                    print(f"Failed to cache trial: {cache_error}")

        # Format API results
        formatted_matches = []
        for study in api_data.get('studies', []):
            try:
                protocol = study.get('protocolSection')
                if not protocol:
                    continue

                identification = protocol.get('identificationModule', {})
                nct_id = identification.get('nctId')
                if not nct_id:
                    continue

                status_module = protocol.get('statusModule', {})
                design_module = protocol.get('designModule', {})

                formatted_matches.append({
                    'nctId': nct_id,
                    'title': identification.get('briefTitle', 'Unknown Title'),
                    'status': status_module.get('overallStatus', 'Unknown'),
                    'phase': design_module.get('phases', []),
                    'matchScore': 0
                })
            except Exception:
                continue

        return {
            'success': True,
            'matches': formatted_matches,
            'totalMatches': len(formatted_matches),
            'method': 'api_fallback'
        }

    except Exception as e:
        print(f"API fallback error: {e}")
        return {
            'success': False,
            'matches': [],
            'totalMatches': 0,
            'error': str(e)
        }

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
            params['filter.overallStatus'] = status

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
# Graph-Based Trial Matching Endpoints (Neo4j)
# ============================================================================

@app.route('/api/trials/smart-match', methods=['POST'])
def smart_match_trials():
    """
    Intelligent trial matching using Neo4j graph database
    Falls back to ClinicalTrials.gov API if no graph results found

    POST body:
    {
      "conditions": ["diabetes", "heart disease"],
      "location": "Boston, MA",
      "age": 45,
      "gender": "FEMALE",
      "maxDistance": 50  // kilometers, optional
    }
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        data = request.json
        conditions = data.get('conditions', [])
        location = data.get('location')
        age = data.get('age')
        gender = data.get('gender')
        max_distance = data.get('maxDistance')

        # Step 1: Try Neo4j graph matching
        results = graph_models.find_matching_trials(
            conditions=conditions,
            location_id=location,
            status='RECRUITING',
            max_distance_km=max_distance,
            limit=20
        )

        # Step 2: If Neo4j found results, return them
        if len(results) > 0:
            return jsonify({
                'success': True,
                'matches': results,
                'totalMatches': len(results),
                'method': 'graph'
            })

        # Step 3: FALLBACK - Search ClinicalTrials.gov API
        print(f"No graph results for {conditions}, falling back to ClinicalTrials.gov API...")

        # Build API query
        query_parts = []
        if conditions:
            # Join conditions with OR for broader search
            condition_query = ' OR '.join(conditions)
            query_parts.append(f"AREA[ConditionSearch]{condition_query}")
        if location:
            query_parts.append(f"AREA[LocationSearch]{location}")

        params = {
            'format': 'json',
            'pageSize': 20,
            'filter.overallStatus': 'RECRUITING'
        }

        if query_parts:
            params['query.term'] = ' AND '.join(query_parts)

        # Call ClinicalTrials.gov API
        response = requests.get(
            f"{CLINICAL_TRIALS_API_BASE}/studies",
            params=params,
            timeout=10
        )

        # Check for HTTP errors
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error calling ClinicalTrials.gov API: {http_err}")
            print(f"Status code: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            raise

        # Parse JSON response
        try:
            api_data = response.json()
        except ValueError as json_err:
            print(f"Failed to parse JSON from API: {json_err}")
            print(f"Response text: {response.text[:500]}")
            raise

        # Cache and auto-sync results to MongoDB + Neo4j
        # If caching fails, still return results to user
        cached_count = 0
        if 'studies' in api_data:
            for study in api_data['studies']:
                try:
                    trial_cache.cache_trial(study)  # Also syncs to Neo4j automatically
                    cached_count += 1
                except Exception as cache_error:
                    import traceback
                    print(f"Failed to cache trial (non-critical): {cache_error}")
                    print(f"Full traceback: {traceback.format_exc()}")
                    # Continue processing other trials

            print(f"Cached {cached_count}/{len(api_data.get('studies', []))} trials")

        # Format API results to match graph response
        formatted_matches = []
        for study in api_data.get('studies', []):
            try:
                protocol = study.get('protocolSection')
                if not protocol:
                    print(f"Skipping study with no protocolSection")
                    continue

                identification = protocol.get('identificationModule', {})
                nct_id = identification.get('nctId')
                if not nct_id:
                    print(f"Skipping study with no NCT ID")
                    continue

                status_module = protocol.get('statusModule', {})
                design_module = protocol.get('designModule', {})

                formatted_matches.append({
                    'nctId': nct_id,
                    'title': identification.get('briefTitle', 'Unknown Title'),
                    'status': status_module.get('overallStatus', 'Unknown'),
                    'phase': design_module.get('phases', []),
                    'matchScore': 0  # No graph score for API fallback results
                })
            except Exception as format_err:
                print(f"Error formatting study: {format_err}")
                continue

        return jsonify({
            'success': True,
            'matches': formatted_matches,
            'totalMatches': len(formatted_matches),
            'method': 'api_fallback',      # Indicates fallback was used
            'cached_to_graph': True        # These trials are now in Neo4j for next time
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"=== SMART-MATCH ERROR ===")
        print(f"Error: {e}")
        print(f"Type: {type(e).__name__}")
        print(error_details)
        print(f"=== END ERROR ===")
        return jsonify({
            'error': str(e),
            'type': type(e).__name__,
            'details': error_details if app.debug else None
        }), 500

@app.route('/api/chat', methods=['POST'])
@rate_limit_chat(max_requests=10, window_seconds=60)
def chat():
    """
    LLM-powered conversational chat endpoint
    Processes natural language and calls smart matching when ready

    POST body:
    {
      "message": "I have diabetes",
      "conversationHistory": [
        {"role": "assistant", "content": "...", "timestamp": "..."},
        {"role": "user", "content": "...", "timestamp": "..."}
      ]
    }
    """
    if not genai_client:
        return jsonify({
            'success': False,
            'error': 'Gemini API not configured',
            'assistantMessage': 'Sorry, the chat service is unavailable.'
        }), 503

    data = request.json
    user_message = data.get('message', '')
    conversation_history = data.get('conversationHistory', [])

    if not user_message:
        return jsonify({'success': False, 'error': 'Message required'}), 400

    try:
        # Build contents array for multi-turn conversation
        contents = []

        # Add conversation history (last 10 messages for cost optimization)
        for msg in conversation_history[-10:]:
            role = "user" if msg['role'] == 'user' else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg['content']}]
            })

        # Add current user message
        contents.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })

        # Configure with function calling
        config = types.GenerateContentConfig(
            tools=[smart_match_trials_tool],
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7
        )

        # Generate response
        response = genai_client.models.generate_content(
            model=os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash'),
            contents=contents,
            config=config
        )

        assistant_message = ""
        trials = None
        extracted_criteria = None

        # Check if model called the function
        if response.function_calls:
            function_call = response.function_calls[0]

            # Extract criteria
            extracted_criteria = {
                'conditions': list(function_call.args.get('conditions', [])),
                'location': function_call.args.get('location'),
                'age': function_call.args.get('age'),
                'gender': function_call.args.get('gender'),
                'maxDistance': function_call.args.get('maxDistance', 50)
            }

            # Execute the function
            match_result = smart_match_trials_tool(**function_call.args)
            trials = match_result.get('matches', [])

            # Send function result back to model for explanation
            contents.append(response.candidates[0].content)
            contents.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": function_call.name,
                        "response": match_result
                    }
                }]
            })

            # Get model's explanation
            followup_response = genai_client.models.generate_content(
                model=os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash'),
                contents=contents,
                config=config
            )
            assistant_message = followup_response.text
        else:
            # No function call - just return the text response
            assistant_message = response.text

        return jsonify({
            'success': True,
            'assistantMessage': assistant_message,
            'trials': trials,
            'extractedCriteria': extracted_criteria,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        print(f"Chat error: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': 'Failed to process chat message',
            'assistantMessage': "I'm sorry, I encountered an error. Could you try rephrasing your message?"
        }), 500

@app.route('/api/trials/<nct_id>/related', methods=['GET'])
def get_related_trials(nct_id):
    """
    Get trials related to a specific trial via graph relationships
    Returns trials with shared conditions, locations, or other connections
    """
    try:
        limit = int(request.args.get('limit', 10))

        # Use Neo4j to find related trials
        results = graph_models.find_related_trials(nct_id, limit=limit)

        return jsonify({
            'success': True,
            'nctId': nct_id,
            'relatedTrials': results,
            'totalFound': len(results)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """
    Get personalized trial recommendations for the current user
    Based on their medical history and graph relationships
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        user_id = session['user_id']
        limit = int(request.args.get('limit', 10))

        # Use Neo4j to get personalized recommendations
        results = graph_models.get_patient_recommendations(user_id, limit=limit)

        return jsonify({
            'success': True,
            'recommendations': results,
            'totalFound': len(results)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conditions/hierarchy', methods=['GET'])
def get_condition_hierarchy():
    """
    Get the hierarchical relationships for a condition
    Returns parent and child conditions in the medical ontology
    """
    try:
        condition = request.args.get('condition')

        if not condition:
            return jsonify({'error': 'condition parameter required'}), 400

        # Get condition hierarchy from Neo4j
        hierarchy = graph_models.get_condition_hierarchy(condition)

        return jsonify({
            'success': True,
            'hierarchy': hierarchy
        })

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
