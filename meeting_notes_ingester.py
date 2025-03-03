import spacy
import nltk
from keybert import KeyBERT
from typing import List, Dict
from datetime import datetime
import re
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
from neo4j.exceptions import ServiceUnavailable

# Download required NLTK data
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')

class MeetingNotesIngester:
    def __init__(self):
        # Load NLP models
        self.nlp = spacy.load("en_core_web_sm")
        self.keyword_model = KeyBERT()
        
        # Initialize Neo4j connection
        load_dotenv()
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
        
        # Patterns for information extraction
        self.action_patterns = [
            r"action(?:\s+item)?s?:?\s*(.*)",
            r"todo:?\s*(.*)",
            r"(?:assigned|assigned to|responsible):\s*(.*)",
            r"(\w+)\s+(?:will|shall|to)\s+(?:handle|do|implement|create|setup|prepare)(.*)",
        ]
        
        self.decision_patterns = [
            r"decision:?\s*(.*)",
            r"decided:?\s*(.*)",
            r"agreed:?\s*(.*)",
            r"conclusion:?\s*(.*)",
            r"resolved:?\s*(.*)",
        ]
        
        self.attendee_patterns = [
            r"attendees?:?\s*(.*)",
            r"participants?:?\s*(.*)",
            r"present:?\s*(.*)",
        ]

    def extract_topics(self, text: str) -> List[str]:
        """Extract main topics using KeyBERT for keyword extraction"""
        # Extract keywords with scores
        keywords = self.keyword_model.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 2),
            stop_words='english',
            use_maxsum=True,
            nr_candidates=20,
            top_n=5
        )
        
        # Return only the keywords, not their scores
        return [keyword for keyword, _ in keywords]

    def extract_action_items(self, text: str) -> List[Dict]:
        """Extract action items and their assignees"""
        action_items = []
        
        # Split text into sentences
        doc = self.nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents]
        
        for sentence in sentences:
            # Check for action item patterns
            for pattern in self.action_patterns:
                matches = re.finditer(pattern, sentence, re.IGNORECASE)
                for match in matches:
                    action_text = match.group(1).strip()
                    if action_text:
                        # Try to find assignee
                        assignee = self._extract_assignee(sentence)
                        priority = self._determine_priority(sentence)
                        
                        action_items.append({
                            'description': action_text,
                            'assignee': assignee,
                            'priority': priority,
                            'status': 'pending'
                        })
        
        return action_items

    def extract_decisions(self, text: str) -> List[str]:
        """Extract decisions from the text"""
        decisions = []
        
        # Split text into sentences
        doc = self.nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents]
        
        for sentence in sentences:
            # Check for decision patterns
            for pattern in self.decision_patterns:
                matches = re.finditer(pattern, sentence, re.IGNORECASE)
                for match in matches:
                    decision = match.group(1).strip()
                    if decision:
                        decisions.append(decision)
        
        return decisions

    def extract_attendees(self, text: str) -> List[Dict]:
        """Extract attendees and their email addresses if available"""
        attendees = []
        
        # First try to find explicit attendee lists
        for pattern in self.attendee_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                attendee_text = match.group(1)
                if attendee_text:
                    # Split by common separators
                    names = re.split(r'[,;]|\sand\s', attendee_text)
                    for name in names:
                        name = name.strip()
                        if name:
                            attendees.append({
                                'name': name,
                                'email': self._extract_email(name, text)
                            })
        
        # If no explicit list found, try to extract names using NLP
        if not attendees:
            doc = self.nlp(text)
            for ent in doc.ents:
                if ent.label_ == 'PERSON':
                    attendees.append({
                        'name': ent.text,
                        'email': self._extract_email(ent.text, text)
                    })
        
        return attendees

    def _extract_assignee(self, sentence: str) -> str:
        """Extract the assignee from an action item sentence"""
        doc = self.nlp(sentence)
        
        # Look for person entities
        for ent in doc.ents:
            if ent.label_ == 'PERSON':
                return ent.text
        
        # Look for patterns like "Assigned to: X"
        assigned_match = re.search(r'assigned to:?\s*(\w+)', sentence, re.IGNORECASE)
        if assigned_match:
            return assigned_match.group(1)
        
        return None

    def _determine_priority(self, sentence: str) -> str:
        """Determine priority based on keywords in the sentence"""
        priority_indicators = {
            'high': ['urgent', 'critical', 'important', 'asap', 'high priority'],
            'medium': ['medium', 'moderate', 'normal'],
            'low': ['low', 'minor', 'when possible', 'if time permits']
        }
        
        sentence_lower = sentence.lower()
        
        for priority, indicators in priority_indicators.items():
            if any(indicator in sentence_lower for indicator in indicators):
                return priority
        
        return 'medium'  # Default priority

    def _extract_email(self, name: str, text: str) -> str:
        """Try to find an email address associated with a name"""
        # Look for email pattern near the name
        name_parts = name.split()
        if name_parts:
            name_pattern = re.escape(name_parts[0])
            email_pattern = fr'{name_pattern}.*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{{2,}})'
            match = re.search(email_pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def store_in_neo4j(self, meeting_title: str, meeting_type: str, meeting_date: datetime, 
                       topics: List[str], action_items: List[Dict], 
                       decisions: List[str], attendees: List[Dict]):
        with self.driver.session() as session:
            # Create meeting node
            session.run("""
                CREATE (m:Meeting {
                    title: $title,
                    type: $type,
                    timestamp: datetime($date)
                })
                RETURN m
            """, title=meeting_title, type=meeting_type, date=meeting_date.isoformat())
            
            # Create and link topics
            for topic in topics:
                if topic:  # Only process non-empty topics
                    session.run("""
                        MATCH (m:Meeting {title: $title})
                        MERGE (t:Topic {name: $topic})
                        CREATE (m)-[:DISCUSSES]->(t)
                    """, title=meeting_title, topic=topic)
            
            # Create and link action items
            for item in action_items:
                if item['description'] and item['assignee']:  # Check required fields
                    session.run("""
                        MATCH (m:Meeting {title: $title})
                        CREATE (a:ActionItem {
                            description: $description,
                            status: COALESCE($status, 'pending'),
                            priority: COALESCE($priority, 'medium')
                        })
                        CREATE (m)-[:HAS_ACTION_ITEM]->(a)
                        MERGE (p:Person {name: $assignee})
                        CREATE (a)-[:ASSIGNED_TO]->(p)
                    """, title=meeting_title, **item)
            
            # Create and link decisions
            for decision in decisions:
                if decision:  # Only process non-empty decisions
                    session.run("""
                        MATCH (m:Meeting {title: $title})
                        CREATE (d:Decision {content: $decision})
                        CREATE (m)-[:MADE_DECISION]->(d)
                    """, title=meeting_title, decision=decision)
            
            # Create and link attendees
            for attendee in attendees:
                if attendee['name']:  # Only process attendees with names
                    session.run("""
                        MATCH (m:Meeting {title: $title})
                        MERGE (p:Person {name: $name})
                        WITH m, p, $email as email
                        WHERE email IS NOT NULL
                        SET p.email = email
                        WITH m, p
                        CREATE (m)-[:HAS_ATTENDEE]->(p)
                    """, title=meeting_title, **attendee)

    def process_meeting_notes(self, notes_text: str, meeting_title: str, 
                            meeting_type: str, meeting_date: datetime):
        """Process meeting notes and store in Neo4j"""
        # Extract information
        topics = self.extract_topics(notes_text)
        action_items = self.extract_action_items(notes_text)
        decisions = self.extract_decisions(notes_text)
        attendees = self.extract_attendees(notes_text)
        
        # Store in Neo4j
        self.store_in_neo4j(
            meeting_title=meeting_title,
            meeting_type=meeting_type,
            meeting_date=meeting_date,
            topics=topics,
            action_items=action_items,
            decisions=decisions,
            attendees=attendees
        )
        
        return {
            'topics': topics,
            'action_items': action_items,
            'decisions': decisions,
            'attendees': attendees
        }

def main():
    ingester = MeetingNotesIngester()
    
    # Process all meeting notes in the directory
    notes_dir = "meeting_notes"
    for filename in os.listdir(notes_dir):
        if filename.endswith(".txt"):
            print(f"\nProcessing {filename}...")
            
            # Read the file
            with open(os.path.join(notes_dir, filename), 'r') as f:
                notes_text = f.read()
            
            # Extract meeting title and date from filename
            # Expected format: type_YYYY_MM_DD.txt
            parts = filename.replace('.txt', '').split('_')
            meeting_type = ' '.join(parts[:-3]).title()
            year, month, day = parts[-3:]
            meeting_date = datetime(int(year), int(month), int(day))
            
            # Get the title from the first line of the file
            meeting_title = notes_text.split('\n')[0].strip()
            
            # Process the notes
            results = ingester.process_meeting_notes(
                notes_text=notes_text,
                meeting_title=meeting_title,
                meeting_type=meeting_type,
                meeting_date=meeting_date
            )
            
            print(f"\nResults for {meeting_title}:")
            print("\nExtracted Topics:")
            for topic in results['topics']:
                print(f"- {topic}")
            
            print("\nExtracted Action Items:")
            for item in results['action_items']:
                print(f"- {item['description']}")
                print(f"  Assigned to: {item['assignee']}")
                print(f"  Priority: {item['priority']}")
            
            print("\nExtracted Decisions:")
            for decision in results['decisions']:
                print(f"- {decision}")
            
            print("\nExtracted Attendees:")
            for attendee in results['attendees']:
                print(f"- {attendee['name']} ({attendee['email'] if attendee['email'] else 'no email'})")
            
            print("\n" + "="*50)

if __name__ == "__main__":
    main()
