"""
Initialize MongoDB collections and indexes

Run this script after starting the MongoDB Docker container:
    docker-compose up -d
    uv run init_mongo.py

This file can also be converted to a Jupyter notebook (.ipynb)
"""

from mongo_db import test_connection, create_indexes, get_stats

def main():
    """Initialize MongoDB collections and indexes"""
    print("Initializing Clinect MongoDB...")
    print("=" * 50)

    # Test connection
    if test_connection():
        print("✓ MongoDB connection successful")
    else:
        print("✗ MongoDB connection failed")
        print("\nMake sure MongoDB is running:")
        print("  docker-compose up -d")
        return

    # Create indexes
    try:
        create_indexes()
        print("✓ MongoDB indexes created")
    except Exception as e:
        print(f"✗ Index creation failed: {e}")
        return

    # Verify collections
    try:
        stats = get_stats()
        print("\n✓ Collections initialized:")
        print(f"  - trials_cache: {stats['trials_cache_count']} documents")
        print(f"  - eligibility_criteria: {stats['eligibility_count']} documents")
    except Exception as e:
        print(f"✗ Collection verification failed: {e}")

    print("\n" + "=" * 50)
    print("MongoDB initialization complete!")
    print("\nYou can now run the Flask app:")
    print("  uv run app.py")

if __name__ == "__main__":
    main()
