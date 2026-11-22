"""Testes de capas, NFO e metadata.json."""
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="mo_meta_"))
os.environ["MEDIAORGANIZER_HOME"] = str(TMP / "app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ensure_dirs  # noqa: E402
from core.database import Database  # noqa: E402
from core.safety import SafeFileManager  # noqa: E402
from integrations.tmdb import TMDbClient  # noqa: E402
from movies.metadata import MetadataManager  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 5000
DETAILS = {
    "id": 157336, "title": "Interstellar", "original_title": "Interstellar",
    "release_date": "2014-11-05", "overview": "Uma equipa de exploradores viaja…",
    "runtime": 169, "imdb_id": "tt0816692", "genres": [{"name": "Ficção científica"}, {"name": "Drama"}],
    "credits": {"crew": [{"job": "Director", "name": "Christopher Nolan"}],
                "cast": [{"name": "Matthew McConaughey", "character": "Cooper"}]},
    "images": {"posters": [{"file_path": "/en.jpg", "iso_639_1": "en", "width": 2000, "vote_average": 5},
                           {"file_path": "/pt.jpg", "iso_639_1": "pt", "width": 1000, "vote_average": 4}]},
    "poster_path": "/default.jpg",
}


def fetch(url, headers):
    if headers.get("image"):
        assert url.endswith("/pt.jpg"), url
        return JPEG
    if "/search/movie" in url:
        return {"results": [{"id": 157336, "title": "Interstellar", "original_title": "Interstellar",
                             "release_date": "2014-11-05"}]}
    if "/movie/157336" in url:
        return DETAILS
    raise AssertionError(url)


class TestMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_dirs()
        cls.db = Database(TMP / "app" / "database" / "m.db")
        cls.dir = TMP / "Filmes" / "Interstellar (2014)"
        cls.dir.mkdir(parents=True)
        cls.video = cls.dir / "Interstellar (2014).mkv"
        cls.video.write_bytes(b"x" * 1000)
        cls.db.execute("INSERT INTO movies(path, folder, filename, status, title_guess, year_guess, "
                       "duration, width, height, video_codec, audio_codec) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (str(cls.video), str(cls.dir), cls.video.name, "ok", "Interstellar", 2014,
                        10140.0, 1920, 800, "h264", "aac"))

    def movie(self):
        return self.db.query_one("SELECT * FROM movies")

    def test_1_tmdb(self):
        mm = MetadataManager(self.db, SafeFileManager(self.db), TMDbClient("k", fetch=fetch))
        r = mm.process(self.movie())
        self.assertEqual((r["cover"], r["nfo"], r["json"]), ("obtida", "criado", "criado"))
        self.assertEqual((self.dir / "cover.jpg").read_bytes(), JPEG)
        meta = json.loads((self.dir / "Interstellar (2014).metadata.json").read_text(encoding="utf-8"))
        self.assertEqual((meta["imdb_id"], meta["year"], meta["poster"]), ("tt0816692", 2014, "cover.jpg"))
        root = ET.parse(self.dir / "Interstellar (2014).nfo").getroot()
        self.assertEqual(root.find("title").text, "Interstellar")
        self.assertEqual(root.find("uniqueid[@type='imdb']").text, "tt0816692")
        self.assertEqual(self.movie()["has_cover"], 1)
        self.assertEqual(self.movie()["has_nfo"], 1)

    def test_2_preserve_existing(self):
        meta = self.dir / "Interstellar (2014).metadata.json"
        data = json.loads(meta.read_text(encoding="utf-8"))
        data["minha_nota"] = "favorito"
        meta.write_text(json.dumps(data), encoding="utf-8")
        mm = MetadataManager(self.db, SafeFileManager(self.db), TMDbClient("k", fetch=fetch))
        r = mm.process(self.movie())
        self.assertEqual((r["cover"], r["nfo"], r["json"]), ("mantida", "mantido", "mantido"))
        r = mm.process(self.movie(), replace=True)
        self.assertEqual(r["json"], "criado")
        self.assertEqual(json.loads(meta.read_text(encoding="utf-8"))["minha_nota"], "favorito")

    def test_3_offline(self):
        d = TMP / "Filmes" / "Outro (1999)"
        d.mkdir()
        v = d / "Outro (1999).avi"
        v.write_bytes(b"y")
        self.db.execute("INSERT INTO movies(path, folder, filename, status, title_guess, year_guess) "
                        "VALUES(?,?,?,?,?,?)", (str(v), str(d), v.name, "ok", "Outro", 1999))
        m = self.db.query_one("SELECT * FROM movies WHERE filename=?", (v.name,))
        r = MetadataManager(self.db).process(m)
        self.assertEqual((r["nfo"], r["json"]), ("criado", "criado"))
        self.assertEqual(ET.parse(d / "Outro (1999).nfo").getroot().find("year").text, "1999")


if __name__ == "__main__":
    unittest.main()
