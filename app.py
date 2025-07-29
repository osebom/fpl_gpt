from flask import Flask, request, jsonify
import requests
import unicodedata
from difflib import get_close_matches
import os
from datetime import datetime
from collections import OrderedDict
import json

app = Flask(__name__)

# Custom JSON encoder to preserve order
class OrderedJSONEncoder(json.JSONEncoder):
    def encode(self, obj):
        if isinstance(obj, OrderedDict):
            return '{' + ','.join(f'"{k}":{self.encode(v)}' for k, v in obj.items()) + '}'
        return super().encode(obj)

app.json_encoder = OrderedJSONEncoder

# Health check endpoint
@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "message": "FPL API is running!"})

# Test endpoint
@app.route('/test')
def test():
    return jsonify({"message": "API is working!", "test": "success"})

# Normalize name for matching
def normalize(text):
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode("utf-8")
    return text.strip().lower()

# Map FDR to labels
fdr_labels = {
    1: "Very Easy",
    2: "Easy",
    3: "Evenly Matched",
    4: "Difficult",
    5: "Likely To Lose"
}

# Load historical match data from openfootball
def load_historical_data():
    try:
        # Load last two seasons
        seasons = [
            ("2023-24", "2023/24"),
            ("2022-23", "2022/23")
        ]
        
        all_matches = []
        for season_code, season_name in seasons:
            url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{season_code}/en.1.json"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for match in data.get('matches', []):
                    if 'score' in match and 'ft' in match['score']:
                        match['season'] = season_name
                        all_matches.append(match)
        
        return all_matches
    except Exception as e:
        print(f"Error loading historical data: {e}")
        return []

# Find head-to-head matches between two teams
def find_head_to_head_matches(team1_name, team2_name, historical_matches):
    matches = []
    
    # Normalize team names for comparison
    team1_norm = normalize(team1_name)
    team2_norm = normalize(team2_name)
    
    for match in historical_matches:
        team1_match = normalize(match['team1'])
        team2_match = normalize(match['team2'])
        
        # Check if this match involves both teams
        if (team1_norm in team1_match and team2_norm in team2_match) or \
           (team1_norm in team2_match and team2_norm in team1_match):
            
            # Determine which team is which
            if team1_norm in team1_match:
                home_team = team1_name
                away_team = team2_name
                home_score = match['score']['ft'][0]
                away_score = match['score']['ft'][1]
            else:
                home_team = team2_name
                away_team = team1_name
                home_score = match['score']['ft'][1]
                away_score = match['score']['ft'][0]
            
            matches.append({
                'date': match['date'],
                'season': match['season'],
                'home_team': home_team,
                'away_team': away_team,
                'home_score': home_score,
                'away_score': away_score
            })
    
    # Sort by date (most recent first) and take last 4
    matches.sort(key=lambda x: x['date'], reverse=True)
    return matches[:4]

# Generate head-to-head summary
def generate_h2h_summary(matches, player_team):
    if not matches:
        return "No recent matches"
    
    wins = 0
    draws = 0
    losses = 0
    
    for match in matches:
        if match['home_team'] == player_team:
            # Player's team was home
            if match['home_score'] > match['away_score']:
                wins += 1
            elif match['home_score'] < match['away_score']:
                losses += 1
            else:
                draws += 1
        else:
            # Player's team was away
            if match['away_score'] > match['home_score']:
                wins += 1
            elif match['away_score'] < match['home_score']:
                losses += 1
            else:
                draws += 1
    
    # Build summary string
    parts = []
    if wins > 0:
        parts.append(f"{wins} win{'s' if wins != 1 else ''}")
    if draws > 0:
        parts.append(f"{draws} draw{'s' if draws != 1 else ''}")
    if losses > 0:
        parts.append(f"{losses} loss{'es' if losses != 1 else ''}")
    
    return ", ".join(parts) if parts else "No recent matches"

# Format head-to-head data for API response
def format_h2h_data(matches, player_team):
    if not matches:
        return None
    
    formatted_matches = []
    for match in matches:
        # Determine result and venue from player's team perspective
        if match['home_team'] == player_team:
            venue = "home"
            if match['home_score'] > match['away_score']:
                result = "W"
            elif match['home_score'] < match['away_score']:
                result = "L"
            else:
                result = "D"
        else:
            venue = "away"
            if match['away_score'] > match['home_score']:
                result = "W"
            elif match['away_score'] < match['home_score']:
                result = "L"
            else:
                result = "D"
        
        formatted_matches.append({
            "date": match['date'],
            "season": match['season'],
            "result": result,
            "venue": venue,
            "full_time_score": f"{match['home_score']}-{match['away_score']}"
        })
    
    summary = generate_h2h_summary(matches, player_team)
    
    return {
        "summary": summary,
        "matches": formatted_matches
    }

# Load all FPL data with timeout and error handling
def load_fpl_data():
    try:
        # Add timeout to prevent hanging
        static = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=10).json()
        fixtures = requests.get("https://fantasy.premierleague.com/api/fixtures/", timeout=10).json()
        return static['elements'], static['teams'], fixtures
    except Exception as e:
        print(f"Error loading FPL data: {e}")
        return [], [], []

