from typing import List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

class MeetingAnalytics:
    def __init__(self):
        load_dotenv()
        
        # Initialize Neo4j connection
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
        )
        
        # Initialize LangChain
        self.llm = ChatOpenAI(
            temperature=0,
            model="gpt-3.5-turbo",
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Setup summary prompt
        self.summary_prompt = PromptTemplate(
            template="""Analyze the following meeting data and provide insights:
            Topics Discussed: {topics}
            Decisions Made: {decisions}
            Action Items: {action_items}
            
            Please provide:
            1. Key themes and patterns
            2. Notable decisions and their potential impact
            3. Progress on action items
            4. Recommendations for follow-up
            
            Analysis:""",
            input_variables=["topics", "decisions", "action_items"]
        )

    def analyze_topic_relationships(self) -> List[Dict[str, Any]]:
        """Analyze relationships between topics across meetings"""
        cypher_query = """
        MATCH (m:Meeting)
        MATCH (m)-[:DISCUSSES]->(t1:Topic)
        MATCH (m)-[:DISCUSSES]->(t2:Topic)
        WHERE t1 <> t2
        WITH t1.name as topic1, t2.name as topic2, count(m) as cooccurrence
        WHERE cooccurrence > 1
        RETURN topic1, topic2, cooccurrence
        ORDER BY cooccurrence DESC
        """
        with self.driver.session() as session:
            result = session.run(cypher_query)
            return [dict(record) for record in result]

    def generate_progress_report(self, days: int = 30) -> Dict[str, Any]:
        """Generate a comprehensive progress report for the specified time period"""
        cypher_query = """
        MATCH (m:Meeting)
        WHERE m.timestamp >= datetime() - duration({days: $days})
        OPTIONAL MATCH (m)-[:DISCUSSES]->(t:Topic)
        OPTIONAL MATCH (m)-[:HAS_DECISION]->(d:Decision)
        OPTIONAL MATCH (m)-[:HAS_ACTION_ITEM]->(a:ActionItem)-[:ASSIGNED_TO]->(p:Person)
        RETURN count(DISTINCT m) as total_meetings,
               collect(DISTINCT t.name) as topics,
               collect(DISTINCT d.description) as decisions,
               collect(DISTINCT {
                   description: a.description,
                   assignee: p.name,
                   status: a.status
               }) as action_items
        """
        with self.driver.session() as session:
            result = session.run(cypher_query, days=days)
            data = dict(result.single())
            
            # Generate summary using LangChain
            summary_input = {
                "topics": ", ".join(data["topics"]),
                "decisions": ", ".join(data["decisions"]),
                "action_items": str(data["action_items"])
            }
            
            chain = self.summary_prompt | self.llm
            analysis = chain.invoke(summary_input)
            
            data["analysis"] = analysis.content
            return data

    def identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """Identify potential bottlenecks and overloaded team members"""
        cypher_query = """
        MATCH (p:Person)<-[:ASSIGNED_TO]-(a:ActionItem)
        WHERE a.status = 'pending'
        WITH p, count(a) as pending_tasks,
             collect(a.description) as task_descriptions
        WHERE pending_tasks >= 3
        RETURN p.name as person,
               pending_tasks,
               task_descriptions
        ORDER BY pending_tasks DESC
        """
        with self.driver.session() as session:
            result = session.run(cypher_query)
            return [dict(record) for record in result]

    def track_decision_implementation(self) -> List[Dict[str, Any]]:
        """Track the implementation status of decisions"""
        cypher_query = """
        MATCH (m:Meeting)-[:HAS_DECISION]->(d:Decision)
        OPTIONAL MATCH (d)-[:RESULTS_IN]->(a:ActionItem)
        WITH d, m,
             collect(DISTINCT {
                 description: a.description,
                 status: a.status
             }) as related_actions
        RETURN m.title as meeting,
               d.description as decision,
               d.impact_level as impact,
               related_actions,
               CASE 
                   WHEN size(related_actions) = 0 THEN 'no_action'
                   WHEN all(x IN related_actions WHERE x.status = 'completed') THEN 'implemented'
                   WHEN any(x IN related_actions WHERE x.status = 'in_progress') THEN 'in_progress'
                   ELSE 'pending'
               END as implementation_status
        ORDER BY m.timestamp DESC
        """
        with self.driver.session() as session:
            result = session.run(cypher_query)
            return [dict(record) for record in result]

    def get_meeting_efficiency_metrics(self) -> Dict[str, Any]:
        """Calculate meeting efficiency metrics"""
        cypher_query = """
        MATCH (m:Meeting)
        OPTIONAL MATCH (m)-[:HAS_ACTION_ITEM]->(a:ActionItem)
        OPTIONAL MATCH (m)-[:HAS_DECISION]->(d:Decision)
        OPTIONAL MATCH (m)-[:DISCUSSES]->(t:Topic)
        WITH m,
             count(DISTINCT a) as action_count,
             count(DISTINCT d) as decision_count,
             count(DISTINCT t) as topic_count,
             m.duration as duration
        RETURN 
            avg(duration) as avg_duration,
            avg(toFloat(action_count + decision_count) / duration) as productivity_rate,
            avg(topic_count) as avg_topics_per_meeting,
            sum(action_count) as total_actions,
            sum(decision_count) as total_decisions
        """
        with self.driver.session() as session:
            result = session.run(cypher_query)
            return dict(result.single())

    def close(self):
        """Close the Neo4j connection"""
        self.driver.close()

# Example usage
if __name__ == "__main__":
    analytics = MeetingAnalytics()
    
    # Generate a progress report
    print("\nGenerating progress report...")
    report = analytics.generate_progress_report(days=30)
    print(f"Analysis: {report['analysis']}")
    
    # Check for bottlenecks
    print("\nChecking for bottlenecks...")
    bottlenecks = analytics.identify_bottlenecks()
    for bottleneck in bottlenecks:
        print(f"{bottleneck['person']} has {bottleneck['pending_tasks']} pending tasks")
    
    # Get efficiency metrics
    print("\nCalculating efficiency metrics...")
    metrics = analytics.get_meeting_efficiency_metrics()
    print(f"Average meeting duration: {metrics['avg_duration']} minutes")
    print(f"Average productivity rate: {metrics['productivity_rate']} items/minute")
    
    analytics.close()
