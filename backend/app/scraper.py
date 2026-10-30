import re
import os
import json
import requests
from datetime import datetime, date, timedelta, time
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from .models import User, Prediction, EngineMatch
from .config import settings

URL = "https://footystats.org/stats/over15-goals"

# Cache file for FootyStats data (used when scraping is blocked)
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "footystats_cache.json")

# Realistic browser headers to mimic a human browsing FootyStats.
# Cloudflare checks these headers; missing ones trigger 403.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
# Keep BARE_UA as alias for backward compat
BARE_UA = BROWSER_HEADERS

# Optional cloudscraper (bypasses Cloudflare JS challenge). Installed only if
# available; falls back to plain requests otherwise.
try:
    import cloudscraper as _cloudscraper
    _HAS_CLOUDSCRAPER = True
except Exception:
    _cloudscraper = None
    _HAS_CLOUDSCRAPER = False


def _proxies():
    """Return a proxies dict if proxy_url is configured, else None."""
    pu = getattr(settings, "proxy_url", "") or os.getenv("PROXY_URL", "")
    if not pu:
        return None
    return {"http": pu, "https": pu}


def _request_get(url, headers=None, timeout=30, verify=True):
    """GET with proxy support and Cloudflare-friendly headers."""
    headers = dict(headers or BARE_UA)
    proxies = _proxies()
    kwargs = {"url": url, "headers": headers, "timeout": timeout, "verify": verify}
    if proxies:
        kwargs["proxies"] = proxies
    # Try cloudscraper first if available (bypasses Cloudflare JS challenge)
    if _HAS_CLOUDSCRAPER:
        try:
            scraper = _cloudscraper.create_scraper()
            if proxies:
                scraper.proxies.update(proxies)
            # cloudscraper handles SSL internally; don't pass verify=False
            resp = scraper.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and "Just a moment" not in resp.text:
                return resp
            # If cloudscraper got a non-200 or challenge page, try with verify=False
            if resp.status_code != 200 or "Just a moment" in resp.text:
                pass  # fall through to plain requests
        except Exception as e:
            print(f"cloudscraper error: {e}")
    # Plain requests fallback
    try:
        resp = requests.get(**kwargs)
        return resp
    except Exception as e:
        print(f"requests error (verify={verify}): {e}")
        return None


def _save_cache(matches):
    """Save FootyStats matches to cache file for fallback use."""
    try:
        cache_path = os.path.abspath(CACHE_FILE)
        data = []
        for m in matches:
            data.append({
                "home": m["home"],
                "away": m["away"],
                "odds": m["odds"],
                "date": str(m["date"]),
                "over15": m["over15"],
                "avg_goals": m["avg_goals"],
                "link": m.get("link"),
            })
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"saved_at": datetime.utcnow().isoformat(), "matches": data}, f, ensure_ascii=False)
        print(f"FootyStats cache saved: {len(data)} matches")
    except Exception as e:
        print(f"cache save error: {e}")


def _load_cache():
    """Load cached FootyStats matches if available and recent (within 3 days)."""
    try:
        cache_path = os.path.abspath(CACHE_FILE)
        if not os.path.exists(cache_path):
            return []
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        saved_at = datetime.fromisoformat(data["saved_at"])
        if (datetime.utcnow() - saved_at).days > 3:
            print("FootyStats cache too old (>3 days), ignoring")
            return []
        matches = []
        for m in data.get("matches", []):
            try:
                d = datetime.strptime(m["date"], "%Y-%m-%d").date()
                matches.append({
                    "home": m["home"],
                    "away": m["away"],
                    "odds": m["odds"],
                    "date": d,
                    "over15": m["over15"],
                    "avg_goals": m["avg_goals"],
                    "link": m.get("link"),
                })
            except Exception:
                continue
        print(f"FootyStats cache loaded: {len(matches)} matches (saved {saved_at})")
        return matches
    except Exception as e:
        print(f"cache load error: {e}")
        return []


