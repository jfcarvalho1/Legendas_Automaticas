"""Módulo Filmes — inventário."""
from __future__ import annotations

import html

from movies.identification import suggested_name

from .media_view import MediaView
from .widgets import human_duration, human_size, status_fmt


def _yes(v, _r):
    return "✓" if v else "—"


class MoviesView(MediaView):
    table = "movies"
    kind = "movies"
    report_kind = "filmes"
    title = "Filmes"
    subtitle = "Inventário da pasta de filmes. Duplo clique abre a pasta; botão direito para mais acções."
    columns = [
        ("title_guess", "Título provável", None),
        ("year_guess", "Ano", None),
        ("resolution", "Resolução", None),
        ("video_codec", "Vídeo", None),
        ("audio_codec", "Áudio", None),
        ("duration", "Duração", lambda v, r: human_duration(v)),
        ("size", "Tamanho", lambda v, r: human_size(v)),
        ("external_subtitles", "Legendas", lambda v, r: "✓" if (v or r.get("embedded_subtitles")) else "—"),
        ("has_cover", "Capa", _yes),
        ("has_nfo", "NFO", _yes),
        ("status", "Estado", status_fmt),
        ("filename", "Ficheiro original", None),
    ]
    filters = [
        ("all", "Todos (activos)", "status NOT IN ('missing','quarantined')"),
        ("no_subs", "Sem legendas", "status='ok' AND COALESCE(external_subtitles,'')='' "
                                    "AND COALESCE(embedded_subtitles,'')=''"),
        ("no_cover", "Sem capa", "status='ok' AND has_cover=0"),
        ("no_metadata", "Metadados incompletos", "status='ok' AND (has_nfo=0 OR has_metadata_json=0)"),
        ("uncertain", "Identificação incerta", "status='ok' AND confidence='baixa'"),
        ("zero_bytes", "0 bytes", "status='zero_bytes'"),
        ("invalid", "Inválidos", "status='invalid'"),
        ("missing", "Em falta", "status='missing'"),
        ("quarantined", "Em quarentena", "status='quarantined'"),
        ("everything", "Tudo", ""),
    ]
    search_cols = ("title_guess", "filename", "folder")
    order_by = "title_guess COLLATE NOCASE"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        from PySide6.QtWidgets import QPushButton
        b = QPushButton("Organizar / renomear…")
        b.clicked.connect(lambda: self.ctx.navigate.emit("analysis", ""))
        self.header_actions.insertWidget(0, b)

    def detail_html(self, r: dict) -> str:
        e = lambda v: html.escape(str(v)) if v not in (None, "") else "<span style='color:#8b98a5'>—</span>"  # noqa: E731
        sug = suggested_name(r.get("title_guess") or "", r.get("year_guess"))
        conf = r.get("confidence") or ""
        conf_color = {"alta": "#46c37b", "média": "#e3a33b", "baixa": "#e5534b"}.get(conf, "#8b98a5")
        rows = [
            ("Nome sugerido", f"{sug}.{r.get('extension') or ''}"),
            ("Ficheiro original", r.get("filename")),
            ("Pasta", r.get("folder")),
            ("Tamanho", human_size(r.get("size"))),
            ("Duração", human_duration(r.get("duration"))),
            ("Resolução", f"{r.get('resolution') or ''} ({r.get('width') or '?'}×{r.get('height') or '?'})"
             if r.get("width") else None),
            ("Codec de vídeo", r.get("video_codec")),
            ("Codec de áudio", r.get("audio_codec")),
            ("Idiomas de áudio", r.get("audio_languages")),
            ("Legendas embutidas", r.get("embedded_subtitles")),
            ("Legendas externas", r.get("external_subtitles")),
            ("Capa", r.get("cover_path")),
            ("NFO", "sim" if r.get("has_nfo") else "não"),
            ("metadata.json", "sim" if r.get("has_metadata_json") else "não"),
            ("Erro de leitura", r.get("probe_error")),
            ("Analisado em", (r.get("scanned_at") or "").replace("T", " ")),
        ]
        body = "".join(
            f"<tr><td style='color:#8b98a5;padding:3px 10px 3px 0;vertical-align:top'>{k}</td>"
            f"<td style='padding:3px 0'>{e(v)}</td></tr>" for k, v in rows)
        return (f"<h2 style='margin-bottom:2px'>{e(r.get('title_guess'))}</h2>"
                f"<div style='color:#8b98a5'>{e(r.get('year_guess'))} · "
                f"<span style='color:{conf_color}'>confiança {e(conf)}</span> · "
                f"{e(status_fmt(r.get('status'), r))}</div>"
                f"<table style='margin-top:10px'>{body}</table>"
                "<p style='color:#8b98a5;font-size:9pt;margin-top:12px'>Casos de confiança baixa "
                "nunca são renomeados sem confirmação (página Organizar).</p>")
