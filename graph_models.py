"""
Neo4j graph models and Cypher query operations for clinical trials
"""

from neo4j_db import execute_query, execute_write
from typing import List, Dict, Optional
import math

# ============================================================================
# Node Creation Functions
# ============================================================================

def create_trial_node(nct_id: str, title: str, status: str, phase: List[str] = None):
    """
    Create or update a Trial node

    Args:
        nct_id: NCT identifier
        title: Trial title
        status: Overall status (RECRUITING, COMPLETED, etc.)
        phase: List of trial phases

    Returns:
        Created/updated node properties
    """
    query = """
    MERGE (t:Trial {nctId: $nct_id})
    SET t.title = $title,
        t.status = $status,
        t.phase = $phase,
        t.updatedAt = datetime()
    RETURN t
    """
    params = {
        'nct_id': nct_id,
        'title': title,
        'status': status,
        'phase': phase or []
    }
    result = execute_query(query, params)
    return result[0]['t'] if result else None

def create_condition_node(condition_name: str, category: str = None):
    """
    Create or update a Condition node

    Args:
        condition_name: Name of the medical condition
        category: Optional category/classification

    Returns:
        Created/updated node properties
    """
    query = """
    MERGE (c:Condition {name: $name})
    SET c.category = $category,
        c.nameNormalized = toLower($name)
    RETURN c
    """
    params = {
        'name': condition_name,
        'category': category
    }
    result = execute_query(query, params)
    return result[0]['c'] if result else None

def create_location_node(city: str, state: str = None, country: str = None,
                        lat: float = None, lon: float = None):
    """
    Create or update a Location node

    Args:
        city: City name
        state: State/province
        country: Country name
        lat: Latitude
        lon: Longitude

    Returns:
        Created/updated node properties
    """
    # Create unique identifier for location
    location_id = f"{city}, {state}" if state else f"{city}, {country}"

    query = """
    MERGE (l:Location {locationId: $location_id})
    SET l.city = $city,
        l.state = $state,
        l.country = $country,
        l.latitude = $lat,
        l.longitude = $lon
    RETURN l
    """
    params = {
        'location_id': location_id,
        'city': city,
        'state': state,
        'country': country,
        'lat': lat,
        'lon': lon
    }
    result = execute_query(query, params)
    return result[0]['l'] if result else None

def create_patient_node(user_id: int, age: int = None, gender: str = None):
    """
    Create or update a Patient node

    Args:
        user_id: PostgreSQL user ID
        age: Patient age
        gender: Patient gender

    Returns:
        Created/updated node properties
    """
    query = """
    MERGE (p:Patient {userId: $user_id})
    SET p.age = $age,
        p.gender = $gender,
        p.updatedAt = datetime()
    RETURN p
    """
    params = {
        'user_id': user_id,
        'age': age,
        'gender': gender
    }
    result = execute_query(query, params)
    return result[0]['p'] if result else None

# ============================================================================
# Relationship Creation Functions
# ============================================================================

def link_trial_to_condition(nct_id: str, condition_name: str):
    """Create TREATS relationship between Trial and Condition"""
    query = """
    MATCH (t:Trial {nctId: $nct_id})
    MATCH (c:Condition {name: $condition_name})
    MERGE (t)-[r:TREATS]->(c)
    RETURN r
    """
    params = {'nct_id': nct_id, 'condition_name': condition_name}
    execute_write(query, params)

def link_trial_to_location(nct_id: str, location_id: str):
    """Create LOCATED_IN relationship between Trial and Location"""
    query = """
    MATCH (t:Trial {nctId: $nct_id})
    MATCH (l:Location {locationId: $location_id})
    MERGE (t)-[r:LOCATED_IN]->(l)
    RETURN r
    """
    params = {'nct_id': nct_id, 'location_id': location_id}
    execute_write(query, params)

