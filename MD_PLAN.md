# Betva Acca App — Master Implementation Plan

## 1. ANALYSIS: Current System vs SRS Requirements

### 1.1 What to FOLLOW (Keep & Reuse)
| Component | Current | SRS Need | Action |
|---|---|---|---|
| FootyStats scraper | `scraper.py` | Match data source | ✅ Keep, adapt |
| API-Football integration | `ai_results.py` | Score/kickoff lookup | ✅ Keep |
| Admin auth pattern | `deps.py` | Admin-only routes | ✅ Keep |
| CORS/Security middleware | `main.py` | Same | ✅ Keep |
| DB connection | `db.py` | PostgreSQL | ✅ Keep |
| APScheduler | `main.py` | Cron jobs | ✅ Keep |
| Password hashing | `auth.py` | Same | ✅ Keep |

### 1.2 What to CHANGE (Modify)
| Component | Current | SRS Required | Action |
|---|---|---|---|
| User model | email, nickname, profile | phone_number, role (Mteja/Admin) | 🔄 Modify |
| Auth router | email login | phone login + OTP reset | 🔄 Modify |
| Database schema | predictions, user_picks, follows | users, subscriptions, daily_accumulators, individual_matches | 🔄 Replace |
| Frontend | Mechi, Mkeka, Wataalamu, Mimi | Leo, Malipo, Mimi, Historia | 🔄 Replace |
| Admin panel | Predictions, picks, experts | Matches, Accumulators, Subscriptions, Users | 🔄 Modify |
| Cron jobs | Ingest + settle | Expiration + SMS warning | 🔄 Modify |

### 1.3 What to REMOVE (Discard)
| Component | Reason |
|---|---|
| User picks / UserPickLeg | SRS has no user picks |
| Follow / Followers | SRS has no follow system |
| Experts leaderboard | SRS has no experts |
| Visitor stats (optional) | Not in SRS (keep for analytics maybe) |
| Engine slips (EngineSlip) | Replace with daily_accumulators |
| Profile emoji/color | Not in SRS |

### 1.4 What Has Meaning (Valuable for SRS)
- FootyStats scraping → Provides match data for accumulators
- API-Football → Provides scores for settlement
- Admin auth → Admin panel access
- Security middleware → Protects API
- DB connection → Data persistence
- APScheduler → Cron jobs for expiration/SMS

### 1.5 What Has No Meaning (Irrelevant for SRS)
- User picks with legs → No user picks in SRS
- Follow/unfollow → No social features in SRS
- Experts leaderboard → No expert system in SRS
- Visitor tracking → Not required (optional analytics)
- Engine slips → Different from daily_accumulators
- Profile customization → Not in SRS

---

## 2. DATABASE SCHEMA (New)

### 2.1 Users Table
```sql
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    phone_number VARCHAR(15) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(10) NOT NULL DEFAULT 'Mteja',  -- Mteja / Admin
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX(phone_number)
);
```

