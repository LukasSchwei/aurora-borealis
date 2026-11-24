"""Core test suite for Aurora Borealis."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QScrollArea

from aurora_borealis.config import AppConfig
from aurora_borealis.engine import RulesEngine
from aurora_borealis.loader import ContentRepository
from aurora_borealis.models import CharacterState, Element, InventoryItem
from aurora_borealis.paths import get_elements_dir, get_templates_dir
from aurora_borealis.pdf_export import export_character_pdf
from aurora_borealis.persistence import encode_portrait_file, load_dnd5e, save_dnd5e
from aurora_borealis.ui.dialogs import DuplicateReportDialog, NewCharacterDialog
from aurora_borealis.ui.main_window import MainWindow, _item_rarity_info, _make_magic_sparkles_pixmap

DATA_DIR = get_elements_dir()
TEMPLATES_DIR = get_templates_dir()


class AuroraBorealisTests(unittest.TestCase):
    repo: ContentRepository
    engine: RulesEngine

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = ContentRepository()
        cls.repo.load_directory(DATA_DIR)
        cls.engine = RulesEngine(cls.repo)
        cls.app = QApplication.instance() or QApplication([])

    def test_01_elements_and_templates_present(self) -> None:
        xml_files = list(DATA_DIR.glob("*.xml"))
        self.assertGreaterEqual(len(xml_files), 70)
        self.assertGreaterEqual(len(self.repo.by_id), 1800)
        self.assertIn("ID_RACE_DRAGONBORN", self.repo.by_id)
        self.assertIn("ID_WOTC_PHB_CLASS_WIZARD", self.repo.by_id)
        self.assertIn("ID_BACKGROUND_ACOLYTE", self.repo.by_id)
        self.assertTrue((TEMPLATES_DIR / "dnd5e_sheet.pdf").is_file())
        self.assertTrue((TEMPLATES_DIR / "dnd55e_sheet.pdf").is_file())

    def test_02_rules_engine_dragonborn_wizard(self) -> None:
        state = CharacterState(
            name="Balthazar",
            race_id="ID_RACE_DRAGONBORN",
            class_id="ID_WOTC_PHB_CLASS_WIZARD",
            background_id="ID_BACKGROUND_ACOLYTE",
            level=5,
            abilities={
                "strength": 10,
                "dexterity": 14,
                "constitution": 13,
                "intelligence": 15,
                "wisdom": 12,
                "charisma": 8,
            },
        )
        comp = self.engine.evaluate(state)

        self.assertEqual(comp.ability_bonuses["strength"], 2)
        self.assertEqual(comp.ability_bonuses["charisma"], 1)
        self.assertEqual(comp.ability_totals["strength"], 12)
        self.assertEqual(comp.ability_totals["charisma"], 9)
        self.assertEqual(comp.speed, 30)
        self.assertEqual(comp.proficiency_bonus, 3)

        self.assertTrue(comp.saving_throws["intelligence"].proficient)
        self.assertTrue(comp.saving_throws["wisdom"].proficient)
        self.assertFalse(comp.saving_throws["strength"].proficient)
        self.assertTrue(comp.skills["Insight"].proficient)
        self.assertTrue(comp.skills["Religion"].proficient)

        self.assertIsNotNone(comp.spellcasting)
        assert comp.spellcasting is not None
        self.assertEqual(comp.spellcasting.ability, "Intelligence")
        self.assertEqual(comp.spellcasting.save_dc, 13)
        self.assertEqual(comp.spellcasting.attack_bonus, 5)
        self.assertEqual(comp.spellcasting.slots.get(1), 4)
        self.assertEqual(comp.spellcasting.slots.get(3), 2)
        self.assertEqual(comp.spellcasting.max_cantrips, 4)
        self.assertEqual(comp.spellcasting.max_known_spells, 14)
        self.assertEqual(comp.spellcasting.max_spell_level, 3)
        self.assertGreater(len(comp.active_selections), 0)

        # Spellcasting class-feature <select type="Spell"> rules must resolve real options
        cantrip_sels = [s for s in comp.active_selections if s.rule.type == "Spell" and "cantrip" in s.rule.name.lower()]
        book_sels = [s for s in comp.active_selections if s.rule.type == "Spell" and "spellbook" in s.rule.name.lower()]
        self.assertTrue(cantrip_sels and len(cantrip_sels[0].options) > 5)
        self.assertTrue(book_sels and len(book_sels[0].options) > 5)
        chosen_cantrip_id = cantrip_sels[0].options[0][0]
        state.selections[cantrip_sels[0].key] = [chosen_cantrip_id]
        comp_with_cantrip = self.engine.evaluate(state)
        self.assertIn(chosen_cantrip_id, comp_with_cantrip.spellcasting.granted_spell_ids)

        self.assertEqual(comp.armor_class, 12)
        state.inventory.append(
            InventoryItem(
                element_id="ID_WOTC_ARMOR_LIGHT_PADDED",
                name="Padded",
                quantity=1,
                equipped=True,
                weight=8.0,
                category="Armor",
            )
        )
        comp_armored = self.engine.evaluate(state)
        self.assertEqual(comp_armored.armor_class, 13)

    def test_03_dnd5e_round_trip(self) -> None:
        state = CharacterState(
            name="Lyra Nightbreeze",
            player_name="Lukas",
            race_id="ID_RACE_DRAGONBORN",
            class_id="ID_WOTC_PHB_CLASS_WIZARD",
            background_id="ID_BACKGROUND_ACOLYTE",
            level=3,
            currency={"cp": 5, "sp": 12, "ep": 0, "gp": 45, "pp": 1},
            known_spells=["ID_PHB_SPELL_ACID_SPLASH"],
            prepared_spells=["ID_PHB_SPELL_ACID_SPLASH"],
            notes="Met at the Yawning Portal.",
        )
        comp = self.engine.evaluate(state)
        if comp.active_selections:
            first_sel = comp.active_selections[0]
            if first_sel.options:
                state.selections[first_sel.key] = [first_sel.options[0][0]]

        state.inventory.append(
            InventoryItem(
                element_id="ID_WOTC_PHB_WEAPON_CLUB",
                name="Club",
                quantity=1,
                equipped=True,
                weight=2.0,
                category="Weapon",
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "lyra.dnd5e"
            save_dnd5e(state, self.repo, comp, out_file)
            loaded = load_dnd5e(out_file, self.repo)

        self.assertEqual(loaded.name, state.name)
        self.assertEqual(loaded.player_name, state.player_name)
        self.assertEqual(loaded.race_id, state.race_id)
        self.assertEqual(loaded.class_id, state.class_id)
        self.assertEqual(loaded.background_id, state.background_id)
        self.assertEqual(loaded.level, 3)
        self.assertEqual(loaded.currency, state.currency)
        self.assertEqual(loaded.known_spells, state.known_spells)
        self.assertEqual(loaded.prepared_spells, state.prepared_spells)
        self.assertEqual(loaded.notes, state.notes)
        self.assertEqual(loaded.selections, state.selections)
        self.assertEqual(len(loaded.inventory), 1)
        self.assertEqual(loaded.inventory[0].element_id, "ID_WOTC_PHB_WEAPON_CLUB")

    def test_04_pdf_export_5e_and_55e(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "avatar.png"
            img = QImage(32, 32, QImage.Format.Format_ARGB32)
            img.fill(QColor("#2b6cb0"))
            self.assertTrue(img.save(str(img_path), "PNG"))
            portrait_b64 = encode_portrait_file(img_path)

            state_55e = CharacterState(
                name="Lyra 2024",
                ruleset="5.5e",
                race_id="ID_RACE_DRAGONBORN",
                class_id="ID_WOTC_PHB_CLASS_WIZARD",
                background_id="ID_BACKGROUND_ACOLYTE",
                level=5,
                background_asi={"intelligence": 2, "constitution": 1},
                known_spells=["ID_PHB_SPELL_ACID_SPLASH"],
                portrait_path=str(img_path),
                portrait_base64=portrait_b64,
            )
            comp_55e = self.engine.evaluate(state_55e)
            self.assertEqual(comp_55e.ability_bonuses["strength"], 0)
            self.assertEqual(comp_55e.ability_bonuses["intelligence"], 2)
            self.assertTrue(
                any(s.rule.name == "Origin Feat (5.5e)" for s in comp_55e.active_selections)
            )

            pdf_55e = Path(tmp) / "sheet_55e.pdf"
            export_character_pdf(state_55e, comp_55e, self.repo, pdf_55e, TEMPLATES_DIR)
            self.assertTrue(pdf_55e.is_file())
            self.assertTrue(pdf_55e.read_bytes().startswith(b"%PDF-"))

    def test_05_gui_smoke_empty_defaults_and_10_tabs(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg = AppConfig(characters_dir=str(tmp_path / "chars"))
            win = MainWindow(
                self.repo,
                DATA_DIR,
                custom_dir=tmp_path / "custom",
                templates_dir=TEMPLATES_DIR,
                config=cfg,
                config_path=tmp_path / "config.json",
                auto_sync=False,
            )
            # Nothing pre-selected on creation
            self.assertEqual(win.state.race_id, "")
            self.assertEqual(win.state.class_id, "")
            self.assertEqual(win.state.background_id, "")

            # 3 screens + 10 builder tabs
            self.assertEqual(win.screen_stack.currentIndex(), 0)
            win.show_github_manager()
            self.assertEqual(win.screen_stack.currentIndex(), 1)
            win.show_builder()
            self.assertEqual(win.screen_stack.currentIndex(), 2)
            self.assertEqual(win.builder_tabs_stack.count(), 10)

            win.spn_level.setValue(4)
            self.assertEqual(win.state.level, 4)
            self.assertTrue(win._dirty)
            win.save_character()
            self.assertFalse(win._dirty)

            win.select_race_by_id("ID_RACE_DRAGONBORN")
            win.select_class_by_id("ID_WOTC_PHB_CLASS_WIZARD")
            self.assertTrue(win._dirty)
            self.assertEqual(win.state.race_id, "ID_RACE_DRAGONBORN")
            self.assertEqual(win.state.class_id, "ID_WOTC_PHB_CLASS_WIZARD")
            self.assertFalse(win.chk_manual_spells.isChecked())
            self.assertFalse(win.state.allow_extra_spells)
            self.assertGreater(win.lst_spell_catalog.count(), 0)
            self.assertGreater(win.tbl_equip_catalog.rowCount(), 0)
            # Spell list rows use custom widgets cleanly; equipment table uses Type/Name/Rarity/Weight/Cost columns
            self.assertEqual(win.lst_spell_catalog.item(0).text(), "")
            self.assertNotIn("[Weapon]", win.tbl_equip_catalog.item(0, 1).text())

            # Skills & Saving Throws tables fit directly without an enclosing QScrollArea
            self.assertEqual(win.tbl_saves.rowCount(), 6)
            self.assertEqual(win.tbl_skills.rowCount(), 18)
            self.assertEqual(win.tbl_saves.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.assertEqual(win.tbl_skills.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.assertNotIsInstance(win.tbl_saves.parentWidget().parentWidget(), QScrollArea)

            # Ability score spinboxes hide native arrows in favor of + and - buttons
            for spn in win.ab_spinboxes.values():
                self.assertEqual(spn.buttonSymbols(), QAbstractSpinBox.ButtonSymbols.NoButtons)

            # Clickable column header sorting + custom-colored magic sparkles pixmap
            win._on_equip_header_clicked(2)
            self.assertEqual(win._equip_sort_col, 2)
            self.assertEqual(win._equip_sort_order, Qt.SortOrder.AscendingOrder)
            win._on_equip_header_clicked(2)
            self.assertEqual(win._equip_sort_order, Qt.SortOrder.DescendingOrder)
            self.assertGreater(win.tbl_equip_catalog.rowCount(), 0)
            spark_pix = _make_magic_sparkles_pixmap("#f472b6", 14)
            self.assertFalse(spark_pix.isNull())
            self.assertEqual((spark_pix.width(), spark_pix.height()), (14, 14))
            vr_el = Element(id="ID_VR", name="Staff", type="Magic Item", setters={"rarity": "Very Rare"})
            self.assertEqual(_item_rarity_info(vr_el)[:3], (4, "V", "Very Rare"))

            dlg = NewCharacterDialog(win)
            dlg.rad_55e.setChecked(True)
            self.assertEqual(dlg.selected_ruleset(), "5.5e")

            dup_dlg = DuplicateReportDialog(self.repo.duplicates, win)
            self.assertEqual(dup_dlg.table.rowCount(), len(self.repo.duplicates))
            win._dirty = False
            win.close()


if __name__ == "__main__":
    unittest.main()
