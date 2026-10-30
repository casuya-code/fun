import re
import json
import requests
from datetime import datetime, timedelta, date
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from .config import settings


class AIResult:
    def __init__(self, finished=False, home_score=None, away_score=None, confidence=0.0, source=None,
                 postponed=False):
        self.finished = finished
        self.home_score = home_score
        self.away_score = away_score
        self.confidence = confidence
        self.source = source
        # True when the source says the match will not be played as scheduled
        # (postponed / cancelled / abandoned / suspended) - no score exists.
        self.postponed = postponed


# ---------------------------------------------------------------------------
# Groq AI extraction
#
# Groq is used ONLY to read text the app has already downloaded (match/search
# pages). It is never asked "what was the score?" from memory, so it cannot
# fabricate a result: a score is accepted only when the same numbers appear in
# the page text next to a full-time marker ("FT", "Full Time", "Final", ...).
# ---------------------------------------------------------------------------
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_FALLBACK_MODEL = "openai/gpt-oss-20b"
_GROQ_CACHE = {}          # (source, home, away, date) -> (timestamp, AIResult|None)
_GROQ_TTL = 6 * 3600      # do not re-ask the same question for 6 hours

_SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–:]\s*(\d{1,2})(?!\d)")
# "result" is deliberately excluded: search pages label head-to-head history
# with it, which would let an old meeting masquerade as today's score.
_FINISHED_RE = re.compile(r"\b(?:ft|aet|pen|full[- ]?time|final|finished|ended)\b", re.I)
_POSTPONED_RE = re.compile(
    r"postpon|cancel|abandon|suspend|not (?:been )?played|walkover|awarded", re.I)


