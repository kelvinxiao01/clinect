"""
Database connection and schema management using psycopg
"""

import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

def get_connection():
    """Get a database connection"""
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def create_schema():
    """Create database schema"""
    conn = get_connection()
    cur = conn.cursor()

    # Create users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create medical_histories table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS medical_histories (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            age INTEGER,
            gender VARCHAR(50),
            location VARCHAR(255),
            conditions TEXT,
            medications TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id)
        )
    """)

    # Create saved_trials table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_trials (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            nct_id VARCHAR(50) NOT NULL,
            trial_title TEXT,
            trial_status VARCHAR(100),
            trial_summary TEXT,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, nct_id)
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

    print("Database schema created successfully")

def drop_schema():
    """Drop all tables (use with caution)"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS saved_trials CASCADE")
    cur.execute("DROP TABLE IF EXISTS medical_histories CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")

    conn.commit()
    cur.close()
    conn.close()

    print("Database schema dropped")

if __name__ == "__main__":
    # Can be run as a script or imported as a module
    print("Database module loaded")
    print(f"Database URL: {DATABASE_URL}")
