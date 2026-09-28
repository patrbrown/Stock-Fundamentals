"""Thin client for SEC EDGAR's free JSON APIs (no API key), with an on-disk cache."""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

import requests

from .settings import CACHE_DIR, sec_user_agent

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

TICKER_MAP_TTL = 7 * 24 * 3600   # ticker list rarely changes
FACTS_TTL = 12 * 3600            # financials change at most a few times a quarter


class SecError(RuntimeError):
    pass


_last_call = 0.0
_lock = threading.Lock()


def _request(url: str, not_found: str = "The SEC has no XBRL financial data for this company.") -> requests.Response:
    global _last_call
    ua = sec_user_agent()
    if not ua:
        raise SecError("The SEC contact name/email isn't set. An admin can add it under Admin → Settings.")
    # SEC allows 10 requests/second per IP; stay well under it (shared across all users of this server).
    with _lock:
        wait = 0.15 - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
    try:
        resp = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=60)
    except requests.RequestException as exc:
        raise SecError(f"Couldn't reach the SEC ({exc.__class__.__name__}). Check your internet connection and try again.")
    if resp.status_code == 404:
        raise SecError(not_found)
    if resp.status_code in (403, 429):
        raise SecError("The SEC temporarily refused the request (rate limit or missing contact info). Wait a minute and retry.")
    resp.raise_for_status()
    return resp


def _get_json(url: str) -> dict:
    return _request(url).json()


def get_bytes(url: str) -> bytes:
    return _request(url, not_found=f"File not found on SEC: {url}").content


def get_json(url: str) -> dict:
    return _request(url, not_found=f"File not found on SEC: {url}").json()


def _cached(path: Path, ttl: int, fetch, force: bool = False) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not force and path.exists() and time.time() - path.stat().st_mtime < ttl:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    data = fetch()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def ticker_map(force: bool = False) -> dict[str, dict]:
    """{'AAPL': {'cik': 320193, 'title': 'Apple Inc.', 'rank': 1}, ...}  (rank ~ SEC's size ordering)"""
    raw = _cached(CACHE_DIR / "company_tickers.json", TICKER_MAP_TTL, lambda: _get_json(TICKERS_URL), force)
    out = {}
    for i, row in enumerate(raw.values()):
        t = row["ticker"].upper()
        if t not in out:
            out[t] = {"cik": int(row["cik_str"]), "title": pretty_name(row["title"]), "rank": i}
    return out


def pretty_name(title: str) -> str:
    """SEC names are often ALL CAPS ('NETFLIX INC') with state/country tags ('/UK', '/DE/'); tidy them."""
    title = re.sub(r"\s*/[A-Za-z]{2,3}/?\s*$", "", title.strip())
    if not title.isupper():
        return title
    small = {"OF", "AND", "THE", "&"}
    keep = {"LLC", "LP", "PLC", "NV", "SA", "AG", "SE", "ETF", "REIT", "USA", "US", "II", "III", "IV"}
    words = []
    for i, w in enumerate(title.split()):
        core = w.strip(".,")
        if core in keep:
            words.append(w)
        elif core in small and i:
            words.append(w.lower())
        else:
            words.append(w.capitalize())
    return " ".join(words)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("&", " and ")).strip()


def search(query: str, limit: int = 10) -> list[dict]:
    """Match by ticker or company name. 'netflix', 'nflx' and 'Netflix Inc' all find NFLX."""
    q = _norm(query)
    if not q:
        return []
    qt = query.strip().upper().replace(".", "-")
    hits = []
    for t, info in ticker_map().items():
        name = _norm(info["title"])
        words = name.split()
        if t == qt:
            score = 0
        elif name == q or name.startswith(q + " "):
            score = 1
        elif t.startswith(qt) and len(qt) >= 2:
            score = 2
        elif words and all(any(w.startswith(p) for w in words) for p in q.split()):
            score = 3
        elif q in name:
            score = 4
        else:
            continue
        hits.append((score, info["rank"], t, info))
    hits.sort(key=lambda h: (h[0], h[1]))
    return [{"ticker": t, **info} for _, _, t, info in hits[:limit]]


def lookup(query: str) -> dict:
    """Exact ticker first; otherwise the best company-name match."""
    t = query.strip().upper().replace(".", "-")
    m = ticker_map()
    if t in m:
        return {"ticker": t, **m[t]}
    hits = search(query, limit=1)
    if hits:
        return hits[0]
    raise SecError(
        f"No US SEC filer matches '{query}'. "
        "TSX-only and other non-SEC companies aren't covered."
    )


def company_facts(cik: int, force: bool = False) -> dict:
    return _cached(CACHE_DIR / f"facts_{cik}.json", FACTS_TTL, lambda: _get_json(FACTS_URL.format(cik=cik)), force)
