"""Identificação provável de título e ano a partir do nome do ficheiro.

Só leitura: nesta fase o resultado é apenas guardado como sugestão no
inventário. A renomeação (Fase 3) usará estas sugestões e só actuará quando a
confiança for suficiente.
"""
from __future__ import annotations

import re
from datetime import date

NOISE = {
    # resolução / fonte
    "2160p", "1080p", "1080i", "720p", "576p", "480p", "4k", "uhd", "hd", "fhd", "sd",
    "bluray", "blu-ray", "bdrip", "brrip", "bdremux", "remux", "dvdrip", "dvdscr", "dvd",
    "dvd5", "dvd9", "webrip", "web-dl", "webdl", "web", "hdtv", "hdrip", "tvrip", "cam",
    "ts", "telesync", "screener", "scr", "r5", "hdcam",
    # codecs / áudio
    "x264", "x265", "h264", "h265", "h.264", "h.265", "hevc", "avc", "xvid", "divx",
    "10bit", "8bit", "hdr", "hdr10", "dv", "dolby", "vision", "aac", "ac3", "eac3",
    "dts", "dts-hd", "truehd", "atmos", "mp3", "flac", "ddp5", "dd5", "5.1", "7.1", "2.0",
    # idiomas / legendas / outros
    "dual", "multi", "audio", "legendado", "dublado", "pt", "ptbr", "pt-br", "pt-pt",
    "eng", "por", "subs", "sub", "proper", "repack", "extended", "unrated", "remastered",
    "limited", "internal", "complete", "yify", "yts", "rarbg", "ettv", "eztv", "nf",
    "amzn", "dsnp", "hmax", "atvp",
}

_YEAR = re.compile(r"(?<!\d)(19[0-9]{2}|20[0-9]{2})(?!\d)")
_BRACKETS = re.compile(r"\[[^\]]*\]|\{[^}]*\}")


def parse_filename(filename: str) -> dict:
    """Devolve {'title', 'year', 'confidence'} — confiança: alta, média ou baixa."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    original = stem
    # Já no formato "Título (Ano)"
    m = re.match(r"^\s*(.+?)\s*\((\d{4})\)\s*$", stem)
    if m and 1900 <= int(m.group(2)) <= date.today().year + 1:
        return {"title": m.group(1).strip(), "year": int(m.group(2)), "confidence": "alta"}

    stem = re.sub(r"[\[(]((?:19|20)\d{2})[\])]", r" \1 ", stem)  # [2014] / (2014) -> 2014
    stem = _BRACKETS.sub(" ", stem)
    stem = re.sub(r"\([^)]*\)", " ", stem)
    text = re.sub(r"[._]+", " ", stem)
    text = re.sub(r"\s+-\s+", " - ", text)
    year = None
    title_part = text
    max_year = date.today().year + 1
    for ym in _YEAR.finditer(text):
        y = int(ym.group(1))
        # o ano não pode ser a primeira palavra (ex.: "2001 Odisseia..." é título)
        if 1900 <= y <= max_year and ym.start() > 0:
            year = y
            title_part = text[:ym.start()]
            break

    words = []
    for w in re.split(r"\s+", title_part.strip(" -()")):
        if not w:
            continue
        if w.lower().strip("()[]") in NOISE:
            if year is None:
                break  # sem ano, o ruído técnico marca o fim do título
            continue
        words.append(w)
    title = " ".join(words).strip(" -()")
    title = re.sub(r"\s+", " ", title)

    if not title:
        return {"title": original, "year": year, "confidence": "baixa"}
    if title.isupper() or title.islower():
        title = title.title()
    confidence = "média" if year else "baixa"
    return {"title": title, "year": year, "confidence": confidence}


def suggested_name(title: str, year: int | None) -> str:
    return f"{title} ({year})" if year else title
