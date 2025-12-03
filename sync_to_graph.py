"""
Sync existing trial data from MongoDB to Neo4j graph database
Run this script to populate Neo4j with trials already cached in MongoDB
"""

from mongo_db import get_collection
from graph_models import (
    create_trial_node,
    create_condition_node,
    create_location_node,
    link_trial_to_condition,
    link_trial_to_location
)
from neo4j_db import test_connection, get_stats

def sync_trials_from_mongo(limit=None):
    """
    Sync clinical trials from MongoDB cache to Neo4j graph

    Args:
        limit: Optional limit on number of trials to sync (default: all)

    Returns:
        Dictionary with sync statistics
    """
    trials_collection = get_collection('trials_cache')

    # Query MongoDB for trials
    query = {}
    cursor = trials_collection.find(query)

    if limit:
        cursor = cursor.limit(limit)

    stats = {
        'trials_synced': 0,
        'conditions_created': 0,
        'locations_created': 0,
        'relationships_created': 0,
        'errors': 0
    }

    print(f"Starting sync from MongoDB to Neo4j...")

    for trial_doc in cursor:
        try:
            nct_id = trial_doc.get('nctId')
            protocol = trial_doc.get('protocolSection', {})

            # Extract trial information
            identification = protocol.get('identificationModule', {})
            status_module = protocol.get('statusModule', {})
            design_module = protocol.get('designModule', {})
            contacts_locations_module = protocol.get('contactsLocationsModule', {})

            title = identification.get('briefTitle', '')
            status = status_module.get('overallStatus', '')
            phases = design_module.get('phases', [])

            # Create trial node
            create_trial_node(nct_id, title, status, phases)
            stats['trials_synced'] += 1

            # Process conditions
            searchable = trial_doc.get('searchableFields', {})
            conditions = searchable.get('conditions', [])

            for condition_name in conditions:
                if condition_name:
                    # Create condition node
                    create_condition_node(condition_name)
                    stats['conditions_created'] += 1

                    # Link trial to condition
                    link_trial_to_condition(nct_id, condition_name)
                    stats['relationships_created'] += 1

            # Process locations
            locations = searchable.get('locations', [])

            for location_str in locations:
                if location_str and ', ' in location_str:
                    parts = location_str.split(', ')
                    city = parts[0]
                    state_or_country = parts[1] if len(parts) > 1 else None

                    # Determine if it's a state or country (simple heuristic)
                    if state_or_country and len(state_or_country) == 2:
                        # Likely a US state
                        create_location_node(city, state=state_or_country, country='USA')
                    else:
                        # Likely a country
                        create_location_node(city, country=state_or_country)

                    stats['locations_created'] += 1

                    # Link trial to location
                    link_trial_to_location(nct_id, location_str)
                    stats['relationships_created'] += 1

            # Progress indicator
            if stats['trials_synced'] % 10 == 0:
                print(f"  Synced {stats['trials_synced']} trials...")

        except Exception as e:
            print(f"  Error syncing trial {trial_doc.get('nctId', 'unknown')}: {e}")
            stats['errors'] += 1

    return stats

def sync_patients_from_postgres():
    """
    Sync patient data from PostgreSQL to Neo4j
    Creates Patient nodes and links them to Conditions and Locations
    """
    from models import get_user_by_id
    from database import get_connection

    conn = get_connection()
    cur = conn.cursor()

    # Get all users with medical histories
    cur.execute("""
        SELECT u.id, u.firebase_uid, u.email, mh.age, mh.gender,
               mh.location, mh.conditions
        FROM users u
        LEFT JOIN medical_histories mh ON u.id = mh.user_id
        WHERE mh.id IS NOT NULL
    """)

    users = cur.fetchall()
    cur.close()
    conn.close()

    stats = {
        'patients_synced': 0,
        'condition_links': 0,
        'location_links': 0,
        'errors': 0
    }

    print(f"\nSyncing {len(users)} patients from PostgreSQL to Neo4j...")

    from graph_models import create_patient_node, link_patient_to_condition, link_patient_to_location

    for user in users:
        try:
            user_id = user['id']
            age = user['age']
            gender = user['gender']
            location = user['location']
            conditions = user['conditions']

            # Create patient node
            create_patient_node(user_id, age, gender)
            stats['patients_synced'] += 1

            # Link to conditions (stored as comma-separated text)
            if conditions:
                condition_list = [c.strip() for c in conditions.split(',')]
                for condition in condition_list:
                    if condition:
                        link_patient_to_condition(user_id, condition)
                        stats['condition_links'] += 1

            # Link to location
            if location:
                link_patient_to_location(user_id, location)
                stats['location_links'] += 1

        except Exception as e:
            print(f"  Error syncing patient {user.get('id', 'unknown')}: {e}")
            stats['errors'] += 1

    return stats

