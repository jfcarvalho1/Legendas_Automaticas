"""Testes da organização musical."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="mo_mus_"))
os.environ["MEDIAORGANIZER_HOME"] = str(TMP / "app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ensure_dirs  # noqa: E402
from core.database import Database  # noqa: E402
from core.organizer import ORGANIZED, READY, UNCERTAIN  # noqa: E402
from core.safety import SafeFileManager, sha256_file  # noqa: E402
from core.scanner import Scanner  # noqa: E402
from music.organizer import MusicOrganizer, parse_track_filename  # noqa: E402

HAS = shutil.which("ffmpeg") is not None


def mp3(path: Path, freq=440, **tags):
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}", "-t", "1"]
    for k, v in tags.items():
        cmd += ["-metadata", f"{k}={v}"]
    subprocess.run(cmd + [str(path)], check=True)


@unittest.skipUnless(HAS, "ffmpeg necessário")
class TestMusic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_dirs()
        cls.db = Database(TMP / "app" / "database" / "mu.db")
        src = cls.src = TMP / "pen"
        mp3(src / "misc" / "faixa1.mp3", artist="Amália Rodrigues", album="Busto",
            title="Gaivota", track="1", date="1962")
        mp3(src / "misc" / "faixa2.mp3", freq=500, artist="Amália Rodrigues", album="Busto",
            title="Maria Lisboa", track="2/12", date="1962")
        mp3(src / "Madredeus" / "O Espírito da Paz" / "03 - Ajuda.mp3", freq=600)
        mp3(src / "sem_nada.mp3", freq=700)
        shutil.copy(src / "misc" / "faixa1.mp3", src / "copia_gaivota.mp3")
        (src / "misc" / "folder.jpg").write_bytes(b"\xff\xd8\xff" + b"1" * 100)
        Scanner(cls.db).scan_music(src)
        cls.lib = TMP / "Biblioteca_Jellyfin"
        cls.db.set_setting("music_source_folder", str(src))
        cls.db.set_setting("music_library_folder", str(cls.lib))

    def test_0_filename(self):
        self.assertEqual(parse_track_filename("03 - Ajuda"), {"track": 3, "artist": None, "title": "Ajuda"})
        self.assertEqual(parse_track_filename("01. Artista - Tema")["artist"], "Artista")

    def test_1_propose_apply(self):
        org = MusicOrganizer(self.db)
        props = org.propose()
        by = {Path(p["path"]).name: p for p in props}
        pair = [by["faixa1.mp3"], by["copia_gaivota.mp3"]]
        self.assertEqual(sorted(p["status"] for p in pair), sorted([ORGANIZED, READY]))
        kept = next(p for p in pair if p["status"] == READY)
        self.assertEqual(Path(kept["target"]).relative_to(self.lib).as_posix(),
                         "Amália Rodrigues/Busto (1962)/01 - Gaivota.mp3")
        self.assertEqual(Path(by["faixa2.mp3"]["target"]).name, "02 - Maria Lisboa.mp3")
        aj = by["03 - Ajuda.mp3"]
        self.assertEqual((aj["artist"], aj["album"], aj["title"], aj["track"]),
                         ("Madredeus", "O Espírito da Paz", "Ajuda", 3))
        self.assertEqual(aj["status"], READY)
        self.assertFalse(aj["checked"])                      # deduzido: por confirmar
        self.assertEqual(by["sem_nada.mp3"]["status"], UNCERTAIN)
        # confirmar o deduzido e corrigir o incerto
        i = props.index(aj)
        aj["checked"] = True
        j = next(k for k, p in enumerate(props) if p["filename"] == "sem_nada.mp3")
        org.edit(props, [j], {"artist": "Teste", "album": "Álbum X", "title": "Tema", "year": 2001, "track": 1})
        self.assertEqual(props[j]["status"], READY)
        before = {p: sha256_file(p) for p in map(str, self.src.rglob("*.mp3"))}
        s = org.apply(props)
        self.assertEqual(s["errors"], [])
        self.assertEqual(s["tracks"], 4)
        self.assertTrue((self.lib / "Amália Rodrigues" / "Busto (1962)" / "cover.jpg").exists())
        self.assertTrue((self.lib / "Teste" / "Álbum X (2001)" / "01 - Tema.mp3").exists())
        # originais intactos (modo cópia)
        self.assertEqual(before, {p: sha256_file(p) for p in map(str, self.src.rglob("*.mp3"))})
        # reverter o lote retira as cópias (para a quarentena), originais continuam
        done, errs = SafeFileManager(self.db).revert_batch(s["batch"])
        self.assertEqual(errs, [])
        self.assertFalse(list(self.lib.rglob("*.mp3")))
        self.assertEqual(len(before), len(list(self.src.rglob("*.mp3"))))


if __name__ == "__main__":
    unittest.main()
