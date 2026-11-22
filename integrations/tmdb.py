"""TMDb (The Movie Database) — confirmação de título e ano. Opcional.

Precisa de uma chave gratuita (https://www.themoviedb.org/settings/api).
Aceita a "API Key (v3)" ou o "API Read Access Token (v4)".
Só faz pedidos de leitura.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.themoviedb.org/3"


class TMDbError(Exception):
    pass


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"^(the|a|an|o|a|os|as|le|la|les|el|los|las|il|der|die|das) ", "", s)
    return s


def similarity(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


class TMDbClient:
    def __init__(self, key: str, language: str = "en-US", timeout: int = 10, fetch=None):
        self.key = key.strip()
        self.language = language
        self.timeout = timeout
        self._fetch = fetch or self._http

    def _http(self, url: str, headers: dict) -> dict:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise TMDbError("Chave TMDb inválida.") from e
            raise TMDbError(f"TMDb respondeu com erro {e.code}.") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise TMDbError(f"Sem ligação ao TMDb: {e}") from e

    def _get(self, path: str, params: dict) -> dict:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        headers = {"Accept": "application/json"}
        if self.key.startswith("eyJ"):        # token v4
            headers["Authorization"] = f"Bearer {self.key}"
        else:                                # chave v3
            params["api_key"] = self.key
        url = f"{API}{path}?{urllib.parse.urlencode(params)}"
        return self._fetch(url, headers)

    def search(self, title: str, year: int | None = None) -> list[dict]:
        data = self._get("/search/movie", {"query": title, "year": year,
                                           "language": self.language, "include_adult": "false"})
        return data.get("results") or []

    def test(self) -> None:
        self._get("/configuration", {})

    def match(self, title: str, year: int | None) -> dict | None:
        """Melhor correspondência, ou None se não houver confiança suficiente."""
        results = self.search(title, year)
        if year and not results:
            results = self.search(title, None)
        scored = []
        for r in results[:20]:
            ry = None
            if (r.get("release_date") or "")[:4].isdigit():
                ry = int(r["release_date"][:4])
            sim = max(similarity(title, r.get("title", "")),
                      similarity(title, r.get("original_title", "")))
            year_ok = bool(year and ry and abs(ry - year) <= 1)
            year_bad = bool(year and ry and abs(ry - year) > 1)
            score = sim + (0.2 if year_ok else 0) - (0.4 if year_bad else 0)
            scored.append((score, sim, year_ok, ry, r))
        if not scored:
            return None
        scored.sort(key=lambda x: (x[0], x[4].get("popularity") or 0), reverse=True)
        score, sim, year_ok, ry, r = scored[0]
        if sim < 0.85 or ry is None:
            return None
        if year and not year_ok:
            return None
        if not year:
            # sem ano no nome: só aceita se não houver outro candidato igualmente parecido
            rivals = [s for s in scored[1:] if s[1] >= 0.85]
            if rivals:
                return None
        return {
            "title": r.get("title") or title,
            "original_title": r.get("original_title"),
            "year": ry,
            "tmdb_id": r.get("id"),
            "confidence": "alta" if year_ok else "média",
        }
