import os
import warnings
import logging
from concurrent.futures import ThreadPoolExecutor
import httpx
import pandas as pd
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from google.cloud.sql.connector import Connector, IPTypes

# CrewAI imports
from crewai import Agent, Task, Crew, LLM

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Fantasy Football CrewAI Service")

# 1. Initialization Config
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
my_llm = LLM(
    model='gemini/gemini-2.5-flash',
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com",
    temperature=0.0
)

connector = Connector()

def getconn():
    return connector.connect(
        os.environ.get("INSTANCE_CONNECTION_NAME"),
        "pg8000",
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASS"),
        db=os.environ.get("DB_NAME"),
        ip_type=IPTypes.PUBLIC
    )

engine = create_engine("postgresql+pg8000://", creator=getconn)

# 2. Parallel Database Fetcher (No LLM Overhead)
def fetch_single_query(name: str, query: str) -> str:
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
            table_str = "No rows returned." if df.empty else df.to_markdown(index=False)
            return f"### {name}\n{table_str}"
    except Exception as e:
        return f"### {name}\nError executing query: {str(e)}"

def get_all_fantasy_data_fast(user_id: str, matchday: str) -> str:
    queries = {
        "FORMATION": f"SELECT formation FROM users WHERE id = '{user_id}';",
        "HOME SQUAD": f"SELECT t.api_player_id, t.name, p.position, te.name AS team FROM teamsheets t LEFT JOIN players p ON t.api_player_id = p.api_player_id LEFT JOIN teams te ON p.teams_id = te.id WHERE user_id = '{user_id}' AND p.account_id = t.account_id ORDER BY position;",
        "MATCHWEEK FIXTURES": f"SELECT round, hteamid, hteamname, ateamid, ateamname FROM prem_fixtures WHERE round = '{matchday}';",
        "PLAYER ATTACKING STATS": f"SELECT api_player_id, name, injured, team_id, team_name, appearances, lineups, position, rating, shots_total, shots_on, goals_total, goals_assists, passes_key, passes_accuracy, dribbles_attempts, dribbles_success, fouls_drawn FROM player_statistics WHERE api_player_id IN (SELECT api_player_id FROM teamsheets WHERE user_id = '{user_id}' AND season = '26-27');",
        "TEAM DEFENSIVE STATS": f"SELECT team_id, name, played_home, played_away, played_total, goals_against_home, goals_against_away, avg_goals_against_home, avg_goals_against_away, avg_goals_against_total, clean_sheets_home, clean_sheets_away FROM team_statistics WHERE team_id IN (SELECT id FROM teams WHERE id IN (SELECT p.teams_id FROM teamsheets t LEFT JOIN players p ON t.api_player_id = p.api_player_id WHERE t.user_id = '{user_id}' AND season = '26-27'));",
        "TEAM ATTACKING STATS": f"SELECT team_id, name, played_home, played_away, played_total, wins_home, wins_away, draws_home, draws_away, losses_home, losses_away, goals_for_home, goals_for_away, avg_goals_for_home, avg_goals_for_away, avg_goals_for_total, failed_to_score_home, failed_to_score_away FROM team_statistics WHERE team_id IN (SELECT id FROM teams WHERE id IN (SELECT p.teams_id FROM teamsheets t LEFT JOIN players p ON t.api_player_id = p.api_player_id WHERE t.user_id = '{user_id}' AND season = '26-27'));",
        "PLAYER DEFENSIVE STATS": f"SELECT api_player_id, name, injured, team_id, team_name, appearances, lineups, position, rating, goals_conceded, tackles_total, tackles_blocks, tackles_interceptions, duels_total, duels_won, fouls_committed FROM player_statistics WHERE api_player_id IN (SELECT api_player_id FROM teamsheets WHERE user_id = '{user_id}' AND position = 'Defender' AND season = '26-27');",
        "GOALKEEPER STATS": f"SELECT api_player_id, name, team_id, team_name, appearances, lineups, position, rating, goals_conceded, goals_saves, duels_total, duels_won FROM player_statistics WHERE api_player_id IN (SELECT api_player_id FROM teamsheets WHERE user_id = '{user_id}' AND season = '26-27' AND position = 'Goalkeeper');",
        "INJURED PLAYERS": f"SELECT api_player_id, name, injured, team_id, team_name, position FROM player_statistics WHERE api_player_id IN (SELECT api_player_id FROM teamsheets WHERE user_id = '{user_id}' AND season = '26-27');",
        "PREMIER LEAGUE STANDINGS": "SELECT * FROM standings;"
    }

    output_sections = []

    # Read CSV directly
    try:
        if os.path.exists("farpost_data_dictionary.csv"):
            dict_df = pd.read_csv("farpost_data_dictionary.csv")
            output_sections.append("### DATA DICTIONARY DEFINITIONS\n" + dict_df.to_markdown(index=False))
    except Exception as e:
        output_sections.append(f"### DATA DICTIONARY DEFINITIONS\nError reading dictionary: {str(e)}")

    # Execute all 10 SQL queries simultaneously across 5 threads
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_single_query, name, sql) for name, sql in queries.items()]
        for future in futures:
            output_sections.append(future.result())

    return "\n\n".join(output_sections)

