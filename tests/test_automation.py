"""Testes da automatização, backups e Jellyfin."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="mo_auto_"))
os.environ["MEDIAORGANIZER_HOME"] = str(TMP / "app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.automation import Automation  # noqa: E402
from core.backup import backup_database, list_backups  # noqa: E402
from core.config import ensure_dirs  # noqa: E402
from core.database import Database  # noqa: E402
from core.jellyfin_check import check_movies  # noqa: E402
from integrations.jellyfin import JellyfinClient  # noqa: E402

HAS = shutil.which("ffmpeg") is not None


def video(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=5",
                    "-t", "1", str(p)], check=True)


@unittest.skipUnless(HAS, "ffmpeg necessário")
class TestAutomation(unittest.TestCase):
    def test_modes(self):
        ensure_dirs()
        db = Database(TMP / "app" / "database" / "a.db")
        lib = TMP / "Filmes"
        video(lib / "Up (2009)" / "Up.2009.1080p.mkv")
        (lib / "Up (2009)" / "Up.2009.1080p.pt-BR.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nVocê está falando no celular?\n", encoding="utf-8")
        video(lib / "Matrix.1999.mkv")
        video(lib / "sem ano.mkv")
        db.set_setting("movies_folder", str(lib))
        db.set_setting("auto_apply_medium", True)
        before = sorted(str(p) for p in lib.rglob("*"))
        logs = []
        Automation(db, logs.append).run("analise")
        self.assertEqual(before, sorted(str(p) for p in lib.rglob("*")))   # análise não altera
        self.assertTrue(any("por organizar" in m for m in logs))
        Automation(db, logs.append).run("automatico")
        self.assertTrue((lib / "Up (2009)" / "Up (2009).mkv").exists())
        self.assertTrue((lib / "Up (2009)" / "Up (2009).pt-PT.srt").exists())   # adaptada
        self.assertIn("a falar no telemóvel",
                      (lib / "Up (2009)" / "Up (2009).pt-PT.srt").read_text(encoding="utf-8"))
        self.assertTrue((lib / "Up (2009)" / "Up (2009).pt-BR.srt").exists())   # original mantido
        self.assertTrue((lib / "Matrix (1999)" / "Matrix (1999).mkv").exists())
        self.assertTrue((lib / "Matrix (1999)" / "Matrix (1999).nfo").exists())
        self.assertTrue((lib / "sem ano.mkv").exists())                         # incerto: intocado
        self.assertTrue(list((TMP / "app" / "reports").glob("relatorio_duplicados_*.html")))
        self.assertGreaterEqual(len(list_backups(TMP / "app" / "backups")), 1)
        c = check_movies(db)   # sem TMDb não há capas: o único aviso deve ser esse
        organised = [i for i in c["issues"] if "(1999)" in i["path"] or "(2009)" in i["path"]]
        self.assertEqual([i["problems"] for i in organised], [["sem capa"], ["sem capa"]])
        Automation(db, logs.append).run("recuperacao")
        Automation(db, logs.append).run("reparacao")
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM jobs WHERE status='running'"), 0)

    def test_backup_and_jellyfin(self):
        db = Database(TMP / "app" / "database" / "b.db")
        for _ in range(3):
            backup_database(db.path, keep=2, out_dir=TMP / "bk")
            import time
            time.sleep(1.05)
        self.assertEqual(len(list(Path(TMP / "bk").glob("*.db"))), 2)
        calls = []
        j = JellyfinClient("http://nas:8096/", "k", fetch=lambda m, p: calls.append((m, p)) or
                           {"ServerName": "Casa", "Version": "10.10"})
        self.assertIn("Casa", j.test())
        j.refresh()
        self.assertEqual(calls[-1], ("POST", "/Library/Refresh"))


if __name__ == "__main__":
    unittest.main()
