"""NFO compatível com Jellyfin/Kodi (só com os campos disponíveis e confirmados)."""
from __future__ import annotations

import xml.etree.ElementTree as ET


def _add(parent, tag, value, **attrs):
    if value in (None, "", [], 0):
        return None
    el = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    el.text = str(value)
    return el


def build_nfo(info: dict) -> bytes:
    m = ET.Element("movie")
    _add(m, "title", info.get("title"))
    _add(m, "originaltitle", info.get("original_title"))
    _add(m, "year", info.get("year"))
    _add(m, "premiered", info.get("release_date"))
    _add(m, "plot", info.get("plot"))
    _add(m, "outline", info.get("plot"))
    _add(m, "tagline", info.get("tagline"))
    _add(m, "runtime", info.get("duration_minutes"))
    for g in info.get("genre") or []:
        _add(m, "genre", g)
    for d in info.get("directors") or []:
        _add(m, "director", d)
    for c in info.get("countries") or []:
        _add(m, "country", c)
    if info.get("imdb_id"):
        _add(m, "uniqueid", info["imdb_id"], type="imdb", default="true")
        _add(m, "imdbid", info["imdb_id"])
    if info.get("tmdb_id"):
        _add(m, "uniqueid", info["tmdb_id"], type="tmdb",
             **({} if info.get("imdb_id") else {"default": "true"}))
        _add(m, "tmdbid", info["tmdb_id"])
    for a in (info.get("actors") or [])[:15]:
        el = ET.SubElement(m, "actor")
        _add(el, "name", a.get("name"))
        _add(el, "role", a.get("role"))
        _add(el, "type", "Actor")
    if info.get("poster"):
        _add(m, "thumb", info["poster"], aspect="poster")
    tech = info.get("technical") or {}
    if tech:
        fi = ET.SubElement(m, "fileinfo")
        sd = ET.SubElement(fi, "streamdetails")
        v = ET.SubElement(sd, "video")
        _add(v, "codec", tech.get("video_codec"))
        _add(v, "width", tech.get("width"))
        _add(v, "height", tech.get("height"))
        _add(v, "durationinseconds", tech.get("duration_seconds"))
        for codec in (tech.get("audio_codec") or "").split(","):
            if codec:
                a = ET.SubElement(sd, "audio")
                _add(a, "codec", codec)
        for lang in info.get("subtitle_languages") or []:
            s = ET.SubElement(sd, "subtitle")
            _add(s, "language", lang)
    ET.indent(m, space="  ")
    body = ET.tostring(m, encoding="unicode")
    return ('<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n' + body + "\n").encode("utf-8")
