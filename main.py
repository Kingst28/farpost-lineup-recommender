# Warning control
import warnings
warnings.filterwarnings('ignore')

from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import FileReadTool
from crewai_tools import StagehandTool
from stagehand.schemas import AvailableModel
from google import genai
import os

# 1. Access keys from Codespaces Secrets
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BROWSERBASE_API_KEY = os.environ.get('BROWSERBASE_API_KEY')
BROWSERBASE_PROJECT_ID = os.environ.get('BROWSERBASE_PROJECT_ID')

# 2. Define the LLM using CrewAI's native class
# Note the provider prefix 'gemini/' which is required for LiteLLM routing
my_llm = LLM(
    model='gemini/gemini-2.5-flash',
    api_key=GEMINI_API_KEY,
)

home_line_up_file_read_tool = FileReadTool(file_path='home_team.csv')

away_line_up_file_read_tool = FileReadTool(file_path='away_team.csv')

fixtures_file_read_tool = FileReadTool(file_path='fixtures_matchweek_10.csv')

fixtures_difficulty_file_read_tool = FileReadTool(file_path='fixture_difficulty_rating.csv')

injury_difficulty_file_read_tool = FileReadTool(file_path='injuries.csv')

attacking_stats_file_read_tool = FileReadTool(file_path='attacking_stats.csv')

team_defensive_stats_file_read_tool = FileReadTool(file_path='team_defending_stats.csv')

team_attacking_stats_file_read_tool = FileReadTool(file_path='team_attacking_stats.csv')

defending_stats_file_read_tool = FileReadTool(file_path='defending_stats.csv')

goalkeeping_stats_file_read_tool = FileReadTool(file_path='goalkeeping_stats.csv')

# Initialize the tool with your API keys using a context manager
with StagehandTool(
    api_key=BROWSERBASE_API_KEY,
    project_id=BROWSERBASE_PROJECT_ID,
    model_name='google/gemini-2.0-flash',  # Optional: specify which model to use
    model_api_key=GEMINI_API_KEY,
) as stagehand_tool:
    # Define the Scraper Agent
    scraper_agent = Agent(
      role="Data Extraction Specialist",
      goal="Extract Premier League stats and format them for CSV export.",
      backstory="You are a specialist in transforming web data into structured CSV formats.",
      tools=[stagehand_tool],
      llm = my_llm,
      verbose=True
    )

ff_data_collection_agent = Agent(
    role="Fantasy Football Data Collection Agent",
    goal="Retrieve Fantasy Football data from relevant "
    "data sources which will inform the fantasy football data analyst agent",
    backstory=(
        "Your job is to retrieve a set of pre-defined fantasy football related data. "
        "These data sets include both home team and away team line up data for the current matchweek, "
        "the real world fixtures for the current matchweek in the Premier League, "
        "the current Premier League table standings, "
        "the attacking and defending performance data for the current season of each player and club they play for found in the line ups, "
        "the current injuries data for players injured in the Premier League "
        "and the fixture difficulty rating defined by the Premier League for each real world fixture."
    ),
    allow_delegation=False,
    llm = my_llm,
    tools=[home_line_up_file_read_tool, away_line_up_file_read_tool, fixtures_file_read_tool,fixtures_difficulty_file_read_tool,
           injury_difficulty_file_read_tool, attacking_stats_file_read_tool,team_defensive_stats_file_read_tool,
           team_attacking_stats_file_read_tool, defending_stats_file_read_tool, goalkeeping_stats_file_read_tool],
    verbose=True
)

ff_data_analyst_agent = Agent(
    role="Fantasy Football Data Analyst Agent",
    goal="Analyse the lineup, real world fixture, player performance and fixture difficulty rating "
    "data provided by the fantasy football data collection agent in order to recommend the best "
    "line up for the Home team for that gameweek in order to beat the squad of the Away team on most goals scored and fewest goals conceded.",
    backstory=(
        "You are a fantasy football data analyst who aims to recommend the best lineup for the home "
        "team for a given matchweek fixture. You will base your recommendation off of the squads of both "
        "the home and away teams, the real world Premier League fixtures for that matchweek and thier corresponding "
        "fixture difficulty ratings. In addition to these data sets, you will also utilise the current Premier League "
        "season player performance data for each player (and the clubs they play for) in the lineups to make the recommendation."
    ),
    allow_delegation=False,
    llm = my_llm,
    verbose=True
)

# 4. Define the Task with File Output
player_attacking_stats_web_scrape = Task(
    description=(
        "Navigate to 'https://theanalyst.com/competition/premier-league/stats'. "
        "Extract all player attacking stats data available from the table. Navigate through all the pages to ensure you have a comprehensive data set."
        "Format the output strictly as a CSV with a header row."
    ),
    expected_output="A CSV formatted list of all players attacking stats.",
    agent=scraper_agent,
    output_file="attacking_stats.csv"  # This creates the file automatically
)

extract_data = Task(
    description=(
        "1. Extract home team lineup data from the home_team.csv file using the home_line_up_file_read_tool. \n"
        "2. Extract away team lineup data from the away_team.csv file using the away_line_up_file_read_tool. \n"
        "3. Extract the current matchweeks fixture data from the fixtures_matchweek_10.csv file using the fixtures_file_read_tool. \n"
        "4. Extract the current matchweeks fixture difficulty ratings data from the fixture_difficulty_rating.csv file using the fixtures_difficulty_file_read_tool. \n"
        "5. Extract the attacking player stats data for each home team player from the attacking_stats.csv file. \n"
        "6. Extract the team defensive stats data for each home team players club from the team_defending_stats.csv file. \n"
        "7. Extract the team attacking stats data for each home team player club from the team_attacking_stats.csv file. \n"
        "8. Extract the player defensive stats data for each home team player from the defending_stats.csv file. \n"
        "9. Extract the goalkeeper stats data for each home team player from the goalkeeper_stats.csv file. \n"
        "10. Extract the current injured players data for the Premier League from the injuries.csv file \n"
    ),
    expected_output="A comprehensive set of data you can provide to the Fantasy Football Data Analyst Agent",
    agent=ff_data_collection_agent,
)

analyse_data = Task(
    description=(
        "1. Analyse the lineup, real world fixture, player and team attacking and defending stats and the fixture difficulty rating data provided by the data collection agent /n"
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
        "3. Analyse each player in the Home team lineup individually taking into consideration thier individual and club attacking and defending stats, the real world fixture, difficulty rating and injury data. /n"
    ),
    expected_output="Recommendation of the Home Team lineup (1 Goalkeeper, 4 Defenders, 4 Midfielders, 2 Strikers) the fantasy football player should select for the gameweek in order to beat the Away team squad based on all data available, game rules and ensuring the player is not injured and makes a high number of appearances for his team. Ensure the players picked are only players from the home_team.csv file even if there are no stats available attacking and defending wise for an individual player. Provide a summary of the logic used.",
    agent=ff_data_analyst_agent,
)

crew = Crew(
    agents=[scraper_agent],
    tasks=[player_attacking_stats_web_scrape],
    verbose=False
)

result = crew.kickoff()

from IPython.display import Markdown
Markdown(result.raw)