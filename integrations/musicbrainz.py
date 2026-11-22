"""MusicBrainz — ano e identificador de álbuns (sem chave; máx. 1 pedido/s)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from core.config import APP_VERSION

API = "https://musicbrainz.org/ws/2"
UA = f"MediaOrganizer/{APP_VERSION} ( https://github.com/jfcarvalho1/Legendas_Automaticas )"


class MusicBrainzError(Exception):
    pass


class MusicBrainzClient:
    def __init__(self, timeout: int = 15, fetch=None):
        self.timeout = timeout
        self._fetch = fetch or self._http
        self._last = 0.0
        self.cache: dict[tuple, dict | None] = {}

    def _http(self, url: str) -> dict:
        wait = 1.1 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise MusicBrainzError(f"Sem ligação ao MusicBrainz: {e}") from e

    def release(self, artist: str, album: str) -> dict | None:
        key = (artist.lower(), album.lower())
        if key in self.cache:
            return self.cache[key]
        q = f'release:"{album}" AND artist:"{artist}"'
        data = self._fetch(f"{API}/release/?" + urllib.parse.urlencode({"query": q, "fmt": "json",
                                                                         "limit": 5}))
        best = None
        for r in data.get("releases", []):
            if int(r.get("score", 0)) < 90:
                continue
            date = r.get("date") or ""
            if date[:4].isdigit():
                cand = {"mbid": r.get("id"), "year": int(date[:4]), "title": r.get("title")}
                if best is None or cand["year"] < best["year"]:   # edição original
                    best = cand
        self.cache[key] = best
        return best
