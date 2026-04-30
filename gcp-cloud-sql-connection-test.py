from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import FileReadTool
from crewai.tools import tool
import os
from sqlalchemy import create_engine, text
from google.cloud.sql.connector import Connector, IPTypes
from crewai.tools import BaseTool

class CloudSQLQueryTool(BaseTool):
    name: str = "Cloud SQL Query Tool"
    description: str = "Use this tool to query the Google Cloud SQL database. Input should be a raw SQL query."

    def _run(self, query: str) -> str:
        # Initialize Connector
        connector = Connector()

        def getconn():
            conn = connector.connect(
                os.environ.get("INSTANCE_CONNECTION_NAME"), # project:region:instance
                "pg8000",
                user=os.environ.get("DB_USER"),
                password=os.environ.get("DB_PASS"),
                db=os.environ.get("DB_NAME"),
                credentials_path=os.environ.get("GCP_KEY_JSON"),
                ip_type=IPTypes.PUBLIC  # Or IPTypes.PRIVATE
            )
            return conn

        # Create Engine
        engine = create_engine("postgresql+pg8000://", creator=getconn)

        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            return str(rows)

# Usage
cloud_sql_tool = CloudSQLQueryTool()

# Get a few rows from a specific table
sample_query = "SELECT * FROM players LIMIT 5;"
print(cloud_sql_tool._run(query=sample_query))