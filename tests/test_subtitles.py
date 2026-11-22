"""Testes de legendas e tradução."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="mo_sub_"))
os.environ["MEDIAORGANIZER_HOME"] = str(TMP / "app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ensure_dirs  # noqa: E402
from core.database import Database  # noqa: E402
from integrations.opensubtitles import OpenSubtitlesClient, movie_hash  # noqa: E402
from movies import translation as T  # noqa: E402
from movies.subtitle_manager import SubtitleManager, list_subtitles  # noqa: E402
from movies.subtitles import (decode_bytes, detect_language, load_cues, parse_srt,  # noqa: E402
                              validate_srt)

SRT_EN = """1
00:00:01,000 --> 00:00:03,500
<i>Hello, how are you?</i>

2
00:00:04,000 --> 00:00:06,000
- What is this?
- I don't know.

3
00:01:10,250 --> 00:01:12,000
We are going home now.
"""
ASS = """[Script Info]
Title: x

[V4+ Styles]
Format: Name, Fontname
Style: Default,Arial

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,{\\i1}Olá, mundo{\\i0}
Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,Linha um\\NLinha dois
"""
VTT = """WEBVTT

00:00:01.000 --> 00:00:02.000
Primeira

00:01.000 --> 00:03.000
<v Pedro>Segunda</v>
"""


class FakeEngine(T.Engine):
    name = "fake"
    calls = 0

    def available(self):
        return True

    def translate(self, texts, src):
        FakeEngine.calls += 1
        return [T.to_pt_pt("[PT] " + t) for t in texts]


class TestSubtitles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_dirs()
        cls.db = Database(TMP / "app" / "database" / "s.db")
        cls.dir = TMP / "Filmes" / "Interstellar (2014)"
        cls.dir.mkdir(parents=True)
        cls.video = cls.dir / "Interstellar (2014).mkv"
        cls.video.write_bytes(os.urandom(300_000))
        (cls.dir / "Interstellar (2014).en.srt").write_text(SRT_EN, encoding="utf-8")
        (cls.dir / "Interstellar (2014).ass").write_text(ASS, encoding="utf-8")
        (cls.dir / "Interstellar (2014).pt-BR.srt").write_bytes(
            "1\n00:00:01,000 --> 00:00:02,000\nVocê está falando no celular no ônibus?\n".encode("cp1252"))
        cls.db.execute("INSERT INTO movies(path, folder, filename, status, title_guess, year_guess) "
                       "VALUES(?,?,?,?,?,?)", (str(cls.video), str(cls.dir), cls.video.name, "ok",
                                               "Interstellar", 2014))
        cls.movie = cls.db.query_one("SELECT * FROM movies")

    def test_parse_and_validate(self):
        cues = parse_srt(SRT_EN)
        self.assertEqual(len(cues), 3)
        self.assertEqual((cues[2].start, cues[2].end), (70250, 72000))
        self.assertEqual(validate_srt(SRT_EN), [])
        self.assertTrue(validate_srt("1\nisto não é tempo\nola"))

    def test_formats(self):
        a, _ = load_cues(self.dir / "Interstellar (2014).ass")
        self.assertEqual(a[0].text, "<i>Olá, mundo</i>")
        self.assertEqual(a[1].text, "Linha um\nLinha dois")
        p = TMP / "x.vtt"
        p.write_text(VTT)
        v, _ = load_cues(p)
        self.assertEqual([c.text for c in v], ["Primeira", "Segunda"])
        text, enc = decode_bytes("ação".encode("cp1252"))
        self.assertEqual((text, enc), ("ação", "cp1252"))

    def test_language(self):
        en = " ".join(["you know what is the thing that I have to do"] * 5)
        self.assertEqual(detect_language(en)[0], "en")
        br = " ".join(["você está falando com o cara do ônibus, não é legal"] * 5)
        self.assertEqual(detect_language(br)[0], "pt-BR")
        pt = " ".join(["tu estás a falar com o miúdo do autocarro, não é fixe"] * 5)
        self.assertEqual(detect_language(pt)[0], "pt-PT")

    def test_pt_pt(self):
        self.assertEqual(T.to_pt_pt("Você está falando no celular no ônibus?"),
                         "Você está a falar no telemóvel no autocarro?")
        self.assertEqual(T.to_pt_pt("Estamos comendo. Ele continua partindo."),
                         "Estamos a comer. Ele continua a partir.")
        self.assertEqual(T.to_pt_pt("Contato no Banheiro"), "Contacto no Casa de banho")

    def test_list_and_convert(self):
        (self.dir / "Subs").mkdir(exist_ok=True)
        (self.dir / "Subs" / "3_Portuguese.srt").write_text(SRT_EN, encoding="utf-8")
        subs = {s["name"]: s["language"] for s in list_subtitles(self.video)}
        self.assertEqual(subs[str(Path("Subs") / "3_Portuguese.srt")], "pt")
        self.assertEqual(subs["Interstellar (2014).en.srt"], "en")
        self.assertEqual(subs["Interstellar (2014).pt-BR.srt"], "pt-BR")
        sm = SubtitleManager(self.db)
        op = sm.convert_to_srt(self.movie, str(self.dir / "Interstellar (2014).ass"))
        out = Path(op["new_path"])
        self.assertTrue(out.exists() and out.suffix == ".srt")
        self.assertEqual(validate_srt(out.read_text(encoding="utf-8")), [])
        self.assertTrue((self.dir / "Interstellar (2014).ass").exists())  # original intacto

    def test_translate_resume(self):
        src = self.dir / "Interstellar (2014).en.srt"
        cues, _ = load_cues(src)
        cp = TMP / "cp.json"
        T.BATCH = 1
        calls = {"n": 0}

        def cancel_after_two():
            calls["n"] += 1
            return calls["n"] > 2
        with self.assertRaises(T.TranslationError):
            T.translate_cues(cues, FakeEngine(), "en", cancelled=cancel_after_two, checkpoint=cp)
        self.assertTrue(cp.exists())
        FakeEngine.calls = 0
        out = T.translate_cues(cues, FakeEngine(), "en", checkpoint=cp)
        self.assertEqual(FakeEngine.calls, 1)                    # retomou: só faltava 1 bloco
        self.assertEqual([(c.start, c.end, c.index) for c in out],
                         [(c.start, c.end, c.index) for c in cues])
        self.assertTrue(out[0].text.startswith("<i>[PT]"))
        self.assertTrue(out[1].text.startswith("- "))
        data = T.translate_subtitle_file(src, "en", FakeEngine())
        self.assertEqual(validate_srt(data.decode("utf-8")), [])
        T.BATCH = 40

    def test_opensubtitles(self):
        self.assertEqual(len(movie_hash(self.video)), 16)
        responses = {
            "/subtitles": {"data": [
                {"attributes": {"language": "en", "download_count": 900, "moviehash_match": True,
                                "files": [{"file_id": 1, "file_name": "a.srt"}]}},
                {"attributes": {"language": "pt-BR", "download_count": 50,
                                "files": [{"file_id": 2, "file_name": "b.srt"}]}},
                {"attributes": {"language": "pt-PT", "download_count": 10,
                                "files": [{"file_id": 3, "file_name": "c.srt"}]}}]},
            "/login": {"token": "tok"},
            "/download": {"link": "https://dl/x", "file_name": "c.srt"},
        }

        def fetch(method, url, headers, body):
            if url.startswith("https://dl/"):
                return SRT_EN.encode("utf-8")
            for k, v in responses.items():
                if k in url:
                    return v
            raise AssertionError(url)
        c = OpenSubtitlesClient("key", "user", "pw", fetch=fetch)
        res = SubtitleManager(self.db).download(self.movie, c)
        self.assertEqual(res["language"], "pt-PT")
        self.assertTrue(Path(res["path"]).name.endswith(".pt-PT.srt"))
        res2 = SubtitleManager(self.db).download(self.movie, c)  # nunca escreve por cima
        self.assertNotEqual(res["path"], res2["path"])


if __name__ == "__main__":
    unittest.main()