def link_patient_to_condition(user_id: int, condition_name: str):
    """Create HAS_CONDITION relationship between Patient and Condition"""
    query = """
    MATCH (p:Patient {userId: $user_id})
    MERGE (c:Condition {name: $condition_name})
    MERGE (p)-[r:HAS_CONDITION]->(c)
    RETURN r
    """
    params = {'user_id': user_id, 'condition_name': condition_name}
    execute_write(query, params)

def link_patient_to_location(user_id: int, location_id: str):
    """Create LIVES_IN relationship between Patient and Location"""
    query = """
    MATCH (p:Patient {userId: $user_id})
    MATCH (l:Location {locationId: $location_id})
    MERGE (p)-[r:LIVES_IN]->(l)
    RETURN r
    """
    params = {'user_id': user_id, 'location_id': location_id}
    execute_write(query, params)

def link_patient_saved_trial(user_id: int, nct_id: str):
    """Create SAVED_TRIAL relationship between Patient and Trial"""
    query = """
    MATCH (p:Patient {userId: $user_id})
    MATCH (t:Trial {nctId: $nct_id})
    MERGE (p)-[r:SAVED_TRIAL {savedAt: datetime()}]->(t)
    RETURN r
    """
    params = {'user_id': user_id, 'nct_id': nct_id}
    execute_write(query, params)

def link_condition_hierarchy(child_condition: str, parent_condition: str):
    """Create IS_SUBTYPE_OF relationship between Conditions"""
    query = """
    MATCH (child:Condition {name: $child_condition})
    MATCH (parent:Condition {name: $parent_condition})
    MERGE (child)-[r:IS_SUBTYPE_OF]->(parent)
    RETURN r
    """
    params = {'child_condition': child_condition, 'parent_condition': parent_condition}
    execute_write(query, params)

# ============================================================================
# Query Functions - Trial Matching
# ============================================================================

def find_matching_trials(conditions: List[str] = None, location_id: str = None,
                        status: str = 'RECRUITING', max_distance_km: float = None,
                        limit: int = 20) -> List[Dict]:
    """
    Find trials matching patient criteria using graph traversal

    Args:
        conditions: List of condition names
        location_id: Location identifier
        status: Trial status (default: RECRUITING)
        max_distance_km: Maximum distance in kilometers (if location has coordinates)
        limit: Maximum number of results

    Returns:
        List of matching trials with match scores
    """
    # Start with base query filtering by status
    query = "MATCH (t:Trial)\n"
    query += "WHERE t.status = $status\n"

    params = {'limit': limit, 'status': status}

    # Build optional matches and scoring logic
    if conditions and len(conditions) > 0:
        # Only add condition matching if conditions provided
        params['conditions'] = conditions
        params['conditions_normalized'] = [c.lower() for c in conditions]

        query += """OPTIONAL MATCH (t)-[:TREATS]->(c:Condition)
WHERE c.name IN $conditions OR c.nameNormalized IN $conditions_normalized
"""
        condition_score = "count(DISTINCT c) * 10"
    else:
        # No conditions provided, score is 0
        condition_score = "0"

    if location_id:
        # Only add location matching if location provided
        params['location_id'] = location_id
        query += "OPTIONAL MATCH (t)-[:LOCATED_IN]->(l:Location {locationId: $location_id})\n"
        location_score = "count(DISTINCT l) * 5"
    else:
        # No location provided, score is 0
        location_score = "0"

    # Calculate match score and return
    # Use dynamic scoring based on what was matched
    query += f"""WITH t, {condition_score} as conditionScore, {location_score} as locationScore
WITH t, (conditionScore + locationScore) as matchScore
WHERE matchScore > 0
RETURN t.nctId as nctId,
       t.title as title,
       t.status as status,
       t.phase as phase,
       matchScore
ORDER BY matchScore DESC
LIMIT $limit
"""

    results = execute_query(query, params)
    return results

