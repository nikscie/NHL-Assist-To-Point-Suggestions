import requests
import pandas
import time
from requests.exceptions import RequestException, ConnectionError

# YYYYYYYY format season ID; 20252026, 20242025, ect. 
# previous seasons with more games will take more time :(
SEASON = "20252026"

# team configs from NHL API
teams = [
    {"name": "New Jersey Devils", "abbr": "NJD", "id": 1},
    {"name": "New York Islanders", "abbr": "NYI", "id": 2},
    {"name": "New York Rangers", "abbr": "NYR", "id": 3},
    {"name": "Philadelphia Flyers", "abbr": "PHI", "id": 4},
    {"name": "Pittsburg Penguins", "abbr": "PIT", "id": 5},
    {"name": "Boston Bruins", "abbr": "BOS", "id": 6},
    {"name": "Buffalo Sabres", "abbr": "BUF", "id": 7},
    {"name": "Montreal Canadiens", "abbr": "MTL", "id": 8},
    {"name": "Ottawa Senators", "abbr": "OTT", "id": 9},
    {"name": "Toronto Maple Leafs", "abbr": "TOR", "id": 10},
    {"name": "Carolina Hurricanes", "abbr": "CAR", "id": 12},
    {"name": "Florida Panthers", "abbr": "FLA", "id": 13},
    {"name": "Tampa Bay Lightning", "abbr": "TBL", "id": 14},
    {"name": "Washington Capitals", "abbr": "WSH", "id": 15},
    {"name": "Chicago Blackhawks", "abbr": "CHI", "id": 16},
    {"name": "Detroit Red Wings", "abbr": "DET", "id": 17},
    {"name": "Nashville Predators", "abbr": "NSH", "id": 18},
    {"name": "St. Louis Blues", "abbr": "STL", "id": 19},
    {"name": "Calgary Flames", "abbr": "CGY", "id": 20},
    {"name": "Colorado Avalanche", "abbr": "COL", "id": 21},
    {"name": "Edmonton Oilers", "abbr": "EDM", "id": 22},
    {"name": "Vancouver Canucks", "abbr": "VAN", "id": 23},
    {"name": "Anaheim Ducks", "abbr": "ANA", "id": 24},
    {"name": "Dallas Stars", "abbr": "DAL", "id": 25},
    {"name": "Los Angeles Kings", "abbr": "LAK", "id": 26},
    {"name": "San Jose Sharks", "abbr": "SJS", "id": 28},
    {"name": "Columbus Blue Jackets", "abbr": "CBJ", "id": 29},
    {"name": "Minnesota Wild", "abbr": "MIN", "id": 30},
    {"name": "Winnipeg Jets", "abbr": "WPG", "id": 52},
    {"name": "Vegas Golden Knights", "abbr": "VGK", "id": 54},
    {"name": "Seattle Kraken", "abbr": "SEA", "id": 55},
    {"name": "Utah Mammoth", "abbr": "UTA", "id": 68},
]

# this section of code is to scrape the data from NHL API

# for use instead of requests.get(), adds retry and backoff to amend server disconnection issues
def safe_get(url, max_retries=5, backoff=2):
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp
        except (ConnectionError, RequestException) as e:
            wait = backoff * (2 ** attempt)
            print(f"Request failed ({e}), retrying in {wait}s…")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} retries")

# get players
def get_team_roster(team_abbr, team_name):
    url = f"https://api-web.nhle.com/v1/roster/{team_abbr}/{SEASON}"
    resp = safe_get(url)
    # resp contains status code, check status code not an error; aka HTTP successful
    resp.raise_for_status()
    data = resp.json()
    players = data.get("forwards", []) + data.get("defensemen", []) + data.get("goalies", [])
    df = pandas.DataFrame(players)
    
    # parses player name from dict/string -> string
    def get_name(field):
        if isinstance(field, dict):
            return field.get("default", "")
        return field or ""

    # pair names with IDs to use with PBP data
    df["firstName_clean"] = df["firstName"].apply(get_name)
    df["lastName_clean"] = df["lastName"].apply(get_name)
    df["fullName"] = df["firstName_clean"] + " " + df["lastName_clean"]
    id_to_name = dict(zip(df["id"], df["fullName"]))
    print(f"Loaded {len(id_to_name)} {team_name} players")
    return id_to_name

