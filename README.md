# Betva

## Description

Betva is a betting picks web application built with FastAPI, PostgreSQL, and vanilla JavaScript. The application allows users to view daily matches, create accumulators (ACCAs), follow experts, and track their betting statistics.

### Features

- Daily match predictions with Over 1.5 goals filter
- Accumulator builder with 12-leg base extending to 20 legs
- Expert tracking and following system
- User authentication (register/login/forgot/password reset)
- Admin panel for match management and accumulator generation
- Visitor counter (counts all visits)
- Swahili UI text

### Tech Stack

- **Backend**: FastAPI, PostgreSQL, SQLAlchemy
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Deployment**: Uvicorn server on port 8000

### Setup

1. Install dependencies: pip install -r requirements.txt
2. Start the server: uvicorn app.main:app --host 127.0.0.1 --port 8000
3. Access the application at http://127.0.0.1:8000

### Deploy to Render

The repository ships `render.yaml` (a Render Blueprint) that creates:

- a free Python web service (`betva`) serving both the API and the frontend
- a free Render Postgres database (`betva-db`) wired to `DATABASE_URL`

Steps:

1. Push this repository to GitHub.
2. In the Render Dashboard choose **New → Blueprint** and connect the repo.
3. Enter the secrets Render prompts for: `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `FOOTBALL_API_KEY`.
4. Apply the Blueprint and wait for the first deploy; the health check is `/health`.
5. Open `https://<service-name>.onrender.com`.

Notes:

- Free web services spin down after 15 minutes without traffic and wake on the
  next request (~1 minute cold start).
- Free Postgres expires 30 days after creation (14-day grace, then deleted) and
  has 1 GB of storage with no backups. Upgrade the database before expiry to
  keep the data.
- Database URLs are normalized automatically (`postgres://` →
  `postgresql+psycopg2://`) and external Render hosts get `sslmode=require`.
- In-process schedulers (ingest every 6 h, settle every 30 min) run only while
  the service is awake.

### API Endpoints

- /api/auth/* - Authentication (register, login, forgot, reset)
- /api/picks/* - User picks and accumulators
- /api/experts/* - Expert tracking and following
- /api/visits* - Visitor statistics
- /api/adm/* - Admin-only accumulator engine
- /api/predictions/* - Prediction management

### Bug Fixes

- Password validation (>72 bytes → 422 error)
- Case-insensitive email login/register
- Blank nickname rejection
- EAT timezone handling (UTC+3)
- Bulk settle validation
- Duplicate match ID rejection
- And more...