def find_related_trials(nct_id: str, limit: int = 10) -> List[Dict]:
    """
    Find trials related to a given trial through shared conditions or locations

    Args:
        nct_id: NCT identifier of the reference trial
        limit: Maximum number of results

    Returns:
        List of related trials with relationship types
    """
    query = """
    MATCH (t1:Trial {nctId: $nct_id})

    // Find trials treating same conditions
    OPTIONAL MATCH (t1)-[:TREATS]->(c:Condition)<-[:TREATS]-(t2:Trial)
    WHERE t2.nctId <> $nct_id
    WITH t1, t2, collect(DISTINCT c.name) as sharedConditions

    // Find trials in same locations
    OPTIONAL MATCH (t1)-[:LOCATED_IN]->(l:Location)<-[:LOCATED_IN]-(t2)
    WITH t2,
         sharedConditions,
         collect(DISTINCT l.locationId) as sharedLocations

    // Calculate relationship score
    WITH t2,
         sharedConditions,
         sharedLocations,
         (size(sharedConditions) * 3 + size(sharedLocations)) as relationshipScore
    WHERE relationshipScore > 0

    RETURN t2.nctId as nctId,
           t2.title as title,
           t2.status as status,
           t2.phase as phase,
           sharedConditions,
           sharedLocations,
           relationshipScore
    ORDER BY relationshipScore DESC
    LIMIT $limit
    """
    params = {'nct_id': nct_id, 'limit': limit}
    results = execute_query(query, params)
    return results

def get_patient_recommendations(user_id: int, limit: int = 10) -> List[Dict]:
    """
    Get personalized trial recommendations for a patient

    Args:
        user_id: PostgreSQL user ID
        limit: Maximum number of results

    Returns:
        List of recommended trials with reasoning
    """
    query = """
    MATCH (p:Patient {userId: $user_id})

    // Find patient's conditions
    OPTIONAL MATCH (p)-[:HAS_CONDITION]->(pc:Condition)

    // Find trials treating those conditions
    OPTIONAL MATCH (t:Trial)-[:TREATS]->(pc)
    WHERE t.status = 'RECRUITING'

    // Exclude already saved trials
    OPTIONAL MATCH (p)-[:SAVED_TRIAL]->(saved:Trial)
    WHERE t <> saved OR saved IS NULL

    // Calculate recommendation score
    WITH p, t, collect(DISTINCT pc.name) as matchingConditions
    WHERE size(matchingConditions) > 0

    RETURN t.nctId as nctId,
           t.title as title,
           t.status as status,
           t.phase as phase,
           matchingConditions,
           size(matchingConditions) as matchScore
    ORDER BY matchScore DESC
    LIMIT $limit
    """
    params = {'user_id': user_id, 'limit': limit}
    results = execute_query(query, params)
    return results

def calculate_geographic_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two geographic coordinates using Haversine formula

    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates

    Returns:
        Distance in kilometers
    """
    R = 6371  # Earth's radius in kilometers

    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))

    return R * c

# ============================================================================
# Utility Functions
# ============================================================================

def get_condition_hierarchy(condition_name: str) -> Dict:
    """
    Get the hierarchy tree for a condition (parents and children)

    Args:
        condition_name: Name of the condition

    Returns:
        Dictionary with parent and child conditions
    """
    query = """
    MATCH (c:Condition {name: $condition_name})

    // Find parent conditions
    OPTIONAL MATCH (c)-[:IS_SUBTYPE_OF*]->(parent:Condition)

    // Find child conditions
    OPTIONAL MATCH (child:Condition)-[:IS_SUBTYPE_OF*]->(c)

    RETURN c.name as condition,
           collect(DISTINCT parent.name) as parents,
           collect(DISTINCT child.name) as children
    """
    params = {'condition_name': condition_name}
    result = execute_query(query, params)
    return result[0] if result else {'condition': condition_name, 'parents': [], 'children': []}

if __name__ == "__main__":
    print("Graph models module loaded")
    print("Available functions:")
    print("  - create_trial_node, create_condition_node, create_location_node, create_patient_node")
    print("  - find_matching_trials, find_related_trials, get_patient_recommendations")
    print("  - get_condition_hierarchy")