def fetch_matches_footstats_api():
    """Fallback: FootyStats API when HTML scraping is blocked.

    Requires FOOTYSTATS_API_KEY. The API may not provide Over 1.5 frequency
    stats (uses defaults: 78% and 2.5 avg goals).
    """
    key = getattr(settings, "footystats_api_key", "") or os.getenv("FOOTYSTATS_API_KEY", "")
    if not key:
        return []
    try:
        r = requests.get("https://api.football-data-api.com/todays-matches",
                         params={"key": key}, timeout=20, proxies=_proxies())
        if r.status_code != 200:
            print(f"fetch_matches_footstats_api: HTTP {r.status_code}")
            return []
        data = r.json()
        if not data.get("success"):
            print(f"fetch_matches_footstats_api: {data.get('message', 'failed')}")
            return []
        matches = []
        for m in (data.get("data") or []):
            try:
                home = m.get("home_name") or m.get("homeName") or ""
                away = m.get("away_name") or m.get("awayName") or ""
                if not home or not away:
                    continue
                du = m.get("date_unix") or m.get("dateUnix")
                if du:
                    d = datetime.utcfromtimestamp(int(du)).date()
                else:
                    d = datetime.utcnow().date()
                odds = float(m.get("odds_ft_over15") or m.get("oddsFtOver15") or 1.8)
                o15 = m.get("o15_potential") or m.get("over15_potential")
                try:
                    o15 = float(o15) if o15 is not None else 78.0
                except (ValueError, TypeError):
                    o15 = 78.0
                if o15 == 0:
                    o15 = 78.0
                avg = float(m.get("avg_potential") or m.get("avgPotential") or 2.5)
                if avg == 0:
                    avg = 2.5
                link = m.get("match_url") or m.get("matchUrl")
                matches.append({"home": home, "away": away, "odds": odds, "date": d,
                                "over15": o15, "avg_goals": avg, "link": link})
            except Exception as e:
                print(f"fetch_matches_footstats_api parse error: {e}")
                continue
        print(f"fetch_matches_footstats_api: {len(matches)} matches from FootyStats API")
        return matches
    except Exception as e:
        print(f"fetch_matches_footstats_api error: {e}")
        return []


