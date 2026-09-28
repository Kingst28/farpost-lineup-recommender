import os
import warnings
import logging
from typing import Type
import httpx
import pandas as pd
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, HttpUrl, Field
from sqlalchemy import create_engine, text
from google.cloud.sql.connector import Connector, IPTypes

# CrewAI imports
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool

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

# 2. Batch Database & Data Dictionary Tool (Replaces single query tool)
class BatchFantasyDataInput(BaseModel):
    user_id: str = Field(..., description="The user ID to fetch fantasy football data for.")
    matchday: str = Field(..., description="The matchday/round number.")

class BatchFantasyDataTool(BaseTool):
    name: str = "Batch Fantasy Data Tool"
    description: str = "Retrieves all fantasy football datasets (squad, fixtures, stats, standings, injuries) and data dictionary definitions in a single call."
    args_schema: Type[BaseModel] = BatchFantasyDataInput

    def _run(self, user_id: str, matchday: str) -> str:
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
        
        # 1. Read Data Dictionary CSV directly
        try:
            if os.path.exists("farpost_data_dictionary.csv"):
                dict_df = pd.read_csv("farpost_data_dictionary.csv")
                output_sections.append("### DATA DICTIONARY DEFINITIONS\n" + dict_df.to_markdown(index=False))
        except Exception as e:
            output_sections.append(f"### DATA DICTIONARY DEFINITIONS\nError reading dictionary: {str(e)}")

        # 2. Execute all SQL queries sequentially in Python
        with engine.connect() as conn:
            for section_name, sql_query in queries.items():
                try:
                    df = pd.read_sql(text(sql_query), con=conn)
                    table_str = "No rows returned." if df.empty else df.to_markdown(index=False)
                except Exception as e:
                    table_str = f"Error executing query: {str(e)}"
                output_sections.append(f"### {section_name}\n{table_str}")

        return "\n\n".join(output_sections)

batch_fantasy_data_tool = BatchFantasyDataTool()

# 3. Pydantic Schema for incoming Rails requests
class CrewRequest(BaseModel):
    user_id: str
    callback_url: str
    matchday: str
    team_name: str

