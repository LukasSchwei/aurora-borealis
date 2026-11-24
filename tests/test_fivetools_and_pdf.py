"""Tests for OS Documents path detection, 5e.tools importer, and official 5e/5.5e PDF export."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication

from aurora_borealis.engine import RulesEngine
from aurora_borealis.fivetools_importer import (
    import_5etools_directory,
    import_5etools_from_github,
    is_official_5etools_source,
    render_5etools_text,
)
from aurora_borealis.loader import ContentRepository
from aurora_borealis.models import CharacterState, Element
from aurora_borealis.paths import get_elements_dir, get_os_documents_dir, get_templates_dir
from aurora_borealis.pdf_export import export_character_pdf, validate_character_for_pdf
from aurora_borealis.rules_55e import get_55e_background_abilities


class FiveToolsAndPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.repo = ContentRepository()
        cls.repo.load_directory(get_elements_dir())
        cls.engine = RulesEngine(cls.repo)
        cls.templates_dir = get_templates_dir()

    def test_os_documents_dir_does_not_create_fake_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp) / "fakehome"
            fake_home.mkdir()
            with mock.patch("aurora_borealis.paths.Path.home", return_value=fake_home), mock.patch(
                "aurora_borealis.paths.subprocess.run", side_effect=OSError("no xdg-user-dir")
            ), mock.patch(
                "PySide6.QtCore.QStandardPaths.writableLocation", return_value=""
            ):
                docs = get_os_documents_dir()
                self.assertFalse((fake_home / "Documents").exists())
                self.assertEqual(docs, fake_home)

    def test_render_5etools_tags(self) -> None:
        txt = "Cast {@spell fireball|PHB} for {@damage 8d6} fire damage ({@dc 15} Dex save)."
        rendered = render_5etools_text(txt)
        self.assertEqual(rendered, "Cast fireball for 8d6 fire damage (DC 15 Dex save).")

    def test_5etools_non_homebrew_filter_and_55e_backgrounds(self) -> None:
        self.assertTrue(is_official_5etools_source("PHB"))
        self.assertTrue(is_official_5etools_source("XPHB"))
        self.assertFalse(is_official_5etools_source("WoW"))
        self.assertFalse(is_official_5etools_source("UATheMysticClass"))
        self.assertFalse(is_official_5etools_source("PHB", {"_isHomebrew": True}))

        acolyte = self.repo.get("ID_BACKGROUND_ACOLYTE")
        self.assertEqual(
            get_55e_background_abilities(acolyte),
            ("intelligence", "wisdom", "charisma"),
        )
        custom_bg = Element(id="ID_CUSTOM_BG", name="Temple Watcher", type="Background")
        self.assertEqual(len(get_55e_background_abilities(custom_bg)), 3)

    def test_import_5etools_directory_and_github_fetcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "5etools_data"
            (src_dir / "spells").mkdir(parents=True)
            (src_dir / "class").mkdir(parents=True)

            (src_dir / "races.json").write_text(
                json.dumps(
                    {
                        "race": [
                            {
                                "name": "5eTools Aasimar",
                                "source": "XPHB",
                                "size": ["M"],
                                "speed": 30,
                                "entries": ["Blessed by celestial power."],
                            },
                            {
                                "name": "Homebrew Elf",
                                "source": "WoW",
                                "size": ["M"],
                                "speed": 30,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (src_dir / "spells" / "spells-xphb.json").write_text(
                json.dumps(
                    {
                        "spell": [
                            {
                                "name": "Starlight Burst",
                                "source": "XPHB",
                                "level": 1,
                                "school": "V",
                                "entries": ["Deals {@damage 2d6} radiant damage."],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (src_dir / "class" / "index.json").write_text(
                json.dumps({"Wizard": "class-wizard.json"}), encoding="utf-8"
            )
            (src_dir / "class" / "class-wizard.json").write_text(
                json.dumps(
                    {
                        "class": [
                            {
                                "name": "5eTools Scholar",
                                "source": "XPHB",
                                "hd": {"faces": 6},
                                "proficiency": ["int", "wis"],
                                "spellcastingAbility": "int",
                                "entries": ["Master of arcane lore."],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            custom_out = tmp_path / "custom"
            rec = import_5etools_directory(src_dir, custom_out)
            self.assertGreaterEqual(rec.file_count, 3)

            repo = ContentRepository()
            repo.load_directory(custom_out)
            self.assertIn("ID_5ETOOLS_RACE_XPHB_5ETOOLS_AASIMAR", repo.by_id)
            self.assertNotIn("ID_5ETOOLS_RACE_WOW_HOMEBREW_ELF", repo.by_id)
            self.assertIn("ID_5ETOOLS_SPELL_XPHB_STARLIGHT_BURST", repo.by_id)
            self.assertIn("ID_5ETOOLS_CLASS_XPHB_5ETOOLS_SCHOLAR", repo.by_id)

            # Test GitHub fetcher path using local files
            def _mock_fetch(url: str) -> bytes:
                rel = url.split("/data/", 1)[1]
                p = src_dir / rel
                if not p.is_file():
                    raise FileNotFoundError(rel)
                return p.read_bytes()

            custom_gh = tmp_path / "custom_gh"
            rec_gh = import_5etools_from_github(
                custom_gh,
                base_url="https://raw.githubusercontent.com/5etools-mirror-3/5etools-src/main/data/",
                fetcher=_mock_fetch,
            )
            self.assertGreaterEqual(rec_gh.file_count, 3)

    def test_official_5e_acroform_pdf_fill_and_readback(self) -> None:
        state = CharacterState(
            name="Balthazar 5e",
            player_name="Lukas",
            ruleset="5e",
            race_id="ID_RACE_DRAGONBORN",
            class_id="ID_WOTC_PHB_CLASS_WIZARD",
            background_id="ID_BACKGROUND_ACOLYTE",
            level=5,
            known_spells=["ID_PHB_SPELL_ACID_SPLASH"],
        )
        comp = self.engine.evaluate(state)
        with tempfile.TemporaryDirectory() as tmp:
            out_pdf = Path(tmp) / "balthazar_5e.pdf"
            export_character_pdf(state, comp, self.repo, out_pdf, self.templates_dir)
            self.assertTrue(out_pdf.is_file())

            probe = subprocess.run(
                ["qpdf", "--json", "--json-key=acroform", "--json-key=qpdf", str(out_pdf)],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(probe.stdout)
            objs = data["qpdf"][1]
            values = {}
            for f in data["acroform"]["fields"]:
                fn = f.get("fullname", "")
                ref = "obj:" + f["object"]
                values[fn] = objs.get(ref, {}).get("value", {}).get("/V")

            self.assertEqual(values.get("CharacterName"), "u:Balthazar 5e")
            self.assertEqual(values.get("ClassLevel"), "u:Wizard 5")
            self.assertEqual(values.get("Race "), "u:Dragonborn")
            self.assertEqual(values.get("Check Box 20"), "/Yes")  # INT save

    def test_official_55e_overlay_pdf_pages(self) -> None:
        state = CharacterState(
            name="Lyra 5.5e",
            ruleset="5.5e",
            race_id="ID_RACE_DRAGONBORN",
            class_id="ID_WOTC_PHB_CLASS_WIZARD",
            background_id="ID_BACKGROUND_ACOLYTE",
            level=5,
            background_asi={"intelligence": 2, "constitution": 1},
        )
        comp = self.engine.evaluate(state)
        with tempfile.TemporaryDirectory() as tmp:
            out_pdf = Path(tmp) / "lyra_55e.pdf"
            export_character_pdf(state, comp, self.repo, out_pdf, self.templates_dir)
            self.assertTrue(out_pdf.is_file())
            probe = subprocess.run(
                ["qpdf", "--json", "--json-key=pages", str(out_pdf)],
                capture_output=True,
                text=True,
                check=True,
            )
            pages = json.loads(probe.stdout).get("pages", [])
            self.assertEqual(len(pages), 2)

    def test_pdf_validation_reports_missing_fields(self) -> None:
        empty_state = CharacterState()
        comp = self.engine.evaluate(empty_state)
        missing = validate_character_for_pdf(empty_state, comp, self.repo)
        self.assertIn("Character Name", missing)
        self.assertIn("Race", missing)
        self.assertIn("Class", missing)
        self.assertIn("Background", missing)
        self.assertIn("Alignment", missing)


if __name__ == "__main__":
    unittest.main()