def fetch_matches_footstats_ai():
    """AI scrape fallback for FootStats only (no external API data)."""
    headers_list = [
        BARE_UA,
        {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"},
    ]
    for headers in headers_list:
        try:
            resp = _request_get(URL, headers=headers, timeout=20, verify=False)
            if resp is None or resp.status_code != 200:
                continue
            if "Just a moment" in resp.text:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            return _parse_footstats(soup)
        except Exception as e:
            print("footstats ai error:", e)
    return []


def _parse_footstats(soup):
    headings = []
    for h in soup.find_all(["h2", "h3"]):
        txt = h.get_text()
        if "Over" in txt and "Goals" in txt:
            headings.append(h)
    tables = []
    for h in headings:
        for sib in h.find_all_next():
            if sib.name == "table":
                tables.append(sib)
                break
    if not tables:
        for t in soup.find_all("table"):
            if "Over" in t.get_text():
                tables.append(t)
    results = []
    seen = set()
    all_rows = []
    for table in tables:
        all_rows.extend(table.find_all("tr"))
    for row in all_rows:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        match_text = cells[1].get_text(" ", strip=True)
        over_text = cells[2].get_text(strip=True)
        avg_text = cells[3].get_text(strip=True)
        date_text = cells[4].get_text(strip=True)
        odds_text = cells[5].get_text(strip=True)
        try:
            over15 = float(re.sub(r"[^0-9.]", "", over_text))
        except ValueError:
            over15 = None
        try:
            avg_goals = float(re.sub(r"[^0-9.]", "", avg_text))
        except ValueError:
            avg_goals = None
        m = re.split(r"\s+vs\s+", match_text, flags=re.I)
        if len(m) != 2:
            continue
        home, away = m[0].strip(), m[1].strip()
        try:
            odds = float(odds_text)
        except ValueError:
            continue
        low = date_text.lower()
        if "today" in low:
            d = datetime.utcnow().date()
        elif "tomorrow" in low:
            d = datetime.utcnow().date() + timedelta(days=1)
        else:
            try:
                d = datetime.strptime(date_text, "%d %b").date().replace(year=datetime.utcnow().year)
            except Exception:
                d = datetime.utcnow().date()
        key = (home.lower(), away.lower(), str(d))
        if key in seen:
            continue
        seen.add(key)
        link = None
        for a in cells[1].find_all("a", href=True):
            if "h2h-stats" in a["href"]:
                link = a["href"]
                break
        results.append({"home": home, "away": away, "odds": odds, "date": d,
                        "over15": over15, "avg_goals": avg_goals, "link": link})
    return results


def fetch_matches():
    """Fetch matches from FootyStats (PRIMARY and ONLY source).

    FootyStats is the trusted source for match data. AI is only used to
    read FootyStats match pages for scores - never to generate matches.

    Tries multiple techniques to bypass Cloudflare. If all fail, uses
    cached data from a previous successful scrape.
    """
    print("fetch_matches: trying FootyStats (primary and only source)...")

    # --- Attempt 1: FootyStats with cloudscraper + proxy ---
    resp = None
    headers = dict(BARE_UA)
    for verify in [True, False]:
        try:
            resp = _request_get(URL, headers=headers, timeout=30, verify=verify)
            if resp is not None and resp.status_code == 200 and "Just a moment" not in resp.text:
                break
            resp = None
        except Exception as e:
            print(f"fetch_matches error (verify={verify}): {e}")
            resp = None

    if resp is not None and resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "lxml")
        headings = []
        for h in soup.find_all(["h2", "h3"]):
            txt = h.get_text()
            if "Over" in txt and "Goals" in txt:
                headings.append(h)
        tables = []
        for h in headings:
            for sib in h.find_all_next():
                if sib.name == "table":
                    tables.append(sib)
                    break
        if not tables:
            for t in soup.find_all("table"):
                if "Over" in t.get_text():
                    tables.append(t)
        results = []
        seen = set()
        if tables:
            all_rows = []
            for table in tables:
                all_rows.extend(table.find_all("tr"))
            for row in all_rows:
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue
                match_text = cells[1].get_text(" ", strip=True)
                over_text = cells[2].get_text(strip=True)
                avg_text = cells[3].get_text(strip=True)
                date_text = cells[4].get_text(strip=True)
                odds_text = cells[5].get_text(strip=True)
                try:
                    over15 = float(re.sub(r"[^0-9.]", "", over_text))
                except ValueError:
                    over15 = None
                try:
                    avg_goals = float(re.sub(r"[^0-9.]", "", avg_text))
                except ValueError:
                    avg_goals = None
                m = re.split(r"\s+vs\s+", match_text, flags=re.I)
                if len(m) != 2:
                    continue
                home, away = m[0].strip(), m[1].strip()
                try:
                    odds = float(odds_text)
                except ValueError:
                    continue
                low = date_text.lower()
                if "today" in low:
                    d = datetime.utcnow().date()
                elif "tomorrow" in low:
                    d = datetime.utcnow().date() + timedelta(days=1)
                else:
                    try:
                        d = datetime.strptime(date_text, "%d %b").date().replace(year=datetime.utcnow().year)
                    except Exception:
                        d = datetime.utcnow().date()
                key = (home.lower(), away.lower(), str(d))
                if key in seen:
                    continue
                seen.add(key)
                link = None
                for a in cells[1].find_all("a", href=True):
                    if "h2h-stats" in a["href"]:
                        link = a["href"]
                        break
                results.append({"home": home, "away": away, "odds": odds, "date": d,
                                "over15": over15, "avg_goals": avg_goals, "link": link})
        if results:
            print(f"fetch_matches: {len(results)} matches from FootyStats (primary source)")
            _save_cache(results)
            return results
        else:
            print("fetch_matches: FootyStats returned 0 matches (Cloudflare block or page change)")

    # --- Attempt 2: AI scrape of same FootyStats page ---
    print("fetch_matches: trying AI scrape of FootyStats page...")
    ai_results = fetch_matches_footstats_ai()
    if ai_results:
        print(f"fetch_matches: {len(ai_results)} matches from FootyStats AI scrape")
        _save_cache(ai_results)
        return ai_results

    # --- Attempt 3: FootyStats API (if key is configured) ---
    print("fetch_matches: trying FootyStats API...")
    api_results = fetch_matches_footstats_api()
    if api_results:
        print(f"fetch_matches: {len(api_results)} matches from FootyStats API")
        _save_cache(api_results)
        return api_results

    # --- Attempt 4: Use cached data from previous successful scrape ---
    print("fetch_matches: FootyStats blocked, trying cached data...")
    cached = _load_cache()
    if cached:
        print(f"fetch_matches: {len(cached)} matches from cache (FootyStats data)")
        return cached

    print("fetch_matches: ALL FootyStats attempts failed, no cached data available")
    return []


