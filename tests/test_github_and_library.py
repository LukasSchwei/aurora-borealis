"""Tests for GitHub .index/.xml importing, character library, and config."""

from __future__ import annotations

import functools
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aurora_borealis.config import AppConfig, load_config, save_config
from aurora_borealis.engine import RulesEngine
from aurora_borealis.github_importer import (
    install_from_url,
    is_third_party_path,
    normalize_github_url,
    remove_index,
    update_index,
)
from aurora_borealis.library import (
    delete_character,
    duplicate_character,
    scan_characters_folder,
)
from aurora_borealis.loader import ContentRepository
from aurora_borealis.models import CharacterState
from aurora_borealis.persistence import save_dnd5e


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


class GitHubAndLibraryTests(unittest.TestCase):
    def test_normalize_github_url(self) -> None:
        blob = "https://github.com/AuroraLegacy/elements/blob/master/core.index"
        raw = "https://raw.githubusercontent.com/AuroraLegacy/elements/master/core.index"
        self.assertEqual(normalize_github_url(blob), raw)
        self.assertEqual(normalize_github_url(raw), raw)

    def test_install_recursive_index_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srv_dir = root / "server"
            custom_dir = root / "custom"
            (srv_dir / "sub").mkdir(parents=True)

            # Create two XML element files and a nested .index
            (srv_dir / "races.xml").write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<elements>
  <element name="Test Tiefling" type="Race" source="Custom GH" id="ID_GH_RACE_TIEFLING">
    <description><p>From GitHub index.</p></description>
    <rules><stat name="charisma" value="2"/></rules>
  </element>
</elements>
""",
                encoding="utf-8",
            )
            (srv_dir / "sub" / "feats.xml").write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<elements>
  <element name="Test Lucky" type="Feat" source="Custom GH" id="ID_GH_FEAT_LUCKY">
    <description><p>Nested feat.</p></description>
  </element>
</elements>
""",
                encoding="utf-8",
            )

            handler = functools.partial(_QuietHandler, directory=str(srv_dir))
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()

            try:
                (srv_dir / "sub" / "nested.index").write_text(
                    f"""<?xml version="1.0" encoding="utf-8"?>
<index>
  <info><name>Nested</name></info>
  <files>
    <file name="sub/feats.xml" url="http://127.0.0.1:{port}/sub/feats.xml" />
  </files>
</index>
""",
                    encoding="utf-8",
                )
                (srv_dir / "root.index").write_text(
                    f"""<?xml version="1.0" encoding="utf-8"?>
<index>
  <info>
    <name>Aurora Homebrew Pack</name>
    <description>Test index</description>
    <author>Tester</author>
    <update version="1.2.3" />
  </info>
  <files>
    <file name="races.xml" url="http://127.0.0.1:{port}/races.xml" />
    <file name="nested.index" url="http://127.0.0.1:{port}/sub/nested.index" />
    <file name="third-party/broken.xml" url="http://127.0.0.1:{port}/third-party/broken.xml" />
    <file name="collaborations.index" url="http://127.0.0.1:{port}/collaborations.index" />
  </files>
</index>
""",
                    encoding="utf-8",
                )

                self.assertTrue(is_third_party_path("third-party/foo.xml"))
                self.assertTrue(is_third_party_path("collaborations.index"))
                self.assertFalse(is_third_party_path("core/races.xml"))

                rec = install_from_url(f"http://127.0.0.1:{port}/root.index", custom_dir)
                self.assertEqual(rec.name, "Aurora Homebrew Pack")
                self.assertEqual(rec.version, "1.2.3")
                self.assertEqual(rec.file_count, 2)

                repo = ContentRepository()
                loaded_count = repo.load_directory(custom_dir)
                self.assertEqual(loaded_count, 2)
                self.assertIn("ID_GH_RACE_TIEFLING", repo.by_id)
                self.assertIn("ID_GH_FEAT_LUCKY", repo.by_id)

                updated = update_index(rec, custom_dir)
                self.assertEqual(updated.file_count, 2)

                remove_index(updated)
                self.assertFalse(Path(updated.local_dir).exists())
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_install_direct_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srv_dir = root / "server"
            custom_dir = root / "custom"
            srv_dir.mkdir(parents=True)
            (srv_dir / "extra_spells.xml").write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<elements>
  <element name="Aurora Bolt" type="Spell" source="GH" id="ID_GH_SPELL_AURORA_BOLT">
    <setters><set name="level">1</set></setters>
  </element>
