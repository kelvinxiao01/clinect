"""
Initialize Neo4j graph database with constraints and indexes
Run this script once after setting up Neo4j
"""

from neo4j_db import get_driver, test_connection, get_stats

def create_constraints():
    """Create uniqueness constraints for node properties"""
    driver = get_driver()

    constraints = [
        # Trial nodes must have unique nctId
        "CREATE CONSTRAINT trial_nct_id IF NOT EXISTS FOR (t:Trial) REQUIRE t.nctId IS UNIQUE",

        # Condition nodes must have unique name
        "CREATE CONSTRAINT condition_name IF NOT EXISTS FOR (c:Condition) REQUIRE c.name IS UNIQUE",

        # Location nodes must have unique locationId
        "CREATE CONSTRAINT location_id IF NOT EXISTS FOR (l:Location) REQUIRE l.locationId IS UNIQUE",

        # Patient nodes must have unique userId
        "CREATE CONSTRAINT patient_user_id IF NOT EXISTS FOR (p:Patient) REQUIRE p.userId IS UNIQUE",
    ]

    with driver.session() as session:
        for constraint in constraints:
            try:
                session.run(constraint)
                print(f"✓ Created constraint: {constraint.split('FOR')[1].split('REQUIRE')[0].strip()}")
            except Exception as e:
                print(f"  Note: {str(e)}")

def create_indexes():
    """Create indexes for faster queries"""
    driver = get_driver()

    indexes = [
        # Index on Trial status for filtering
        "CREATE INDEX trial_status IF NOT EXISTS FOR (t:Trial) ON (t.status)",

        # Index on Trial phase for filtering
        "CREATE INDEX trial_phase IF NOT EXISTS FOR (t:Trial) ON (t.phase)",

        # Index on Condition normalized name for case-insensitive search
        "CREATE INDEX condition_normalized IF NOT EXISTS FOR (c:Condition) ON (c.nameNormalized)",

        # Index on Condition category
        "CREATE INDEX condition_category IF NOT EXISTS FOR (c:Condition) ON (c.category)",

        # Index on Location city for search
        "CREATE INDEX location_city IF NOT EXISTS FOR (l:Location) ON (l.city)",

        # Index on Location state for search
        "CREATE INDEX location_state IF NOT EXISTS FOR (l:Location) ON (l.state)",

        # Index on Patient age for filtering
        "CREATE INDEX patient_age IF NOT EXISTS FOR (p:Patient) ON (p.age)",

        # Index on Patient gender for filtering
        "CREATE INDEX patient_gender IF NOT EXISTS FOR (p:Patient) ON (p.gender)",
    ]

    with driver.session() as session:
        for index in indexes:
            try:
                session.run(index)
                print(f"✓ Created index: {index.split('FOR')[1].split('ON')[0].strip()}")
            except Exception as e:
                print(f"  Note: {str(e)}")

def verify_setup():
    """Verify database setup"""
    driver = get_driver()

    # Check constraints
    with driver.session() as session:
        result = session.run("SHOW CONSTRAINTS")
        constraints = [record["name"] for record in result]
        print(f"\n✓ Total constraints: {len(constraints)}")

        # Check indexes
        result = session.run("SHOW INDEXES")
        indexes = [record["name"] for record in result]
        print(f"✓ Total indexes: {len(indexes)}")

def initialize():
    """Main initialization function"""
    print("=" * 70)
    print("Initializing Neo4j Graph Database for Clinect")
    print("=" * 70)

    # Test connection
    if not test_connection():
        print("\n❌ Error: Cannot connect to Neo4j")
        print("   Make sure Neo4j is running: docker-compose up -d neo4j")
        print("   Then wait a few seconds for Neo4j to start up")
        return

    print("\n✓ Connected to Neo4j successfully\n")

    # Create constraints
    print("Creating uniqueness constraints...")
    create_constraints()

    print("\nCreating indexes for faster queries...")
    create_indexes()

    print("\nVerifying setup...")
    verify_setup()

    # Show stats
    print("\nDatabase statistics:")
    stats = get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 70)
    print("✅ Neo4j initialization complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Access Neo4j Browser at: http://localhost:7474")
    print("     Username: neo4j")
    print("     Password: clinect_neo4j_password")
    print("\n  2. Import existing trial data:")
    print("     uv run sync_to_graph.py")
    print("\n  3. Test graph queries:")
    print("     uv run python -c 'from graph_models import find_matching_trials; print(find_matching_trials())'")
    print("=" * 70)

if __name__ == "__main__":
    initialize()