# get schedule for given team
def get_team_schedule(team_abbr, team_name):
    url = f"https://api-web.nhle.com/v1/club-schedule-season/{team_abbr}/{SEASON}"
    resp = safe_get(url)
    # make sure the http request was successful
    resp.raise_for_status()
    # flatten JSON data into df
    schedule_data = pandas.json_normalize(resp.json(), "games")
    # only use completed games
    played_games = schedule_data[schedule_data["gameState"].str.startswith("OFF")]
    print(f"Found {len(played_games)} completed games for {team_name}")
    return played_games

# get goal info for given team (sorting out goals by the other team)
def get_team_goals(team_id, played_games):
    goal_data = []
    # for each game 
    for _, game in played_games.iterrows():
        game_id = game["id"]
        date = game["gameDate"]
        url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
        resp = safe_get(url)
        if resp.status_code != 200:
            continue
        # only keep scoring info
        plays = resp.json().get("plays", [])
        for p in plays:
            if p.get("typeDescKey") == "goal":
                details = p.get("details", {})
                if details.get("eventOwnerTeamId") != team_id:
                    continue
                goal_data.append({
                    "gameId": game_id,
                    "date": date,
                    "scorer": details.get("scoringPlayerId"),
                    "assist1": details.get("assist1PlayerId"),
                    "assist2": details.get("assist2PlayerId"),
                })
    df = pandas.DataFrame(goal_data)
    return df

# the below code is to get correlation data

# loop through teams
for team in teams:
    name = team["name"]
    abbr = team["abbr"]
    tid = team["id"]

    print(f"\nProcessing {name} ({abbr})")

    # roster and mapping
    id_to_name = get_team_roster(abbr, name)

    # schedule and completed games
    played_games = get_team_schedule(abbr, name)
    if played_games.empty:
        print(f"No completed games for {name}")
        continue

    # goal data
    goals_df = get_team_goals(tid, played_games)
    if goals_df.empty:
        print(f"No {name} goal data")
        continue

    # map IDs -> names
    for col in ["scorer", "assist1", "assist2"]:
        goals_df[col] = goals_df[col].map(id_to_name).fillna(goals_df[col])

    # compute assist -> any point on same goal 
    # dropna gets rid of blank assists
    # unique gets rid of duplicate names; ie one name per player who's ever gotten an assist/point
    assisters = pandas.Series(pandas.concat([goals_df['assist1'], goals_df['assist2']])).dropna().unique()
    players_all = pandas.Series(pandas.concat([goals_df['scorer'], goals_df['assist1'], goals_df['assist2']])).dropna().unique()
    # create a data frame with a row per assist-getter, and a column for anyone who's gotten a point this season
    co_assist_point = pandas.DataFrame(index=assisters, columns=players_all, dtype=float)

    for assister in assisters:
        # get all goals where this player registers an assist
        goals_with_assist = goals_df[
            (goals_df['assist1'] == assister) | (goals_df['assist2'] == assister)
        ]
        # get total assist count
        n_assists = len(goals_with_assist)
        # incase we somehow got someone without an assist
        if n_assists == 0:
            co_assist_point.loc[assister] = 0
            continue
        # for each other player who's recorded a point this season, 
        # count the number of points recorded on the same goal as our assister
        for player in players_all:
            count = (
                (goals_with_assist['scorer'] == player) |
                (goals_with_assist['assist1'] == player) |
                (goals_with_assist['assist2'] == player)
            ).sum()
            # get probability
            co_assist_point.loc[assister, player] = count / n_assists

    # set diagonals to 0; we don't want to suggest betting on the same player twice
    for assister in assisters:
        if assister in co_assist_point.columns:
            co_assist_point.loc[assister, assister] = 0.0

    # save to csv for suggestion program to use
    out_path = f"{abbr}_assist_point_same_goal_{SEASON}.csv"
    co_assist_point.to_csv(out_path)
    print(f"saved as {out_path}")