</elements>
""",
                encoding="utf-8",
            )

            handler = functools.partial(_QuietHandler, directory=str(srv_dir))
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            try:
                rec = install_from_url(f"http://127.0.0.1:{port}/extra_spells.xml", custom_dir)
                self.assertEqual(rec.file_count, 1)
                repo = ContentRepository()
                repo.load_directory(custom_dir)
                self.assertIn("ID_GH_SPELL_AURORA_BOLT", repo.by_id)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_character_library_scan_and_ops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "chars"
            folder.mkdir()
            repo = ContentRepository()
            engine = RulesEngine(repo)

            c1 = CharacterState(
                name="Aria",
                ruleset="5.5e",
                level=2,
                portrait_base64="ZmFrZQ==",
            )
            c2 = CharacterState(name="Bram", level=6)
            save_dnd5e(c1, repo, engine.evaluate(c1), folder / "aria.dnd5e")
            save_dnd5e(c2, repo, engine.evaluate(c2), folder / "bram.dnd5e")

            summaries = scan_characters_folder(folder, favorites={"aria.dnd5e"})
            self.assertEqual(len(summaries), 2)
            self.assertEqual(summaries[0].name, "Aria")
            self.assertEqual(summaries[0].ruleset, "5.5e")
            self.assertEqual(summaries[0].portrait_base64, "ZmFrZQ==")
            self.assertGreater(summaries[0].hp, 0)
            self.assertTrue(summaries[0].favorite)
            self.assertEqual(summaries[1].level, 6)

            dup = duplicate_character(folder / "aria.dnd5e")
            self.assertTrue(dup.is_file())
            self.assertEqual(len(scan_characters_folder(folder)), 3)

            delete_character(dup)
            self.assertEqual(len(scan_characters_folder(folder)), 2)

    def test_duplicate_detection_and_priority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "01_srd.xml").write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<elements>
  <element name="Dragonborn" type="Race" source="System Reference Document" id="ID_SRD_DRAGONBORN">
    <description><p>SRD</p></description>
  </element>
</elements>
""",
                encoding="utf-8",
            )
            (d / "02_phb.xml").write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<elements>
  <element name="Dragonborn" type="Race" source="Player’s Handbook" id="ID_PHB_DRAGONBORN">
    <description><p>PHB</p></description>
  </element>
  <element name="Dragonborn Dupe ID" type="Race" source="System Reference Document" id="ID_PHB_DRAGONBORN">
    <description><p>Dupe ID</p></description>
  </element>
</elements>
""",
                encoding="utf-8",
            )
            repo = ContentRepository()
            repo.load_directory(d)
            races = repo.of_type("Race")
            # Only the higher-priority PHB Dragonborn stays in the selectable Race list
            self.assertEqual(len(races), 1)
            self.assertEqual(races[0].source, "Player’s Handbook")
            # Also verify duplicate-ID replacement after a lower-priority name collision still keeps 1 unique name
            (d / "03_5etools_then_phb.xml").write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<elements>
  <element name="Wizard" type="Class" source="System Reference Document" id="ID_DUP_WIZ"/>
  <element name="Wizard" type="Class" source="5e.tools (PHB)" id="ID_5ETOOLS_WIZ"/>
  <element name="Wizard" type="Class" source="Player’s Handbook" id="ID_DUP_WIZ"/>
</elements>
""",
                encoding="utf-8",
            )
            repo2 = ContentRepository()
            repo2.load_directory(d)
            self.assertEqual([c.name for c in repo2.of_type("Class")], ["Wizard"])
            # Both IDs remain resolvable by ID for backwards compatibility
            self.assertIn("ID_SRD_DRAGONBORN", repo.by_id)
            self.assertIn("ID_PHB_DRAGONBORN", repo.by_id)
            self.assertEqual(len(repo.duplicates), 2)
            self.assertEqual(repo.duplicate_summary(), {"Race": 2})

    def test_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg = AppConfig(
                characters_dir="/tmp/chars",
                custom_dirs=["/tmp/homebrew"],
                installed_indexes=[{"slug": "core", "name": "Core"}],
                favorites=["hero.dnd5e"],
                auto_imported_official=True,
            )
            save_config(cfg, cfg_path)
            loaded = load_config(cfg_path)
            self.assertEqual(loaded.characters_dir, "/tmp/chars")
            self.assertEqual(loaded.custom_dirs, ["/tmp/homebrew"])
            self.assertEqual(loaded.installed_indexes, [{"slug": "core", "name": "Core"}])
            self.assertEqual(loaded.favorites, ["hero.dnd5e"])
            self.assertTrue(loaded.auto_imported_official)


if __name__ == "__main__":
    unittest.main()
