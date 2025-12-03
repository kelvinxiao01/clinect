"""
Migration script to add Firebase authentication fields to existing users table
Run this script once to update your database schema for Firebase support
"""

from database import get_connection

def migrate_users_table():
    """Add firebase_uid and email columns to existing users table"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Add firebase_uid column if it doesn't exist
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'firebase_uid'
                ) THEN
                    ALTER TABLE users ADD COLUMN firebase_uid VARCHAR(255) UNIQUE;
                END IF;
            END $$;
        """)

        # Add email column if it doesn't exist
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'email'
                ) THEN
                    ALTER TABLE users ADD COLUMN email VARCHAR(255);
                END IF;
            END $$;
        """)

        # Make username nullable (for Firebase-only users)
        cur.execute("""
            ALTER TABLE users ALTER COLUMN username DROP NOT NULL;
        """)

        # Create index on firebase_uid for faster lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid);
        """)

        conn.commit()
        print("✅ Migration successful! Firebase columns added to users table.")
        print("   - Added firebase_uid column (unique)")
        print("   - Added email column")
        print("   - Made username nullable")
        print("   - Created index on firebase_uid")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise e
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    print("Running Firebase migration...")
    migrate_users_table()
