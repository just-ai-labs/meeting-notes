from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
from neo4j.exceptions import ServiceUnavailable

load_dotenv()

class Neo4jInitializer:
    def __init__(self):
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            # Verify connection
            self.driver.verify_connectivity()
            print("Successfully connected to Neo4j database!")
        except ServiceUnavailable as e:
            print(f"Failed to connect to Neo4j: {e}")
            raise

    def close(self):
        self.driver.close()

    def clear_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def create_sample_data(self):
        with self.driver.session() as session:
            # Create sample meetings and action items
            session.run("""
                // Create People
                CREATE (alice:Person {name: 'Alice Johnson', email: 'alice@example.com'})
                CREATE (bob:Person {name: 'Bob Smith', email: 'bob@example.com'})
                CREATE (carol:Person {name: 'Carol Williams', email: 'carol@example.com'})

                // Create Meetings
                CREATE (m1:Meeting {
                    id: 1,
                    type: 'Sprint Review',
                    timestamp: datetime('2025-02-01T10:00:00'),
                    title: 'Sprint 23 Review'
                })
                CREATE (m2:Meeting {
                    id: 2,
                    type: 'Sprint Review',
                    timestamp: datetime('2025-02-04T14:00:00'),
                    title: 'Sprint 24 Review'
                })

                // Create Topics
                CREATE (t1:Topic {name: 'Database Optimization'})
                CREATE (t2:Topic {name: 'UI Enhancement'})
                CREATE (t3:Topic {name: 'API Integration'})

                // Create Action Items
                CREATE (a1:ActionItem {
                    description: 'Implement database indexing for better query performance',
                    status: 'pending',
                    assignee: 'alice@example.com',
                    priority: 'high'
                })
                CREATE (a2:ActionItem {
                    description: 'Create new dashboard components',
                    status: 'pending',
                    assignee: 'bob@example.com',
                    priority: 'medium'
                })
                CREATE (a3:ActionItem {
                    description: 'Set up integration tests for new API endpoints',
                    status: 'pending',
                    assignee: 'carol@example.com',
                    priority: 'high'
                })

                // Create Relationships
                CREATE (m1)-[:HAS_ATTENDEE]->(alice)
                CREATE (m1)-[:HAS_ATTENDEE]->(bob)
                CREATE (m2)-[:HAS_ATTENDEE]->(alice)
                CREATE (m2)-[:HAS_ATTENDEE]->(carol)

                CREATE (m1)-[:DISCUSSES]->(t1)
                CREATE (m1)-[:DISCUSSES]->(t2)
                CREATE (m2)-[:DISCUSSES]->(t2)
                CREATE (m2)-[:DISCUSSES]->(t3)

                CREATE (m1)-[:HAS_ACTION_ITEM]->(a1)
                CREATE (m1)-[:HAS_ACTION_ITEM]->(a2)
                CREATE (m2)-[:HAS_ACTION_ITEM]->(a3)

                CREATE (a1)-[:ASSIGNED_TO]->(alice)
                CREATE (a2)-[:ASSIGNED_TO]->(bob)
                CREATE (a3)-[:ASSIGNED_TO]->(carol)
            """)

def main():
    initializer = Neo4jInitializer()
    print("Clearing existing data...")
    initializer.clear_database()
    print("Creating sample data...")
    initializer.create_sample_data()
    print("Database initialization complete!")
    initializer.close()

if __name__ == "__main__":
    main()
