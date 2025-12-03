"""
Clinical trial caching operations using MongoDB
Automatically syncs to Neo4j when trials are cached
"""

from datetime import datetime, timedelta
from mongo_db import get_collection
from pymongo.errors import DuplicateKeyError

# Cache expiration time (7 days)
CACHE_EXPIRATION_DAYS = 7

def sync_trial_to_neo4j(trial_data):
    """
    Sync a single trial from MongoDB to Neo4j graph database
    Called automatically after caching to keep Neo4j in sync

    Args:
        trial_data: Full trial JSON from ClinicalTrials.gov API

    Returns:
        bool: True if synced successfully, False otherwise
    """
    try:
        from graph_models import (
            create_trial_node,
            create_condition_node,
            create_location_node,
            link_trial_to_condition,
            link_trial_to_location
        )

        # Extract trial metadata
        protocol = trial_data.get('protocolSection', {})
        identification = protocol.get('identificationModule', {})
        status_module = protocol.get('statusModule', {})
        design_module = protocol.get('designModule', {})
        conditions_module = protocol.get('conditionsModule', {})
        contacts_locations_module = protocol.get('contactsLocationsModule', {})

        nct_id = identification.get('nctId')
        title = identification.get('briefTitle', '')
        status = status_module.get('overallStatus', '')
        phases = design_module.get('phases', [])

        if not nct_id:
            return False

        # Create trial node in Neo4j
        create_trial_node(nct_id, title, status, phases)

        # Process and link conditions
        conditions = conditions_module.get('conditions', [])
        for condition_name in conditions:
            if condition_name:
                create_condition_node(condition_name)
                link_trial_to_condition(nct_id, condition_name)

        # Process and link locations
        locations = contacts_locations_module.get('locations', [])
        for loc in locations:
            city = loc.get('city', '')
            state = loc.get('state', '')
            country = loc.get('country', '')

            if city and state:
                location_id = f"{city}, {state}"
                create_location_node(city, state=state, country='USA')
                link_trial_to_location(nct_id, location_id)
            elif city and country:
                location_id = f"{city}, {country}"
                create_location_node(city, country=country)
                link_trial_to_location(nct_id, location_id)

        return True

    except Exception as e:
        # Don't fail the cache operation if Neo4j sync fails
        print(f"Neo4j sync failed for {trial_data.get('protocolSection', {}).get('identificationModule', {}).get('nctId', 'unknown')} (non-critical): {e}")
        return False

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

        # Auto-sync to Neo4j to keep graph database in sync
        sync_trial_to_neo4j(trial_data)

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
