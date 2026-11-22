"""OpenSubtitles.com (API REST oficial). Opcional.

Precisa de conta gratuita em opensubtitles.com e de uma chave de API
(https://www.opensubtitles.com/consumers). As contas gratuitas têm um limite
diário de descargas — a aplicação respeita-o e não tenta contorná-lo.
"""
from __future__ import annotations

import json
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from core.config import APP_VERSION

API = "https://api.opensubtitles.com/api/v1"
USER_AGENT = f"MediaOrganizer v{APP_VERSION}"
# ordem de preferência (secção 8 da especificação)
LANG_PRIORITY = ["pt-PT", "pt-BR", "en"]


class OpenSubtitlesError(Exception):
    pass


def movie_hash(path: Path | str) -> str | None:
    """Hash do OpenSubtitles: tamanho + soma de 64 KB do início e do fim."""
    path = Path(path)
    size = path.stat().st_size
    chunk = 65536
    if size < chunk * 2:
        return None
    h = size
    with open(path, "rb") as f:
        for pos in (0, size - chunk):
            f.seek(pos)
            buf = f.read(chunk)
            for (v,) in struct.iter_unpack("<Q", buf):
                h = (h + v) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


class OpenSubtitlesClient:
    def __init__(self, api_key: str, username: str = "", password: str = "",
                 timeout: int = 20, fetch=None):
        self.api_key = api_key.strip()
        self.username, self.password = username, password
        self.timeout = timeout
        self.token: str | None = None
        self._fetch = fetch or self._http
        self._last = 0.0

    def _http(self, method: str, url: str, headers: dict, body: bytes | None):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                ctype = r.headers.get("Content-Type", "")
                return json.loads(raw.decode("utf-8")) if "json" in ctype else raw
        except urllib.error.HTTPError as e:
            msg = {401: "Credenciais OpenSubtitles inválidas.",
                   403: "Acesso recusado pelo OpenSubtitles (chave de API?).",
                   406: "Limite diário de descargas do OpenSubtitles atingido.",
                   429: "Demasiados pedidos ao OpenSubtitles; tente mais tarde."}.get(e.code)
            raise OpenSubtitlesError(msg or f"OpenSubtitles respondeu com erro {e.code}.") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise OpenSubtitlesError(f"Sem ligação ao OpenSubtitles: {e}") from e

    def _call(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        # respeitar o limite de pedidos (máx. ~5/s)
        wait = 0.25 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        url = API + path
        if params:
            url += "?" + urllib.parse.urlencode(sorted((k, v) for k, v in params.items() if v))
        headers = {"Api-Key": self.api_key, "User-Agent": USER_AGENT,
                   "Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        return self._fetch(method, url, headers, data)

    def login(self) -> None:
        if not (self.username and self.password):
            raise OpenSubtitlesError("Para descarregar legendas é preciso utilizador e "
                                     "palavra-passe do OpenSubtitles (Configuração).")
        r = self._call("POST", "/login", body={"username": self.username,
                                                 "password": self.password})
        self.token = r.get("token")
        if not self.token:
            raise OpenSubtitlesError("Login no OpenSubtitles falhou.")

    def search(self, *, query: str | None = None, year: int | None = None,
               imdb_id: str | None = None, tmdb_id: int | None = None,
               moviehash: str | None = None, languages=LANG_PRIORITY) -> list[dict]:
        params = {"languages": ",".join(l.lower() for l in languages), "type": "movie"}
        if moviehash:
            params["moviehash"] = moviehash
        if imdb_id:
            params["imdb_id"] = str(imdb_id).lstrip("t")
        elif tmdb_id:
            params["tmdb_id"] = tmdb_id
        elif query:
            params["query"] = query
            if year:
                params["year"] = year
        r = self._call("GET", "/subtitles", params=params)
        out = []
        for item in r.get("data", []):
            a = item.get("attributes", {})
            files = a.get("files") or []
            if not files:
                continue
            lang = (a.get("language") or "").lower()
            lang = {"pt-pt": "pt-PT", "pt-br": "pt-BR", "pb": "pt-BR", "pt": "pt-PT"}.get(lang, lang)
            out.append({
                "file_id": files[0].get("file_id"), "file_name": files[0].get("file_name"),
                "language": lang, "hash_match": bool(a.get("moviehash_match")),
                "downloads": a.get("download_count") or 0, "release": a.get("release") or "",
                "machine": bool(a.get("machine_translated") or a.get("ai_translated")),
                "hearing_impaired": bool(a.get("hearing_impaired")),
            })
        return out

    @staticmethod
    def best(results: list[dict], priority=LANG_PRIORITY) -> dict | None:
        """pt-PT > pt-BR > en; dentro do idioma: correspondência por hash, humanos, descargas."""
        def key(r):
            lang_rank = priority.index(r["language"]) if r["language"] in priority else 99
            return (lang_rank, not r["hash_match"], r["machine"], -r["downloads"])
        cands = [r for r in results if r.get("file_id")]
        return sorted(cands, key=key)[0] if cands else None

    def download(self, file_id: int) -> tuple[bytes, str]:
        if not self.token:
            self.login()
        r = self._call("POST", "/download", body={"file_id": file_id, "sub_format": "srt"})
        link = r.get("link")
        if not link:
            raise OpenSubtitlesError(r.get("message") or "Descarga recusada.")
        data = self._fetch("GET", link, {"User-Agent": USER_AGENT}, None)
        if isinstance(data, dict):
            raise OpenSubtitlesError("Resposta inesperada na descarga.")
        return data, r.get("file_name") or "legenda.srt"

    def test(self) -> None:
        self._call("GET", "/infos/formats")