# Match player
def match_player(name, players):
    name_clean = normalize(name)
    player_map = {}
    for p in players:
        web = normalize(p['web_name'])
        full = normalize(f"{p['first_name']} {p['second_name']}")
        last = normalize(p['second_name'])
        for variant in [web, full, last]:
            player_map[variant] = p

    if name_clean in player_map:
        return player_map[name_clean], None

    close = get_close_matches(name_clean, list(player_map.keys()), n=1, cutoff=0.6)
    return (None, close[0]) if close else (None, None)

# Team name mapping for FPL to openfootball
team_name_mapping = {
    "Man City": "Manchester City",
    "Man Utd": "Manchester United", 
    "Spurs": "Tottenham Hotspur",
    "Newcastle": "Newcastle United",
    "Brighton": "Brighton & Hove Albion",
    "West Ham": "West Ham United",
    "Crystal Palace": "Crystal Palace",
    "Aston Villa": "Aston Villa",
    "Brentford": "Brentford",
    "Fulham": "Fulham",
    "Wolves": "Wolverhampton Wanderers",
    "Burnley": "Burnley",
    "Luton": "Luton Town",
    "Sheffield Utd": "Sheffield United",
    "Nottingham Forest": "Nottingham Forest",
    "Nott'm Forest": "Nottingham Forest",
    "Everton": "Everton",
    "Chelsea": "Chelsea",
    "Liverpool": "Liverpool",
    "Arsenal": "Arsenal",
    "Bournemouth": "AFC Bournemouth"
}

# Get team name
def get_team_name(team_id, teams):
    for t in teams:
        if t['id'] == team_id:
            return t['name']
    return "Unknown"

# Map FPL team name to openfootball format
def map_team_name(fpl_name):
    return team_name_mapping.get(fpl_name, fpl_name)

# Get next 4 fixtures with head-to-head data
def get_next_fixtures(team_id, fixtures, teams, historical_matches):
    upcoming = []
    for f in fixtures:
        if f['team_h'] == team_id or f['team_a'] == team_id:
            is_home = f['team_h'] == team_id
            opp_id = f['team_a'] if is_home else f['team_h']
            difficulty = f['team_h_difficulty'] if is_home else f['team_a_difficulty']
            
            # Get team names
            team_name = get_team_name(team_id, teams)
            opp_name = get_team_name(opp_id, teams)
            
            # Map to openfootball format
            team_name_mapped = map_team_name(team_name)
            opp_name_mapped = map_team_name(opp_name)
            
            # Get head-to-head data
            h2h_matches = find_head_to_head_matches(team_name_mapped, opp_name_mapped, historical_matches)
            h2h_data = format_h2h_data(h2h_matches, team_name_mapped)
            
            # Debug: print what we're looking for
            print(f"Looking for H2H: {team_name_mapped} vs {opp_name_mapped}")
            print(f"Found {len(h2h_matches)} matches")
            
            fixture_data = OrderedDict([
                ("opponent", opp_name),
                ("home", is_home),
                ("kickoff_time", f['kickoff_time']),
                ("label", fdr_labels.get(difficulty, "Unknown")),
                ("difficulty", difficulty)
            ])
            
            if h2h_data:
                fixture_data["head_to_head"] = h2h_data
            
            upcoming.append(fixture_data)
    
    upcoming = sorted(upcoming, key=lambda x: x['kickoff_time'])[:4]
    return upcoming

# Count FDR labels
def summarize_difficulty(fixtures):
    counts = {}
    for f in fixtures:
        label = f['label']
        counts[label] = counts.get(label, 0) + 1
    return ", ".join([f"{v} {k.lower()}" for k, v in counts.items()])

# Main endpoint
@app.route('/compare', methods=['GET'])
def compare_players():
    try:
        query = request.args.get('players')
        if not query:
            return jsonify({"error": "Missing 'players' parameter"}), 400

        names = [n.strip() for n in query.split(",")]
        players, teams, fixtures = load_fpl_data()
        
        if not players:
            return jsonify({"error": "Unable to load FPL data. Please try again later."}), 500

        # Load historical data once for all players
        historical_matches = load_historical_data()

        results = []
        for name in names:
            player, suggestion = match_player(name, players)
            if player:
                team_name = get_team_name(player['team'], teams)
                next_games = get_next_fixtures(player['team'], fixtures, teams, historical_matches)
                summary = summarize_difficulty(next_games)

                player_data = OrderedDict([
                    ("player", f"{player['first_name']} {player['second_name']}"),
                    ("team", team_name),
                    ("price", player['now_cost'] / 10),
                    ("ppg", float(player['points_per_game'])),
                    ("status", player['status']),
                    ("summary", summary),
                    ("fixtures", next_games)
                ])
                results.append(player_data)
            else:
                msg = {
                    "error": f"No match for '{name}'"
                }
                if suggestion:
                    msg["suggestion"] = suggestion
                results.append(msg)

        response = Flask.response_class(
            json.dumps(results, cls=OrderedJSONEncoder, indent=2),
            mimetype='application/json'
        )
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False) 