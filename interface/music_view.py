"""Módulo Música — inventário."""
from __future__ import annotations

import html

from .media_view import MediaView
from .widgets import human_duration, human_size, status_fmt


def _kbps(v, _r):
    return f"{round(v / 1000)} kbps" if v else ""


def _khz(v, _r):
    return f"{v / 1000:.1f} kHz".replace(".", ",") if v else ""


class MusicView(MediaView):
    table = "music"
    kind = "music"
    report_kind = "musica"
    title = "Música"
    subtitle = "Inventário da pasta de música de origem. Nada é convertido nem alterado."
    columns = [
        ("artist", "Artista", None),
        ("album", "Álbum", None),
        ("year", "Ano", None),
        ("track", "Faixa", None),
        ("title", "Título", None),
        ("duration", "Duração", lambda v, r: human_duration(v)),
        ("codec", "Formato", None),
        ("bitrate", "Bitrate", _kbps),
        ("sample_rate", "Amostragem", _khz),
        ("size", "Tamanho", lambda v, r: human_size(v)),
        ("has_embedded_cover", "Capa", lambda v, r: "✓" if (v or r.get("folder_cover")) else "—"),
        ("status", "Estado", status_fmt),
        ("filename", "Ficheiro", None),
    ]
    filters = [
        ("all", "Todas (activas)", "status NOT IN ('missing','quarantined')"),
        ("no_cover", "Sem capa", "status='ok' AND has_embedded_cover=0 AND COALESCE(folder_cover,'')=''"),
        ("incomplete_tags", "Tags incompletas", "status='ok' AND (COALESCE(artist,'')='' OR "
                                                "COALESCE(title,'')='' OR COALESCE(album,'')='')"),
        ("zero_bytes", "0 bytes", "status='zero_bytes'"),
        ("invalid", "Inválidas", "status='invalid'"),
        ("missing", "Em falta", "status='missing'"),
        ("quarantined", "Em quarentena", "status='quarantined'"),
        ("everything", "Tudo", ""),
    ]
    search_cols = ("artist", "album_artist", "album", "title", "filename", "genre")
    order_by = ("COALESCE(album_artist, artist) COLLATE NOCASE, album COLLATE NOCASE, "
                "disc, track, filename")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        from PySide6.QtWidgets import QPushButton
        b = QPushButton("Organizar música…")
        b.clicked.connect(lambda: self.ctx.navigate.emit("analysis", "music"))
        self.header_actions.insertWidget(0, b)

    def detail_html(self, r: dict) -> str:
        e = lambda v: html.escape(str(v)) if v not in (None, "") else "<span style='color:#8b98a5'>—</span>"  # noqa: E731
        rows = [
            ("Artista", r.get("artist")), ("Artista do álbum", r.get("album_artist")),
            ("Álbum", r.get("album")), ("Título", r.get("title")),
            ("Faixa", r.get("track")), ("Disco", r.get("disc")), ("Ano", r.get("year")),
            ("Género", r.get("genre")), ("Formato", r.get("codec")),
            ("Bitrate", _kbps(r.get("bitrate"), r)), ("Amostragem", _khz(r.get("sample_rate"), r)),
            ("Canais", r.get("channels")), ("Duração", human_duration(r.get("duration"))),
            ("Tamanho", human_size(r.get("size"))),
            ("Capa embutida", "sim" if r.get("has_embedded_cover") else "não"),
            ("Capa na pasta", r.get("folder_cover")),
            ("Ficheiro", r.get("filename")), ("Pasta", r.get("folder")),
            ("Erro de leitura", r.get("probe_error")),
        ]
        body = "".join(
            f"<tr><td style='color:#8b98a5;padding:3px 10px 3px 0;vertical-align:top'>{k}</td>"
            f"<td style='padding:3px 0'>{e(v)}</td></tr>" for k, v in rows)
        return (f"<h2 style='margin-bottom:2px'>{e(r.get('title') or r.get('filename'))}</h2>"
                f"<div style='color:#8b98a5'>{e(r.get('artist'))} · {e(r.get('album'))} · "
                f"{e(status_fmt(r.get('status'), r))}</div>"
                f"<table style='margin-top:10px'>{body}</table>")
