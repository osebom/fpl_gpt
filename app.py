from flask import Flask, request, jsonify
import requests
import unicodedata
from difflib import get_close_matches
import os

app = Flask(__name__)

# Health check endpoint
@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "message": "FPL API is running!"})

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

# Load all FPL data
def load_fpl_data():
    static = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/").json()
    fixtures = requests.get("https://fantasy.premierleague.com/api/fixtures/").json()
    return static['elements'], static['teams'], fixtures

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

# Get team name
def get_team_name(team_id, teams):
    for t in teams:
        if t['id'] == team_id:
            return t['name']
    return "Unknown"

# Get next 4 fixtures
def get_next_fixtures(team_id, fixtures, teams):
    upcoming = []
    for f in fixtures:
        if f['team_h'] == team_id or f['team_a'] == team_id:
            is_home = f['team_h'] == team_id
            opp_id = f['team_a'] if is_home else f['team_h']
            difficulty = f['team_h_difficulty'] if is_home else f['team_a_difficulty']
            upcoming.append({
                "opponent": get_team_name(opp_id, teams),
                "home": is_home,
                "difficulty": difficulty,
                "label": fdr_labels.get(difficulty, "Unknown"),
                "kickoff_time": f['kickoff_time']
            })
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
    query = request.args.get('players')
    if not query:
        return jsonify({"error": "Missing 'players' parameter"}), 400

    names = [n.strip() for n in query.split(",")]
    players, teams, fixtures = load_fpl_data()

    results = []
    for name in names:
        player, suggestion = match_player(name, players)
        if player:
            team_name = get_team_name(player['team'], teams)
            next_games = get_next_fixtures(player['team'], fixtures, teams)
            summary = summarize_difficulty(next_games)

            results.append({
                "player": f"{player['first_name']} {player['second_name']}",
                "team": team_name,
                "price": player['now_cost'] / 10,
                "ppg": float(player['points_per_game']),
                "status": player['status'],
                "fixtures": next_games,
                "summary": summary
            })
        else:
            msg = {
                "error": f"No match for '{name}'"
            }
            if suggestion:
                msg["suggestion"] = suggestion
            results.append(msg)

    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True) 