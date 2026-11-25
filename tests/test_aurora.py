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
            self.assertGreater(win.tbl_spell_catalog.rowCount(), 0)
            self.assertGreater(win.tbl_equip_catalog.rowCount(), 0)
            # Spell catalog uses Name/Level columns with clickable sorting; equipment uses Type/Name/Rarity/Weight/Cost
            self.assertTrue(bool(win.tbl_spell_catalog.item(0, 0).text()))
            self.assertNotIn("[Weapon]", win.tbl_equip_catalog.item(0, 1).text())
            win._on_spell_header_clicked(1)
            self.assertEqual(win._spell_sort_col, 1)
            self.assertEqual(win._spell_sort_order, Qt.SortOrder.AscendingOrder)
            win._on_spell_header_clicked(1)
            self.assertEqual(win._spell_sort_order, Qt.SortOrder.DescendingOrder)

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
            win.current_file = tmp_path / "test.dnd5e"
            win.close()

    def test_06_ui_fixes_spell_sort_tables_choices_spinboxes(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit
        from aurora_borealis.config import AppConfig
        from aurora_borealis.loader import ContentRepository
        from aurora_borealis.models import Element, GrantRule, SelectRule
        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        repo = ContentRepository()
        for el in [
            Element(id="ID_SP_Z", name="Zeta Bolt", type="Spell", setters={"level": "1"}),
            Element(id="ID_SP_A", name="Acid Splash", type="Spell", setters={"level": "0"}),
            Element(id="ID_SP_F", name="Fireball", type="Spell", setters={"level": "3"}),
            Element(id="ID_SP_M", name="Magic Missile", type="Spell", setters={"level": "1"}),
            Element(id="ID_SKILL_ATH", name="Skill (Athletics)", type="Proficiency", supports=["Skill"]),
            Element(id="ID_SKILL_PER", name="Skill (Perception)", type="Proficiency", supports=["Skill"]),
            Element(id="ID_SKILL_STE", name="Skill (Stealth)", type="Proficiency", supports=["Skill"]),
            Element(id="ID_LANG_COMMON", name="Common", type="Language", supports=["Standard"]),
            Element(id="ID_LANG_ELVISH", name="Elvish", type="Language", supports=["Standard"]),
            Element(id="ID_LANG_DWARVISH", name="Dwarvish", type="Language", supports=["Standard"]),
            Element(
                id="ID_RACE_TEST",
                name="Test Elf",
                type="Race",
                grant_rules=[GrantRule(type="Language", id="ID_LANG_COMMON", level=1)],
                select_rules=[
                    SelectRule(type="Language", name="Extra Language", number=2, level=1, supports="Standard"),
                ],
            ),
            Element(
                id="ID_CLASS_TEST",
                name="Test Rogue",
                type="Class",
                select_rules=[
                    SelectRule(type="Proficiency", name="Class Skills", number=2, level=1, supports="Skill"),
                ],
            ),
        ]:
            repo.by_id[el.id] = el
            repo.by_type[el.type].append(el)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            win = MainWindow(
                repo,
                tmp_path,
                custom_dir=tmp_path / "custom",
                templates_dir=tmp_path / "templates",
                config=AppConfig(characters_dir=str(tmp_path / "chars")),
                config_path=tmp_path / "config.json",
                auto_sync=False,
            )
            win.show_builder()
            win.show()
            app.processEvents()

            # 1. Spell catalog sorting by Name (col 0) and Level (col 1)
            names_asc = [win.tbl_spell_catalog.item(r, 0).text() for r in range(win.tbl_spell_catalog.rowCount())]
            self.assertEqual(names_asc, ["Acid Splash", "Fireball", "Magic Missile", "Zeta Bolt"])
            win._on_spell_header_clicked(0)
            names_desc = [win.tbl_spell_catalog.item(r, 0).text() for r in range(win.tbl_spell_catalog.rowCount())]
            self.assertEqual(names_desc, ["Zeta Bolt", "Magic Missile", "Fireball", "Acid Splash"])
            win._on_spell_header_clicked(1)
            lvls_asc = [win.tbl_spell_catalog.item(r, 0).text() for r in range(win.tbl_spell_catalog.rowCount())]
            self.assertEqual(lvls_asc, ["Acid Splash", "Magic Missile", "Zeta Bolt", "Fireball"])
            win._on_spell_header_clicked(1)
            lvls_desc = [win.tbl_spell_catalog.item(r, 0).text() for r in range(win.tbl_spell_catalog.rowCount())]
            self.assertEqual(lvls_desc, ["Fireball", "Zeta Bolt", "Magic Missile", "Acid Splash"])

            # 2. Saving Throws & Skills tables show all rows without scrolling
            win.builder_tabs_stack.setCurrentIndex(6)
            app.processEvents()
            self.assertEqual(win.tbl_saves.verticalScrollBar().maximum(), 0)
            self.assertEqual(win.tbl_skills.verticalScrollBar().maximum(), 0)
            self.assertEqual(win.tbl_saves.rowHeight(0), 22)
            self.assertEqual(win.tbl_skills.rowHeight(0), 22)

            # 3. No duplicate choices within a multi-slot choice or against already-granted elements
            win.select_race_by_id("ID_RACE_TEST")
            win.select_class_by_id("ID_CLASS_TEST")
            app.processEvents()
            def _layout_combos(layout) -> list[QComboBox]:
                out: list[QComboBox] = []
                for i in range(layout.count()):
                    w = layout.itemAt(i).widget()
                    if w is not None:
                        out.extend(w.findChildren(QComboBox))
                return out

            lang_combos = _layout_combos(win.tab_race.choices_layout)
            self.assertEqual(len(lang_combos), 2)
            # Already-granted Common must not appear in either Language combo
            for cmb in lang_combos:
                data_vals = [cmb.itemData(i) for i in range(cmb.count())]
                self.assertNotIn("ID_LANG_COMMON", data_vals)
                self.assertIn("ID_LANG_ELVISH", data_vals)
                self.assertIn("ID_LANG_DWARVISH", data_vals)

            # Selecting Elvish in slot 0 removes Elvish from slot 1
            lang_combos[0].setCurrentIndex(lang_combos[0].findData("ID_LANG_ELVISH"))
            app.processEvents()
            lang_combos_after = _layout_combos(win.tab_race.choices_layout)
            self.assertEqual(len(lang_combos_after), 2)
            slot0_vals = [lang_combos_after[0].itemData(i) for i in range(lang_combos_after[0].count())]
            slot1_vals = [lang_combos_after[1].itemData(i) for i in range(lang_combos_after[1].count())]
            self.assertIn("ID_LANG_ELVISH", slot0_vals)
            self.assertNotIn("ID_LANG_ELVISH", slot1_vals)
            self.assertIn("ID_LANG_DWARVISH", slot1_vals)

            # Selecting Athletics in Class Skills slot 0 removes Athletics from slot 1
            skill_combos = _layout_combos(win.tab_class.choices_layout)
            skill_combos[0].setCurrentIndex(skill_combos[0].findData("ID_SKILL_ATH"))
            app.processEvents()
            skill_combos_after = _layout_combos(win.tab_class.choices_layout)
            sk1_vals = [skill_combos_after[1].itemData(i) for i in range(skill_combos_after[1].count())]
            self.assertNotIn("ID_SKILL_ATH", sk1_vals)
            self.assertIn("ID_SKILL_PER", sk1_vals)

            # 4. Level & Ability score spinboxes have full usable inner QLineEdit width
            win.builder_tabs_stack.setCurrentIndex(2)
            app.processEvents()
            lvl_le = win.spn_level.findChild(QLineEdit)
            self.assertGreaterEqual(lvl_le.width(), 30)

            win.builder_tabs_stack.setCurrentIndex(4)
            app.processEvents()
            for spn in win.ab_spinboxes.values():
                le = spn.findChild(QLineEdit)
                self.assertGreaterEqual(le.width(), 30)

            # 5. SVG App Icon loaded, File/Tools menu bar removed, KDE custom titlebar + +/- scale + theme
            self.assertFalse(win.windowIcon().isNull())
            self.assertFalse(win.menuBar().isVisible())
            self.assertEqual(len(win.menuBar().actions()), 0)
            self.assertGreaterEqual(len(win.actions()), 5)
            self.assertTrue(bool(win.windowFlags() & Qt.WindowType.FramelessWindowHint))
            self.assertFalse(win.title_bar.btn_min.icon().isNull())
            self.assertFalse(win.title_bar.btn_max.icon().isNull())
            self.assertFalse(win.title_bar.btn_close.icon().isNull())
            self.assertEqual(win.config.theme, "dark")
            self.assertEqual(win.title_bar.btn_theme.text(), "")
            self.assertFalse(win.title_bar.btn_theme.icon().isNull())
            self.assertEqual(win.title_bar.btn_theme.property("_aurora_icon_name"), "sun")
            win.toggle_theme()
            self.assertEqual(win.config.theme, "light")
            self.assertEqual(win.title_bar.btn_theme.text(), "")
            self.assertFalse(win.title_bar.btn_theme.icon().isNull())
            self.assertEqual(win.title_bar.btn_theme.property("_aurora_icon_name"), "moon")
            win.toggle_theme()
            self.assertEqual(win.config.theme, "dark")
            self.assertEqual(win.title_bar.btn_theme.property("_aurora_icon_name"), "sun")
            win.title_bar.btn_scale_plus.click()
            self.assertEqual(win.config.ui_scale, 1.1)
            self.assertEqual(win.title_bar.cmb_scale_stage.currentText(), "Large (110%)")
            win.title_bar.btn_scale_minus.click()
            self.assertEqual(win.config.ui_scale, 1.0)
            self.assertEqual(win.title_bar.cmb_scale_stage.currentText(), "Normal (100%)")

            win._dirty = False
            win.current_file = tmp_path / "test.dnd5e"
            win.close()

    def test_07_filters_overwrite_guard_legacy_dnd5e_and_cards(self) -> None:
        from unittest import mock
        from PySide6.QtWidgets import QApplication, QFrame, QPushButton
        from aurora_borealis.config import AppConfig
        from aurora_borealis.loader import ContentRepository
        from aurora_borealis.models import CharacterState, Element, SelectRule
        from aurora_borealis.persistence import load_dnd5e
        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        repo = ContentRepository()
        for el in [
            Element(id="ID_SP_FB", name="Fireball", type="Spell", setters={"level": "3", "school": "Evocation"}),
            Element(id="ID_SP_ID", name="Identify", type="Spell", setters={"level": "1", "school": "Divination", "isRitual": "true"}),
            Element(id="ID_IT_POT", name="Potion of Healing", type="Magic Item", setters={"rarity": "Common", "category": "Potion"}),
            Element(id="ID_IT_SWD", name="Longsword", type="Weapon", setters={"rarity": "Common", "category": "Weapon"}),
            Element(id="ID_SKILL_ARC", name="Skill (Arcana)", type="Proficiency", supports=["Skill"]),
            Element(id="ID_CLS_WIZ", name="Wizard", type="Class", select_rules=[
                SelectRule(type="Proficiency", name="Wizard Skill", number=1, level=1, supports="Skill"),
            ]),
        ]:
            repo.by_id[el.id] = el
            repo.by_type[el.type].append(el)

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            # 1. Backward compatibility with original Aurora .dnd5e XML (no <selections>, nested elements, <notes><note>, <storage>)
            legacy_xml = p / "legacy_aurora.dnd5e"
            legacy_xml.write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<character version="0.2">
  <display-properties><name>Legacy Merlyn</name><level>3</level></display-properties>
  <build>
    <input>
      <name>Legacy Merlyn</name>
      <background-story>Born in Waterdeep.</background-story>
      <notes><note column="left">Left note</note><note column="right">Right note</note></notes>
    </input>
    <abilities><strength>8</strength><dexterity>14</dexterity><constitution>12</constitution><intelligence>16</intelligence><wisdom>10</wisdom><charisma>10</charisma></abilities>
    <elements>
      <element type="Level" name="1" id="ID_LVL_1">
        <element type="Class" name="Wizard" id="ID_CLS_WIZ">
          <element type="Proficiency" name="Skill (Arcana)" id="ID_SKILL_ARC" />
        </element>
      </element>
      <element type="Level" name="2" id="ID_LVL_2" />
      <element type="Level" name="3" id="ID_LVL_3" />
    </elements>
    <equipment>
      <storage>
        <item identifier="ID_IT_POT" name="Potion of Healing" amount="2" weight="0.5 lb." equipped="false" />
      </storage>
    </equipment>
    <magic><spellcasting name="Wizard" ability="Intelligence"><spells><spell id="ID_SP_FB" always-prepared="true" /></spells></spellcasting></magic>
  </build>
</character>
""",
                encoding="utf-8",
            )
            loaded = load_dnd5e(legacy_xml, repo)
            self.assertEqual(loaded.name, "Legacy Merlyn")
            self.assertEqual(loaded.level, 3)
            self.assertEqual(loaded.class_id, "ID_CLS_WIZ")
            self.assertEqual(loaded.backstory, "Born in Waterdeep.")
            self.assertIn("Left note", loaded.notes)
            self.assertIn("Right note", loaded.notes)
            self.assertEqual(len(loaded.inventory), 1)
            self.assertAlmostEqual(loaded.inventory[0].weight, 0.5)
            self.assertIn("ID_SP_FB", loaded.prepared_spells)
            self.assertTrue(any("ID_SKILL_ARC" in vals for vals in loaded.selections.values()))

            # 2. Duplicate character name overwrite check
            win = MainWindow(
                repo, p, custom_dir=p / "c", templates_dir=p / "t",
                config=AppConfig(characters_dir=str(p / "chars")),
                config_path=p / "cfg.json", auto_sync=False,
            )
            win.state = CharacterState(name="Lyra")
            self.assertTrue(win.save_character())
            win.current_file = None
            win.state = CharacterState(name="Lyra")
            with mock.patch("aurora_borealis.ui.main_window.QMessageBox.warning") as mock_warn:
                self.assertFalse(win.save_character())
                self.assertTrue(mock_warn.called)

            # 3. Equipment (Consumables) & Spell (School / Ritual) filters
            win.cmb_equip_category.setCurrentText("Consumables")
            self.assertEqual(win.tbl_equip_catalog.rowCount(), 1)
            self.assertEqual(win.tbl_equip_catalog.item(0, 1).text(), "Potion of Healing")

            win.cmb_spell_school.setCurrentText("Evocation")
            self.assertEqual(win.tbl_spell_catalog.rowCount(), 1)
            self.assertEqual(win.tbl_spell_catalog.item(0, 0).text(), "Fireball")
            win.cmb_spell_school.setCurrentText("All Schools")
            win.cmb_spell_prop.setCurrentText("Ritual")
            self.assertEqual(win.tbl_spell_catalog.rowCount(), 1)
            self.assertEqual(win.tbl_spell_catalog.item(0, 0).text(), "Identify")

            # 4. Additional Content actions column scales width to buttons
            win.github_view.set_installed_indexes([{
                "slug": "core", "name": "Core", "url": "https://example.com/core.index",
                "version": "1.0", "file_count": 10, "local_dir": str(p / "c" / "core"),
            }])
            self.assertGreaterEqual(win.github_view.tbl_indexes.columnWidth(4), 150)

            # 5. Square portrait character cards + trash bin icon on delete button
            win.refresh_library()
            cards = [
                win.select_view.grid.itemAt(i).widget()
                for i in range(win.select_view.grid.count())
                if isinstance(win.select_view.grid.itemAt(i).widget(), QFrame)
            ]
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].width(), cards[0].height())
            trash_btns = [b for b in cards[0].findChildren(QPushButton) if b.objectName() == "TrashBtn"]
            self.assertEqual(len(trash_btns), 1)
            self.assertFalse(trash_btns[0].icon().isNull())

            # 6. Magic / Infused Armor & Weapon dialog + AC calculation
            from aurora_borealis.ui.dialogs import MagicGearDialog
            plate = Element(id="ID_ARM_PLATE", name="Plate Armor", type="Armor", setters={"armor": "Heavy", "armorClass": "18"})
            repo.by_id[plate.id] = plate
            repo.by_type[plate.type].append(plate)
            mg_dlg = MagicGearDialog(repo, initial_element=plate, parent=win)
            mg_dlg.spn_bonus.setValue(2)
            inv_magic = mg_dlg.build_inventory_item()
            self.assertIsNotNone(inv_magic)
            self.assertEqual(inv_magic.magic_bonus, 2)
            self.assertEqual(inv_magic.category, "Armor")
            win.state.inventory = [inv_magic]
            comp_magic = win.engine.evaluate(win.state)
            self.assertEqual(comp_magic.armor_class, 20)

            # 7. XP spinbox + Attunement rules enforcement & override
            win.spn_xp.setValue(6500)
            self.assertEqual(win.state.xp, 6500)
            from aurora_borealis.models import InventoryItem
            win.state.inventory = [
                InventoryItem(element_id=f"ID_ATT_{i}", name=f"Ring {i}", quantity=1, equipped=True, attuned=(i < 3), category="Magic Item")
                for i in range(4)
            ]
            win.config.enforce_attunement = True
            win._sync_equipment_tab()
            cb4 = win.tbl_inventory.cellWidget(3, 4)
            with mock.patch("aurora_borealis.ui.main_window.QMessageBox.information") as mock_info:
                cb4.setChecked(True)
                self.assertTrue(mock_info.called)
                self.assertFalse(win.state.inventory[3].attuned)
            # Disabling enforcement allows 4th attuned item
            win.chk_enforce_attunement.setChecked(False)
            cb4 = win.tbl_inventory.cellWidget(3, 4)
            cb4.setChecked(True)
            self.assertTrue(win.state.inventory[3].attuned)

            win._dirty = False
            win.current_file = p / "chars" / "done.dnd5e"
            win.close()


if __name__ == "__main__":
    unittest.main()
