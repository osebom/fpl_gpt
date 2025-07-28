# FPL Player Comparison API

A Flask API that compares Fantasy Premier League players and their upcoming fixtures.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

The API will be available at `http://localhost:5000`

## Usage

### Compare Players

**Endpoint:** `GET /compare`

**Parameters:**
- `players`: Comma-separated list of player names

**Example:**
```
GET /compare?players=Haaland,Salah,Kane
```

**Response:**
Returns player information including:
- Player name and team
- Current price and points per game
- Next 4 fixtures with difficulty ratings
- Summary of fixture difficulties

## Features

- Fuzzy player name matching
- FPL data integration via official API
- Fixture difficulty ratings (FDR)
- Player status and performance metrics 