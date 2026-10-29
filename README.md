# BetPicks

## Description

BetPicks is a betting picks web application built with FastAPI, PostgreSQL, and vanilla JavaScript. The application allows users to view daily matches, create accumulators (ACCAs), follow experts, and track their betting statistics.

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