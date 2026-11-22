"""Verificação de compatibilidade da biblioteca com as convenções do Jellyfin."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .database import Database

_FOLDER = re.compile(r"^.+ \((\d{4})\)$")


def check_movies(db: Database) -> dict:
    root = db.get_setting("movies_folder") or ""
    prefix = os.path.join(root, "")
    issues = []
    ok = 0
    for m in db.query("SELECT * FROM movies WHERE status='ok'"):
        if not m["path"].startswith(prefix):
            continue
        p = Path(m["path"])
        probs = []
        if p.parent == Path(root):
            probs.append("vídeo solto na pasta Filmes (sem pasta própria)")
        elif not _FOLDER.match(p.parent.name):
            probs.append("pasta fora do formato «Título (Ano)»")
        elif not (p.stem == p.parent.name or p.stem.startswith(p.parent.name + " - ")):
            probs.append("nome do ficheiro diferente do nome da pasta")
        if not m["has_cover"]:
            probs.append("sem capa")
        if not m["has_nfo"]:
            probs.append("sem NFO")
        if probs:
            issues.append({"path": m["path"], "problems": probs})
        else:
            ok += 1
    return {"ok": ok, "issues": issues}
