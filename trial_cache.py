"""
Clinical trial caching operations using MongoDB
"""

from datetime import datetime, timedelta
from mongo_db import get_collection
from pymongo.errors import DuplicateKeyError

# Cache expiration time (7 days)
CACHE_EXPIRATION_DAYS = 7

def cache_trial(trial_data):
    """
    Cache a clinical trial document from the API

    Args:
        trial_data: Full trial JSON from ClinicalTrials.gov API

    Returns:
        bool: True if cached successfully, False otherwise
    """
    trials = get_collection('trials_cache')

    # Extract NCT ID
    protocol = trial_data.get('protocolSection', {})
    identification = protocol.get('identificationModule', {})
    nct_id = identification.get('nctId')

    if not nct_id:
        return False

    # Extract searchable fields for indexing
    status_module = protocol.get('statusModule', {})
    description_module = protocol.get('descriptionModule', {})
    conditions_module = protocol.get('conditionsModule', {})
    design_module = protocol.get('designModule', {})
    contacts_locations_module = protocol.get('contactsLocationsModule', {})

    # Build searchable fields
    searchable_fields = {
        'conditions': conditions_module.get('conditions', []),
        'status': status_module.get('overallStatus', ''),
        'phase': design_module.get('phases', []),
        'locations': []
    }

    # Extract location data
    locations = contacts_locations_module.get('locations', [])
    for loc in locations:
        city = loc.get('city', '')
        state = loc.get('state', '')
        country = loc.get('country', '')
        if city and state:
            searchable_fields['locations'].append(f"{city}, {state}")
        elif city and country:
            searchable_fields['locations'].append(f"{city}, {country}")

    # Create document to cache
    cache_doc = {
        'nctId': nct_id,
        'protocolSection': protocol,
        'cachedAt': datetime.utcnow(),
        'searchableFields': searchable_fields
    }

    try:
        # Upsert (insert or update)
        trials.update_one(
            {'nctId': nct_id},
            {'$set': cache_doc},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"Error caching trial {nct_id}: {e}")
        return False

def get_cached_trial(nct_id):
    """
    Get a cached trial by NCT ID

    Args:
        nct_id: NCT ID of the trial

    Returns:
        dict: Trial data or None if not found/expired
    """
    trials = get_collection('trials_cache')

    trial = trials.find_one({'nctId': nct_id})

    if not trial:
        return None

    # Check if cache is expired
    cached_at = trial.get('cachedAt')
    if cached_at:
        expiration = datetime.utcnow() - timedelta(days=CACHE_EXPIRATION_DAYS)
        if cached_at < expiration:
            # Cache expired, delete it
            trials.delete_one({'nctId': nct_id})
            return None

    return trial

def search_cached_trials(condition=None, location=None, status=None, limit=20):
    """
    Search cached trials

    Args:
        condition: Disease/condition to search for
        location: Geographic location
        status: Recruitment status
        limit: Maximum number of results

    Returns:
        list: List of matching trials
    """
    trials = get_collection('trials_cache')

    # Build query
    query = {}

    if condition:
        query['searchableFields.conditions'] = {
            '$regex': condition,
            '$options': 'i'  # Case-insensitive
        }

    if location:
        query['searchableFields.locations'] = {
            '$regex': location,
            '$options': 'i'
        }

    if status:
        query['searchableFields.status'] = status

    # Filter out expired cache entries
    expiration = datetime.utcnow() - timedelta(days=CACHE_EXPIRATION_DAYS)
    query['cachedAt'] = {'$gte': expiration}

    # Execute query
    results = trials.find(query).limit(limit)

    return list(results)

def get_cache_stats():
    """Get cache statistics"""
    trials = get_collection('trials_cache')

    total_count = trials.count_documents({})

    expiration = datetime.utcnow() - timedelta(days=CACHE_EXPIRATION_DAYS)
    valid_count = trials.count_documents({'cachedAt': {'$gte': expiration}})
    expired_count = trials.count_documents({'cachedAt': {'$lt': expiration}})

    return {
        'total': total_count,
        'valid': valid_count,
        'expired': expired_count
    }

def clear_expired_cache():
    """Remove expired cache entries"""
    trials = get_collection('trials_cache')

    expiration = datetime.utcnow() - timedelta(days=CACHE_EXPIRATION_DAYS)
    result = trials.delete_many({'cachedAt': {'$lt': expiration}})

    return result.deleted_count

def clear_all_cache():
    """Clear all cached trials (use with caution)"""
    trials = get_collection('trials_cache')
    result = trials.delete_many({})
    return result.deleted_count

if __name__ == "__main__":
    # Can be run as a script or imported as a module
    print("Trial cache module loaded")
    stats = get_cache_stats()
    print(f"Cache stats: {stats}")
