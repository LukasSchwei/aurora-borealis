"""Automated tests for all 12 reported Windows/Linux UI, scroll, Point Buy, cap, override & wizard bug fixes."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aurora_borealis.config import AppConfig
from aurora_borealis.engine import RulesEngine
from aurora_borealis.loader import ContentRepository
from aurora_borealis.models import CharacterState, ClassLevel, Element, GrantRule, SelectRule, SpellcastingInfo
from aurora_borealis.persistence import load_dnd5e, save_dnd5e
from aurora_borealis.ui.styles import DARK_STYLESHEET, LIGHT_STYLESHEET


def _populate_repo(repo: ContentRepository, elements: list[Element]) -> None:
    for el in elements:
        repo.by_id[el.id] = el
        repo.by_type[el.type].append(el)
        repo._type_by_id[el.type][el.id] = el
        repo._by_type_name[(el.type, el.name.lower())] = el
        repo._index_element_metadata(el)
    repo._sync_type_lists_and_caches()


class UiAndRuleBugfixTests(unittest.TestCase):
    def _make_repo(self) -> ContentRepository:
        repo = ContentRepository()
        langs = [Element(id=f"ID_LANG_{i}", name=f"Language {i:02d}", type="Language") for i in range(30)]
        skills = [Element(id=f"ID_SKILL_{i}", name=f"Skill ({i:02d})", type="Proficiency", supports=["Skill"]) for i in range(12)]
        spells = [
            Element(id=f"ID_SP_C_{i}", name=f"Cantrip {i}", type="Spell", supports=["Wizard", "Sorcerer", "Bard"], setters={"level": "0", "school": "Evocation"})
            for i in range(6)
        ] + [
            Element(id=f"ID_SP_L1_{i}", name=f"Spell Lv1 {i}", type="Spell", supports=["Wizard", "Sorcerer", "Bard"], setters={"level": "1", "school": "Evocation"})
            for i in range(10)
        ]
        _populate_repo(
            repo,
            [
                *langs,
                *skills,
                *spells,
                Element(
                    id="ID_CLS_WIZ",
                    name="Wizard",
                    type="Class",
                    setters={"hd": "d6"},
                    spellcasting=SpellcastingInfo(name="Wizard", ability="Intelligence", spell_list="Wizard", prepare=True),
                    select_rules=[
                        SelectRule(type="Language", name="Wizard Languages", number=6, level=1, supports=""),
                        SelectRule(type="Proficiency", name="Wizard Extra Skill", number=4, level=1, supports="Skill"),
                    ],
                ),
                Element(
                    id="ID_CLS_SORC",
                    name="Sorcerer",
                    type="Class",
                    setters={"hd": "d6"},
                    spellcasting=SpellcastingInfo(name="Sorcerer", ability="Charisma", spell_list="Sorcerer", prepare=False),
                ),
                Element(
                    id="ID_BG_SAGE",
                    name="Sage",
                    type="Background",
                    setters={"ability_scores": "Constitution, Intelligence, Wisdom"},
                ),
            ],
        )
        return repo

    def test_01_styles_radiobutton_spinbox_stacked_arrows_and_wheel_scroll(self) -> None:
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtWidgets import QApplication, QComboBox, QScrollArea, QVBoxLayout, QWidget

        from aurora_borealis.ui.ui_helpers import configure_dropdown_combo, install_global_wheel_filter

        app = QApplication.instance() or QApplication([])
        install_global_wheel_filter(app)

        assets = Path(__file__).resolve().parent.parent / "aurora_borealis" / "assets"
        for svg in ("chevron-up-light.svg", "chevron-down-light.svg", "chevron-up-dark.svg", "chevron-down-dark.svg"):
            self.assertTrue((assets / svg).is_file(), f"Missing chevron icon {svg}")

        for css in (DARK_STYLESHEET, LIGHT_STYLESHEET):
            self.assertIn("QRadioButton::indicator:checked", css)
            self.assertIn("qradialgradient", css)
            self.assertIn('QSpinBox[buttonSymbols="0"]::up-button', css)
            self.assertIn("subcontrol-position: top right;", css)
            self.assertIn('QSpinBox[buttonSymbols="0"]::down-button', css)
            self.assertIn("subcontrol-position: bottom right;", css)
            self.assertIn("combobox-popup: 0;", css)

        # Hovering QComboBox inside a QScrollArea forwards wheel events to QScrollArea
        scroll = QScrollArea()
        scroll.resize(300, 160)
        host = QWidget()
        vl = QVBoxLayout(host)
        cmb = QComboBox()
        configure_dropdown_combo(cmb, max_visible=14)
        self.assertLessEqual(cmb.maxVisibleItems(), 14)
        for i in range(25):
            cmb.addItem(f"Option {i}", i)
        cmb.setCurrentIndex(0)
        vl.addWidget(cmb)
        spacer = QWidget()
        spacer.setFixedHeight(800)
        vl.addWidget(spacer)
        scroll.setWidget(host)
        scroll.show()
        app.processEvents()

        self.assertEqual(scroll.verticalScrollBar().value(), 0)
        ev = QWheelEvent(
            QPointF(10, 10),
            QPointF(cmb.mapToGlobal(QPoint(10, 10))),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(cmb, ev)
        app.processEvents()
        self.assertEqual(cmb.currentIndex(), 0)
        self.assertGreater(scroll.verticalScrollBar().value(), 0)
        scroll.close()

    def test_02_point_buy_enforced_asi_cap_above_20_and_proficiency_overrides(self) -> None:
        from PySide6.QtWidgets import QApplication
        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        repo = self._make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            win = MainWindow(
                repo,
                p,
                custom_dir=p / "c",
                templates_dir=p / "t",
                config=AppConfig(characters_dir=str(p / "chars")),
                config_path=p / "cfg.json",
                auto_sync=False,
            )

            # Default character starts with 27/27 Point Buy enforced
            self.assertTrue(win._is_point_buy_enforced())
            self.assertIn("27 / 27", win.lbl_point_buy.text())
            self.assertFalse(win.ab_plus_btns["strength"].isEnabled())
            win._step_ability("strength", 1)
            self.assertEqual(win.state.abilities["strength"], 15)

            # Lowering STR frees points, allowing DEX to increase
            win._step_ability("strength", -1)
            self.assertEqual(win.state.abilities["strength"], 14)
            self.assertTrue(win.ab_plus_btns["dexterity"].isEnabled())

            # Override Point Buy unlocks up to 20; Override ASI Cap unlocks up to 30
            win.chk_override_point_buy.setChecked(True)
            self.assertFalse(win._is_point_buy_enforced())
            win.ab_spinboxes["strength"].setValue(20)
            self.assertEqual(win.state.abilities["strength"], 20)

            win.state.abilities["strength"] = 24
            win._recalculate_and_refresh()
            # Without override_asi_cap, total is capped at 20
            self.assertEqual(win.computed.ability_totals["strength"], 20)

            win.chk_override_asi_cap.setChecked(True)
            app.processEvents()
            self.assertEqual(win.ab_spinboxes["strength"].maximum(), 30)
            self.assertEqual(win.computed.ability_totals["strength"], 24)

            # Manual Proficiency Override (Saves, Skills + Expertise, Extra Proficiencies + Persistence)
            self.assertFalse(win.computed.saving_throws["constitution"].proficient)
            win.chk_override_proficiencies.setChecked(True)
            win._on_save_cell_clicked(2, 1)  # CON save
            self.assertTrue(win.computed.saving_throws["constitution"].proficient)

            win._on_skill_cell_clicked(0, 2)  # Acrobatics -> Proficient
            self.assertTrue(win.computed.skills["Acrobatics"].proficient)
            self.assertFalse(win.computed.skills["Acrobatics"].expertise)
            win._on_skill_cell_clicked(0, 2)  # Acrobatics -> Expertise
            self.assertTrue(win.computed.skills["Acrobatics"].expertise)

            win.cmb_manual_prof.setCurrentText("Heavy Armor")
            win._add_manual_proficiency()
            self.assertIn("Heavy Armor", win.computed.proficiencies)

            save_path = p / "overrides.dnd5e"
            save_dnd5e(win.state, repo, win.computed, save_path)
            loaded = load_dnd5e(save_path, repo)
            self.assertIn("constitution", loaded.manual_save_profs)
            self.assertIn("Acrobatics", loaded.manual_skill_expertise)
            self.assertIn("Heavy Armor", loaded.manual_proficiencies)

            win._dirty = False
            win.close()

    def test_03_overview_scroll_full_hp_table_bg_asi_and_choices_scroll_preserve(self) -> None:
        from PySide6.QtWidgets import QApplication, QScrollArea
        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        repo = self._make_repo()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            win = MainWindow(
                repo,
                p,
                custom_dir=p / "c",
                templates_dir=p / "t",
                config=AppConfig(characters_dir=str(p / "chars")),
                config_path=p / "cfg.json",
                auto_sync=False,
            )
            win.resize(900, 620)
            win.show()

            # Overview tab is wrapped in a QScrollArea
            self.assertIsInstance(win.builder_tabs_stack.widget(0), QScrollArea)
            self.assertIs(win.overview_scroll, win.builder_tabs_stack.widget(0))

            # Full HP table without scrolling for Lv 12 rolled HP
            win.state.ruleset = "5.5e"
            win.state.classes = [ClassLevel("ID_CLS_WIZ", 12)]
            win.state.sync_from_classes()
            win.state.hp_mode = "rolled"
            win.state.background_id = "ID_BG_SAGE"
            win._recalculate_and_refresh()
            app.processEvents()

            self.assertEqual(win.tbl_hp_rolls.rowCount(), 12)
            self.assertEqual(win.tbl_hp_rolls.verticalScrollBar().maximum(), 0)
            self.assertGreaterEqual(win.tbl_hp_rolls.height(), 12 * 34)

            # Choices scroll preserved across choice combo selection
            win.builder_tabs_stack.setCurrentIndex(5)
            app.processEvents()
            sb = win.selections_scroll.verticalScrollBar()
            if sb.maximum() > 20:
                sb.setValue(sb.maximum() // 2)
                saved = sb.value()
                # Trigger a selection change
                combos = win.selections_container.findChildren(type(win.cmb_ruleset))
                self.assertTrue(len(combos) >= 1)
                combos[0].setCurrentIndex(1)
                app.processEvents()
                self.assertGreater(win.selections_scroll.verticalScrollBar().value(), 0)
                self.assertLessEqual(abs(win.selections_scroll.verticalScrollBar().value() - saved), 40)

            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()

    def test_04_level_up_wizard_choices_width_and_spell_limit_enforcement(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from aurora_borealis.ui.level_up_wizard import LevelUpWizardDialog

        app = QApplication.instance() or QApplication([])
        repo = self._make_repo()
        engine = RulesEngine(repo)

        # Level 1 -> Level 2 Sorcerer: Lv 2 Sorcerer knows max 4 cantrips & 3 leveled spells in 5e
        st = CharacterState(
            name="Lyra",
            ruleset="5e",
            classes=[ClassLevel("ID_CLS_SORC", 1)],
            known_spells=["ID_SP_C_0", "ID_SP_C_1", "ID_SP_C_2", "ID_SP_L1_0", "ID_SP_L1_1"],
            spell_sources={s: "ID_CLS_SORC" for s in ("ID_SP_C_0", "ID_SP_C_1", "ID_SP_C_2", "ID_SP_L1_0", "ID_SP_L1_1")},
        )
        st.sync_from_classes()
        dlg = LevelUpWizardDialog(st, repo, engine)
        self.assertEqual(dlg.choices_scroll.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertGreaterEqual(dlg.spn_hp_roll.width(), 84)

        dlg.go_to = None
        dlg._go_to_page(3)  # Spells page
        app.processEvents()

        # Select Cantrip 3 (4th cantrip - allowed because Sorcerer max_cantrips == 4)
        def select_spell_by_id(sid: str) -> None:
            for r in range(dlg.tbl_spell_catalog.rowCount()):
                if dlg.tbl_spell_catalog.item(r, 0).data(Qt.ItemDataRole.UserRole) == sid:
                    dlg.tbl_spell_catalog.selectRow(r)
                    return

        select_spell_by_id("ID_SP_C_3")
        dlg._add_wizard_spell()
        self.assertIn("ID_SP_C_3", dlg._wizard_added_spells)

        # Trying to add a 5th cantrip (ID_SP_C_4) is blocked with info popup
        select_spell_by_id("ID_SP_C_4")
        with mock.patch("aurora_borealis.ui.level_up_wizard.QMessageBox.information") as m_info:
            dlg._add_wizard_spell()
            self.assertTrue(m_info.called)
        self.assertNotIn("ID_SP_C_4", dlg._wizard_added_spells)

        # Add 3rd leveled spell (ID_SP_L1_2 -> allowed since Sorc Lv2 max_known == 3)
        select_spell_by_id("ID_SP_L1_2")
        dlg._add_wizard_spell()
        self.assertIn("ID_SP_L1_2", dlg._wizard_added_spells)

        # Trying to add a 4th leveled spell (ID_SP_L1_3) is blocked
        select_spell_by_id("ID_SP_L1_3")
        with mock.patch("aurora_borealis.ui.level_up_wizard.QMessageBox.information") as m_info:
            dlg._add_wizard_spell()
            self.assertTrue(m_info.called)
        self.assertNotIn("ID_SP_L1_3", dlg._wizard_added_spells)

        # Checking "Override spell limits" unlocks adding ID_SP_L1_3
        dlg.chk_override_spells.setChecked(True)
        select_spell_by_id("ID_SP_L1_3")
        dlg._add_wizard_spell()
        self.assertIn("ID_SP_L1_3", dlg._wizard_added_spells)
        dlg.close()

    def test_05_xp_level_bidirectional_sync_and_rescale_performance(self) -> None:
        from PySide6.QtWidgets import QApplication
        from aurora_borealis.engine import level_for_xp, xp_for_level
        from aurora_borealis.level_up import apply_level_up_step
        from aurora_borealis.library import CharacterSummary
        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        self.assertEqual(xp_for_level(1), 0)
        self.assertEqual(xp_for_level(2), 300)
        self.assertEqual(xp_for_level(5), 6500)
        self.assertEqual(xp_for_level(20), 355000)
        self.assertEqual(level_for_xp(0), 1)
        self.assertEqual(level_for_xp(299), 1)
        self.assertEqual(level_for_xp(300), 2)
        self.assertEqual(level_for_xp(6500), 5)
        self.assertEqual(level_for_xp(400000), 20)

        repo = self._make_repo()
        st = CharacterState(name="Xena", classes=[ClassLevel("ID_CLS_WIZ", 1)])
        st.sync_from_classes()
        step2 = apply_level_up_step(st, "ID_CLS_WIZ")
        self.assertEqual(step2.level, 2)
        self.assertEqual(step2.xp, 300)

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            win = MainWindow(
                repo,
                p,
                custom_dir=p / "c",
                templates_dir=p / "t",
                config=AppConfig(characters_dir=str(p / "chars")),
                config_path=p / "cfg.json",
                auto_sync=False,
            )
            win.select_class_by_id("ID_CLS_WIZ")

            # Level -> XP
            win.spn_level.setValue(5)
            app.processEvents()
            self.assertEqual(win.state.xp, 6500)
            self.assertEqual(win.spn_xp.value(), 6500)

            win.spn_level.setValue(2)
            app.processEvents()
            self.assertEqual(win.state.xp, 300)

            # XP -> Level
            win.spn_xp.setValue(14000)
            app.processEvents()
            self.assertEqual(win.state.level, 6)
            self.assertEqual(win.state.classes[0].level, 6)

            win.spn_xp.setValue(900)
            app.processEvents()
            self.assertEqual(win.state.level, 3)

            # Rescale updates fixed widget sizes cleanly without scrollbars on Saves/Skills
            win.apply_scale(1.3, persist=False)
            app.processEvents()
            self.assertEqual(win.sidebar_panel.minimumWidth(), round(265 * 1.3))
            self.assertEqual(win.tbl_saves.rowHeight(0), round(22 * 1.3))
            self.assertEqual(win.tbl_saves.verticalScrollBar().maximum(), 0)
            self.assertEqual(win.tbl_skills.verticalScrollBar().maximum(), 0)

            # CharacterSelectView _relayout_cards reuses card instances without recreating widgets
            win.select_view.set_characters([
                CharacterSummary(
                    path=p / "chars" / f"c{i}.dnd5e",
                    filename=f"c{i}.dnd5e",
                    name=f"Char {i}",
                    level=i + 1,
                    race="Human",
                    class_name="Wizard",
                    background="Sage",
                    ruleset="5e",
                    modified_ts=0.0,
                    portrait_base64="",
                    portrait_path="",
                    favorite=False,
                )
                for i in range(6)
            ])
            cards_before = list(win.select_view._cards)
            win.select_view._last_cols = 1
            win.select_view._relayout_cards()
            cards_after = list(win.select_view._cards)
            self.assertEqual(cards_before, cards_after)
            for a, b in zip(cards_before, cards_after):
                self.assertIs(a, b)

            win._dirty = False
            win.close()

    def test_06_level_up_wizard_add_and_remove_known_and_new_spells(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from aurora_borealis.level_up import compute_character_diff, render_diff_html
        from aurora_borealis.ui.level_up_wizard import LevelUpWizardDialog

        app = QApplication.instance() or QApplication([])
        repo = self._make_repo()
        # Add a sorcerer-granted always-prepared spell to verify [Granted] cannot be removed
        _populate_repo(
            repo,
            [
                Element(
                    id="ID_SP_GRANTED",
                    name="Granted Surge",
                    type="Spell",
                    supports=["Sorcerer"],
                    setters={"level": "1", "school": "Evocation"},
                ),
                Element(
                    id="ID_FEAT_GRANT_SP",
                    name="Sorcerer Bloodline",
                    type="Archetype Feature",
                    grant_rules=[GrantRule(type="Spell", id="ID_SP_GRANTED", level=2)],
                ),
                Element(
                    id="ID_CLS_SORC_FULL",
                    name="Sorcerer",
                    type="Class",
                    setters={"hd": "d6"},
                    spellcasting=SpellcastingInfo(name="Sorcerer", ability="Charisma", spell_list="Sorcerer", prepare=False),
                    grant_rules=[GrantRule(type="Archetype Feature", id="ID_FEAT_GRANT_SP", level=2)],
                ),
            ],
        )
        engine = RulesEngine(repo)

        # Level 1 -> Level 2 Sorcerer: starts with 3 leveled spells (already at Lv 2 Sorcerer cap of 3!)
        st = CharacterState(
            name="Kaelen",
            ruleset="5e",
            classes=[ClassLevel("ID_CLS_SORC_FULL", 1)],
            known_spells=["ID_SP_C_0", "ID_SP_L1_0", "ID_SP_L1_1", "ID_SP_L1_2"],
            spell_sources={s: "ID_CLS_SORC_FULL" for s in ("ID_SP_C_0", "ID_SP_L1_0", "ID_SP_L1_1", "ID_SP_L1_2")},
        )
        st.sync_from_classes()
        dlg = LevelUpWizardDialog(st, repo, engine)
        dlg._go_to_page(3)
        app.processEvents()

        # Verify current known spells + granted spell are shown in lst_added_spells
        listed_ids = {
            dlg.lst_added_spells.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(dlg.lst_added_spells.count())
        }
        self.assertTrue({"ID_SP_C_0", "ID_SP_L1_0", "ID_SP_L1_1", "ID_SP_L1_2", "ID_SP_GRANTED"}.issubset(listed_ids))

        def select_catalog_spell(sid: str) -> bool:
            for r in range(dlg.tbl_spell_catalog.rowCount()):
                if dlg.tbl_spell_catalog.item(r, 0).data(Qt.ItemDataRole.UserRole) == sid:
                    dlg.tbl_spell_catalog.selectRow(r)
                    return True
            return False

        def select_owned_spell(sid: str) -> bool:
            for i in range(dlg.lst_added_spells.count()):
                it = dlg.lst_added_spells.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == sid:
                    dlg.lst_added_spells.setCurrentItem(it)
                    return True
            return False

        # Initially at known leveled spell cap (3/3): adding ID_SP_L1_3 is blocked
        self.assertTrue(select_catalog_spell("ID_SP_L1_3"))
        with mock.patch("aurora_borealis.ui.level_up_wizard.QMessageBox.information") as m_info:
            dlg._add_wizard_spell()
            self.assertTrue(m_info.called)
        self.assertNotIn("ID_SP_L1_3", dlg._draft_state.known_spells)

        # Attempting to remove feature-granted spell shows info and keeps it
        self.assertTrue(select_owned_spell("ID_SP_GRANTED"))
        with mock.patch("aurora_borealis.ui.level_up_wizard.QMessageBox.information") as m_info:
            dlg._remove_wizard_spell()
            self.assertTrue(m_info.called)

        # Remove an already-known spell (ID_SP_L1_0) -> frees a slot & reappears in catalog
        self.assertTrue(select_owned_spell("ID_SP_L1_0"))
        dlg._remove_wizard_spell()
        app.processEvents()
        self.assertIn("ID_SP_L1_0", dlg._wizard_removed_spells)
        self.assertNotIn("ID_SP_L1_0", dlg._draft_state.known_spells)
        self.assertTrue(select_catalog_spell("ID_SP_L1_0"))

        # Now add replacement spell ID_SP_L1_3 without override -> succeeds!
        self.assertTrue(select_catalog_spell("ID_SP_L1_3"))
        dlg._add_wizard_spell()
        app.processEvents()
        self.assertIn("ID_SP_L1_3", dlg._wizard_added_spells)
        self.assertIn("ID_SP_L1_3", dlg._draft_state.known_spells)

        # Also add and then remove a newly added cantrip (ID_SP_C_1) in the same wizard session
        self.assertTrue(select_catalog_spell("ID_SP_C_1"))
        dlg._add_wizard_spell()
        self.assertIn("ID_SP_C_1", dlg._wizard_added_spells)
        self.assertTrue(select_owned_spell("ID_SP_C_1"))
        dlg._remove_wizard_spell()
        self.assertNotIn("ID_SP_C_1", dlg._wizard_added_spells)
        self.assertNotIn("ID_SP_C_1", dlg._draft_state.known_spells)

        final_st = dlg.result_state()
        self.assertNotIn("ID_SP_L1_0", final_st.known_spells)
        self.assertIn("ID_SP_L1_3", final_st.known_spells)

        diff = compute_character_diff(st, engine.evaluate(st), final_st, engine.evaluate(final_st), repo, "ID_CLS_SORC_FULL")
        self.assertIn("Spell Lv1 3", [s for s, _ in diff.new_spells])
        self.assertIn("Spell Lv1 0", [s for s, _ in diff.removed_spells])
        diff_html = render_diff_html(diff)
        self.assertIn("Removed Spells", diff_html)
        self.assertIn("Spell Lv1 0", diff_html)
        dlg.close()

    def test_07_level4_asi_options_populated_and_applied(self) -> None:
        from PySide6.QtWidgets import QApplication, QComboBox
        from aurora_borealis.engine import is_synthetic_asi_id
        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        repo = ContentRepository()
        _populate_repo(
            repo,
            [
                Element(
                    id="ID_FEAT_ALERT",
                    name="Alert",
                    type="Feat",
                    description_html="<p>+5 bonus to initiative.</p>",
                ),
                # (a) Aurora-style Fighter class with ASI <select> & empty repo "Ability Score Improvement"
                Element(
                    id="ID_CLS_FIGHTER_AURORA",
                    name="Fighter",
                    type="Class",
                    setters={"hd": "d10"},
                    select_rules=[
                        SelectRule(
                            type="Class Feature",
                            name="Ability Score Improvement (Level 4)",
                            number=1,
                            level=4,
                            supports="Improvement Option,Fighter,4",
                        ),
                        SelectRule(
                            type="Class Feature",
                            name="Ability Score Improvement (Level 6)",
                            number=1,
                            level=6,
                            supports="Improvement Option,Fighter,6",
                        ),
                    ],
                ),
                # (b) 2-slot <select type="Ability Score Improvement" number="2">
                Element(
                    id="ID_CLS_CLERIC_2SLOT",
                    name="Cleric",
                    type="Class",
                    setters={"hd": "d8"},
                    select_rules=[
                        SelectRule(
                            type="Ability Score Improvement",
                            name="Ability Score Improvement",
                            number=2,
                            level=4,
                            supports="",
                        ),
                    ],
                ),
                # (c) 5e.tools-style class with NO ASI <select> rule
                Element(
                    id="ID_CLS_BARB_5T",
                    name="Barbarian",
                    type="Class",
                    setters={"hd": "d12"},
                ),
            ],
        )
        engine = RulesEngine(repo)

        # (a) Level 6 Fighter gets Lv4 + Lv6 ASI options populated (21 synthetic ASI + 1 Feat = 22)
        st_f = CharacterState(
            name="Bram",
            ruleset="5e",
            classes=[ClassLevel("ID_CLS_FIGHTER_AURORA", 6)],
            abilities={"strength": 15, "dexterity": 12, "constitution": 14, "intelligence": 8, "wisdom": 10, "charisma": 10},
        )
        st_f.sync_from_classes()
        comp_f0 = engine.evaluate(st_f)
        asi_sels = [s for s in comp_f0.active_selections if "Ability Score Improvement" in s.rule.name]
        self.assertEqual(len(asi_sels), 2)
        for s in asi_sels:
            self.assertEqual(len(s.options), 22)
            self.assertTrue(any(is_synthetic_asi_id(oid) for oid, _ in s.options))
            self.assertTrue(any(oid == "ID_FEAT_ALERT" for oid, _ in s.options))

        # Selecting +2 STR at Lv4 AND +1 STR / +1 DEX at Lv6 adds +3 STR, +1 DEX
        st_f.selections[asi_sels[0].key] = ["ID_AURORA_ASI_PLUS2_STRENGTH"]
        st_f.selections[asi_sels[1].key] = ["ID_AURORA_ASI_PLUS1_STRENGTH_DEXTERITY"]
        comp_f1 = engine.evaluate(st_f)
        self.assertEqual(comp_f1.ability_totals["strength"], 18)
        self.assertEqual(comp_f1.ability_totals["dexterity"], 13)

        # Selecting same +2 STR twice respects 20 cap unless override_asi_cap is enabled
        st_f.abilities["strength"] = 18
        st_f.selections[asi_sels[1].key] = ["ID_AURORA_ASI_PLUS2_STRENGTH"]
        comp_f_cap = engine.evaluate(st_f)
        self.assertEqual(comp_f_cap.ability_totals["strength"], 20)
        st_f.set_override("override_asi_cap", True)
        comp_f_uncap = engine.evaluate(st_f)
        self.assertEqual(comp_f_uncap.ability_totals["strength"], 22)

        # (b) 2-slot ASI yields 6 +1 options and stacking same +1 twice yields +2
        st_c = CharacterState(
            name="Mira",
            classes=[ClassLevel("ID_CLS_CLERIC_2SLOT", 4)],
            abilities={"strength": 10, "dexterity": 10, "constitution": 12, "intelligence": 10, "wisdom": 15, "charisma": 10},
        )
        st_c.sync_from_classes()
        comp_c0 = engine.evaluate(st_c)
        c_asi = next(s for s in comp_c0.active_selections if s.rule.type == "Ability Score Improvement")
        self.assertEqual(len(c_asi.options), 6)
        st_c.selections[c_asi.key] = ["ID_AURORA_ASI_PLUS1_WISDOM", "ID_AURORA_ASI_PLUS1_WISDOM"]
        comp_c1 = engine.evaluate(st_c)
        self.assertEqual(comp_c1.ability_totals["wisdom"], 17)

        # (c) 5e.tools-style Barbarian with NO XML ASI select still emits Lv4 ASI and skips it if level_up_asi is set
        st_b = CharacterState(
            name="Grog",
            classes=[ClassLevel("ID_CLS_BARB_5T", 4)],
            abilities={"strength": 15, "dexterity": 14, "constitution": 14, "intelligence": 8, "wisdom": 10, "charisma": 8},
        )
        st_b.sync_from_classes()
        comp_b0 = engine.evaluate(st_b)
        b_asi = [s for s in comp_b0.active_selections if "Ability Score Improvement" in s.rule.name]
        self.assertEqual(len(b_asi), 1)
        st_b.selections[b_asi[0].key] = ["ID_FEAT_ALERT"]
        comp_b1 = engine.evaluate(st_b)
        self.assertTrue(any(e.id == "ID_FEAT_ALERT" for e in comp_b1.granted_elements))

        st_b.level_up_asi["ID_CLS_BARB_5T::4"] = {"strength": 2}
        comp_b2 = engine.evaluate(st_b)
        self.assertEqual([s for s in comp_b2.active_selections if "Ability Score Improvement" in s.rule.name], [])

        # (d) MainWindow Choices tab shows all ASI options (not just --Choose--) & allows picking duplicate +2 STR across levels
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            win = MainWindow(
                repo,
                p,
                custom_dir=p / "c",
                templates_dir=p / "t",
                config=AppConfig(characters_dir=str(p / "chars")),
                config_path=p / "cfg.json",
                auto_sync=False,
            )
            win.state.classes = [ClassLevel("ID_CLS_FIGHTER_AURORA", 6)]
            win.state.sync_from_classes()
            win._recalculate_and_refresh()
            win.builder_tabs_stack.setCurrentIndex(5)
            app.processEvents()

            combos = win.selections_container.findChildren(QComboBox)
            self.assertEqual(len(combos), 2)
            self.assertEqual(combos[0].count(), 23)  # 1 "-- Choose --" + 21 ASI + 1 Feat
            self.assertEqual(combos[1].count(), 23)

            idx_str2 = combos[0].findData("ID_AURORA_ASI_PLUS2_STRENGTH")
            self.assertGreater(idx_str2, 0)
            combos[0].setCurrentIndex(idx_str2)
            app.processEvents()
            self.assertEqual(win.computed.ability_totals["strength"], 17)

            # Second ASI combo STILL offers ID_AURORA_ASI_PLUS2_STRENGTH (not hidden by taken_ids!)
            combos_after = win.selections_container.findChildren(QComboBox)
            idx_str2_lv6 = combos_after[1].findData("ID_AURORA_ASI_PLUS2_STRENGTH")
            self.assertGreater(idx_str2_lv6, 0)
            combos_after[1].setCurrentIndex(idx_str2_lv6)
            app.processEvents()
            self.assertEqual(win.computed.ability_totals["strength"], 19)

            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()

    def test_08_no_elision_and_full_sizing_on_buttons_combos_tabs_and_tables(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QSizePolicy
        from aurora_borealis.ui.companion_view import CompanionEditorView
        from aurora_borealis.ui.level_up_wizard import LevelUpWizardDialog
        from aurora_borealis.ui.main_window import MainWindow
        from aurora_borealis.ui.ui_helpers import configure_dropdown_combo

        app = QApplication.instance() or QApplication([])
        repo = self._make_repo()

        cmb_standalone = QComboBox()
        cmb_standalone.addItem("A Very Long Ability Score Improvement Option Label (+1 Strength, +1 Dexterity)", "x")
        configure_dropdown_combo(cmb_standalone)
        self.assertEqual(cmb_standalone.sizeAdjustPolicy(), QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.assertEqual(cmb_standalone.view().textElideMode(), Qt.TextElideMode.ElideNone)

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            win = MainWindow(
                repo,
                p,
                custom_dir=p / "c",
                templates_dir=p / "t",
                config=AppConfig(characters_dir=str(p / "chars")),
                config_path=p / "cfg.json",
                auto_sync=False,
            )
            win.show()
            app.processEvents()

            self.assertGreaterEqual(win.select_view._card_size(), 280)
            self.assertEqual(win.tab6_right_tabs.elideMode(), Qt.TextElideMode.ElideNone)
            self.assertEqual(win.tbl_spell_catalog.textElideMode(), Qt.TextElideMode.ElideNone)
            self.assertEqual(win.tbl_equip_catalog.textElideMode(), Qt.TextElideMode.ElideNone)
            self.assertGreaterEqual(win.tbl_equip_catalog.columnWidth(2), 90)
            self.assertGreaterEqual(win.tbl_spell_catalog.columnWidth(2), 130)

            for cmb in win.findChildren(QComboBox):
                self.assertEqual(cmb.sizeAdjustPolicy(), QComboBox.SizeAdjustPolicy.AdjustToContents)
                self.assertEqual(cmb.view().textElideMode(), Qt.TextElideMode.ElideNone)

            fixed_names = {
                "ThemeToggleBtn",
                "KdeWinBtn",
                "KdeCloseBtn",
                "StepperBtn",
                "TrashBtn",
                "FavBtn",
                "RailPortraitBtn",
                "CharPortraitBtn",
                "NewCharDashedCard",
                "OverviewCard",
            }
            for btn in win.findChildren(QPushButton):
                if btn.objectName() in fixed_names or not btn.text().strip():
                    continue
                self.assertEqual(btn.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Minimum)
                self.assertGreaterEqual(btn.minimumWidth(), btn.sizeHint().width())

            # Scaling up widens buttons & columns so nothing truncates at 130%
            win.apply_scale(1.3, persist=False)
            app.processEvents()
            self.assertGreaterEqual(win.btn_rule_overrides.minimumWidth(), win.btn_rule_overrides.sizeHint().width())

            win.current_file = p / "dummy.dnd5e"
            win._dirty = False
            win.close()

        # Wizard & CompanionEditorView also configure non-eliding combos/tabs
        st = CharacterState(name="Aria", classes=[ClassLevel("ID_CLS_WIZ", 1)])
        st.sync_from_classes()
        wiz = LevelUpWizardDialog(st, repo, RulesEngine(repo))
        for cmb in wiz.findChildren(QComboBox):
            self.assertEqual(cmb.view().textElideMode(), Qt.TextElideMode.ElideNone)
        wiz.close()

        comp_view = CompanionEditorView()
        self.assertEqual(comp_view.tabs.elideMode(), Qt.TextElideMode.ElideNone)
        for cmb in comp_view.findChildren(QComboBox):
            self.assertEqual(cmb.view().textElideMode(), Qt.TextElideMode.ElideNone)
        comp_view.close()

    def test_09_linux_and_windows_setup_wizards(self) -> None:
        import os
        import subprocess
        from PySide6.QtWidgets import QApplication
        from installer.linux_wizard import (
            build_install_command,
            build_uninstall_command,
            build_qt_wizard_dialog,
            detect_linux_installation,
        )

        root_dir = Path(__file__).resolve().parent.parent
        for rel in (
            "setup-wizard-linux.sh",
            "installer/__init__.py",
            "installer/linux_wizard.py",
            "setup-wizard-windows.bat",
            "setup-wizard-windows.ps1",
            "install-linux.sh",
            "uninstall-linux.sh",
            "install-windows.ps1",
            "uninstall-windows.ps1",
        ):
            self.assertTrue((root_dir / rel).is_file(), f"Missing {rel}")

        # Shell syntax validation on all Linux setup scripts
        for sh in ("setup-wizard-linux.sh", "install-linux.sh", "uninstall-linux.sh"):
            proc = subprocess.run(["bash", "-n", str(root_dir / sh)], capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)

        # Windows setup wizard, installer & Inno Setup feature checks
        win_wiz_ps1 = (root_dir / "setup-wizard-windows.ps1").read_text(encoding="utf-8")
        self.assertIn("System.Windows.Forms", win_wiz_ps1)
        self.assertIn("install-windows.ps1", win_wiz_ps1)
        self.assertIn("uninstall-windows.ps1", win_wiz_ps1)
        self.assertIn("-PurgeConfig", win_wiz_ps1)
        self.assertIn("-InstallAuroraLegacy", win_wiz_ps1)
        self.assertIn("-InstallFiveTools", win_wiz_ps1)
        self.assertIn("Install / Repair Aurora Borealis", win_wiz_ps1)
        self.assertIn("Uninstall Aurora Borealis", win_wiz_ps1)

        win_inst_ps1 = (root_dir / "install-windows.ps1").read_text(encoding="utf-8")
        self.assertIn("$InstallAuroraLegacy", win_inst_ps1)
        self.assertIn("$InstallFiveTools", win_inst_ps1)
        self.assertIn("--sync-official", win_inst_ps1)
        self.assertIn("--sync-5etools", win_inst_ps1)

        inno_iss = (root_dir / "packaging" / "windows" / "aurora-borealis.iss").read_text(encoding="utf-8")
        self.assertIn("auroralegacy", inno_iss)
        self.assertIn("fivetools", inno_iss)
        self.assertIn("--sync-official", inno_iss)
        self.assertIn("--sync-5etools", inno_iss)

        # Command builder & --help checks
        help_proc = subprocess.run(["bash", str(root_dir / "install-linux.sh"), "--help"], capture_output=True, text=True, check=False)
        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertIn("--install-aurora-legacy", help_proc.stdout)
        self.assertIn("--install-5etools", help_proc.stdout)
        self.assertIn("--gui", help_proc.stdout)

        in_cmd = build_install_command(root_dir, "/tmp/ab", in_place=False, install_system_deps=False, install_desktop=True)
        self.assertEqual(in_cmd[:2], ["bash", str(root_dir / "install-linux.sh")])
        self.assertIn("--prefix", in_cmd)
        self.assertIn("/tmp/ab", in_cmd)
        self.assertIn("--no-system-deps", in_cmd)
        self.assertNotIn("--install-aurora-legacy", in_cmd)
        self.assertNotIn("--install-5etools", in_cmd)

        in_cmd_packs = build_install_command(
            root_dir,
            "/tmp/ab",
            in_place=False,
            install_system_deps=False,
            install_desktop=True,
            install_aurora_legacy=True,
            install_5etools=True,
        )
        self.assertIn("--install-aurora-legacy", in_cmd_packs)
        self.assertIn("--install-5etools", in_cmd_packs)

        un_cmd = build_uninstall_command(root_dir, "/tmp/ab", purge_config=True)
        self.assertEqual(un_cmd[:2], ["bash", str(root_dir / "uninstall-linux.sh")])
        self.assertIn("--purge-config", un_cmd)

        # Qt Wizard offscreen instantiation, content pack toggles & Install/Uninstall switching
        app = QApplication.instance() or QApplication([])
        dlg = build_qt_wizard_dialog(root_dir, initial_action="install", initial_prefix="/tmp/ab-test")
        self.assertFalse(dlg.is_uninstall_selected())
        self.assertTrue(dlg.chk_aurora_legacy.isChecked())
        self.assertTrue(dlg.chk_5etools.isChecked())
        self.assertIn("--install-aurora-legacy", dlg.planned_command())
        self.assertIn("--install-5etools", dlg.planned_command())
        dlg.chk_5etools.setChecked(False)
        self.assertIn("--install-aurora-legacy", dlg.planned_command())
        self.assertNotIn("--install-5etools", dlg.planned_command())
        dlg.rad_uninstall.setChecked(True)
        dlg._go_to_page(1)
        app.processEvents()
        self.assertTrue(dlg.is_uninstall_selected())
        self.assertEqual(dlg.opt_stack.currentIndex(), 1)
        self.assertIn("Uninstall", dlg.btn_next.text())
        dlg.close()

        # Isolated uninstall-linux.sh --prefix --purge-config preserves Documents characters
        with tempfile.TemporaryDirectory() as fake_home:
            fh = Path(fake_home)
            app_dir = fh / ".local" / "share" / "aurora-borealis" / "app"
            cfg_dir = fh / ".config" / "aurora-borealis"
            bin_dir = fh / ".local" / "bin"
            docs_dir = fh / "Documents" / "Aurora Borealis" / "Characters"
            for d in (app_dir / "aurora_borealis", cfg_dir, bin_dir, docs_dir):
                d.mkdir(parents=True, exist_ok=True)
            (bin_dir / "aurora-borealis").write_text("#!/bin/sh\n", encoding="utf-8")
            (cfg_dir / "config.json").write_text("{}", encoding="utf-8")
            char_file = docs_dir / "hero.dnd55e"
            char_file.write_text("{}", encoding="utf-8")

            det_before = detect_linux_installation(fh)
            self.assertTrue(det_before["installed"])

            env = dict(os.environ)
            env["HOME"] = str(fh)
            env["XDG_DATA_HOME"] = str(fh / ".local" / "share")
            env["XDG_CONFIG_HOME"] = str(fh / ".config")
            proc_un = subprocess.run(
                ["bash", str(root_dir / "uninstall-linux.sh"), "--prefix", str(app_dir), "--purge-config"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc_un.returncode, 0, proc_un.stderr)
            self.assertFalse(app_dir.exists())
            self.assertFalse((bin_dir / "aurora-borealis").exists())
            self.assertFalse(cfg_dir.exists())
            self.assertTrue(char_file.is_file(), "Saved characters in Documents must be preserved!")


if __name__ == "__main__":
    unittest.main()