def _load_json(text):
    """Parse a JSON object from a model reply (tolerates ```json fences)."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.S)
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _groq_request(system: str, user: str):
    key = (getattr(settings, "groq_api_key", "") or "").strip()
    if not key:
        return None
    model = (getattr(settings, "groq_model", "") or "").strip() or "openai/gpt-oss-120b"
    models = [model]
    if model != _GROQ_FALLBACK_MODEL:
        models.append(_GROQ_FALLBACK_MODEL)
    for name in models:
        try:
            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": name,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                    "max_completion_tokens": 400,
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                obj = _load_json(content)
                if obj is not None:
                    return obj
                print(f"Groq returned unparsable JSON ({name})")
            else:
                print(f"Groq error {r.status_code} ({name}): {r.text[:160]}")
                # auth/rate-limit problems will not improve with another model
                if r.status_code not in (400, 404):
                    break
        except Exception as e:
            print("Groq request error:", e)
            break
    return None


def _team_in(name: str, low_window: str) -> bool:
    first = name.lower().split()[0] if name.split() else ""
    for cand in (name.lower(), first if len(first) >= 4 else "", _norm(name)[:6]):
        if len(cand) >= 3 and cand in low_window:
            return True
    return False


def _date_near(text: str, start: int, end: int, match_date) -> bool:
    """True when the match date appears beside a scoreline.

    Used for search-result pages, where several fixtures (and old meetings) are
    listed together; the date is what tells today's match apart from history.
    """
    try:
        if isinstance(match_date, datetime):
            d = match_date.date()
        elif isinstance(match_date, date):
            d = match_date
        else:
            d = datetime.strptime(str(match_date)[:10], "%Y-%m-%d").date()
    except Exception:
        return True  # unknown date: rely on the full-time marker check
    tokens = [
        d.strftime("%d %b").lower(),
        d.strftime("%b %d").lower(),
        d.strftime("%d %B").lower(),
        d.strftime("%B %d").lower(),
        d.isoformat(),
    ]
    window = text[max(0, start - 350):end + 350].lower()
    return any(t in window for t in tokens)


def _slice_for_ai(text: str, home_team: str, away_team: str, limit: int = 7000,
                  match_date=None, require_final_results: bool = False) -> str:
    """Window around the current match's result, never the page header/nav.

    Only two kinds of anchors are trusted:
      1. a "Final Results" section (FootyStats' current-match block);
      2. a scoreline with a full-time marker AND the fixture date next to it.
    If neither exists, no text is sent to the model - the match stays pending
    instead of risking a head-to-head score being mistaken for today's result.
    """
    low = text.lower()

    # 1) FootyStats current-match section
    start = 0
    while True:
        i = low.find("final results", start)
        if i < 0:
            break
        a = max(0, i - 600)
        b = min(len(text), i + 5000)
        window = low[a:b]
        if _team_in(home_team, window) and _team_in(away_team, window):
            return text[a:b][:limit]
        start = i + len("final results")

    if require_final_results:
        # Match pages must prove the CURRENT meeting finished; the form guide
        # below them is full of old "2 - 1 FT" lines we must never settle on.
        return ""

    # 2) A scoreline with a full-time marker ("FT", "Full Time", "Final", ...)
    for m in _SCORE_RE.finditer(text):
        around = text[max(0, m.start() - 140):m.end() + 140]
        if not _FINISHED_RE.search(around):
            continue
        wide = low[max(0, m.start() - 300):m.end() + 300]
        if not (_team_in(home_team, wide) and _team_in(away_team, wide)):
            continue
        if match_date is not None and not _date_near(text, m.start(), m.end(), match_date):
            continue
        a = max(0, m.start() - 800)
        b = min(len(text), m.end() + 3000)
        return text[a:b][:limit]

    return ""


def _score_pair_with_final(text: str, hg: int, ag: int) -> bool:
    """The exact score must appear in the text next to a full-time marker."""
    for m in _SCORE_RE.finditer(text):
        if int(m.group(1)) != hg or int(m.group(2)) != ag:
            continue
        around = text[max(0, m.start() - 140):m.end() + 140]
        if _FINISHED_RE.search(around):
            return True
    return False


def _validate_groq(obj, text: str, home_team: str, away_team: str, source: str):
    """Reject anything the page text does not actually support."""
    if not isinstance(obj, dict):
        return None
    status = str(obj.get("status", "")).strip().lower()
    if status == "postponed":
        if not _POSTPONED_RE.search(text):
            return None
        return AIResult(postponed=True, confidence=0.8, source=source)
    if status != "finished":
        return None
    try:
        hg = int(obj.get("home_score"))
        ag = int(obj.get("away_score"))
    except (TypeError, ValueError):
        return None
    if not (0 <= hg <= 15 and 0 <= ag <= 15):
        return None
    if not _score_pair_with_final(text, hg, ag):
        return None
    return AIResult(finished=True, home_score=hg, away_score=ag, confidence=0.8, source=source)


_GROQ_SYSTEM = (
    "You extract football results from text. Reply with ONLY a JSON object:\n"
    '{"status":"finished"|"postponed"|"unknown","home_score":int|null,'
    '"away_score":int|null,"evidence":"short exact quote","confidence":0..1}\n'
    "Rules:\n"
    "- Use ONLY the supplied text. Never use outside knowledge.\n"
    "- 'finished' only when the text clearly shows the FINAL score of THIS match\n"
    "  (home team vs away team), e.g. next to FT / Full Time / Final.\n"
    "- Ignore head-to-head history and previous meetings; they must not be used.\n"
    "- 'postponed' only when the text says postponed/cancelled/abandoned/suspended.\n"
    "- If the text does not prove a result, return status 'unknown' with null scores.\n"
    "- Never guess."
)


def groq_extract_page(text: str, home_team: str, away_team: str, source: str = "groq",
                      match_date=None, require_final_results: bool = False):
    """Ask Groq to read a page we already downloaded. Returns AIResult or None.

    A cheap pre-check (score or postponement wording in the snippet) avoids
    calling the API for pages that cannot possibly contain a result.

    ``require_final_results`` is set for match pages: only the page's own
    "Final Results" block may be used, never the head-to-head form guide below.
    """
    if not text or not home_team or not away_team:
        return None
    if not (getattr(settings, "groq_api_key", "") or "").strip():
        return None
    snippet = _slice_for_ai(text, home_team, away_team, match_date=match_date,
                            require_final_results=require_final_results)
    if not snippet:
        return None
    if not (_SCORE_RE.search(snippet) or _POSTPONED_RE.search(snippet)):
        return None

    cache_key = (source, _norm(home_team), _norm(away_team), str(match_date)[:10])
    import time as _time
    hit = _GROQ_CACHE.get(cache_key)
    if hit and (_time.time() - hit[0]) < _GROQ_TTL:
        return hit[1]

    user = (f"Match: {home_team} vs {away_team}\n"
            f"Date: {str(match_date)[:10] if match_date else 'unknown'}\n\n"
            f"TEXT:\n{snippet}")
    obj = _groq_request(_GROQ_SYSTEM, user)
    result = _validate_groq(obj, snippet, home_team, away_team, source)
    # Cache only successes: a transient API failure must not silence retries
    # for the next 6 hours while the match is still pending.
    if result is not None:
        _GROQ_CACHE[cache_key] = (_time.time(), result)
    return result


def _extract_score_regex(text: str, home_team: str, away_team: str):
    """Read a final score only when a full-time marker sits next to it.

    Search pages also list previous meetings; without this guard an old
    head-to-head score could settle today's match.
    """
    for m in _SCORE_RE.finditer(text):
        hg, ag = int(m.group(1)), int(m.group(2))
        if hg > 15 or ag > 15:
            continue
        around = text[max(0, m.start() - 160):m.end() + 160]
        low = around.lower()
        if not _FINISHED_RE.search(around):
            continue
        if home_team.lower()[:4] not in low or away_team.lower()[:4] not in low:
            continue
        # keep the page's order: "Home 2-1 Away" vs "Away 1-2 Home"
        if low.find(home_team.lower()[:4]) > low.find(away_team.lower()[:4]):
            hg, ag = ag, hg
        return hg, ag
    return None


def _page_text(url: str, headers: dict):
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        return BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)
    except Exception as e:
        print(f"page fetch error ({url[:60]}): {e}")
        return None


def fetch_via_web_scrape(home_team: str, away_team: str, match_date=None) -> Optional[AIResult]:
    """Try free sources; regex first, then Groq reads the same page text."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    h, a = home_team.replace(' ', '%20'), away_team.replace(' ', '%20')
    sources = [
        ("livescore", f"https://www.livescore.com/en/football/search/?q={h}%20{a}"),
        ("flashscore", f"https://www.flashscore.com/search/?q={home_team.replace(' ', '+')}+{away_team.replace(' ', '+')}"),
        ("espn", f"https://www.espn.com/soccer/search/_/q/{h}%20{a}"),
    ]
    for name, url in sources:
        text = _page_text(url, headers)
        if not text:
            continue
        pair = _extract_score_regex(text, home_team, away_team)
        if pair:
            hg, ag = pair
            return AIResult(finished=True, home_score=hg, away_score=ag,
                            confidence=0.85, source=name)
        # Groq reads the same downloaded text (it never recalls facts itself)
        ai = groq_extract_page(text, home_team, away_team, f"groq/{name}", match_date)
        if ai:
            return ai
    return None


# Simple in-memory cache for API-Football fixtures by date, with a TTL so a
# fixture cached before kickoff does not stay "not started" forever.
_FIXTURE_CACHE = {}
_FIXTURE_TTL = 600  # seconds

def _get_fixtures(host: str, key: str, ds: str) -> list:
    import time as _time
    hit = _FIXTURE_CACHE.get(ds)
    if hit and (_time.time() - hit[0]) < _FIXTURE_TTL:
        return hit[1]
    data = []
    try:
        r = requests.get(f"https://{host}/fixtures", headers={"x-apisports-key": key},
                         params={"date": ds}, timeout=15)
        if r.status_code == 200:
            data = r.json().get("response", []) or []
    except Exception as e:
        print(f"API-Football error ({ds}): {e}")
        data = []
    _FIXTURE_CACHE[ds] = (_time.time(), data)
    return data

import unicodedata
def _norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', s.lower())

def _names_match(api_home, api_away, home_team, away_team):
    ah, aa = _norm(api_home), _norm(api_away)
    hh, aw = _norm(home_team), _norm(away_team)
    home_ok = (hh in ah) or (ah in hh) or (hh[:4] and hh[:4] in ah)
    away_ok = (aw in aa) or (aa in aw) or (aw[:4] and aw[:4] in aa)
    return home_ok and away_ok

def fetch_via_api_football(home_team: str, away_team: str, match_date=None) -> Optional[AIResult]:
    key = getattr(settings, "football_api_key", None)
    if not key:
        return None
    host = getattr(settings, "football_api_host", "v3.football.api-sports.io")
    # determine date range
    if isinstance(match_date, datetime):
        base = match_date.date()
    elif isinstance(match_date, date):
        base = match_date
    else:
        try:
            base = datetime.strptime(str(match_date)[:10], "%Y-%m-%d").date()
        except Exception:
            base = datetime.utcnow().date()
    dates = [base + timedelta(days=d) for d in (-1, 0, 1)]
    for d in dates:
        ds = d.isoformat()
        fixtures = _get_fixtures(host, key, ds)
        for fx in fixtures:
            try:
                api_home = fx["teams"]["home"]["name"]
                api_away = fx["teams"]["away"]["name"]
                if not _names_match(api_home, api_away, home_team, away_team):
                    continue
                status = (fx.get("fixture", {}).get("status", {}) or {}).get("short", "")
                goals = fx.get("goals", {}) or {}
                hg = goals.get("home")
                ag = goals.get("away")
                if status in ("FT", "AET", "PEN", "AWD", "WO") and hg is not None and ag is not None:
                    return AIResult(finished=True, home_score=int(hg), away_score=int(ag),
                                    confidence=0.99, source="api-football")
                if status in ("PST", "CANC", "ABD", "SUSP", "INT"):
                    # match will not be played / was interrupted - never guess a score
                    return AIResult(postponed=True, confidence=0.99, source="api-football",
                                    finished=False)
                # not finished yet
                return None
            except Exception as e:
                print(f"API-Football parse error: {e}")
    return None

def ai_fetch_score(home_team: str, away_team: str, match_date=None,
                   alt_home: str = None, alt_away: str = None) -> Optional[AIResult]:
    """Main settlement function - tries API-Football first, then web scraping.

    alt_home/alt_away: alternate names for the same fixture (e.g. a slug
    derived from the footystats URL like "dac 1904 dunajska streda" vs the DB
    short name "DAC") - used only when the primary names find no fixture.
    """
    def _try(h, a):
        try:
            r = fetch_via_api_football(h, a, match_date)
            if r and (r.finished or r.postponed) and r.confidence >= 0.9:
                return r
        except Exception as e:
            print(f"API-Football fetch error: {e}")
        return None

    # 1) API-Football (reliable)
    result = _try(home_team, away_team)
    if result:
        return result
    # 1b) API-Football with alternate names
    if alt_home and alt_away:
        result = _try(alt_home, alt_away)
        if result:
            return result
    # 2) web scraping fallback
    result = fetch_via_web_scrape(home_team, away_team, match_date)
    if result and result.finished and result.confidence >= 0.7:
        return result
    return None


def fetch_kickoff_api(home_team: str, away_team: str, match_date=None):
    key = getattr(settings, "football_api_key", None)
    if not key:
        return None
    host = getattr(settings, "football_api_host", "v3.football.api-sports.io")
    if isinstance(match_date, datetime):
        base = match_date.date()
    elif isinstance(match_date, date):
        base = match_date
    else:
        try:
            base = datetime.strptime(str(match_date)[:10], "%Y-%m-%d").date()
        except Exception:
            base = datetime.utcnow().date()
    for d in (base + timedelta(days=x) for x in (-1, 0, 1)):
        ds = d.isoformat()
        for fx in _get_fixtures(host, key, ds):
            try:
                if not _names_match(fx["teams"]["home"]["name"], fx["teams"]["away"]["name"], home_team, away_team):
                    continue
                dt_str = fx["fixture"].get("date")
                if dt_str:
                    return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                continue
    return None
