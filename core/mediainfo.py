"""Leitura técnica de ficheiros através do FFprobe (só leitura)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class ProbeError(Exception):
    pass


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def probe(path: Path | str, timeout: int = 30) -> dict:
    exe = ffprobe_path()
    if not exe:
        raise ProbeError("FFprobe não está instalado.")
    cmd = [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
           str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ProbeError(f"FFprobe excedeu {timeout}s.") from e
    if r.returncode != 0:
        raise ProbeError((r.stderr or "FFprobe falhou.").strip().splitlines()[-1][:300])
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError as e:
        raise ProbeError("Resposta do FFprobe inválida.") from e
    if not data.get("streams"):
        raise ProbeError("Sem fluxos de vídeo ou áudio legíveis.")
    return data


def _float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def resolution_label(width: int | None, height: int | None) -> str:
    if not width or not height:
        return ""
    if width >= 3800 or height >= 2100:
        return "4K"
    if width >= 2500 or height >= 1400:
        return "1440p"
    if width >= 1900 or height >= 1000:
        return "1080p"
    if width >= 1200 or height >= 700:
        return "720p"
    if height >= 560:
        return "576p"
    if height >= 470:
        return "480p"
    return f"{height}p"


def summarize_video(data: dict) -> dict:
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    video = [s for s in streams if s.get("codec_type") == "video"
             and not s.get("disposition", {}).get("attached_pic")]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    subs = [s for s in streams if s.get("codec_type") == "subtitle"]
    v = video[0] if video else {}
    w, h = _int(v.get("width")), _int(v.get("height"))

    def langs(lst):
        out = []
        for s in lst:
            lang = (s.get("tags") or {}).get("language")
            if lang and lang not in out and lang != "und":
                out.append(lang)
        return ",".join(out)

    return {
        "width": w, "height": h, "resolution": resolution_label(w, h),
        "video_codec": v.get("codec_name"),
        "audio_codec": ",".join(dict.fromkeys(a.get("codec_name", "") for a in audio if a.get("codec_name"))),
        "duration": _float(fmt.get("duration")) or _float(v.get("duration")),
        "audio_languages": langs(audio),
        "embedded_subtitles": langs(subs) or (f"{len(subs)} pista(s)" if subs else ""),
        "has_video": bool(video),
    }


def summarize_audio(data: dict) -> dict:
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    a = audio[0] if audio else {}
    pic = any(s.get("disposition", {}).get("attached_pic") for s in streams)
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    tags.update({k.lower(): v for k, v in (a.get("tags") or {}).items() if k.lower() not in tags})
    return {
        "codec": a.get("codec_name"),
        "duration": _float(fmt.get("duration")) or _float(a.get("duration")),
        "bitrate": _int(a.get("bit_rate")) or _int(fmt.get("bit_rate")),
        "sample_rate": _int(a.get("sample_rate")),
        "channels": _int(a.get("channels")),
        "has_embedded_cover": pic,
        "tags": tags,
        "has_audio": bool(audio),
    }
