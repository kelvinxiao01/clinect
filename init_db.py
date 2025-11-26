"""
Initialize the database schema

Run this script after starting the PostgreSQL Docker container:
    docker-compose up -d
    uv run init_db.py

This file can also be converted to a Jupyter notebook (.ipynb)
"""

from database import create_schema, drop_schema, get_connection

def main():
    """Initialize database schema"""
    print("Initializing Clinect database...")
    print("=" * 50)

    # Test connection
    try:
        conn = get_connection()
        print("✓ Database connection successful")
        conn.close()
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("\nMake sure PostgreSQL is running:")
        print("  docker-compose up -d")
        return

    # Create schema
    try:
        create_schema()
        print("✓ Database schema created")
    except Exception as e:
        print(f"✗ Schema creation failed: {e}")
        return

    # Verify tables
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        tables = cur.fetchall()
        print("\n✓ Tables created:")
        for table in tables:
            print(f"  - {table['table_name']}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"✗ Table verification failed: {e}")

    print("\n" + "=" * 50)
    print("Database initialization complete!")
    print("\nYou can now run the Flask app:")
    print("  uv run app.py")

if __name__ == "__main__":
    main()