def ingest_engine(db: Session, matches=None):
    """Store/refresh matches in the private admin engine table."""
    if matches is None:
        matches = fetch_matches()
    stored = 0
    for m in matches:
        match_dt = datetime.combine(m["date"], time(12, 0))
        row = db.query(EngineMatch).filter(
            EngineMatch.home_team == m["home"],
            EngineMatch.away_team == m["away"],
            EngineMatch.match_date == match_dt,
        ).first()
        if row:
            row.odds = m["odds"]
            row.over15_pct = m["over15"]
            row.avg_goals = m["avg_goals"]
            if m.get("link"):
                row.match_url = m["link"]
        else:
            db.add(EngineMatch(
                home_team=m["home"], away_team=m["away"], match_date=match_dt,
                odds=m["odds"], over15_pct=m["over15"], avg_goals=m["avg_goals"],
                match_url=m.get("link"), filter_type="over15",
            ))
            stored += 1
    db.commit()
    return stored


def _fetch_kickoff_for_match(home, away, match_date):
    """Try to get real kickoff time from API-Football."""
    try:
        from .ai_results import fetch_kickoff_api
        ko = fetch_kickoff_api(home, away, match_date)
        if ko:
            return ko
    except Exception as e:
        print("kickoff fetch error for", str(home).encode("ascii","replace").decode(), "vs", str(away).encode("ascii","replace").decode(), ":", e)
    return None


def ingest(db: Session):
    admin = db.query(User).filter(User.role == "admin").first()
    if not admin:
        return 0
    matches = fetch_matches()
    ingest_engine(db, matches)
    count = 0
    for m in matches:
        match_date = m["date"]
        # Try to get real kickoff time from API-Football
        ko = _fetch_kickoff_for_match(m["home"], m["away"], match_date)
        if ko:
            match_dt = ko
            print(f"Kickoff found for {m['home']} vs ...")
        else:
            match_dt = datetime.combine(match_date, time(12, 0))
            print("No kickoff found for", m["home"].encode("ascii","replace").decode(), "vs", m["away"].encode("ascii","replace").decode(), "using noon placeholder")
        exists = db.query(Prediction).filter(
            Prediction.home_team == m["home"],
            Prediction.away_team == m["away"],
            Prediction.match_date >= datetime.combine(match_date, time(0,0)),
            Prediction.match_date < datetime.combine(match_date + timedelta(days=1), time(0,0)),
        ).first()
        if exists:
            # Update existing prediction's match_date if we found a real kickoff
            if ko and exists.match_date != ko:
                exists.match_date = ko
                db.commit()
            continue
        p = Prediction(
            home_team=m["home"],
            away_team=m["away"],
            match_date=match_dt,
            odds=m["odds"],
            status="scheduled",
            allowed=True,
            allowed_at=datetime.utcnow(),
            created_by=admin.id,
        )
        db.add(p)
        count += 1
    db.commit()

    # Also update EngineMatch kickoff_at and match_date
    for m in matches:
        match_date = m["date"]
        ko = _fetch_kickoff_for_match(m["home"], m["away"], match_date)
        if ko:
            row = db.query(EngineMatch).filter(
                EngineMatch.home_team == m["home"],
                EngineMatch.away_team == m["away"],
                EngineMatch.match_date >= datetime.combine(match_date, time(0,0)),
                EngineMatch.match_date < datetime.combine(match_date + timedelta(days=1), time(0,0)),
            ).first()
            if row:
                row.kickoff_at = ko
                row.match_date = ko
                db.commit()

    return count