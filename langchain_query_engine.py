from typing import List, Dict, Any
from langchain_core.prompts import PromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnablePassthrough
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
import json

class MeetingQueryEngine:
    def __init__(self):
        load_dotenv()
        
        # Initialize Neo4j connection
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
        )
        
        # Initialize LangChain components
        self.llm = ChatOpenAI(
            temperature=0,
            model="gpt-3.5-turbo",
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Setup output parser for Cypher queries
        self.output_parser = StructuredOutputParser.from_response_schemas([
            ResponseSchema(name="cypher_query", description="The Cypher query to execute"),
            ResponseSchema(name="query_type", description="Type of query (e.g., decision, action_item, topic)"),
            ResponseSchema(name="time_range", description="Time range for the query in days")
        ])
        
        # Setup prompt template for query conversion
        self.query_prompt = PromptTemplate(
            template="""Convert the following natural language query into a Neo4j Cypher query.

The database has the following node types:
- Meeting (properties: title, type, timestamp)
- Topic (properties: name)
- Person (properties: name, email)
- ActionItem (properties: description, status, priority)
- Decision (properties: content)

Relationships:
- (Meeting)-[:DISCUSSES]->(Topic)
- (Meeting)-[:HAS_ACTION_ITEM]->(ActionItem)
- (ActionItem)-[:ASSIGNED_TO]->(Person)
- (Meeting)-[:HAS_DECISION]->(Decision)
- (Meeting)-[:HAS_ATTENDEE]->(Person)

For time-based queries:
- Use "datetime() - duration('P7D')" for "last week"
- Use "datetime() - duration('P30D')" for "last month"
- Use "datetime() - duration('P1D')" for "yesterday"

Natural language query: {query}

Format your response as a JSON object with the following schema:
{{
    "cypher_query": "The Cypher query that will answer the question",
    "query_type": "The type of information being queried (decision, action_item, topic, attendee)",
    "time_range": "Time range in days (if applicable, otherwise 0)"
}}

Make sure to:
1. Use proper Cypher syntax for datetime operations (e.g., datetime() - duration('P7D'))
2. Consider case-insensitive matches where appropriate using toLower()
3. Return relevant properties that answer the question
4. Use pattern matching to find connected information
5. Include proper WHERE clauses for filtering

Response:""",
            input_variables=["query"]
        )
        
        # Setup reasoning prompt for contextual responses
        self.reasoning_prompt = PromptTemplate(
            template="""Analyze the following meeting data and provide insights:
            
            Query: {query}
            Query Type: {query_type}
            Time Range: {time_range} days
            
            Raw Data:
            {raw_data}
            
            Consider:
            1. Historical context and patterns
            2. Related decisions and their impact
            3. Dependencies between topics and action items
            4. Team workload and priorities
            
            Provide a concise but informative response that directly addresses the query.
            
            Response:""",
            input_variables=["query", "query_type", "time_range", "raw_data"]
        )
        
    def process_query(self, query: str) -> Dict[str, Any]:
        """Process a natural language query and return structured results with reasoning"""
        try:
            # Convert natural language to Cypher
            response = self.llm.invoke(self.query_prompt.format(query=query))
            
            try:
                query_info = json.loads(response.content)
            except json.JSONDecodeError as e:
                print(f"Error parsing response from LLM. Response: {response.content}")
                query_info = {
                    "cypher_query": "MATCH (m:Meeting) RETURN m LIMIT 1",
                    "query_type": "error",
                    "time_range": "0"
                }
            
            # Execute Cypher query
            with self.driver.session() as session:
                result = session.run(query_info["cypher_query"])
                data = result.data()
            
            # Generate reasoning and insights
            reasoning = self.llm.invoke(
                self.reasoning_prompt.format(
                    query=query,
                    query_type=query_info["query_type"],
                    time_range=query_info["time_range"],
                    raw_data=str(data)
                )
            )
            
            return {
                "query_info": query_info,
                "data": data,
                "reasoning": reasoning.content
            }
            
        except Exception as e:
            print(f"Error processing query: {str(e)}")
            return {
                "error": f"Failed to process query: {str(e)}",
                "query": query
            }
    
    def close(self):
        """Close the Neo4j connection"""
        self.driver.close()

# Example usage
if __name__ == "__main__":
    engine = MeetingQueryEngine()
    
    # Example queries
    queries = [
        "What were the key decisions from last week's meetings?",
        "Who is responsible for the database optimization tasks?",
        "Summarize all discussions about user authentication in the last 3 meetings",
        "What are the pending high-priority action items?"
    ]
    
    for query in queries:
        print(f"\nProcessing query: {query}")
        result = engine.process_query(query)
        print("Results:", result)
    
    engine.close()