### 2.2 Subscriptions Table
```sql
CREATE TABLE subscriptions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'Imeisha',  -- Hai / Imeisha
    expires_at DATETIME NOT NULL,
    warning_sms_sent BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### 2.3 Daily Accumulators Table
```sql
CREATE TABLE daily_accumulators (
    id VARCHAR(36) PRIMARY KEY,
    accumulator_date DATE NOT NULL UNIQUE,
    total_odds DECIMAL(5,2) NOT NULL,
    stake_amount DECIMAL(10,2) DEFAULT 5000.00,
    status VARCHAR(10) NOT NULL DEFAULT 'Pending',  -- Pending / Won / Lost
    is_visible BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.4 Individual Matches Table
```sql
CREATE TABLE individual_matches (
    id VARCHAR(36) PRIMARY KEY,
    accumulator_id VARCHAR(36) NOT NULL,
    home_team VARCHAR(100) NOT NULL,
    away_team VARCHAR(100) NOT NULL,
    prediction VARCHAR(50) NOT NULL,
    match_odds DECIMAL(4,2) NOT NULL,
    analysis_text TEXT NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'Pending',  -- Pending / Won / Lost
    FOREIGN KEY (accumulator_id) REFERENCES daily_accumulators(id) ON DELETE CASCADE
);
```

### 2.5 Password Reset Tokens (Keep existing)
```sql
CREATE TABLE password_reset_tokens (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at DATETIME NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.6 Engine Matches (Keep for FootyStats data)
```sql
-- Keep existing engine_matches table for FootyStats scraping
-- Used by admin to create daily accumulators
```

---

## 3. API ENDPOINTS (New)

### 3.1 Authentication (`/api/auth`)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Usajili (phone + password, no duplicates) |
| POST | `/api/auth/login` | Login (phone + password) |
| POST | `/api/auth/forgot` | Request OTP (phone number) |
| POST | `/api/auth/reset` | Reset password (OTP + new password) |
| GET | `/api/auth/me` | Get current user |

### 3.2 Accumulators (`/api/accumulators`)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/accumulators/today` | Get today's accumulator (Leo) |
| GET | `/api/accumulators/history` | Get history (Siku 7 / Siku 90) |
| GET | `/api/accumulators/{id}` | Get accumulator details |
| POST | `/api/accumulators` | Create accumulator (admin) |
| PUT | `/api/accumulators/{id}` | Update accumulator (admin) |
| DELETE | `/api/accumulators/{id}` | Delete accumulator (admin) |

### 3.3 Matches (`/api/matches`)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/matches/{accumulator_id}` | Get matches for accumulator |
| POST | `/api/matches` | Create match (admin) |
| PUT | `/api/matches/{id}` | Update match (admin) |
| DELETE | `/api/matches/{id}` | Delete match (admin) |

### 3.4 Subscriptions (`/api/subscriptions`)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/subscriptions/status` | Check subscription status |
| POST | `/api/subscriptions/activate` | Activate subscription (admin) |
| GET | `/api/subscriptions/all` | List all subscriptions (admin) |

### 3.5 Admin (`/api/admin`)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/admin/users` | List all users |
| PUT | `/api/admin/users/{id}/activate` | Activate user subscription |
| GET | `/api/admin/accumulators` | List all accumulators |
| POST | `/api/admin/accumulators` | Create accumulator |
| GET | `/api/admin/engine-matches` | List FootyStats matches |

---

## 4. FRONTEND SCREENS (New)

### 4.1 Non-Admin User (4 Tabs)
| Tab | Screen | Description |
|---|---|---|
| **Leo** | Today's predictions | Shows today's 4-match accumulator with odds, analysis, status |
| **Malipo** | Payment screen | TZS 4,500/week, payment instructions, activation status |
| **Mimi** | Profile | User info, subscription status, expiry date |
| **Historia** | Performance history | Siku 7 (current week) + Siku 90 (archive) + [See] modal |

### 4.2 Admin Panel
| Module | Description |
|---|---|
| **Wataalamu** | Experts management (keep or remove?) |
| **Mkeka** | Accumulator management (create/edit/delete) |
| **ADM** | Engine matches from FootyStats |
| **Machaguo** | Match management (CRUD) |
| **Mechi** | Match list |

---

## 5. BUSINESS LOGIC

### 5.1 Daily Accumulator Logic
- Exactly 1 accumulator per day
- Exactly 4 matches per accumulator
- Total odds = 4.00
- Stake = TZS 5,000 (simulation)
- Status: Pending → Won/Lost
- is_visible: Admin can hide/show

### 5.2 Subscription Logic
- Price: TZS 4,500/week
- Activation: Admin manually activates after payment verification
- Expiration: Sunday 18:59:59 (regardless of activation day)
- Warning SMS: Saturday 18:59:00
- Status: Hai (active) / Imeisha (expired)

### 5.3 OTP Password Reset
- User enters phone number
- System sends OTP via SMS API
- User enters OTP + new password
- System verifies OTP and updates password

### 5.4 Historia Logic
- Siku 7: Current week (7 days) rolling view
- Siku 90: 90-day archive with counters [Total] | [Won]
- [See]: Modal showing 4 matches, odds, analysis, results

---

## 6. CRON JOBS

### Job 1: Weekly Subscription Expiration
- **Schedule:** Every Sunday at 18:59:59
- **Action:** UPDATE subscriptions SET status='Imeisha' WHERE expires_at <= NOW()

### Job 2: Proactive Saturday Warning SMS
- **Schedule:** Every Saturday at 18:59:00
- **Action:** Query active users, send SMS, mark warning_sms_sent=TRUE

### Job 3: FootyStats Ingest (Keep existing)
- **Schedule:** Every 6 hours
- **Action:** Scrape FootyStats, store in engine_matches

### Job 4: Auto-Settle (Keep existing)
- **Schedule:** Every 30 minutes
- **Action:** Fetch scores, settle matches

---

## 7. SMS TEMPLATES

### 7.1 OTP Verification
```
Betva: Namba yako ya uthibitisho (OTP) ni {otp}. 
Tumia namba hii kuthibitisha akaunti yako. 
Namba hii inaisha baada ya dakika 10.
```

### 7.2 Saturday Warning SMS
```
Betva: Kumbuka! Usajili wako unakwisha kesho Jumapili saa 6:59 jioni. 
Lipa TZS 4,500 kwa wiki kupitia namba ya simu yako. 
Malipo: {payment_number}. 
Asante kwa kuunga mkono Betva!
```

### 7.3 Welcome SMS (Optional)
```
Betva: Karibu! Akaunti yako imeundwa. 
Jisajili kwa TZS 4,500/wiki kupata machaguo ya kila siku. 
Malipo: {payment_number}
```

---

## 8. IMPLEMENTATION PRIORITY

### Phase 1: Foundation (Database + Auth)
1. Update models.py (User, Subscription, DailyAccumulator, IndividualMatch)
2. Update auth router (phone-based login, OTP reset)
3. Update main.py (new routers, cron jobs)

### Phase 2: Core Features (Accumulators + Matches)
4. Create accumulators router (CRUD)
5. Create matches router (CRUD)
6. Create subscriptions router (status, activate)
7. Update admin router

### Phase 3: Frontend
8. Update Leo screen (today's accumulator)
9. Update Malipo screen (payment)
10. Update Mimi screen (profile)
11. Update Historia screen (7-day + 90-day + modal)

### Phase 4: Admin Panel
12. Update admin dashboard
13. Match/accumulator CRUD
14. Subscription activation toggle
15. Visibility toggle (Hide/Delete)

### Phase 5: Cron Jobs & SMS
16. Weekly expiration job
17. Saturday SMS warning job
18. SMS API integration

---

## 9. DECISIONS (CONFIRMED BY USER)

1. **SMS Gateway:** WEB SMS PUSH (web-based SMS API, not traditional gateway)
2. **Payment:** M-Pesa (Tanzania)
3. **Keep FootyStats?** Yes (for match data source)
4. **Keep existing users?** No (schema change from email to phone)
5. **Admin modules:**
   - REMOVE Wataalamu (experts) -> REPLACE with "Orodha ya Watumiaji" (List of Users)
   - Mkeka: Restructured accumulator builder (4 matches, 4.00 odds, analysis text)
   - KEEP ADM (engine matches from FootyStats)
   - KEEP Machaguo (match management CRUD)
   - KEEP Mechi (match list)

### 9.1 Admin Panel Modules (Updated)
| Module | Status | Description |
|---|---|---|
| **Watumiaji** | NEW | List of all users (replaces Wataalamu) |
| **Mkeka** | RESTRUCTURED | 4-match accumulator builder with analysis |
| **ADM** | KEEP | Engine matches from FootyStats |
| **Machaguo** | KEEP | Match management (CRUD) |
| **Mechi** | KEEP | Match list |

### 9.2 Mkeka Replacement Strategy
The Mkeka module is replaced with a **structured accumulator builder**:
- Admin selects 4 matches from FootyStats engine data
- System auto-calculates total odds (must equal ~4.00)
- Admin adds individual analysis text per match
- Admin sets visibility (Hide/Show)
- Admin can settle (Won/Lost/Pending)
- Replaces the old "generate" button with a guided 4-match builder

### 9.3 SMS Gateway: WEB SMS PUSH
- Use HTTP-based SMS API (e.g., Beem SMS API, Africa's Talking, or similar)
- Send OTP via HTTP POST to SMS gateway
- Send Saturday warning via HTTP POST to SMS gateway
- No traditional SMS gateway SDK needed

### 9.4 Payment: M-Pesa (Tanzania)
- Customers pay via M-Pesa to a designated number
- Admin verifies payment and activates subscription
- Expiration: Sunday 18:59:59
- Warning: Saturday 18:59:00

---

**Je, nianze na Phase 1 (Database Models & Auth)?** Au ungependa kubadili mpango?
Pia, **SMS gateway** ungependa kutumia ipi? (Beem, Twilio, au nyingine?)
Pia, **nambari ya malipo** ni ipi? (M-Pesa, Tigo Pesa, Airtel Money?)