from typing import List, Dict
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from neo4j import GraphDatabase
from github import Github

# Load environment variables
load_dotenv()

class MeetingNotesProcessor:
    def __init__(self):
        # Initialize Neo4j connection
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        
        # Initialize GitHub client only if token is available
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token and github_token != "your_github_token":
            self.github = Github(github_token)
            self.repo = self.github.get_repo(os.getenv("GITHUB_REPO"))
        else:
            self.github = None
            self.repo = None
    
    def close(self):
        self.driver.close()

    def get_recent_decisions(self) -> List[Dict]:
        """Get decisions from recent meetings"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:Meeting)
                WITH m ORDER BY m.timestamp DESC LIMIT 1
                MATCH (m)-[:DISCUSSES]->(t:Topic)
                RETURN m.title as meeting, collect(t.name) as topics
            """)
            return [record for record in result]

    def get_pending_action_items(self) -> List[Dict]:
        """Get all pending action items"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:Meeting)-[:HAS_ACTION_ITEM]->(a:ActionItem)-[:ASSIGNED_TO]->(p:Person)
                WHERE a.status = 'pending'
                RETURN a.description as action, p.name as assignee, a.priority as priority
                ORDER BY a.priority DESC
            """)
            return [record for record in result]

    def create_github_issues(self) -> List[str]:
        """Create GitHub issues from pending action items"""
        if not self.github or not self.repo:
            return []
            
        action_items = self.get_pending_action_items()
        created_issues = []
        
        for item in action_items:
            title = f"Action Item: {item['action'][:50]}..."
            body = f"""
            Action Item from Meeting Notes
            
            Description: {item['action']}
            Assignee: {item['assignee']}
            Priority: {item['priority']}
            
            Created automatically from meeting notes.
            """
            
            issue = self.repo.create_issue(
                title=title,
                body=body
            )
            created_issues.append(issue.html_url)
        
        return created_issues

    def get_all_meetings(self) -> List[Dict]:
        """Get all meetings sorted by timestamp"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:Meeting)
                OPTIONAL MATCH (m)-[:HAS_ATTENDEE]->(p:Person)
                WITH m, collect(p.name) as attendees
                RETURN m.title as title, m.type as type, 
                       m.timestamp as timestamp, attendees
                ORDER BY m.timestamp DESC
            """)
            return [record for record in result]

    def get_topic_history(self, topic_name: str) -> List[Dict]:
        """Get history of discussions about a specific topic"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Topic {name: $topic})<-[:DISCUSSES]-(m:Meeting)
                OPTIONAL MATCH (m)-[:HAS_ACTION_ITEM]->(a:ActionItem)
                WITH m, collect(a.description) as actions
                RETURN m.title as meeting, m.timestamp as timestamp, 
                       actions
                ORDER BY m.timestamp DESC
            """, topic=topic_name)
            return [record for record in result]

    def get_person_tasks(self, person_name: str) -> List[Dict]:
        """Get all tasks assigned to a specific person"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Person {name: $name})<-[:ASSIGNED_TO]-(a:ActionItem)
                OPTIONAL MATCH (m:Meeting)-[:HAS_ACTION_ITEM]->(a)
                RETURN a.description as task, a.status as status,
                       a.priority as priority, m.title as meeting
                ORDER BY a.priority DESC, m.timestamp DESC
            """, name=person_name)
            return [record for record in result]

    def search_meetings(self, keyword: str) -> List[Dict]:
        """Search for meetings and action items containing a specific keyword"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:Meeting)
                WHERE EXISTS {
                    MATCH (m)-[:DISCUSSES]->(t:Topic)
                    WHERE toLower(t.name) CONTAINS toLower($keyword)
                }
                OR EXISTS {
                    MATCH (m)-[:HAS_ACTION_ITEM]->(a:ActionItem)
                    WHERE toLower(a.description) CONTAINS toLower($keyword)
                }
                OPTIONAL MATCH (m)-[:DISCUSSES]->(t:Topic)
                OPTIONAL MATCH (m)-[:HAS_ACTION_ITEM]->(a:ActionItem)
                OPTIONAL MATCH (m)-[:HAS_ATTENDEE]->(p:Person)
                RETURN m.title as title,
                       m.timestamp as timestamp,
                       collect(DISTINCT t.name) as topics,
                       collect(DISTINCT a.description) as actions,
                       collect(DISTINCT p.name) as attendees
                ORDER BY m.timestamp DESC
            """, keyword=keyword)
            return [record for record in result]

    def get_meetings_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get meetings within a specific date range with all related information"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:Meeting)
                WHERE m.timestamp >= datetime($start) AND m.timestamp <= datetime($end)
                OPTIONAL MATCH (m)-[:DISCUSSES]->(t:Topic)
                OPTIONAL MATCH (m)-[:HAS_ACTION_ITEM]->(a:ActionItem)-[:ASSIGNED_TO]->(p:Person)
                WITH m,
                     collect(DISTINCT {topic: t.name}) as topics,
                     collect(DISTINCT {action: a.description, assignee: p.name, status: a.status}) as actions
                RETURN m.title as title,
                       m.type as type,
                       m.timestamp as date,
                       topics,
                       actions
                ORDER BY m.timestamp DESC
            """, start=start_date.isoformat(), end=end_date.isoformat())
            return [record for record in result]

def main():
    processor = MeetingNotesProcessor()
    
    try:
        # Get meetings from the last 7 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        print(f"\nMeetings from {start_date.date()} to {end_date.date()}:")
        recent_meetings = processor.get_meetings_by_date_range(start_date, end_date)
        
        for meeting in recent_meetings:
            print(f"\n=== {meeting['title']} ===")
            print(f"Date: {meeting['date']}")
            print(f"Type: {meeting['type']}")
            
            print("\nTopics discussed:")
            for topic in meeting['topics']:
                if topic['topic']:
                    print(f"- {topic['topic']}")
            
            print("\nAction items:")
            for action in meeting['actions']:
                if action['action']:
                    print(f"- {action['action']}")
                    print(f"  Assigned to: {action['assignee']}")
                    print(f"  Status: {action['status']}")
            print("=" * 50)

        # Show pending action items
        print("\nPending Action Items:")
        actions = processor.get_pending_action_items()
        for item in actions:
            print(f"- {item['action']} (Assigned to: {item['assignee']}, Priority: {item['priority']})")

        # Search for database-related content
        print("\nDatabase-related discussions and tasks:")
        database_meetings = processor.search_meetings('database')
        for meeting in database_meetings:
            print(f"\nMeeting: {meeting['title']} ({meeting['timestamp']})")
            print(f"Topics: {', '.join(topic for topic in meeting['topics'] if topic)}")
            print(f"Actions: {', '.join(action for action in meeting['actions'] if action)}")
            print(f"Attendees: {', '.join(meeting['attendees'])}")

    finally:
        processor.close()

if __name__ == "__main__":
    main()
