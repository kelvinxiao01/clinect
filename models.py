"""
Database models and CRUD operations
"""

from database import get_connection

# ============================================================================
# User Operations
# ============================================================================

def get_or_create_user(username):
    """Get user by username or create if doesn't exist"""
    conn = get_connection()
    cur = conn.cursor()

    # Try to get existing user
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()

    if user:
        cur.close()
        conn.close()
        return user

    # Create new user
    cur.execute(
        "INSERT INTO users (username) VALUES (%s) RETURNING *",
        (username,)
    )
    user = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return user

def get_user_by_id(user_id):
    """Get user by ID"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    return user

def get_user_by_username(username):
    """Get user by username"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    return user

def get_or_create_user_by_firebase_uid(firebase_uid, email=None):
    """
    Get or create user by Firebase UID
    Firebase UID is the unique identifier from Firebase Auth
    """
    conn = get_connection()
    cur = conn.cursor()

    # Try to find existing user by Firebase UID
    cur.execute("SELECT * FROM users WHERE firebase_uid = %s", (firebase_uid,))
    user = cur.fetchone()

    if user:
        cur.close()
        conn.close()
        return user

    # Create new user if not found
    cur.execute(
        """
        INSERT INTO users (firebase_uid, email)
        VALUES (%s, %s)
        RETURNING *
        """,
        (firebase_uid, email)
    )
    user = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return user

# ============================================================================
# Medical History Operations
# ============================================================================

def save_medical_history(user_id, age=None, gender=None, location=None,
                         conditions=None, medications=None):
    """Save or update user's medical history"""
    conn = get_connection()
    cur = conn.cursor()

    # Use INSERT ... ON CONFLICT UPDATE (upsert)
    cur.execute("""
        INSERT INTO medical_histories
            (user_id, age, gender, location, conditions, medications, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id)
        DO UPDATE SET
            age = EXCLUDED.age,
            gender = EXCLUDED.gender,
            location = EXCLUDED.location,
            conditions = EXCLUDED.conditions,
            medications = EXCLUDED.medications,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
    """, (user_id, age, gender, location, conditions, medications))

    history = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return history

def get_medical_history(user_id):
    """Get user's medical history"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM medical_histories WHERE user_id = %s",
        (user_id,)
    )
    history = cur.fetchone()

    cur.close()
    conn.close()

    return history

# ============================================================================
# Saved Trials Operations
# ============================================================================

def save_trial(user_id, nct_id, trial_title=None, trial_status=None,
               trial_summary=None):
    """Save a clinical trial for a user"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO saved_trials
                (user_id, nct_id, trial_title, trial_status, trial_summary)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """, (user_id, nct_id, trial_title, trial_status, trial_summary))

        trial = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return trial
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        raise e

def get_saved_trials(user_id):
    """Get all saved trials for a user"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM saved_trials WHERE user_id = %s ORDER BY saved_at DESC",
        (user_id,)
    )
    trials = cur.fetchall()

    cur.close()
    conn.close()

    return trials

def delete_saved_trial(user_id, nct_id):
    """Delete a saved trial"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM saved_trials WHERE user_id = %s AND nct_id = %s",
        (user_id, nct_id)
    )

    conn.commit()
    deleted_count = cur.rowcount
    cur.close()
    conn.close()

    return deleted_count > 0

def is_trial_saved(user_id, nct_id):
    """Check if a trial is already saved by user"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM saved_trials WHERE user_id = %s AND nct_id = %s",
        (user_id, nct_id)
    )
    result = cur.fetchone()

    cur.close()
    conn.close()

    return result is not None

if __name__ == "__main__":
    # Can be run as a script or imported as a module
    print("Models module loaded")
