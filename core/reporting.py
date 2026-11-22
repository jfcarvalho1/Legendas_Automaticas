"""Relatórios de inventário, erros e operações (TXT, CSV, JSON, HTML)."""
from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path

from .config import APP_NAME, APP_VERSION, REPORTS_DIR
from .database import Database

REPORTS = {
    "filmes": ("Filmes", "SELECT title_guess AS titulo, year_guess AS ano, filename AS ficheiro, "
               "resolution AS resolucao, video_codec, audio_codec, ROUND(duration/60) AS minutos, "
               "size AS bytes, external_subtitles AS legendas, has_cover AS capa, "
               "status AS estado, path AS caminho FROM movies ORDER BY title_guess"),
    "musica": ("Música", "SELECT COALESCE(album_artist, artist) AS artista, album, year AS ano, "
               "track AS faixa, title AS titulo, codec, bitrate, sample_rate, size AS bytes, "
               "status AS estado, path AS caminho FROM music ORDER BY artista, album, disc, track"),
    "erros": ("Erros", "SELECT timestamp AS data, level AS nivel, module AS modulo, path AS caminho, "
              "message AS mensagem FROM errors ORDER BY id DESC"),
    "operacoes": ("Operações", "SELECT operation_id, operation AS tipo, original_path AS origem, "
                  "new_path AS destino, timestamp AS data, status AS estado, result AS resultado, "
                  "error AS erro FROM operations WHERE operation!='reserved' ORDER BY id DESC"),
    "em_falta": ("Ficheiros em falta", "SELECT 'filme' AS tipo, path AS caminho, scanned_at AS "
                 "visto_em FROM movies WHERE status='missing' UNION ALL SELECT 'música', path, "
                 "scanned_at FROM music WHERE status='missing'"),
}

FORMATS = ("html", "csv", "json", "txt")


def export_report(db: Database, kind: str, fmt: str = "html",
                  out_dir: Path = REPORTS_DIR) -> Path:
    title, sql = REPORTS[kind]
    rows = db.query(sql)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"relatorio_{kind}_{stamp}.{fmt}"
    cols = list(rows[0].keys()) if rows else []
    if fmt == "csv":
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    elif fmt == "json":
        path.write_text(json.dumps({"report": title, "generated": stamp, "rows": rows},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "txt":
        lines = [f"{APP_NAME} {APP_VERSION} — Relatório: {title}", f"Gerado: {stamp}",
                 f"Registos: {len(rows)}", ""]
        for r in rows:
            lines.append(" | ".join(f"{k}={v}" for k, v in r.items()))
        path.write_text("\n".join(lines), encoding="utf-8")
    else:
        head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(r[c]) if r[c] is not None else '')}</td>"
                                        for c in cols) + "</tr>" for r in rows)
        path.write_text(f"""<!DOCTYPE html><html lang="pt-PT"><head><meta charset="utf-8">
<title>{html.escape(title)}</title><style>
body{{font-family:system-ui,sans-serif;background:#0f141a;color:#e6edf3;margin:32px}}
h1{{font-weight:600}} .meta{{color:#8b98a5;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th{{background:#18212b;text-align:left;position:sticky;top:0}}
th,td{{padding:6px 10px;border-bottom:1px solid #243140}}
tr:hover td{{background:#18212b}}
</style></head><body><h1>{html.escape(title)}</h1>
<div class="meta">{APP_NAME} {APP_VERSION} · {stamp} · {len(rows)} registos</div>
<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></body></html>""",
                        encoding="utf-8")
    return path
