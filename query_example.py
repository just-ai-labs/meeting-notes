from langchain_query_engine import MeetingQueryEngine

def main():
    # Initialize the query engine
    engine = MeetingQueryEngine()
    
    # Add your new queries here
    queries = [
        # Example: Add your new query as a string
        "What topics were discussed in meetings during February 2025?",
        
        # You can add more queries here
        "Show me all high-priority action items from February meetings",
        "List all decisions made about the mobile app development",
        "Who attended the most meetings in February?"
    ]
    
    # Process each query
    for query in queries:
        print(f"\nProcessing query: {query}")
        results = engine.process_query(query)
        print("Results:", results)

if __name__ == "__main__":
    main()
