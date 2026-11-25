"""Tests for Spells icons/class filter, 5.5e rules & .dnd55e, Animal Forms, Companions (.dndcomp), and performance."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aurora_borealis.animal_forms import (
    ANIMAL_FORMS_BY_ID,
    compute_animal_form_access,
    compute_transformed_stats,
    is_form_eligible,
    render_animal_form_html,
)
from aurora_borealis.companions import (
    CompanionState,
    create_companion_from_template,
    export_companion_pdf,
    load_dndcomp,
    render_companion_sheet_html,
    save_dndcomp,
)
from aurora_borealis.config import AppConfig
from aurora_borealis.engine import RulesEngine
from aurora_borealis.library import duplicate_character, scan_characters_folder
from aurora_borealis.loader import ContentRepository, _compile_boolean_expr
from aurora_borealis.models import CharacterState, ClassLevel, Element, GrantRule, SelectRule
from aurora_borealis.persistence import default_character_extension, load_dnd5e, save_dnd5e
from aurora_borealis.rules_55e import (
    check_55e_heavy_weapon_requirement,
    compute_weapon_mastery_limit,
    get_55e_prepared_spells,
    get_weapon_mastery,
)


def _add_elements(repo: ContentRepository, elements: list[Element]) -> None:
    for el in elements:
        repo.by_id[el.id] = el
        repo.by_type[el.type].append(el)
        repo._type_by_id[el.type][el.id] = el
        repo._by_type_name[(el.type, el.name.lower())] = el
        repo._index_element_metadata(el)
    repo._sync_type_lists_and_caches()


class FeatureSuiteTests(unittest.TestCase):
    def _build_rich_repo(self) -> ContentRepository:
        repo = ContentRepository()
        _add_elements(
            repo,
            [
                Element(
                    id="ID_CLASS_WIZ",
                    name="Wizard",
                    type="Class",
                    setters={"hd": "d6", "spellcastingAbility": "Intelligence", "spellcastingProgression": "Full"},
                ),
                Element(
                    id="ID_PROFICIENCY_SAVINGTHROW_WISDOM",
                    name="Saving Throw (Wisdom)",
                    type="Proficiency",
                ),
                Element(
                    id="ID_CLASS_CLE",
                    name="Cleric",
                    type="Class",
                    setters={"hd": "d8", "spellcastingAbility": "Wisdom", "spellcastingProgression": "Full"},
                    grant_rules=[
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_SAVINGTHROW_WISDOM", level=1)
                    ],
                    select_rules=[
                        SelectRule(
                            type="Archetype",
                            name="Divine Domain",
                            number=1,
                            level=1,
                            supports="ID_CLASS_CLE",
                        )
                    ],
                ),
                Element(
                    id="ID_ARCH_LIFE",
                    name="Life Domain",
                    type="Archetype",
                    supports=["ID_CLASS_CLE"],
                ),
                Element(
                    id="ID_CLASS_DRU",
                    name="Druid",
                    type="Class",
                    setters={"hd": "d8", "spellcastingAbility": "Wisdom", "spellcastingProgression": "Full"},
                    select_rules=[
                        SelectRule(
                            type="Archetype",
                            name="Druid Circle",
                            number=1,
                            level=2,
                            supports="ID_CLASS_DRU",
                        )
                    ],
                ),
                Element(
                    id="ID_ARCH_MOON",
                    name="Circle of the Moon",
                    type="Archetype",
                    supports=["ID_CLASS_DRU"],
                ),
                Element(
                    id="ID_CLASS_FTR",
                    name="Fighter",
                    type="Class",
                    setters={"hd": "d10"},
                ),
                Element(
                    id="ID_SP_FB",
                    name="Fireball",
                    type="Spell",
                    supports=["Wizard", "Sorcerer"],
                    setters={"level": "3", "school": "Evocation", "duration": "Instantaneous"},
                ),
                Element(
                    id="ID_SP_ID",
                    name="Identify",
                    type="Spell",
                    supports=["Wizard", "Bard"],
                    setters={"level": "1", "school": "Divination", "isRitual": "true", "duration": "Instantaneous"},
                ),
                Element(
                    id="ID_SP_BLESS",
                    name="Bless",
                    type="Spell",
                    supports=["Cleric", "Paladin"],
                    setters={
                        "level": "1",
                        "school": "Enchantment",
                        "isConcentration": "true",
                        "duration": "Concentration, up to 1 minute",
                    },
                ),
                Element(
                    id="ID_SP_DET",
                    name="Detect Magic",
                    type="Spell",
                    supports=["Wizard", "Cleric", "Druid", "Bard"],
                    setters={
                        "level": "1",
                        "school": "Divination",
                        "isRitual": "true",
                        "isConcentration": "true",
                        "duration": "Concentration, up to 10 minutes",
                    },
                ),
                Element(
                    id="ID_WPN_GREATSWORD",
                    name="Greatsword",
                    type="Weapon",
                    supports=["Heavy", "Two-Handed", "Martial"],
                    setters={"damage": "2d6", "damage_type": "slashing", "weight": "6 lb."},
                ),
                Element(
                    id="ID_ARM_CHAIN",
                    name="Chain Mail",
                    type="Armor",
                    setters={"armor": "Heavy", "armorClass": "16"},
                ),
            ],
        )
        return repo

    def test_01_spells_icons_school_class_filter_and_zero_cell_widgets(self) -> None:
        from PySide6.QtWidgets import QApplication
        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        repo = self._build_rich_repo()
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

            # Catalog has 4 columns and zero QWidgets allocated inside cells
            self.assertEqual(win.tbl_spell_catalog.columnCount(), 4)
            self.assertGreaterEqual(win.tbl_spell_catalog.rowCount(), 4)
            for r in range(win.tbl_spell_catalog.rowCount()):
                for c in range(4):
                    self.assertIsNone(win.tbl_spell_catalog.cellWidget(r, c))

            for r in range(win.tbl_equip_catalog.rowCount()):
                for c in range(5):
                    self.assertIsNone(win.tbl_equip_catalog.cellWidget(r, c))

            # Inspect icons in spell catalog rows
            rows_by_name = {
                win.tbl_spell_catalog.item(r, 0).text(): r
                for r in range(win.tbl_spell_catalog.rowCount())
            }
            self.assertEqual(win.tbl_spell_catalog.item(rows_by_name["Fireball"], 2).text(), "Evocation")
            self.assertFalse(win.tbl_spell_catalog.item(rows_by_name["Fireball"], 1).icon().isNull())
            self.assertFalse(win.tbl_spell_catalog.item(rows_by_name["Fireball"], 2).icon().isNull())
            self.assertTrue(win.tbl_spell_catalog.item(rows_by_name["Fireball"], 3).icon().isNull())

            self.assertFalse(win.tbl_spell_catalog.item(rows_by_name["Identify"], 3).icon().isNull())
            self.assertFalse(win.tbl_spell_catalog.item(rows_by_name["Bless"], 3).icon().isNull())
            self.assertFalse(win.tbl_spell_catalog.item(rows_by_name["Detect Magic"], 3).icon().isNull())

            # Class filter
            idx_cleric = win.cmb_spell_class.findData("cleric")
            self.assertGreaterEqual(idx_cleric, 0)
            win.cmb_spell_class.setCurrentIndex(idx_cleric)
            cleric_names = {
                win.tbl_spell_catalog.item(r, 0).text()
                for r in range(win.tbl_spell_catalog.rowCount())
            }
            self.assertEqual(cleric_names, {"Bless", "Detect Magic"})

            idx_druid = win.cmb_spell_class.findData("druid")
            win.cmb_spell_class.setCurrentIndex(idx_druid)
            self.assertEqual(
                {win.tbl_spell_catalog.item(r, 0).text() for r in range(win.tbl_spell_catalog.rowCount())},
                {"Detect Magic"},
            )

            # Reset class filter & test sorting by School (col 2) & R/C tags (col 3)
            win.cmb_spell_class.setCurrentIndex(0)
            win._on_spell_header_clicked(2)
            schools_asc = [
                win.tbl_spell_catalog.item(r, 2).text()
                for r in range(win.tbl_spell_catalog.rowCount())
            ]
            self.assertEqual(schools_asc, sorted(schools_asc))
            win._on_spell_header_clicked(3)

            # Known spells table has 6 columns with School & R/C icons + Prepared checkbox in col 5
            win.state.classes = [ClassLevel(class_id="ID_CLASS_WIZ", level=5)]
            win.state.sync_from_classes()
            win.state.known_spells = ["ID_SP_ID", "ID_SP_FB", "ID_SP_DET"]
            win._recalculate_and_refresh()
            app.processEvents()
            self.assertEqual(win.tbl_spells.columnCount(), 6)
            self.assertEqual(win.tbl_spells.rowCount(), 3)
            self.assertFalse(win.tbl_spells.item(0, 2).icon().isNull())
            self.assertIsNotNone(win.tbl_spells.cellWidget(0, 5))

            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()

    def test_02_55e_rules_masteries_orders_epic_boons_exhaustion_and_dnd55e(self) -> None:
        from PySide6.QtWidgets import QApplication
        from aurora_borealis.ui.dialogs import RuleOverridesDialog

        app = QApplication.instance() or QApplication([])
        repo = self._build_rich_repo()
        engine = RulesEngine(repo)

        # Extensions
        self.assertEqual(default_character_extension("5.5e"), ".dnd55e")
        self.assertEqual(default_character_extension("5e"), ".dnd5e")

        # Weapon masteries & heavy weapon check
        self.assertEqual(get_weapon_mastery("Longsword"), "Sap")
        self.assertEqual(get_weapon_mastery("Greatsword"), "Graze")
        _add_elements(
            repo,
            [
                Element(id="ID_CLASS_BAR", name="Barbarian", type="Class", setters={"hd": "d12"}),
                Element(id="ID_CLASS_ROG", name="Rogue", type="Class", setters={"hd": "d8"}),
            ],
        )
        self.assertEqual(
            compute_weapon_mastery_limit(
                CharacterState(ruleset="5.5e", classes=[ClassLevel(class_id="ID_CLASS_FTR", level=1)]), repo
            ),
            3,
        )
        self.assertEqual(
            compute_weapon_mastery_limit(
                CharacterState(ruleset="5.5e", classes=[ClassLevel(class_id="ID_CLASS_BAR", level=1)]), repo
            ),
            2,
        )
        self.assertEqual(
            compute_weapon_mastery_limit(
                CharacterState(ruleset="5.5e", classes=[ClassLevel(class_id="ID_CLASS_ROG", level=1)]), repo
            ),
            2,
        )
        self.assertEqual(get_55e_prepared_spells("Wizard", 5), 9)

        gs = repo.get("ID_WPN_GREATSWORD")
        ok_low, warn_low = check_55e_heavy_weapon_requirement(gs, {"strength": 10, "dexterity": 10})
        self.assertFalse(ok_low)
        self.assertIn("13+", warn_low)
        ok_hi, _ = check_55e_heavy_weapon_requirement(gs, {"strength": 14, "dexterity": 10})
        self.assertTrue(ok_hi)

        # Standardized Lv 3 subclass + Divine Order + Lv 19 Epic Boon + Exhaustion
        st = CharacterState(
            name="Kaelen 2024",
            ruleset="5.5e",
            classes=[ClassLevel(class_id="ID_CLASS_CLE", level=2)],
            divine_order_55e="protector",
            exhaustion_level=2,
            heroic_inspiration=True,
            abilities={
                "strength": 14,
                "dexterity": 12,
                "constitution": 14,
                "intelligence": 10,
                "wisdom": 16,
                "charisma": 10,
            },
        )
        st.sync_from_classes()
        comp_lv2 = engine.evaluate(st)
        # Cleric Domain is Lv 1 in 5e, suppressed until Lv 3 in 5.5e
        self.assertFalse(any(s.rule.type == "Archetype" for s in comp_lv2.active_selections))
        self.assertTrue(any("heavy armor" in p.lower() for p in comp_lv2.proficiencies))
        self.assertTrue(any("martial" in p.lower() for p in comp_lv2.proficiencies))
        self.assertEqual(comp_lv2.exhaustion_d20_penalty, -4)
        # Base WIS save at Lv 2 with WIS +3 & PB +2 is +5; with Exhaustion 2 (-4) = +1
        self.assertEqual(comp_lv2.saving_throws["wisdom"].bonus, 1)

        # Manual override unlocks 5.5e Lv 3 subclass timing
        st.set_override("override_55e_subclass_level", True)
        comp_ov = engine.evaluate(st)
        self.assertTrue(any(s.rule.type == "Archetype" for s in comp_ov.active_selections))

        # Lv 19 Epic Boon selection
        st.classes[0].level = 19
        st.sync_from_classes()
        comp_19 = engine.evaluate(st)
        self.assertTrue(any(s.key.startswith("5.5e::EpicBoon") for s in comp_19.active_selections))

        # RuleOverridesDialog
        dlg = RuleOverridesDialog(st)
        self.assertTrue(dlg._checkboxes["override_55e_subclass_level"].isChecked())
        dlg._checkboxes["override_multiclass_prereqs"].setChecked(True)
        chosen_ov = dlg.selected_overrides()
        self.assertTrue(chosen_ov["override_multiclass_prereqs"])
        dlg.close()

        # .dnd55e Save / Load / Scan round-trip
        st.weapon_masteries = ["Longsword", "Longbow"]
        st.animal_forms = ["wolf", "brown_bear"]
        st.active_animal_form_id = "wolf"
        st.companions = [create_companion_from_template("familiar_owl", st, comp_19).to_dict()]
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / f"kaelen{default_character_extension(st.ruleset)}"
            save_dnd5e(st, repo, comp_19, out_path)
            self.assertEqual(out_path.suffix, ".dnd55e")
            summaries = scan_characters_folder(Path(tmp))
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].ruleset, "5.5e")

            loaded = load_dnd5e(out_path, repo)
            self.assertEqual(loaded.ruleset, "5.5e")
            self.assertEqual(loaded.divine_order_55e, "protector")
            self.assertEqual(loaded.exhaustion_level, 2)
            self.assertTrue(loaded.heroic_inspiration)
            self.assertEqual(loaded.weapon_masteries, ["Longsword", "Longbow"])
            self.assertTrue(loaded.has_override("override_55e_subclass_level"))
            self.assertEqual(loaded.animal_forms, ["wolf", "brown_bear"])
            self.assertEqual(loaded.active_animal_form_id, "wolf")
            self.assertEqual(len(loaded.companions), 1)
        app.processEvents()

    def test_03_animal_forms_eligibility_transformed_stats_and_overrides(self) -> None:
        from PySide6.QtWidgets import QApplication
        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        repo = self._build_rich_repo()
        engine = RulesEngine(repo)

        # 5e Druid Lv 2
        st5 = CharacterState(
            name="Sylvan",
            ruleset="5e",
            classes=[ClassLevel(class_id="ID_CLASS_DRU", level=2)],
        )
        st5.sync_from_classes()
        comp5 = engine.evaluate(st5)
        acc5 = compute_animal_form_access(st5, comp5, repo)
        self.assertTrue(acc5.has_access)
        self.assertEqual(acc5.max_cr, 0.25)
        self.assertFalse(acc5.allow_swim)
        self.assertFalse(acc5.allow_fly)
        self.assertTrue(is_form_eligible(ANIMAL_FORMS_BY_ID["wolf"], acc5)[0])
        self.assertFalse(is_form_eligible(ANIMAL_FORMS_BY_ID["owl"], acc5)[0])
        self.assertFalse(is_form_eligible(ANIMAL_FORMS_BY_ID["crocodile"], acc5)[0])

        # 5.5e Circle of the Moon Druid Lv 6 (WIS 18 => AC 17, Temp HP 18, CR 2)
        st55 = CharacterState(
            name="Luna",
            ruleset="5.5e",
            classes=[ClassLevel(class_id="ID_CLASS_DRU", level=6)],
            abilities={
                "strength": 8,
                "dexterity": 12,
                "constitution": 14,
                "intelligence": 12,
                "wisdom": 18,
                "charisma": 10,
            },
        )
        st55.sync_from_classes()
        comp55_pre = engine.evaluate(st55)
        arch_key = next(s.key for s in comp55_pre.active_selections if s.rule.type == "Archetype")
        st55.selections[arch_key] = ["ID_ARCH_MOON"]
        comp55 = engine.evaluate(st55)
        acc55 = compute_animal_form_access(st55, comp55, repo)
        self.assertTrue(acc55.is_moon_druid)
        self.assertEqual(acc55.max_cr, 2.0)
        self.assertEqual(acc55.temp_hp_55e, 18)
        self.assertEqual(acc55.moon_ac_55e, 17)
        self.assertTrue(is_form_eligible(ANIMAL_FORMS_BY_ID["brown_bear"], acc55)[0])
        transformed = compute_transformed_stats(ANIMAL_FORMS_BY_ID["brown_bear"], st55, comp55, acc55)
        self.assertEqual(transformed["ac"], 17)
        self.assertIn("18 Temp HP", transformed["hp_display"])
        self.assertEqual(transformed["abilities"]["wisdom"], 18)
        self.assertEqual(transformed["abilities"]["strength"], 19)
        html_out = render_animal_form_html(ANIMAL_FORMS_BY_ID["brown_bear"], transformed)
        self.assertIn("Brown Bear", html_out)

        # Non-Druid UI Override test
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
            win.state = CharacterState(
                name="Garrick",
                ruleset="5e",
                classes=[ClassLevel(class_id="ID_CLASS_FTR", level=3)],
            )
            win.state.sync_from_classes()
            win._recalculate_and_refresh()
            self.assertEqual(win.tbl_animal_forms.rowCount(), 0)

            win.chk_override_animal_forms.setChecked(True)
            app.processEvents()
            self.assertTrue(win.state.has_override("allow_all_animal_forms"))
            self.assertGreater(win.tbl_animal_forms.rowCount(), 10)
            win.tbl_animal_forms.selectRow(0)
            win._add_selected_animal_form()
            self.assertEqual(len(win.state.animal_forms), 1)
            win._toggle_active_animal_form()
            self.assertEqual(win.state.active_animal_form_id, win.state.animal_forms[0])
            win._remove_selected_animal_form()
            self.assertEqual(win.state.animal_forms, [])
            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()

    def test_04_companions_scaling_dndcomp_library_pdf_and_editor(self) -> None:
        from PySide6.QtWidgets import QApplication
        from aurora_borealis.ui.companion_view import CompanionEditorView
        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        repo = self._build_rich_repo()
        owner_state = CharacterState(name="Tink", ruleset="5.5e", level=7)
        owner_comp = RulesEngine(repo).evaluate(owner_state)

        comp = create_companion_from_template("steel_defender", owner_state, owner_comp)
        comp.name = "Sparky"
        self.assertEqual(comp.owner_name, "Tink")
        self.assertGreaterEqual(comp.max_hp, 30)
        self.assertIn("Sparky", render_companion_sheet_html(comp))

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            comp_file = p / "sparky.dndcomp"
            save_dndcomp(comp, comp_file)
            loaded = load_dndcomp(comp_file)
            self.assertEqual(loaded.name, "Sparky")
            self.assertEqual(loaded.owner_name, "Tink")
            self.assertEqual(loaded.max_hp, comp.max_hp)
            self.assertGreaterEqual(len(loaded.traits), 1)
            self.assertGreaterEqual(len(loaded.actions), 1)

            # Library scans .dndcomp and duplicates keeping .dndcomp suffix
            dup = duplicate_character(comp_file)
            self.assertEqual(dup.suffix, ".dndcomp")
            summaries = scan_characters_folder(p)
            self.assertEqual(len(summaries), 2)
            self.assertTrue(all(s.entry_kind == "companion" for s in summaries))

            # Companion PDF export
            pdf_path = p / "sparky.pdf"
            export_companion_pdf(comp, pdf_path)
            self.assertTrue(pdf_path.is_file())
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF-"))

            # Standalone CompanionEditorView
            editor = CompanionEditorView()
            editor.set_characters_dir(p)
            editor.load_companion(loaded, comp_file)
            editor.txt_name.setText("Sparky MK-II")
            self.assertEqual(editor.comp.name, "Sparky MK-II")
            editor.close()

            # MainWindow attach + open + filter companions in Library
            win = MainWindow(
                repo,
                p,
                custom_dir=p / "c",
                templates_dir=p / "t",
                config=AppConfig(characters_dir=str(p)),
                config_path=p / "cfg.json",
                auto_sync=False,
            )
            win.refresh_library()
            win.select_view.btn_comp.click()
            self.assertEqual(win.select_view._filter_mode, "comp")

            win._add_companion_from_template()
            self.assertEqual(len(win.state.companions), 1)
            win._open_selected_attached_companion()
            self.assertIs(win.screen_stack.currentWidget(), win.companion_view)
            win.companion_view.txt_name.setText("Fang")
            win._on_companion_back()
            self.assertIs(win.screen_stack.currentWidget(), win.builder_view)
            self.assertEqual(win.state.companions[0]["name"], "Fang")

            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()

    def test_05_performance_caches_and_fast_typing(self) -> None:
        from PySide6.QtWidgets import QApplication

        from aurora_borealis.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        repo = self._build_rich_repo()

        _compile_boolean_expr.cache_clear()
        expr1 = _compile_boolean_expr("Heavy, Two-Handed")
        expr2 = _compile_boolean_expr("Heavy, Two-Handed")
        self.assertIs(expr1, expr2)
        self.assertGreaterEqual(_compile_boolean_expr.cache_info().hits, 1)

        res1 = repo.find_matching("Spell", "Wizard")
        res2 = repo.find_matching("Spell", "Wizard")
        self.assertGreaterEqual(len(res1), 2)
        self.assertEqual([e.id for e in res1], [e.id for e in res2])

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
            with mock.patch.object(win.engine, "evaluate", wraps=win.engine.evaluate) as spy_eval:
                win.txt_overview_name.setText("Fast Typer")
                app.processEvents()
                self.assertEqual(spy_eval.call_count, 0)
                self.assertEqual(win.state.name, "Fast Typer")
                self.assertEqual(win.lbl_top_name.text(), "Fast Typer")
                self.assertEqual(win.txt_name.text(), "Fast Typer")

            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()

    def test_06_custom_animal_forms_equipment_icon_sizes_and_installers(self) -> None:
        import os
        import subprocess
        from PySide6.QtWidgets import QApplication
        from aurora_borealis.animal_forms import animal_form_to_dict, find_animal_form
        from aurora_borealis.ui.dialogs import CustomAnimalFormDialog
        from aurora_borealis.ui.main_window import MainWindow, _equip_rarity_icon, _equip_type_icon

        app = QApplication.instance() or QApplication([])
        repo = self._build_rich_repo()

        # 1. Equipment & Spell icon sizes are restored to full size (28x28 and 48x26)
        for icon in (
            _equip_type_icon("Weapon"),
            _equip_type_icon("Armor"),
            _equip_type_icon("Magic Item"),
            _equip_rarity_icon("R", "#60a5fa", "#1e3a5f"),
        ):
            self.assertFalse(icon.isNull())
            pm = icon.pixmap(28, 28)
            self.assertEqual(pm.width(), 28)
            self.assertEqual(pm.height(), 28)

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
            self.assertGreaterEqual(win.tbl_equip_catalog.iconSize().width(), 28)
            self.assertGreaterEqual(win.tbl_equip_catalog.iconSize().height(), 28)
            self.assertGreaterEqual(win.tbl_spell_catalog.iconSize().width(), 48)

            # 2. Custom Animal Form dialog + state + activation + .dnd55e persistence
            dlg = CustomAnimalFormDialog(parent=win)
            dlg.txt_name.setText("Frost Dire Wolf")
            dlg.cmb_cr.setCurrentText("1/2")
            dlg.spn_ac.setValue(15)
            dlg.spn_hp.setValue(32)
            dlg.spn_walk.setValue(50)
            dlg.txt_traits.setPlainText("Cold Aura\nPack Tactics")
            dlg.txt_actions.setPlainText("Frost Bite (+6, 2d6+4 cold)")
            custom_form = dlg.build_animal_form()
            dlg.close()

            self.assertTrue(custom_form.id.startswith("custom_frost_dire_wolf"))
            self.assertEqual(custom_form.cr, 0.5)
            win.state.ruleset = "5.5e"
            win.state.custom_animal_forms.append(animal_form_to_dict(custom_form))
            win.state.animal_forms.append(custom_form.id)
            win._sync_animal_forms_tab()

            self.assertIsNotNone(find_animal_form(custom_form.id, win.state))
            win._select_animal_form_row_by_id(custom_form.id)
            self.assertEqual(win._selected_animal_form_id(), custom_form.id)
            win._toggle_active_animal_form()
            self.assertEqual(win.state.active_animal_form_id, custom_form.id)

            save_path = p / "frost_druid.dnd55e"
            save_dnd5e(win.state, repo, win.computed, save_path)
            reloaded = load_dnd5e(save_path, repo)
            self.assertEqual(len(reloaded.custom_animal_forms), 1)
            reloaded_form = find_animal_form(custom_form.id, reloaded)
            self.assertIsNotNone(reloaded_form)
            self.assertEqual(reloaded_form.name, "Frost Dire Wolf")
            self.assertEqual(reloaded_form.ac, 15)
            self.assertEqual(reloaded.active_animal_form_id, custom_form.id)

            # Removing custom form cleans both animal_forms and custom_animal_forms
            win._remove_selected_animal_form()
            self.assertEqual(win.state.custom_animal_forms, [])
            self.assertNotIn(custom_form.id, win.state.animal_forms)
            self.assertEqual(win.state.active_animal_form_id, "")

            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()

        # 3. Linux & Windows installer files & syntax checks + isolated desktop installer run
        root_dir = Path(__file__).resolve().parent.parent
        for rel in (
            "setup-wizard-linux.sh",
            "installer/install-linux.sh",
            "installer/uninstall-linux.sh",
            "installer/linux_wizard.py",
            "aurora-borealis",
            "setup-wizard-windows.bat",
            "installer/windows_wizard.ps1",
            "installer/install-windows.ps1",
            "installer/uninstall-windows.ps1",
            "aurora-borealis.bat",
        ):
            self.assertTrue((root_dir / rel).is_file(), f"Missing installer/launcher: {rel}")

        for removed in (
            "aurora-borealis.ps1",
            "install-windows.bat",
            "install-desktop.sh",
            "requirements.txt",
            "packaging/windows/aurora-borealis.iss",
        ):
            self.assertFalse((root_dir / removed).exists(), f"Redundant file should be removed: {removed}")

        with tempfile.TemporaryDirectory() as fake_home:
            env = dict(os.environ)
            env["HOME"] = fake_home
            env["XDG_DATA_HOME"] = str(Path(fake_home) / ".local" / "share")
            proc = subprocess.run(
                ["bash", str(root_dir / "installer" / "install-linux.sh"), "--desktop-only"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            desk = Path(fake_home) / ".local" / "share" / "applications" / "aurora-borealis.desktop"
            mime = Path(fake_home) / ".local" / "share" / "mime" / "packages" / "aurora-borealis.xml"
            icon_svg = Path(fake_home) / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps" / "aurora-borealis.svg"
            self.assertTrue(desk.is_file())
            self.assertTrue(mime.is_file())
            self.assertTrue(icon_svg.is_file())
            desk_txt = desk.read_text(encoding="utf-8")
            self.assertIn("application/x-dnd55e", desk_txt)
            self.assertIn("application/x-dndcomp", desk_txt)
            self.assertIn("aurora-borealis\" %f", desk_txt)
            self.assertNotIn("--open %f", desk_txt)
            self.assertIn("Path=", desk_txt)


if __name__ == "__main__":
    unittest.main()