def sync_saved_trials():
    """
    Sync saved trial relationships from PostgreSQL to Neo4j
    Creates SAVED_TRIAL relationships between Patients and Trials
    """
    from database import get_connection
    from graph_models import link_patient_saved_trial

    conn = get_connection()
    cur = conn.cursor()

    # Get all saved trials
    cur.execute("SELECT user_id, nct_id FROM saved_trials")
    saved_trials = cur.fetchall()

    cur.close()
    conn.close()

    stats = {'saved_links': 0, 'errors': 0}

    print(f"\nSyncing {len(saved_trials)} saved trial relationships...")

    for saved in saved_trials:
        try:
            user_id = saved['user_id']
            nct_id = saved['nct_id']

            link_patient_saved_trial(user_id, nct_id)
            stats['saved_links'] += 1

        except Exception as e:
            print(f"  Error syncing saved trial: {e}")
            stats['errors'] += 1

    return stats

def main():
    """Main sync function"""
    print("=" * 70)
    print("Syncing Data to Neo4j Graph Database")
    print("=" * 70)

    # Test Neo4j connection
    if not test_connection():
        print("\n❌ Error: Cannot connect to Neo4j")
        print("   Make sure Neo4j is running: docker-compose up -d neo4j")
        print("   And that you've run: uv run init_neo4j.py")
        return

    print("\n✓ Connected to Neo4j successfully\n")

    # Sync trials from MongoDB
    print("Step 1: Syncing clinical trials from MongoDB...")
    trial_stats = sync_trials_from_mongo()
    print(f"\n✓ Trial sync complete:")
    print(f"  - Trials synced: {trial_stats['trials_synced']}")
    print(f"  - Conditions created: {trial_stats['conditions_created']}")
    print(f"  - Locations created: {trial_stats['locations_created']}")
    print(f"  - Relationships created: {trial_stats['relationships_created']}")
    if trial_stats['errors'] > 0:
        print(f"  - Errors: {trial_stats['errors']}")

    # Sync patients from PostgreSQL
    print("\nStep 2: Syncing patients from PostgreSQL...")
    patient_stats = sync_patients_from_postgres()
    print(f"\n✓ Patient sync complete:")
    print(f"  - Patients synced: {patient_stats['patients_synced']}")
    print(f"  - Condition links: {patient_stats['condition_links']}")
    print(f"  - Location links: {patient_stats['location_links']}")
    if patient_stats['errors'] > 0:
        print(f"  - Errors: {patient_stats['errors']}")

    # Sync saved trials
    print("\nStep 3: Syncing saved trial relationships...")
    saved_stats = sync_saved_trials()
    print(f"\n✓ Saved trials sync complete:")
    print(f"  - Saved trial links: {saved_stats['saved_links']}")
    if saved_stats['errors'] > 0:
        print(f"  - Errors: {saved_stats['errors']}")

    # Show final stats
    print("\n" + "=" * 70)
    print("Final Neo4j Database Statistics:")
    print("=" * 70)
    stats = get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value:,}")

    print("\n✅ Sync complete!")
    print("\nNext steps:")
    print("  1. View graph in Neo4j Browser: http://localhost:7474")
    print("  2. Test matching endpoint: uv run app.py")
    print("  3. Try a query:")
    print("     MATCH (t:Trial)-[:TREATS]->(c:Condition) RETURN t, c LIMIT 25")
    print("=" * 70)

if __name__ == "__main__":
    main()
