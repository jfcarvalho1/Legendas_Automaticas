"""Testes da organização/renomeação de filmes."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="mo_org_"))
os.environ["MEDIAORGANIZER_HOME"] = str(TMP / "app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ensure_dirs  # noqa: E402
from core.database import Database  # noqa: E402
from core.organizer import (CONFLICT, DONE, ORGANIZED, READY, UNCERTAIN,  # noqa: E402
                            MovieOrganizer, subtitle_suffix)
from core.safety import SafeFileManager  # noqa: E402
from core.scanner import Scanner  # noqa: E402
from integrations.tmdb import TMDbClient  # noqa: E402


def make_video(path: Path, size="640x360"):
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc=size={size}:rate=5", "-t", "1", str(path)], check=True)
    else:
        path.write_bytes(os.urandom(2000))


class TestOrganizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_dirs()
        cls.db = Database(TMP / "app" / "database" / "o.db")
        cls.lib = TMP / "Filmes"
        L = cls.lib
        make_video(L / "Interstellar.2014.1080p.BluRay.x264" / "Interstellar.2014.1080p.BluRay.x264.mkv")
        (L / "Interstellar.2014.1080p.BluRay.x264" / "Interstellar.2014.1080p.BluRay.x264.pt-PT.srt").write_text("1\n")
        D = L / "Interstellar.2014.1080p.BluRay.x264"
        (D / "English.srt").write_text("1\n")
        (D / "poster.jpg").write_bytes(b"\xff\xd8")
        (D / "Subs").mkdir()
        (D / "Subs" / "2_English.srt").write_text("1\n")
        (D / "Subs" / "3_Portuguese (Brazil).srt").write_text("1\n")
        (D / "Subs" / "4_Portuguese.srt").write_text("1\n")
        (D / "RARBG.txt").write_text("lixo")
        (D / "Interstellar.2014.1080p.BluRay.x264.nfo").write_text("*** RELEASE INFO ***")
        (D / "Sample").mkdir()
        make_video(D / "Sample" / "sample.mkv")
        make_video(L / "The.Matrix.1999.BDRip.XviD.avi")
        (L / "The.Matrix.1999.BDRip.XviD.por.srt").write_text("1\n")
        make_video(L / "filme_misterioso.mkv")
        make_video(L / "Up (2009)" / "Up (2009).mkv")
        # duas versões do mesmo filme
        make_video(L / "Gladiator.2000.720p.mkv", "1280x720")
        make_video(L / "Gladiator [2000] 1080p.mkv", "1920x1080")
        Scanner(cls.db).scan_movies(L)
        cls.db.set_setting("movies_folder", str(L))

    def test_0_suffix(self):
        self.assertEqual(subtitle_suffix(".pt-PT"), ".pt-PT")
        self.assertEqual(subtitle_suffix("Filme.por"), ".pt")
        self.assertEqual(subtitle_suffix("Filme.pt-br.forced"), ".pt-BR.forced")
        self.assertEqual(subtitle_suffix("English"), ".en")
        self.assertEqual(subtitle_suffix("x"), "")
        self.assertEqual(subtitle_suffix("3_Portuguese (Brazil)"), ".pt-BR")
        self.assertEqual(subtitle_suffix("Cidade.de.Deus"), "")

    def test_1_propose_and_apply_and_revert(self):
        org = MovieOrganizer(self.db)
        props = org.propose()
        by = {Path(p["path"]).name: p for p in props}
        it = by["Interstellar.2014.1080p.BluRay.x264.mkv"]
        self.assertEqual(it["status"], READY)
        dsts = sorted(Path(f["dst"]).relative_to(self.lib).as_posix() for f in it["files"])
        self.assertEqual(dsts, ["Interstellar (2014)/Interstellar (2014).en.2.srt",
                                "Interstellar (2014)/Interstellar (2014).en.srt",
                                "Interstellar (2014)/Interstellar (2014).mkv",
                                "Interstellar (2014)/Interstellar (2014).pt-BR.srt",
                                "Interstellar (2014)/Interstellar (2014).pt-PT.srt",
                                "Interstellar (2014)/Interstellar (2014).pt.srt",
                                "Interstellar (2014)/cover.jpg"])
        self.assertEqual(sorted(Path(x).name for x in it["leftovers"]),
                         ["Interstellar.2014.1080p.BluRay.x264.nfo", "RARBG.txt", "sample.mkv"])
        mx = by["The.Matrix.1999.BDRip.XviD.avi"]
        self.assertEqual(Path(mx["target"]).relative_to(self.lib).as_posix(),
                         "Matrix (1999)/Matrix (1999).avi")
        self.assertIn("Matrix (1999).pt.srt", [Path(f["dst"]).name for f in mx["files"]])
        self.assertEqual(by["filme_misterioso.mkv"]["status"], UNCERTAIN)
        self.assertFalse(by["filme_misterioso.mkv"]["checked"])
        self.assertEqual(by["Up (2009).mkv"]["status"], ORGANIZED)
        g1, g2 = by["Gladiator.2000.720p.mkv"], by["Gladiator [2000] 1080p.mkv"]
        names = sorted([Path(g1["target"]).name, Path(g2["target"]).name])
        self.assertIn("Gladiator (2000).mkv", names)
        self.assertTrue(any(" - " in n for n in names), names)

        # edição manual do incerto
        idx = props.index(by["filme_misterioso.mkv"])
        p = org.edit(props, idx, "O Filme Misterioso", 1987)
        self.assertEqual(p["status"], READY)
        self.assertTrue(p["checked"])

        before = sorted(str(x.relative_to(self.lib)) for x in self.lib.rglob("*") if x.is_file())
        summary = org.apply(props)
        self.assertEqual(summary["errors"], [])
        self.assertEqual(summary["movies"], 5)
        self.assertTrue((self.lib / "Interstellar (2014)" / "Interstellar (2014).mkv").exists())
        self.assertTrue((self.lib / "O Filme Misterioso (1987)" / "O Filme Misterioso (1987).mkv").exists())
        self.assertFalse((self.lib / "Interstellar.2014.1080p.BluRay.x264").exists())
        final = sorted(x.name for x in (self.lib / "Interstellar (2014)").iterdir())
        self.assertEqual(len(final), 7, final)          # só os ficheiros indicados
        q = MovieOrganizer(self.db).quarantine_root() / "Restos_Organizacao"
        self.assertEqual(len([x for x in q.iterdir() if x.suffix != ".json"]), 3)
        row = self.db.query_one("SELECT * FROM movies WHERE title_guess='Interstellar'")
        self.assertTrue(row["path"].endswith("Interstellar (2014).mkv"))
        self.assertEqual(row["has_cover"], 1)
        # segunda proposta: tudo organizado
        again = MovieOrganizer(self.db).propose()
        self.assertTrue(all(p["status"] == ORGANIZED for p in again), [(p["filename"], p["status"], p["note"]) for p in again])

        done, errors = SafeFileManager(self.db).revert_batch(summary["batch"])
        self.assertEqual(errors, [])
        after = sorted(str(x.relative_to(self.lib)) for x in self.lib.rglob("*") if x.is_file())
        self.assertEqual(before, after)
        self.assertFalse((self.lib / "Interstellar (2014)").exists())

    def test_2_conflict_never_overwrites(self):
        (self.lib / "Matrix (1999)").mkdir(exist_ok=True)
        (self.lib / "Matrix (1999)" / "Matrix (1999).avi").write_bytes(b"outro")
        props = MovieOrganizer(self.db).propose()
        mx = [p for p in props if p["filename"] == "The.Matrix.1999.BDRip.XviD.avi"][0]
        self.assertIn(mx["status"], (CONFLICT, READY))
        if mx["status"] == READY:  # foi como versão diferente
            self.assertNotEqual(Path(mx["target"]).name, "Matrix (1999).avi")

    def test_3_tmdb_match(self):
        fake = {"results": [
            {"id": 157336, "title": "Interstellar", "original_title": "Interstellar",
             "release_date": "2014-11-05", "popularity": 100},
            {"id": 1, "title": "Interstellar Wars", "original_title": "Interstellar Wars",
             "release_date": "2016-01-01", "popularity": 2}]}
        c = TMDbClient("abc", fetch=lambda url, h: fake)
        hit = c.match("Interstellar", 2014)
        self.assertEqual((hit["tmdb_id"], hit["year"], hit["confidence"]), (157336, 2014, "alta"))
        self.assertIsNone(c.match("Interstellar", 1990))
        self.assertIsNone(c.match("Outro Filme Qualquer", 2014))


if __name__ == "__main__":
    unittest.main()
