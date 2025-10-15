# Hofix — Real-time On-demand Home Services Web App

## Tech Stack
- Flask, SQLAlchemy, JWT, Socket.IO
- Postgres (via Docker) or SQLite (local default)
- Google Maps API, Bootstrap, Chart.js

## Quick Start (Local)
1. Create venv and install deps
```
pip install -r requirements.txt
```
2. Run the app
```
python app.py
```
3. Open http://127.0.0.1:5000

By default it uses SQLite (`hofix.db`). Set `DATABASE_URL` to use Postgres.

## With Docker
```
docker compose up --build
```
The backend runs on http://127.0.0.1:5000 and Postgres on 5432.

## Environment Variables
- DATABASE_URL (optional) e.g. `postgresql+psycopg2://user:pass@localhost:5432/hofix`
- JWT_SECRET_KEY (required for JWT; default in dev)
- SECRET_KEY (Flask secret; default in dev)

## Credentials & Roles
- Signup as `User` or `Provider` from the UI.

## Project Structure
- `app.py` (entry)
- `extensions.py` (db, jwt, socketio, bcrypt)
- `models.py` (SQLAlchemy models)
- `routes/` (blueprints)
- `templates/`, `static/`

## Notes
- Realtime booking updates use WebSocket rooms keyed by booking id.
- Map uses Google Maps API with browser geolocation; allow location in the browser.
- Google Maps API key is included in the code for development purposes.

