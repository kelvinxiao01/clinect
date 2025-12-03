"""
Neo4j graph database connection and driver management
"""

import os
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'clinect_neo4j_password')

# Global driver instance
_driver = None

def get_driver():
    """Get Neo4j driver singleton"""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    return _driver

def close_driver():
    """Close Neo4j driver connection"""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None

def test_connection():
    """Test Neo4j connection"""
    try:
        driver = get_driver()
        driver.verify_connectivity()
        return True
    except (ServiceUnavailable, AuthError) as e:
        print(f"Neo4j connection failed: {e}")
        return False

def execute_query(query, parameters=None):
    """
    Execute a Cypher query and return results

    Args:
        query: Cypher query string
        parameters: Dictionary of query parameters

    Returns:
        list: List of records
    """
    driver = get_driver()
    with driver.session() as session:
        result = session.run(query, parameters or {})
        return [record.data() for record in result]

def execute_write(query, parameters=None):
    """
    Execute a write transaction

    Args:
        query: Cypher query string
        parameters: Dictionary of query parameters

    Returns:
        Summary of the transaction
    """
    driver = get_driver()

    def _execute(tx):
        result = tx.run(query, parameters or {})
        return result.consume()

    with driver.session() as session:
        return session.execute_write(_execute)

def clear_database():
    """Clear all nodes and relationships (use with caution)"""
    query = "MATCH (n) DETACH DELETE n"
    execute_write(query)
    print("Neo4j database cleared")

def get_stats():
    """Get database statistics"""
    queries = {
        'nodes': "MATCH (n) RETURN count(n) as count",
        'relationships': "MATCH ()-[r]->() RETURN count(r) as count",
        'trials': "MATCH (t:Trial) RETURN count(t) as count",
        'conditions': "MATCH (c:Condition) RETURN count(c) as count",
        'locations': "MATCH (l:Location) RETURN count(l) as count",
        'patients': "MATCH (p:Patient) RETURN count(p) as count"
    }

    stats = {}
    for key, query in queries.items():
        result = execute_query(query)
        stats[key] = result[0]['count'] if result else 0

    return stats

if __name__ == "__main__":
    # Can be run as a script or imported as a module
    print("Neo4j module loaded")
    print(f"Neo4j URI: {NEO4J_URI}")

    if test_connection():
        print("✓ Neo4j connection successful")
        stats = get_stats()
        print(f"Database stats: {stats}")
    else:
        print("✗ Neo4j connection failed")
        print("Make sure Neo4j is running: docker-compose up -d neo4j")
