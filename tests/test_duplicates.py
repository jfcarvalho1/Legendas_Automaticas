"""Testes de duplicados."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="mo_dup_"))
os.environ["MEDIAORGANIZER_HOME"] = str(TMP / "app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ensure_dirs  # noqa: E402
from core.database import Database  # noqa: E402
from core.duplicates import EXACT, PROBABLE, VERSION, DuplicateFinder  # noqa: E402


class TestDuplicates(unittest.TestCase):
    def test_all(self):
        ensure_dirs()
        db = Database(TMP / "app" / "database" / "d.db")
        lib = TMP / "Filmes"
        (lib / "Matrix (1999)").mkdir(parents=True)
        (lib / "Downloads").mkdir()
        data = os.urandom(50_000)
        (lib / "Matrix (1999)" / "Matrix (1999).mkv").write_bytes(data)
        (lib / "Downloads" / "matrix.copy.mkv").write_bytes(data)
        (lib / "Downloads" / "outro.mkv").write_bytes(os.urandom(50_000))   # mesmo tamanho, outro conteúdo
        (lib / "Matrix (1999)" / "cover.jpg").write_bytes(b"\xff\xd8" * 300)
        (lib / "Downloads" / "cover.jpg").write_bytes(b"\xff\xd8" * 300)
        db.set_setting("movies_folder", str(lib))
        for name, title, year, res, size in (
                ("Gladiator (2000).mkv", "Gladiator", 2000, "1080p", 9),
                ("Gladiator.2000.720p.mkv", "Gladiator", 2000, "720p", 4),
                ("Up.2009.mkv", "Up", 2009, "1080p", 5),
                ("Up (2009).mkv", "Up", 2009, "1080p", 5)):
            db.execute("INSERT INTO movies(path, filename, status, title_guess, year_guess, resolution, "
                       "video_codec, size, height) VALUES(?,?,?,?,?,?,?,?,?)",
                       (f"/x/{name}", name, "ok", title, year, res, "h264", size * 2**30,
                        1080 if res == "1080p" else 720))
        for alb, title, br, dur in (("Busto", "Gaivota", 320000, 180), ("Busto", "Gaivota", 128000, 181),
                                    ("Ao Vivo no Coliseu", "Gaivota (Live)", 256000, 240.0),
                                    ("Ao Vivo no Coliseu", "Gaivota", 256000, 239.0)):
            db.execute("INSERT INTO music(path, filename, status, artist, album, title, bitrate, duration, size) "
                       "VALUES(?,?,?,?,?,?,?,?,?)", (f"/m/{alb}/{br}{dur}.mp3", "x.mp3", "ok", "Amália",
                                                     alb, title, br, dur, 5_000_000))
        s = DuplicateFinder(db).analyse()
        types = sorted((g["type"], g["kind"]) for g in s["groups"])
        self.assertIn((EXACT, "filme"), types)
        self.assertIn((EXACT, "capa"), types)
        self.assertIn((VERSION, "filme"), types)    # Gladiator 1080p vs 720p
        self.assertIn((PROBABLE, "filme"), types)   # Up duas vezes, mesma qualidade
        self.assertIn((PROBABLE, "música"), types)  # Gaivota 320 vs 128
        self.assertIn((VERSION, "música"), types)   # ao vivo
        self.assertEqual(s["exact"], 2)
        self.assertEqual(s["space_exact"], 50_000 + 600)
        g = next(g for g in s["groups"] if g["type"] == EXACT and g["kind"] == "filme")
        keep = next(i for i in g["items"] if i["keep"])
        self.assertIn("Matrix (1999)", keep["path"])       # mantém o organizado
        self.assertTrue(db.scalar("SELECT COUNT(*) FROM duplicates") >= 8)


if __name__ == "__main__":
    unittest.main()