# 3. Pydantic Schema
class CrewRequest(BaseModel):
    user_id: str
    callback_url: str
    matchday: str
    team_name: str

# 4. Asynchronous Background Worker
def execute_crew_workflow(user_id: str, callback_url: str, matchday: str, team_name: str):
    logging.info(f"Starting execution for user_id: {user_id}")
    try:
        # Step 1: Fetch all data concurrently in Python (~1-2 seconds)
        raw_data = get_all_fantasy_data_fast(user_id, matchday)

        # Step 2: Define ONLY the Analyst Agent
        ff_data_analyst_agent = Agent(
            role="Fantasy Football Data Analyst Agent",
            goal="Analyse the lineup, real world fixture, current league table standings, team and player performance data in order to recommend the best lineup.",
            backstory="You are a fantasy football data analyst who aims to recommend the best lineup for the home team for a given matchweek fixture.",
            allow_delegation=False,
            llm=my_llm,
            verbose=True
        )

        analyse_data = Task(
            description=(
                f"Below is the complete dataset containing squad, fixtures, stats, standings, injuries, and data dictionary:\n\n"
                f"{raw_data}\n\n"
                "INSTRUCTIONS:\n"
                "1. Utilise the data dictionary to understand the data definitions.\n"
                "2. Analyse the lineup, real world fixture, league table, player and team attacking and defending stats.\n"
                "3. Use the rules of the fantasy football game:\n"
                "- Defensive score: Goalkeeper + Defenders total goals conceded divided by 5.\n"
                "- Subtract goals conceded from total goals scored by starting players.\n"
                "- Do NOT select injured players.\n"
                "4. Recommend the best home team lineup. Provide a short, concise one-line summary per player detailing the logic and stats used. Always mention the team the player is playing against that gameweek in the logic used summary."
            ),
            expected_output="Recommendation of the home team lineup with one line per player highlighting logic and stats used.",
            agent=ff_data_analyst_agent,
        )

        # Step 3: Run Crew with 1 Agent and 1 Task
        crew = Crew(
            agents=[ff_data_analyst_agent],
            tasks=[analyse_data],
            verbose=True
        )

        result = crew.kickoff()
        
        payload = {
            "status": "completed",
            "user_id": user_id,
            "matchday": matchday,
            "team_name": team_name,
            "result": str(result.raw)
        }
    except Exception as e:
        logging.error(f"Crew failed for user {user_id}: {str(e)}")
        payload = {
            "status": "failed",
            "user_id": user_id,
            "error": str(e)
        }

    # Callback to Rails
    try:
        with httpx.Client() as client:
            client.post(callback_url, json=payload, timeout=30.0)
        logging.info(f"Callback successfully sent to Rails for user_id: {user_id}")
    except Exception as callback_err:
        logging.error(f"Failed to transmit callback to Rails: {str(callback_err)}")

# 5. FastAPI Entrypoint
@app.post("/api/v1/lineup-analysis")
async def start_analysis(request: CrewRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(execute_crew_workflow, request.user_id, str(request.callback_url), request.matchday, request.team_name)
    return {"status": "processing", "message": "CrewAI agents are running asynchronously. A webhook will follow."}