# Dynamic Auction Arena Web App

This project now includes a local web app for running the existing Python bots in a live auction arena.

## Backend

Install dependencies from the repository root:

```bash
python -m pip install -r backend/requirements.txt
```

Run Flask:

```bash
python -c "from backend.app import app; app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)"
```

Available endpoints:

- `GET /api/bots`
- `POST /api/games`
- `GET /api/games/<game_id>/events`
- `POST /api/games/<game_id>/reset`

## Frontend

Install dependencies:

```bash
cd frontend
npm install
```

Run Next.js:

```bash
npm run dev
```

Open `http://localhost:3000`.

By default the frontend expects the Flask API at `http://127.0.0.1:5000`. Override it with:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5000 npm run dev
```

## Verification

From the repository root:

```bash
python -m pytest backend/tests
cd frontend
npm run check
npm run build
```

