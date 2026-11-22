"""Jellyfin — testar ligação e pedir a actualização da biblioteca. Opcional."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class JellyfinError(Exception):
    pass


class JellyfinClient:
    def __init__(self, url: str, api_key: str, timeout: int = 15, fetch=None):
        self.url = url.rstrip("/")
        self.key = api_key.strip()
        self.timeout = timeout
        self._fetch = fetch or self._http

    def _http(self, method: str, path: str):
        req = urllib.request.Request(self.url + path, method=method,
                                     headers={"X-Emby-Token": self.key, "Accept": "application/json"},
                                     data=b"" if method == "POST" else None)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise JellyfinError("Chave de API do Jellyfin inválida.") from e
            raise JellyfinError(f"Jellyfin respondeu com erro {e.code}.") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise JellyfinError(f"Sem ligação ao Jellyfin em {self.url}: {e}") from e

    def test(self) -> str:
        info = self._fetch("GET", "/System/Info")
        return f"{info.get('ServerName', 'Jellyfin')} (versão {info.get('Version', '?')})"

    def refresh(self) -> None:
        self._fetch("POST", "/Library/Refresh")