# 4. Asynchronous Background Worker
def execute_crew_workflow(user_id: str, callback_url: str, matchday: str, team_name: str):
    logging.info(f"Starting CrewAI execution for user_id: {user_id}")
    try:
        # Define Agents
        ff_data_collection_agent = Agent(
            role="Fantasy Football Data Collection Agent",
            goal="Retrieve Fantasy Football data from relevant data sources which will inform the fantasy football data analyst agent",
            backstory=(
                "Your job is to retrieve all fantasy football data sets including squad, fixtures, "
                "standings, team and player performance stats, injuries, and the data dictionary using the batch tool."
            ),
            allow_delegation=False,
            llm=my_llm,
            tools=[batch_fantasy_data_tool],
            verbose=True
        )

        ff_data_analyst_agent = Agent(
            role="Fantasy Football Data Analyst Agent",
            goal="Analyse the lineup, real world fixture, current league table standings, team and player performance "
            "data provided by the fantasy football data collection agent in order to recommend the best "
            "line up for the Home team for that gameweek in order to beat the squad of the Away team on most goals scored and fewest goals conceded.",
            backstory=(
                "You are a fantasy football data analyst who aims to recommend the best lineup for the home "
                "team for a given matchweek fixture. You will base your recommendation off of the squad of "
                "the home team and the real world Premier League fixtures for that matchweek. "
                "In addition to these data sets, you will also utilise the current Premier League table and "
                "season player performance data for each player (and the clubs they play for) in the lineups to make the recommendation."
            ),
            allow_delegation=False,
            llm=my_llm,
            verbose=True
        )

        # Simplified Task description to trigger exactly 1 tool call
        extract_data = Task(
            description=(
                f"Extract all required fantasy football datasets and data dictionary definitions in a single call using the "
                f"'Batch Fantasy Data Tool' with user_id = '{user_id}' and matchday = '{matchday}'."
            ),
            expected_output="A comprehensive markdown dataset containing all 10 SQL query results and data dictionary definitions.",
            agent=ff_data_collection_agent,
        )

        analyse_data = Task(
            description=(
                "1. Utilise the data dictionary to understand the data definitions and how to effectively use the data in your analysis /n"
                "2. Analyse the lineup, real world fixture, league table, player and team attacking and defending stats data provided by the data collection agent /n"
                "3. Use the rules of the fantasy football game here: /n"

                "On a ‘Match weekend’ your team will have a score calculated as follows: /n"

                "(i) any goals conceded during the relevant weekend by your goalkeeper and /n"

                "defenders will count against you even if you have all 5 players from the /n"

                "same team. For instance – if your goalkeeper and defenders are all Crystal /n"

                "Palace players and they concede 2 goals during their weekend match then /n"

                "all 5 players will count the 2 goals conceded against them hence arriving at /n"

                "a total of 10. /n"

                "(ii) once you have counted up the total number of goals conceded by your /n"

                "goalkeeper and defenders you divide that total by 5 to /n"

                "calculate how many goals your team has conceded. Using the example /n"

                "above your team will have obviously conceded 2 goals. [10 ÷ 5 = 2] /n"

                "(iii) if your defence concedes 11-14 goals in total that will still equate to 2 /n"

                "goals conceded by your team, 15-19 will equate to 3 goals etc. and so on. /n"

                "(iv) your team will then total the number of goals scored by any of your /n"

                "players deemed to have played in your 1st eleven for that /n"

                "weekend/midweek. The organiser will try and verify goal scorers on at /n"

                "least two sites if there are any queries as to who scored. /n"

                "(v) you then subtract the number of goals conceded from the number of goals /n"

                "scored to calculate what your team has scored that weekend. For instance /n"

                "– your defence has conceded 2 goals but 3 of your players have scored. /n"

                "(vi) players do not have to have played a full game to count as having played /n"

                "but any goals conceded during the match will count against defenders /n"

                "even if they only come on for the last minute of the match. /n"

                "(vii) if an own goal is scored by your goalkeeper or defenders there is no /n"

                "added disadvantage to your team. /n"

                "(viii) your team will also concede one extra goal for every position in defence /n"

                "(goalkeeper and 4 defenders) that you fail to field. /n"

                "(ix) On a 'match weekend' your team will have a score by the API calculated as follows. /n"
                "The organiser will use the details issued or standing on the morning after a set of matches have been played /n"
                "and this will stand even if any other official 'dubious goals' committee credit someone else as scoring that goal at /n"
                "a later date. Due to the way the fantasy football league is run there will be no facility to change goal scorers and any /n"
                "subsequent match scores due to this process. /n"

                "to recommend the best lineup. /n"
                "4. Analyse each player in the Home team lineup individually taking into consideration thier individual and club attacking and defending stats, the real world fixture, league table and injury data. /n"
            ),
            expected_output="Recommendation of the home team lineup (if the team formation is 4-4-2 then 1 Goalkeeper, 4 Defenders, 4 Midfielders, 2 Strikers or if the formation is 4-3-3 1 Goalkeeper, 4 Defenders, 3 Midfielders, 3 Strikers) the fantasy football player should select for the gameweek in order to beat the away team squad based on all data available, game rules and ensuring the player is not injured and makes a high number of appearances for his team. Ensure the players picked are only players from the home team lineup data even if there are no stats available attacking and defending wise for an individual player. Provide a short and concise summary on one line per player of the logic used always highlighting along the way the stats used.",
            agent=ff_data_analyst_agent,
        )

        crew = Crew(
            agents=[ff_data_collection_agent, ff_data_analyst_agent],
            tasks=[extract_data, analyse_data],
            verbose=True
        )

        # Kickoff orchestration
        result = crew.kickoff()
        
        # Outbound Payload back to Ruby on Rails
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

    # Post back to Rails Webhook Controller
    try:
        with httpx.Client() as client:
            client.post(callback_url, json=payload, timeout=30.0)
        logging.info(f"Callback successfully sent to Rails for user_id: {user_id}")
    except Exception as callback_err:
        logging.error(f"Failed to transmit callback to Rails: {str(callback_err)}")

# 5. FastAPI HTTP Entry Endpoint
@app.post("/api/v1/lineup-analysis")
async def start_analysis(request: CrewRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(execute_crew_workflow, request.user_id, str(request.callback_url), request.matchday, request.team_name)
    return {"status": "processing", "message": "CrewAI agents are running asynchronously. A webhook will follow."}