"""Tests for Multiclassing, Rolled/Manual HP, Spell Logic, Level-Up Wizard, and Windows compatibility."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication

from aurora_borealis.config import AppConfig
from aurora_borealis.engine import (
    RulesEngine,
    check_multiclass_prerequisites,
    class_display_summary,
    is_spell_eligible_for_caster,
)
from aurora_borealis.fivetools_importer import _convert_spells
from aurora_borealis.github_importer import _safe_rel_path
from aurora_borealis.level_up import (
    apply_level_up_step,
    compute_character_diff,
    is_asi_level,
    render_diff_html,
)
from aurora_borealis.loader import ContentRepository
from aurora_borealis.models import CharacterState, ClassLevel
from aurora_borealis.paths import get_app_data_dir, get_config_path, get_os_documents_dir
from aurora_borealis.pdf_export import export_character_pdf
from aurora_borealis.persistence import load_dnd5e, save_dnd5e
from aurora_borealis.platform_utils import find_executable, is_windows, subprocess_no_window_kwargs
from aurora_borealis.ui.level_up_wizard import LevelUpWizardDialog
from aurora_borealis.ui.main_window import MainWindow

_SYNTHETIC_XML = """<?xml version="1.0" encoding="utf-8"?>
<elements>
  <element name="Human" type="Race" source="Test" id="ID_TEST_RACE_HUMAN">
    <rules><stat name="innate speed" value="30" bonus="base"/></rules>
  </element>
  <element name="Soldier" type="Background" source="Test" id="ID_TEST_BG_SOLDIER"/>
  <element name="Neutral" type="Alignment" source="Test" id="ID_TEST_ALIGN_N"/>

  <element name="Strength Saving Throw" type="Proficiency" source="Test" id="ID_PROFICIENCY_SAVINGTHROW_STRENGTH"/>
  <element name="Constitution Saving Throw" type="Proficiency" source="Test" id="ID_PROFICIENCY_SAVINGTHROW_CONSTITUTION"/>
  <element name="Intelligence Saving Throw" type="Proficiency" source="Test" id="ID_PROFICIENCY_SAVINGTHROW_INTELLIGENCE"/>
  <element name="Wisdom Saving Throw" type="Proficiency" source="Test" id="ID_PROFICIENCY_SAVINGTHROW_WISDOM"/>
  <element name="Charisma Saving Throw" type="Proficiency" source="Test" id="ID_PROFICIENCY_SAVINGTHROW_CHARISMA"/>
  <element name="Light Armor" type="Proficiency" source="Test" id="ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR"/>
  <element name="Medium Armor" type="Proficiency" source="Test" id="ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR"/>
  <element name="Shields" type="Proficiency" source="Test" id="ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS"/>
  <element name="Simple Weapons" type="Proficiency" source="Test" id="ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS"/>
  <element name="Martial Weapons" type="Proficiency" source="Test" id="ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS"/>

  <element name="Action Surge" type="Class Feature" source="Test" id="ID_TEST_CF_ACTION_SURGE"/>
  <element name="Extra Attack" type="Class Feature" source="Test" id="ID_TEST_CF_EXTRA_ATTACK"/>
  <element name="Fighter Archetype" type="Class Feature" source="Test" id="ID_TEST_CF_FIGHTER_ARCH">
    <rules>
      <select type="Archetype" name="Martial Archetype" supports="Fighter Archetype" level="3"/>
    </rules>
  </element>
  <element name="Eldritch Knight" type="Archetype" source="Test" id="ID_TEST_ARCH_EK">
    <supports>Fighter Archetype</supports>
    <spellcasting name="Eldritch Knight" ability="Intelligence" prepare="false">
      <list>Wizard</list>
    </spellcasting>
    <rules>
      <stat name="eldritch knight:spellcasting:slots:1" value="2" level="3"/>
      <stat name="eldritch knight:spellcasting:slots:1" value="1" level="4"/>
    </rules>
  </element>

  <element name="Fighter" type="Class" source="Test" id="ID_TEST_CLASS_FIGHTER">
    <setters><set name="hd">d10</set></setters>
    <rules>
      <grant type="Proficiency" id="ID_PROFICIENCY_SAVINGTHROW_STRENGTH" level="1"/>
      <grant type="Proficiency" id="ID_PROFICIENCY_SAVINGTHROW_CONSTITUTION" level="1"/>
      <grant type="Class Feature" id="ID_TEST_CF_ACTION_SURGE" level="2"/>
      <grant type="Class Feature" id="ID_TEST_CF_FIGHTER_ARCH" level="3"/>
      <grant type="Class Feature" id="ID_TEST_CF_EXTRA_ATTACK" level="5"/>
      <stat name="fighter:power" value="level:fighter" level="1"/>
    </rules>
    <multiclass id="ID_TEST_MC_FIGHTER">
      <prerequisite>Strength 13 or Dexterity 13</prerequisite>
      <requirements>[str:13]||[dex:13]</requirements>
      <rules>
        <grant type="Proficiency" id="ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR"/>
        <grant type="Proficiency" id="ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS"/>
      </rules>
    </multiclass>
  </element>

  <element name="Arcane Recovery" type="Class Feature" source="Test" id="ID_TEST_CF_ARCANE_RECOVERY"/>
  <element name="Arcane Tradition Feature" type="Class Feature" source="Test" id="ID_TEST_CF_WIZ_TRAD"/>
  <element name="Spell Mastery" type="Class Feature" source="Test" id="ID_TEST_CF_SPELL_MASTERY"/>
  <element name="Wizard" type="Class" source="Test" id="ID_TEST_CLASS_WIZARD">
    <setters><set name="hd">d6</set></setters>
    <spellcasting name="Wizard" ability="Intelligence" prepare="true">
      <list>Wizard</list>
    </spellcasting>
    <rules>
      <grant type="Proficiency" id="ID_PROFICIENCY_SAVINGTHROW_INTELLIGENCE" level="1"/>
      <grant type="Proficiency" id="ID_PROFICIENCY_SAVINGTHROW_WISDOM" level="1"/>
      <grant type="Class Feature" id="ID_TEST_CF_ARCANE_RECOVERY" level="1"/>
      <grant type="Class Feature" id="ID_TEST_CF_WIZ_TRAD" level="2"/>
      <grant type="Class Feature" id="ID_TEST_CF_SPELL_MASTERY" level="3"/>
      <select type="Spell" name="Wizard Cantrips" supports="$(spellcasting:list), 0" number="3" level="1"/>
      <select type="Spell" name="Wizard Spellbook" supports="$(spellcasting:list), $(spellcasting:slots)" number="6" level="1"/>
    </rules>
    <multiclass id="ID_TEST_MC_WIZARD">
      <prerequisite>Intelligence 13</prerequisite>
      <requirements>[int:13]</requirements>
      <rules/>
    </multiclass>
  </element>

  <element name="Bless" type="Spell" source="Test" id="ID_TEST_SP_BLESS">
    <supports>Cleric, Paladin</supports>
    <setters><set name="level">1</set><set name="school">Enchantment</set></setters>
  </element>
  <element name="Cure Wounds" type="Spell" source="Test" id="ID_TEST_SP_CURE_WOUNDS">
    <supports>Cleric, Bard, Druid</supports>
    <setters><set name="level">1</set><set name="school">Evocation</set></setters>
  </element>
  <element name="Magic Missile" type="Spell" source="Test" id="ID_TEST_SP_MAGIC_MISSILE">
    <supports>Wizard, Sorcerer</supports>
    <setters><set name="level">1</set><set name="school">Evocation</set></setters>
  </element>
  <element name="Misty Step" type="Spell" source="Test" id="ID_TEST_SP_MISTY_STEP">
    <supports>Wizard, Sorcerer, Warlock</supports>
    <setters><set name="level">2</set><set name="school">Conjuration</set></setters>
  </element>
  <element name="Fireball" type="Spell" source="Test" id="ID_TEST_SP_FIREBALL">
    <supports>Wizard, Sorcerer</supports>
    <setters><set name="level">3</set><set name="school">Evocation</set></setters>
  </element>
  <element name="Fire Bolt" type="Spell" source="Test" id="ID_TEST_SP_FIRE_BOLT">
    <supports>Wizard, Sorcerer</supports>
    <setters><set name="level">0</set><set name="school">Evocation</set></setters>
  </element>
  <element name="Sacred Flame" type="Spell" source="Test" id="ID_TEST_SP_SACRED_FLAME">
    <supports>Cleric</supports>
    <setters><set name="level">0</set><set name="school">Evocation</set></setters>
  </element>
  <element name="Eldritch Blast" type="Spell" source="Test" id="ID_TEST_SP_ELDRITCH_BLAST">
    <supports>Warlock</supports>
    <setters><set name="level">0</set><set name="school">Evocation</set></setters>
  </element>

  <element name="Life Domain" type="Archetype" source="Test" id="ID_TEST_ARCH_LIFE">
    <supports>Divine Domain</supports>
    <rules>
      <grant type="Spell" id="ID_TEST_SP_BLESS" level="1"/>
      <grant type="Spell" id="ID_TEST_SP_CURE_WOUNDS" level="1"/>
    </rules>
  </element>
  <element name="Cleric" type="Class" source="Test" id="ID_TEST_CLASS_CLERIC">
    <setters><set name="hd">d8</set></setters>
    <spellcasting name="Cleric" ability="Wisdom" prepare="true">
      <list>Cleric</list>
    </spellcasting>
    <rules>
      <grant type="Proficiency" id="ID_PROFICIENCY_SAVINGTHROW_WISDOM" level="1"/>
      <grant type="Proficiency" id="ID_PROFICIENCY_SAVINGTHROW_CHARISMA" level="1"/>
      <grant type="Archetype" id="ID_TEST_ARCH_LIFE" level="1"/>
    </rules>
  </element>

  <element name="Genie Patron" type="Archetype" source="Test" id="ID_TEST_ARCH_GENIE">
    <supports>Otherworldly Patron</supports>
    <spellcasting name="Warlock" extend="true">
      <extend>Cleric</extend>
    </spellcasting>
  </element>
  <element name="Warlock" type="Class" source="Test" id="ID_TEST_CLASS_WARLOCK">
    <setters><set name="hd">d8</set></setters>
    <spellcasting name="Warlock" ability="Charisma" prepare="false">
      <list>Warlock</list>
    </spellcasting>
    <rules>
      <grant type="Proficiency" id="ID_PROFICIENCY_SAVINGTHROW_WISDOM" level="1"/>
      <grant type="Proficiency" id="ID_PROFICIENCY_SAVINGTHROW_CHARISMA" level="1"/>
      <grant type="Archetype" id="ID_TEST_ARCH_GENIE" level="1"/>
    </rules>
  </element>

  <element name="Tough" type="Feat" source="Test" id="ID_TEST_FEAT_TOUGH">
    <description><p>Hit point maximum increases by 2 per level.</p></description>
    <rules><stat name="hp" value="level" level="1"/><stat name="hp" value="level" level="1"/></rules>
  </element>
