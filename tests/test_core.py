"""Testes do núcleo (não precisam de interface gráfica).

Executar:  python3 -m unittest discover -s tests -v
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="mo_test_"))
os.environ["MEDIAORGANIZER_HOME"] = str(TMP / "app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ensure_dirs  # noqa: E402
from core.database import Database  # noqa: E402
from core.operations import OperationManager  # noqa: E402
from core.reporting import export_report  # noqa: E402
from core.safety import SafeFileManager, SafetyError  # noqa: E402
from core.scanner import Scanner  # noqa: E402
from movies.identification import parse_filename  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None


class TestIdentification(unittest.TestCase):
    def test_examples(self):
        g = parse_filename("Interstellar.2014.1080p.BluRay.x264.mkv")
        self.assertEqual((g["title"], g["year"]), ("Interstellar", 2014))
        g = parse_filename("The.Matrix.1999.BDRip.XviD.avi")
        self.assertEqual((g["title"], g["year"]), ("The Matrix", 1999))
        g = parse_filename("Interstellar (2014).mkv")
        self.assertEqual(g["confidence"], "alta")
        g = parse_filename("2001.A.Space.Odyssey.1968.720p.mkv")
        self.assertEqual((g["title"], g["year"]), ("2001 A Space Odyssey", 1968))
        g = parse_filename("filme_sem_ano.mkv")
        self.assertEqual(g["confidence"], "baixa")


class TestCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_dirs()
        cls.db = Database(TMP / "app" / "database" / "t.db")
        cls.lib = TMP / "Filmes"
        cls.lib.mkdir()
        (cls.lib / "Vazio.2010.mkv").write_bytes(b"")
        (cls.lib / "Corrompido.2011.mkv").write_bytes(b"isto nao e video" * 100)
        d = cls.lib / "Interstellar (2014)"
        d.mkdir()
        if HAS_FFMPEG:
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc=size=1280x720:rate=10", "-f", "lavfi", "-i",
                            "sine=frequency=440", "-t", "1", "-shortest",
                            str(d / "Interstellar.2014.1080p.BluRay.x264.mkv")], check=True)
        else:
            (d / "Interstellar.2014.1080p.BluRay.x264.mkv").write_bytes(b"x" * 10)
        (d / "Interstellar.2014.1080p.BluRay.x264.pt-PT.srt").write_text("1\n")
        (d / "cover.jpg").write_bytes(b"\xff\xd8")

    def test_1_scan(self):
        st = Scanner(self.db).scan_movies(self.lib)
        self.assertEqual(st["total"], 3)
        self.assertEqual(st["zero_bytes"], 1)
        rows = {r["filename"]: r for r in self.db.query("SELECT * FROM movies")}
        self.assertEqual(rows["Vazio.2010.mkv"]["status"], "zero_bytes")
        self.assertEqual(rows["Corrompido.2011.mkv"]["status"], "invalid")
        it = rows["Interstellar.2014.1080p.BluRay.x264.mkv"]
        self.assertEqual(it["has_cover"], 1)
        self.assertIn("pt-PT", it["external_subtitles"])
        if HAS_FFMPEG:
            self.assertEqual(it["status"], "ok")
            self.assertEqual(it["resolution"], "720p")
        # segunda passagem: incremental
        st2 = Scanner(self.db).scan_movies(self.lib)
        self.assertEqual(st2["skipped"], 3)

    def test_2_quarantine_and_revert(self):
        sfm = SafeFileManager(self.db)
        src = self.lib / "Vazio.2010.mkv"
        op = sfm.quarantine(src, "Ficheiros_0_bytes", "0 bytes")
        self.assertEqual(op["status"], "completed")
        self.assertFalse(src.exists())
        self.assertTrue(Path(op["new_path"]).exists())
        self.assertTrue(op["operation_id"].startswith("OP_"))
        manifest = Path(op["new_path"]).parent / f"{op['operation_id']}.json"
        self.assertTrue(manifest.exists())
        back = sfm.revert(op["operation_id"])
        self.assertEqual(back["status"], "completed")
        self.assertTrue(src.exists())
        self.assertEqual(OperationManager(self.db).get(op["operation_id"])["status"], "reverted")
        with self.assertRaises(SafetyError):
            sfm.revert(op["operation_id"])

    def test_3_no_overwrite(self):
        sfm = SafeFileManager(self.db)
        a = self.lib / "Corrompido.2011.mkv"
        b = self.lib / "Interstellar (2014)" / "cover.jpg"
        with self.assertRaises(SafetyError):
            sfm.safe_move(a, b)
        self.assertTrue(a.exists() and b.exists())
        last = self.db.query_one("SELECT status FROM operations ORDER BY id DESC LIMIT 1")
        self.assertEqual(last["status"], "failed")

    def test_4_missing_and_reports(self):
        (self.lib / "Corrompido.2011.mkv").rename(TMP / "fora.mkv")
        st = Scanner(self.db).scan_movies(self.lib)
        self.assertEqual(st["missing"], 1)
        for fmt in ("html", "csv", "json", "txt"):
            self.assertTrue(export_report(self.db, "filmes", fmt, TMP / "rep").exists())

    def test_5_locked_settings(self):
        self.db.set_setting("auto_delete", True)
        self.assertFalse(self.db.get_setting("auto_delete"))


if __name__ == "__main__":
    unittest.main()
