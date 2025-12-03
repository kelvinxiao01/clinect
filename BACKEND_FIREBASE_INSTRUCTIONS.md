# Backend Firebase Authentication Integration Instructions

## Overview

The frontend now uses Firebase Authentication. Users authenticate with Firebase (email/password, Google, or anonymously), and the frontend sends a Firebase ID token to your Flask backend for verification and session creation.

## What You Need to Do

### 1. Install Required Packages

```bash
uv add firebase-admin
```

### 2. Get Firebase Admin SDK Credentials

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project
3. Go to **Project Settings** (gear icon) → **Service Accounts**
4. Click **Generate New Private Key**
5. Save the JSON file securely (e.g., `firebase-service-account.json`)
6. **IMPORTANT**: Add this file to `.gitignore` - never commit it!

### 3. Initialize Firebase Admin SDK

Add this to your Flask app initialization (e.g., at the top of your main app file):

```python
import firebase_admin
from firebase_admin import credentials, auth
import os

# Initialize Firebase Admin SDK
cred = credentials.Certificate(os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH', 'firebase-service-account.json'))
firebase_admin.initialize_app(cred)
```

### 4. Create New `/api/firebase-login` Endpoint

Add this endpoint to handle Firebase authentication:

```python
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
```

### 5. Update User Model in `models.py`

Add a new function to handle Firebase UID-based user creation/retrieval:

```python
def get_or_create_user_by_firebase_uid(firebase_uid, email=None):
    """
    Get or create user by Firebase UID
    Firebase UID is the unique identifier from Firebase Auth
    """
    users = db['users']

    # Try to find existing user by Firebase UID
    user = users.find_one({'firebase_uid': firebase_uid})

    if user:
        return user

    # Create new user if not found
    new_user = {
        'firebase_uid': firebase_uid,
        'email': email,
        'created_at': datetime.utcnow()
    }

    result = users.insert_one(new_user)
    new_user['id'] = result.inserted_id

    return new_user
```

### 6. Update Existing User Lookups (Optional but Recommended)

If you want to support both Firebase UID and legacy username lookups during migration:

```python
def get_user_by_id(user_id):
    """Get user by database ID"""
    users = db['users']
    user = users.find_one({'_id': ObjectId(user_id)})
    return user

# Update any queries that look up users to support firebase_uid
```

### 7. Update `/api/current-user` Endpoint (Optional)

Enhance it to return Firebase UID if available:

```python
@app.route('/api/current-user', methods=['GET'])
def current_user():
    """Get current logged-in user"""
    user = session.get('user')
    firebase_uid = session.get('firebase_uid')

    if user:
        return jsonify({
            'logged_in': True,
            'username': user,  # For backwards compatibility
            'email': user if '@' in user else None,
            'firebase_uid': firebase_uid
        })
    return jsonify({'logged_in': False})
```

### 8. Environment Variables

Add to your `.env` file:

```bash
# Path to Firebase service account JSON file
FIREBASE_SERVICE_ACCOUNT_PATH=firebase-service-account.json
```

### 9. Database Migration (If Needed)

If you have existing users with usernames, you may want to:

1. Keep the existing `/api/login` endpoint for backwards compatibility
2. Add a `firebase_uid` field to existing user documents as they log in with Firebase
3. Eventually deprecate username-based auth

## Authentication Flow

Here's how the complete flow works:

1. **Frontend**: User logs in with Firebase (email/password, Google, or anonymous)
2. **Frontend**: Gets Firebase ID token via `auth.currentUser.getIdToken()`
3. **Frontend**: Sends token to `POST /api/firebase-login` with `{"idToken": "..."}`
4. **Backend**: Verifies token with Firebase Admin SDK
5. **Backend**: Extracts `uid` and `email` from verified token
6. **Backend**: Creates/fetches user from MongoDB using Firebase UID
7. **Backend**: Creates Flask session (same as before)
8. **Backend**: Returns success to frontend
9. **Frontend**: All subsequent requests use session cookies (no change)

## Testing

### Test with Email/Password:
1. Frontend: Sign up with email/password at `/signup`
2. Check backend logs for token verification
3. Check MongoDB for new user with `firebase_uid` field

### Test with Google:
1. Frontend: Click "Sign in with Google" at `/login`
2. Check backend creates user with email from Google account

### Test with Anonymous:
1. Frontend: Click "Continue as Guest" at `/login`
2. Check backend creates user with no email (anonymous)

## Security Notes

1. **Never commit** `firebase-service-account.json` to version control
2. **Always verify** the ID token on the backend - never trust client-side auth
3. **Use HTTPS** in production - tokens should never be sent over HTTP
4. **Token expiration**: Firebase ID tokens expire after 1 hour. Frontend automatically handles refresh.

## Troubleshooting

### "Invalid ID token" error:
- Check that Firebase Admin SDK is initialized with correct credentials
- Verify the project ID matches between frontend and backend Firebase configs

### "Module not found: firebase_admin":
- Run `pip install firebase-admin`

### Anonymous users show no email:
- This is expected - anonymous users don't have email addresses
- Store them with `firebase_uid` only

### CORS issues:
- Make sure CORS is configured to allow credentials (already done if you followed earlier CORS setup)

## Questions?

If you need help implementing this, check:
- [Firebase Admin SDK Documentation](https://firebase.google.com/docs/admin/setup)
- [Verify ID Tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