</elements>
"""


class MulticlassHpSpellsLevelUpWindowsTests(unittest.TestCase):
    repo: ContentRepository
    engine: RulesEngine

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])
        cls.tmpdir = tempfile.TemporaryDirectory()
        xml_path = Path(cls.tmpdir.name) / "synthetic.xml"
        xml_path.write_text(_SYNTHETIC_XML, encoding="utf-8")
        cls.repo = ContentRepository()
        cls.repo.load_directory(Path(cls.tmpdir.name))
        cls.engine = RulesEngine(cls.repo)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmpdir.cleanup()

    def test_01_multiclass_scoping_saves_prerequisites_and_hit_dice(self) -> None:
        state = CharacterState(
            name="Garrick",
            race_id="ID_TEST_RACE_HUMAN",
            background_id="ID_TEST_BG_SOLDIER",
            classes=[
                ClassLevel("ID_TEST_CLASS_FIGHTER", 3),
                ClassLevel("ID_TEST_CLASS_WIZARD", 2),
            ],
            abilities={
                "strength": 16,
                "dexterity": 12,
                "constitution": 14,
                "intelligence": 14,
                "wisdom": 10,
                "charisma": 8,
            },
        )
        comp = self.engine.evaluate(state)
        self.assertEqual(state.level, 5)
        self.assertEqual(class_display_summary(state, self.repo), "Fighter 3 / Wizard 2")
        self.assertEqual(comp.hit_dice_summary, "3d10 + 2d6")
        self.assertEqual(comp.proficiency_bonus, 3)

        granted_ids = {e.id for e in comp.granted_elements}
        # Fighter 2 & Wizard 2 features granted; Fighter 5 & Wizard 3 features NOT granted
        self.assertIn("ID_TEST_CF_ACTION_SURGE", granted_ids)
        self.assertIn("ID_TEST_CF_WIZ_TRAD", granted_ids)
        self.assertNotIn("ID_TEST_CF_EXTRA_ATTACK", granted_ids)
        self.assertNotIn("ID_TEST_CF_SPELL_MASTERY", granted_ids)

        # Only primary class (Fighter) saving throws granted
        self.assertTrue(comp.saving_throws["strength"].proficient)
        self.assertTrue(comp.saving_throws["constitution"].proficient)
        self.assertFalse(comp.saving_throws["intelligence"].proficient)
        self.assertFalse(comp.saving_throws["wisdom"].proficient)

        # level:fighter stat resolves to 3 (not 5)
        self.assertEqual(comp.stats.get("fighter:power"), 3.0)

        # Prerequisites check
        cleric_el = self.repo.get("ID_TEST_CLASS_CLERIC")
        wizard_el = self.repo.get("ID_TEST_CLASS_WIZARD")
        assert cleric_el is not None and wizard_el is not None
        ok_wiz, _ = check_multiclass_prerequisites(state, comp, wizard_el, self.repo)
        ok_clr, msg_clr = check_multiclass_prerequisites(state, comp, cleric_el, self.repo)
        self.assertTrue(ok_wiz)
        self.assertFalse(ok_clr)
        self.assertIn("WIS 13+", msg_clr)

    def test_02_hp_average_and_rolled_single_and_multiclass(self) -> None:
        # Fighter 3 (d10) / Wizard 2 (d6), CON 14 (+2)
        state = CharacterState(
            name="HP Tester",
            classes=[
                ClassLevel("ID_TEST_CLASS_FIGHTER", 3),
                ClassLevel("ID_TEST_CLASS_WIZARD", 2),
            ],
            level_order=[
                "ID_TEST_CLASS_FIGHTER",
                "ID_TEST_CLASS_FIGHTER",
                "ID_TEST_CLASS_FIGHTER",
                "ID_TEST_CLASS_WIZARD",
                "ID_TEST_CLASS_WIZARD",
            ],
            abilities={"strength": 16, "dexterity": 12, "constitution": 14, "intelligence": 14, "wisdom": 10, "charisma": 8},
            hp_mode="average",
        )
        comp_avg = self.engine.evaluate(state)
        # Lv1: 10, Lv2: 6, Lv3: 6, Lv4: 4, Lv5: 4 -> 30 + 5*2 = 40
        self.assertEqual(comp_avg.max_hp, 40)

        state.hp_mode = "rolled"
        state.hp_rolls = {1: 10, 2: 9, 3: 8, 4: 6, 5: 5}
        comp_roll = self.engine.evaluate(state)
        # 10 + 9 + 8 + 6 + 5 + 5*2 = 48
        self.assertEqual(comp_roll.max_hp, 48)

    def test_03_spell_logic_class_subclass_and_multiclass(self) -> None:
        # 1. Multiclass Wizard 3 / Cleric 2 -> 5th-level combined slots (4/3/2), individual max levels 2 & 1
        mc_state = CharacterState(
            name="Theurge",
            classes=[
                ClassLevel("ID_TEST_CLASS_WIZARD", 3),
                ClassLevel("ID_TEST_CLASS_CLERIC", 2),
            ],
            abilities={"strength": 8, "dexterity": 12, "constitution": 12, "intelligence": 16, "wisdom": 14, "charisma": 10},
        )
        comp_mc = self.engine.evaluate(mc_state)
        self.assertIsNotNone(comp_mc.spellcasting)
        assert comp_mc.spellcasting is not None
        sc = comp_mc.spellcasting
        self.assertTrue(sc.is_multiclass_caster)
        self.assertEqual(sc.multiclass_caster_level, 5)
        self.assertEqual(sc.slots, {1: 4, 2: 3, 3: 2})
        self.assertEqual(len(sc.casters), 2)

        wiz_c = next(c for c in sc.casters if c.source_class_id == "ID_TEST_CLASS_WIZARD")
        clr_c = next(c for c in sc.casters if c.source_class_id == "ID_TEST_CLASS_CLERIC")
        self.assertEqual(wiz_c.max_spell_level, 2)
        self.assertEqual(clr_c.max_spell_level, 1)
        self.assertEqual(wiz_c.save_dc, 8 + 3 + 3)  # INT 16 (+3) + Prof 3
        self.assertEqual(clr_c.save_dc, 8 + 3 + 2)  # WIS 14 (+2) + Prof 3

        # Life Domain Bless & Cure Wounds are always prepared
        self.assertIn("ID_TEST_SP_BLESS", sc.always_prepared_spell_ids)
        self.assertIn("ID_TEST_SP_CURE_WOUNDS", sc.always_prepared_spell_ids)

        # Class spell list eligibility
        fireball = self.repo.get("ID_TEST_SP_FIREBALL")
        cure = self.repo.get("ID_TEST_SP_CURE_WOUNDS")
        assert fireball is not None and cure is not None
        self.assertTrue(is_spell_eligible_for_caster(fireball, wiz_c))
        self.assertFalse(is_spell_eligible_for_caster(fireball, clr_c))
        self.assertTrue(is_spell_eligible_for_caster(cure, clr_c))

        # 2. Warlock Pact Magic separate from Wizard slots + extended subclass spell list
        wiz_lock = CharacterState(
            name="Pact Scholar",
            classes=[
                ClassLevel("ID_TEST_CLASS_WIZARD", 2),
                ClassLevel("ID_TEST_CLASS_WARLOCK", 2),
            ],
            abilities={"strength": 8, "dexterity": 12, "constitution": 12, "intelligence": 16, "wisdom": 10, "charisma": 16},
        )
        comp_wl = self.engine.evaluate(wiz_lock)
        assert comp_wl.spellcasting is not None
        self.assertEqual(comp_wl.spellcasting.slots, {1: 3})
        self.assertEqual(comp_wl.spellcasting.pact_slots, {1: 2})
        lock_c = next(c for c in comp_wl.spellcasting.casters if c.source_class_id == "ID_TEST_CLASS_WARLOCK")
        self.assertIn("Cleric", lock_c.extended_spell_lists)
        self.assertTrue(is_spell_eligible_for_caster(cure, lock_c))

        # 3. Subclass 1/3-caster (Eldritch Knight at Fighter Lv 3 + multiclass EK 6 / Wizard 3 -> effective caster Lv 5)
        ek_state = CharacterState(
            name="Eldritch Knight",
            classes=[ClassLevel("ID_TEST_CLASS_FIGHTER", 3)],
            selections={
                "ID_TEST_CF_FIGHTER_ARCH::Archetype::Martial Archetype::3::0": ["ID_TEST_ARCH_EK"],
            },
            abilities={"strength": 16, "dexterity": 12, "constitution": 14, "intelligence": 14, "wisdom": 10, "charisma": 8},
        )
        comp_ek = self.engine.evaluate(ek_state)
        self.assertIsNotNone(comp_ek.spellcasting)
        assert comp_ek.spellcasting is not None
        self.assertEqual(comp_ek.spellcasting.casters[0].caster_type, "third")
        self.assertEqual(comp_ek.spellcasting.slots, {1: 2})

        ek_wiz = CharacterState(
            name="Battlemage",
            classes=[
                ClassLevel("ID_TEST_CLASS_FIGHTER", 6),
                ClassLevel("ID_TEST_CLASS_WIZARD", 3),
            ],
            selections={
                "ID_TEST_CF_FIGHTER_ARCH::Archetype::Martial Archetype::3::0": ["ID_TEST_ARCH_EK"],
            },
            abilities={"strength": 16, "dexterity": 12, "constitution": 14, "intelligence": 16, "wisdom": 10, "charisma": 8},
        )
        comp_ek_wiz = self.engine.evaluate(ek_wiz)
        assert comp_ek_wiz.spellcasting is not None
        # Fighter EK 6 -> 6 // 3 = 2; Wizard 3 -> 3; Total effective caster level = 5 -> {1: 4, 2: 3, 3: 2}
        self.assertEqual(comp_ek_wiz.spellcasting.multiclass_caster_level, 5)
        self.assertEqual(comp_ek_wiz.spellcasting.slots, {1: 4, 2: 3, 3: 2})

        # 4. 5e.tools spell conversion preserves class tags
        converted = _convert_spells({
            "spell": [{
                "name": "Star Bolt",
                "source": "PHB",
                "level": 1,
                "school": "V",
                "classes": {"fromClassList": [{"name": "Wizard"}, {"name": "Sorcerer"}]},
                "entries": ["Zaps a target."],
            }]
        })
        self.assertEqual(len(converted), 1)
        self.assertEqual(converted[0].findtext("supports"), "Wizard, Sorcerer")

    def test_04_level_up_diff_wizard_gui_and_persistence(self) -> None:
        base_state = CharacterState(
            name="Lyra",
            race_id="ID_TEST_RACE_HUMAN",
            background_id="ID_TEST_BG_SOLDIER",
            alignment_id="ID_TEST_ALIGN_N",
            classes=[ClassLevel("ID_TEST_CLASS_FIGHTER", 3)],
            abilities={"strength": 16, "dexterity": 12, "constitution": 14, "intelligence": 14, "wisdom": 10, "charisma": 8},
        )
        fighter_el = self.repo.get("ID_TEST_CLASS_FIGHTER")
        self.assertTrue(is_asi_level(fighter_el, 4))
        self.assertTrue(is_asi_level(fighter_el, 6))
        self.assertFalse(is_asi_level(fighter_el, 3))

        # Open Level-Up Wizard GUI offscreen, choose Fighter -> Lv 4, rolled HP=8, ASI STR +2, review diff, apply
        dlg = LevelUpWizardDialog(base_state, self.repo, self.engine)
        dlg.rad_advance.setChecked(True)
        dlg.rad_hp_roll.setChecked(True)
        dlg.spn_hp_roll.setValue(8)
        dlg.go_next()  # Page 1: Features
        dlg.go_next()  # Page 2: ASI / Feat
        dlg.rad_asi.setChecked(True)
        dlg.rad_asi_2.setChecked(True)
        dlg.cmb_asi_a.setCurrentIndex(dlg.cmb_asi_a.findData("strength"))
        dlg.go_next()  # Page 3: Spells
        dlg.go_next()  # Page 4: Review Diff
        diff_html = dlg.diff_browser.toHtml()
        self.assertIn("Level 3", diff_html)
        self.assertIn("Level 4", diff_html)
        self.assertIn("STR", diff_html)
        dlg._on_apply()
        self.assertEqual(dlg.result(), dlg.DialogCode.Accepted)
        upgraded = dlg.result_state()
        self.assertEqual(upgraded.level, 4)
        self.assertEqual(upgraded.hp_mode, "rolled")
        self.assertEqual(upgraded.hp_rolls[4], 8)
        self.assertEqual(upgraded.level_up_asi.get("ID_TEST_CLASS_FIGHTER::4"), {"strength": 2})

        comp_before = self.engine.evaluate(base_state)
        comp_after = self.engine.evaluate(upgraded)
        self.assertEqual(comp_after.ability_totals["strength"], 18)
        # Lv1:10 + Lv2:6 + Lv3:6 + Lv4(roll):8 + 4*2(CON) = 38
        self.assertEqual(comp_after.max_hp, 38)
        diff_obj = compute_character_diff(base_state, comp_before, upgraded, comp_after, self.repo, "ID_TEST_CLASS_FIGHTER")
        self.assertEqual(diff_obj.hp_delta, 10)
        self.assertIn("Max HP", render_diff_html(diff_obj))

        # Multiclass into Wizard via apply_level_up_step + Feat + Persistence round-trip
        mc_up = apply_level_up_step(upgraded, "ID_TEST_CLASS_WIZARD", hp_mode="rolled", hp_roll=5)
        mc_up.known_spells.append("ID_TEST_SP_MAGIC_MISSILE")
        mc_up.spell_sources["ID_TEST_SP_MAGIC_MISSILE"] = "ID_TEST_CLASS_WIZARD"
        mc_up.level_up_feats["ID_TEST_CLASS_WIZARD::1"] = "ID_TEST_FEAT_TOUGH"
        comp_mc = self.engine.evaluate(mc_up)

        with tempfile.TemporaryDirectory() as tmp:
            dnd_path = Path(tmp) / "lyra_mc.dnd5e"
            save_dnd5e(mc_up, self.repo, comp_mc, dnd_path)
            loaded = load_dnd5e(dnd_path, self.repo)

        self.assertEqual([(c.class_id, c.level) for c in loaded.classes], [
            ("ID_TEST_CLASS_FIGHTER", 4),
            ("ID_TEST_CLASS_WIZARD", 1),
        ])
        self.assertEqual(loaded.hp_mode, "rolled")
        self.assertEqual(loaded.hp_rolls.get(4), 8)
        self.assertEqual(loaded.hp_rolls.get(5), 5)
        self.assertEqual(loaded.level_up_asi, {"ID_TEST_CLASS_FIGHTER::4": {"strength": 2}})
        self.assertEqual(loaded.level_up_feats, {"ID_TEST_CLASS_WIZARD::1": "ID_TEST_FEAT_TOUGH"})
        self.assertEqual(loaded.spell_sources.get("ID_TEST_SP_MAGIC_MISSILE"), "ID_TEST_CLASS_WIZARD")

        # MainWindow GUI smoke test for Multiclass + HP Mode + Caster Spell Filter
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            win = MainWindow(
                self.repo, tp, custom_dir=tp / "c", templates_dir=tp / "t",
                config=AppConfig(characters_dir=str(tp / "chars")),
                config_path=tp / "cfg.json", auto_sync=False,
            )
            win.select_class_by_id("ID_TEST_CLASS_WIZARD")
            win.add_multiclass("ID_TEST_CLASS_CLERIC", 1)
            self.assertEqual(len(win.state.normalized_classes()), 2)
            self.assertEqual(win.state.level, 2)
            # Caster spell filter lists Eligible, Wizard, Cleric, All
            caster_items = [win.cmb_spell_caster.itemData(i) for i in range(win.cmb_spell_caster.count())]
            self.assertIn("caster::ID_TEST_CLASS_WIZARD", caster_items)
            self.assertIn("caster::ID_TEST_CLASS_CLERIC", caster_items)
            # Always-prepared Life Domain spells appear in tbl_spells with disabled checkbox
            self.assertGreaterEqual(win.tbl_spells.rowCount(), 2)
            # HP Rolled mode toggle
            win.cmb_hp_mode.setCurrentIndex(win.cmb_hp_mode.findData("rolled"))
            self.assertEqual(win.state.hp_mode, "rolled")
            win.btn_roll_all_hp.click()
            self.assertIn(2, win.state.hp_rolls)
            win._dirty = False
            win.current_file = tp / "chars" / "ok.dnd5e"
            win.close()

    def test_05_windows_compatibility_paths_sanitization_and_pdf_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            local_app = tp / "AppDataLocal"
            roaming_app = tp / "AppDataRoaming"
            docs_dir = tp / "WinDocs"
            docs_dir.mkdir()
            with mock.patch("aurora_borealis.platform_utils.sys.platform", "win32"), mock.patch.dict(
                os.environ,
                {"LOCALAPPDATA": str(local_app), "APPDATA": str(roaming_app)},
                clear=False,
            ), mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AURORA_BOREALIS_DATA_DIR", None)
                os.environ.pop("AURORA_BOREALIS_CONFIG_PATH", None)
                self.assertTrue(is_windows())
                self.assertEqual(get_app_data_dir(), local_app / "Aurora Borealis")
                self.assertEqual(get_config_path(), roaming_app / "Aurora Borealis" / "config.json")
                with mock.patch("aurora_borealis.paths.get_windows_documents_dir", return_value=docs_dir):
                    self.assertEqual(get_os_documents_dir(), docs_dir)
                kwargs = subprocess_no_window_kwargs()
                self.assertIsInstance(kwargs, dict)

            # Windows invalid path characters stripped cleanly by github_importer._safe_rel_path
            rel = _safe_rel_path('sub\\bad:name*?.xml', "https://example.com/x.xml")
            self.assertNotIn(":", str(rel))
            self.assertNotIn("*", str(rel))
            self.assertNotIn("?", str(rel))

            # PDF export falls back cleanly to Qt HTML PDF when qpdf & pypdf are unavailable
            st = CharacterState(
                name="WinHero",
                classes=[ClassLevel("ID_TEST_CLASS_FIGHTER", 2)],
            )
            comp = self.engine.evaluate(st)
            out_pdf = tp / "win_fallback.pdf"
            with mock.patch("aurora_borealis.pdf_export._can_use_pdf_tools", return_value=False):
                export_character_pdf(st, comp, self.repo, out_pdf, templates_dir=tp / "empty_tpl")
            self.assertTrue(out_pdf.is_file())
            self.assertTrue(out_pdf.read_bytes().startswith(b"%PDF-"))
            self.assertIsNone(find_executable("definitely_nonexistent_binary_xyz_123"))


if __name__ == "__main__":
    unittest.main()
