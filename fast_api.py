from abc import abstractmethod
import os
import warnings
import logging
import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, HttpUrl
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
    temperature=0.7
)

# 2. Database Tool
class CloudSQLQueryTool(BaseTool):
    name: str = "Cloud SQL Query Tool"
    description: str = "Use this tool to query the Google Cloud SQL database. Input should be a raw SQL query."

    @abstractmethod
    def _run(self, query: str) -> str:
        db_url = os.environ.get("DATABASE_URL")
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            return str(rows)

cloud_sql_tool = CloudSQLQueryTool()

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
                "Your job is to retrieve a set of pre-defined fantasy football related data. "
                "These data sets include home team squad data for the current matchweek, "
                "the real world fixtures for the current matchweek in the Premier League, "
                "the current Premier League table standings, "
                "the attacking and defending performance data for the current season of each player and club they play for found in the line ups, "
                "the current injuries data for players in the Premier League. "
    
            ),
            allow_delegation=False,
            llm=my_llm,
            tools=[cloud_sql_tool],
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

        # Tasks dynamically modifying user_id based on the Rails request payload
        extract_data = Task(
            description=(
                f"1. Extract home team squad data using the cloud_sql_tool via this SQL Query 'select t.api_player_id, t.name, p.position, te.name as team from teamsheets t left join players p on t.api_player_id = p.api_player_id left join teams te on p.teams_id = te.id where user_id = '{user_id}' and p.account_id = t.account_id ORDER BY position;'\n"
                f"2. Extract the current matchweeks fixture data using the cloud_sql_tool via this SQL Query 'select round, hteamid, hteamname, ateamid, ateamname from prem_fixtures where round = '{matchday}';'\n"
                f"3. Extract the player attacking stats data for each home team player using the cloud_sql_tool via this SQL Query 'SELECT api_player_id, name, injured, team_id, team_name, appearances, lineups, position, rating, shots_total, shots_on, goals_total, goals_assists, passes_key, passes_accuracy, dribbles_attempts, dribbles_success, fouls_drawn FROM player_statistics WHERE api_player_id IN (SELECT api_player_id FROM teamsheets WHERE user_id = '{user_id}');'\n"
                f"4. Extract the team defensive stats data for each home team players club using the cloud_sql_tool via this SQL Query 'select team_id, name, played_home, played_away, played_total, goals_against_home, goals_against_away, avg_goals_against_home, avg_goals_against_away, avg_goals_against_total, clean_sheets_home, clean_sheets_away from team_statistics WHERE team_id IN (SELECT id FROM teams where id IN (SELECT p.teams_id FROM teamsheets t LEFT JOIN players p ON t.api_player_id = p.api_player_id WHERE t.user_id = '{user_id}'));'\n"
                f"5. Extract the team attacking stats data for each home team players club using the cloud_sql_tool via this SQL Query 'select team_id, name, played_home, played_away, played_total, wins_home, wins_away, draws_home, draws_away, losses_home, losses_away goals_for_home, goals_for_away, avg_goals_for_home, avg_goals_for_away, avg_goals_for_total, failed_to_score_home, failed_to_score_away from team_statistics WHERE team_id IN (SELECT id FROM teams where id IN (SELECT p.teams_id FROM teamsheets t LEFT JOIN players p ON t.api_player_id = p.api_player_id WHERE t.user_id = '{user_id}'));'\n"
                f"6. Extract the player defensive stats data for each home team player via the api_player_id from the home team player using the cloud_sql_tool via this SQL Query 'select api_player_id, name, injured, team_id, team_name, appearances, lineups, position, rating, goals_conceded, tackles_total, tackles_blocks, tackles_interceptions, duels_total, duels_won, fouls_committed from player_statistics WHERE api_player_id IN (SELECT api_player_id FROM teamsheets WHERE user_id = '{user_id}' and position = 'Defender');'\n"
                f"7. Extract the goalkeeper stats data for each home team player using the cloud_sql_tool via this SQL Query 'select api_player_id, name, team_id, team_name, appearances, lineups, position, rating, goals_conceded, goals_saves, duels_total, duels_won FROM player_statistics WHERE api_player_id IN (SELECT api_player_id FROM teamsheets WHERE user_id = '{user_id}' and position = 'Goalkeeper');'\n"
                f"8. Extract the current injured players data for the Premier League from the home team lineup data using the cloud_sql_tool via this SQL Query 'select api_player_id, name, injured, team_id, team_name, position from player_statistics WHERE api_player_id IN (SELECT api_player_id FROM teamsheets WHERE user_id = '{user_id}');'. If a player is injured remove the player from the recommendation\n"
                f"9. Extract the current Premier League table using the cloud_sql_tool via this SQL Query 'select * from standings;'"
            ),
            expected_output="A comprehensive set of data you can provide to the Fantasy Football Data Analyst Agent",
            agent=ff_data_collection_agent,
        )

        analyse_data = Task(
            description=(
                "1. Analyse the lineup, real world fixture, league table, player and team attacking and defending stats data provided by the data collection agent /n"
                "2. Use the rules of the fantasy football game here: /n"

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
        "3. In the player attacking stats data set, the goals_total column is the total amount of goals the player has scored, goals_assists is the total amount of assists the player has provided. /n"
        "4. Always use the player position from the home team squad data as the source of truth. /n"
        "5. In the injured players data set, False means the player is not injured so is available to play. /n"
        "6. Analyse each player in the Home team lineup individually taking into consideration thier individual and club attacking and defending stats, the real world fixture, league table and injury data. /n"
            ),
            expected_output="Recommendation of the Home Team lineup (1 Goalkeeper, 4 Defenders, 4 Midfielders, 2 Strikers) the fantasy football player should select for the gameweek in order to beat the Away team squad based on all data available, game rules and ensuring the player is not injured and makes a high number of appearances for his team. Ensure the players picked are only players from the home team lineup data even if there are no stats available attacking and defending wise for an individual player. Provide a short and concise summary of the logic used always highlighting along the way the stats used.",
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
    # Enqueue execution thread instantly and respond with 202
    background_tasks.add_task(execute_crew_workflow, request.user_id, str(request.callback_url), request.matchday, request.team_name)
    return {"status": "processing", "message": "CrewAI agents are running asynchronously. A webhook will follow."}