# NCAA Women's Soccer Transfer Risk Model

Predicts the likelihood of a D1 women's soccer player transferring to another program, using game-level performance data pulled from the NCAA API.

## Project Structure

```
├── data/
│   └── raw/
│       ├── ncaa_wsoccer_raw_games.csv        # One row per player per game
│       └── ncaa_wsoccer_transfer_risk.csv    # Aggregated player-season features
├── ncaa_wsoccer_collector.py                 # Data pipeline script
├── requirements.txt
└── README.md
```

## Data Pipeline

Data is collected from the public NCAA API (`ncaa-api.henrygd.me`) in four steps:

1. **Schedule** — fetch all game dates for the season (Aug–Nov) per year
2. **Scoreboard** — for each date, extract full game IDs from the `game.url` field
3. **Boxscore** — pull individual player stats for every game (`/game/{id}/boxscore`)
4. **Aggregate** — roll up to one row per player per season with engineered features
5. **Label** — infer transfer status by comparing a player's team across consecutive seasons

> **Note:** The scoreboard returns two different game IDs. The `gameID` field is a short internal ID that does not work with the boxscore endpoint. The correct ID (7 digits) must be parsed from the `url` field, e.g. `/game/6348656`.

## Output Files

### `ncaa_wsoccer_raw_games.csv`
One row per player per game. Contains every stat from the boxscore including minutes played, goals, assists, shots, cards, whether they started, penalty info, and game winning goals.

### `ncaa_wsoccer_transfer_risk.csv`
One row per player per season (aggregated from raw games). This is the file used for modeling.

| Column | Description | Transfer Signal |
|---|---|---|
| `start_rate` | est_starts / games_played | Low = bench risk |
| `win_rate` | team_wins / games_played | Low = poor team fit |
| `production_per_game` | (goals + 0.5×assists) / GP | Low = underperforming |
| `games_played` | Total game appearances | Low = limited role |
| `total_minutes` | Sum of minutesPlayed | Low = reduced role |
| `transferred` | 1 if player appears on a different team next season | Target label |
| `left_program` | 1 if player does not appear at all next season | Target label |

## Transfer Labels

Transfer labels are inferred directly from the data by comparing each player's team across consecutive seasons:

- `transferred = 1` — player appears the following season but on a different team
- `left_program = 1` — player does not appear at all the following season (transferred out, graduated, injured, or lost eligibility)

> **Caveat:** `left_program` cannot distinguish between transferring out, graduating, and other reasons for leaving. These labels are a proxy and should be noted as such in any writeup. Cross-references should be used for explainability.

## Setup

```bash
pip install -r requirements.txt
python ncaa_wsoccer_collector.py
```

## Data Source

- **API:** [ncaa-api.henrygd.me](https://ncaa-api.henrygd.me) (MIT license, mirrors ncaa.com)
- **Seasons:** 2022–2024
- **Division:** D1


## Disclaimer
AI was used to help create this README file and provide better commenting on .py scripts.