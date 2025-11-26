"""
MongoDB connection and collection management
"""

import os
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONGODB_URL = os.getenv('MONGODB_URL', 'mongodb://localhost:27017/')
DATABASE_NAME = 'clinect'

# Global client instance
_client = None
_db = None

def get_client():
    """Get MongoDB client singleton"""
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URL)
    return _client

def get_database():
    """Get database instance"""
    global _db
    if _db is None:
        client = get_client()
        _db = client[DATABASE_NAME]
    return _db

def test_connection():
    """Test MongoDB connection"""
    try:
        client = get_client()
        client.admin.command('ping')
        return True
    except ConnectionFailure:
        return False

def get_collection(collection_name):
    """Get a collection from the database"""
    db = get_database()
    return db[collection_name]

def create_indexes():
    """Create indexes for collections"""
    db = get_database()

    # Trials cache collection
    trials = db.trials_cache
    trials.create_index([("nctId", ASCENDING)], unique=True)
    trials.create_index([("searchableFields.conditions", ASCENDING)])
    trials.create_index([("searchableFields.locations", ASCENDING)])
    trials.create_index([("searchableFields.status", ASCENDING)])
    trials.create_index([("cachedAt", DESCENDING)])

    # Eligibility criteria collection (optional)
    eligibility = db.eligibility_criteria
    eligibility.create_index([("nctId", ASCENDING)], unique=True)

    print("MongoDB indexes created successfully")

def drop_collections():
    """Drop all collections (use with caution)"""
    db = get_database()
    db.trials_cache.drop()
    db.eligibility_criteria.drop()
    print("MongoDB collections dropped")

def get_stats():
    """Get database statistics"""
    db = get_database()

    stats = {
        'trials_cache_count': db.trials_cache.count_documents({}),
        'eligibility_count': db.eligibility_criteria.count_documents({})
    }

    return stats

if __name__ == "__main__":
    # Can be run as a script or imported as a module
    print("MongoDB module loaded")
    print(f"MongoDB URL: {MONGODB_URL}")

    if test_connection():
        print("✓ MongoDB connection successful")
        stats = get_stats()
        print(f"Collections: {stats}")
    else:
        print("✗ MongoDB connection failed")
