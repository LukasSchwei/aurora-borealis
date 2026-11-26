"""Comprehensive unit & headless UI test suite for Features 1.C, 1.F, 2.1, 2.2, 2.4, 2.8, 3.4, 3.6, 3.7."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSpinBox

from aurora_borealis.bundle import (
    BUNDLE_EXTENSION,
    export_character_bundle,
    import_character_bundle,
    inspect_character_bundle,
)
from aurora_borealis.config import AppConfig
from aurora_borealis.engine import RulesEngine
from aurora_borealis.equipment import (
    build_starting_equipment,
    deduct_currency,
    element_cost_cp,
    get_character_containers,
    is_container_weightless,
    roll_starting_gold,
)
from aurora_borealis.fivetools_importer import (
    _convert_classes,
    _convert_items,
    _convert_spells,
)
from aurora_borealis.homebrew import (
    build_homebrew_element,
    save_homebrew_pack,
    serialize_homebrew_elements,
    validate_homebrew_xml,
)
from aurora_borealis.loader import ContentRepository
from aurora_borealis.models import CharacterState, ClassLevel, InventoryItem
from aurora_borealis.pdf_export import (
    _build_5e_field_map,
    _compute_weapon_attack_and_damage,
    _ordered_weapons,
)
from aurora_borealis.persistence import load_dnd5e, parse_character_xml, save_dnd5e, serialize_character_xml
from aurora_borealis.planner import generate_default_plan, summarize_build_plan
from aurora_borealis.ui.main_window import MainWindow
from aurora_borealis.ui.planner_dialog import BuildPlannerDialog


def _get_app() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


_FIXTURE_XML = """<?xml version="1.0" encoding="utf-8" ?>
<elements>
  <element name="Player's Handbook" type="Source" source="Core" id="ID_SOURCE_PHB" />
  <element name="Homebrew Tome" type="Source" source="Homebrew" id="ID_SOURCE_HB" />

  <element name="Human" type="Race" source="Player's Handbook" id="ID_RACE_HUMAN">
    <setters><set name="speed">30</set></setters>
    <rules>
      <stat name="strength" value="1" />
      <stat name="constitution" value="1" />
      <stat name="speed:fly" value="25" />
      <grant type="Vision" id="ID_VIS_DARKVISION" />
    </rules>
  </element>

  <element name="Darkvision" type="Vision" source="Player's Handbook" id="ID_VIS_DARKVISION">
    <rules>
      <stat name="darkvision" value="60" />
    </rules>
  </element>

  <element name="Custom Ancestry" type="Race" source="Homebrew Tome" id="ID_RACE_CUSTOM">
    <setters><set name="speed">35</set></setters>
  </element>

  <element name="Fighter" type="Class" source="Player's Handbook" id="ID_CLASS_FIGHTER">
    <setters>
      <set name="hd">d10</set>
    </setters>
    <rules>
      <grant type="Proficiency" id="ID_PROF_SIMPLE" />
      <grant type="Proficiency" id="ID_PROF_MARTIAL" />
      <select type="Archetype" name="Martial Archetype" supports="Martial Archetype" level="3" default="ID_ARCH_CHAMPION" />
    </rules>
  </element>

  <element name="Champion" type="Archetype" source="Player's Handbook" id="ID_ARCH_CHAMPION">
    <supports>Martial Archetype</supports>
    <rules>
      <grant type="Archetype Feature" id="ID_FEAT_REMARKABLE" level="7" />
    </rules>
  </element>

  <element name="Damage Resistance (Fire)" type="Damage Resistance" source="Player's Handbook" id="ID_RESISTANCE_FIRE" />
  <element name="Damage Immunity (Poison)" type="Immunity" source="Player's Handbook" id="ID_DAMAGE_IMMUNITY_POISON" />
  <element name="Charmed" type="Condition" source="Player's Handbook" id="ID_CONDITION_IMMUNITY_CHARMED" />

  <element name="Remarkable Athlete" type="Archetype Feature" source="Player's Handbook" id="ID_FEAT_REMARKABLE">
    <sheet action="Passive" usage="Constant">
      <description>You add {{proficiency:half:up}} to STR/DEX/CON checks you aren't proficient in. AC cap test {{clamped}}.</description>
    </sheet>
    <rules>
      <stat name="strength:misc" value="proficiency:half:up" />
      <stat name="strength:save:misc" value="proficiency:half:up" />
      <stat name="dexterity:misc" value="proficiency:half:up" />
      <stat name="constitution:misc" value="proficiency:half:up" />
      <stat name="clamped" value="25" maximum="20" minimum="5" />
      <grant type="Damage Resistance" id="ID_RESISTANCE_FIRE" />
      <grant type="Immunity" id="ID_DAMAGE_IMMUNITY_POISON" />
      <grant type="Condition" id="ID_CONDITION_IMMUNITY_CHARMED" />
      <stat name="investigation:misc" value="2" />
    </rules>
  </element>

  <element name="Bard" type="Class" source="Player's Handbook" id="ID_CLASS_BARD">
    <setters>
      <set name="hd">d8</set>
      <set name="spellcastingAbility">Charisma</set>
      <set name="caster">full</set>
    </setters>
    <rules>
      <grant type="Class Feature" id="ID_FEAT_JOAT" level="2" />
    </rules>
  </element>

  <element name="Jack of All Trades" type="Class Feature" source="Player's Handbook" id="ID_FEAT_JOAT">
    <rules />
  </element>

  <element name="Wizard" type="Class" source="Player's Handbook" id="ID_CLASS_WIZARD">
    <setters>
      <set name="hd">d6</set>
      <set name="caster">full</set>
    </setters>
    <spellcasting name="Wizard" ability="Intelligence" prepare="true">
      <list>Wizard</list>
    </spellcasting>
  </element>

  <element name="Cleric" type="Class" source="Player's Handbook" id="ID_CLASS_CLERIC">
    <setters>
      <set name="hd">d8</set>
      <set name="caster">full</set>
    </setters>
    <spellcasting name="Cleric" ability="Wisdom" prepare="true">
      <list>Cleric</list>
    </spellcasting>
  </element>

  <element name="Acolyte" type="Background" source="Player's Handbook" id="ID_BG_ACOLYTE">
    <rules>
      <grant type="Proficiency" id="ID_PROF_SKILL_INSIGHT" />
    </rules>
  </element>

  <element name="Simple Weapons" type="Proficiency" source="Player's Handbook" id="ID_PROF_SIMPLE" />
  <element name="Martial Weapons" type="Proficiency" source="Player's Handbook" id="ID_PROF_MARTIAL" />
  <element name="Skill: Insight" type="Proficiency" source="Player's Handbook" id="ID_PROF_SKILL_INSIGHT" />
  <element name="Skill: Athletics" type="Proficiency" source="Player's Handbook" id="ID_PROF_SKILL_ATHLETICS" />

  <element name="Tough" type="Feat" source="Player's Handbook" id="ID_FEAT_TOUGH">
    <rules>
      <stat name="hp" value="level" />
      <stat name="hp" value="level" />
    </rules>
  </element>

  <element name="Longsword" type="Weapon" source="Player's Handbook" id="ID_WPN_LONGSWORD">
    <setters>
      <set name="category">Martial Melee Weapons</set>
      <set name="damage" type="slashing">1d8</set>
      <set name="versatile">1d10</set>
      <set name="cost" currency="gp">15</set>
      <set name="weight">3 lb</set>
      <set name="proficiency">ID_PROF_MARTIAL</set>
    </setters>
  </element>

  <element name="Handaxe" type="Weapon" source="Player's Handbook" id="ID_WPN_HANDAXE">
    <setters>
      <set name="category">Simple Melee Weapons</set>
      <set name="damage" type="slashing">1d6</set>
      <set name="cost" currency="gp">5</set>
      <set name="weight">2 lb</set>
      <set name="proficiency">ID_PROF_SIMPLE</set>
    </setters>
  </element>

  <element name="Chain Mail" type="Armor" source="Player's Handbook" id="ID_ARM_CHAINMAIL">
    <setters>
      <set name="category">Heavy Armor</set>
      <set name="armor">Heavy</set>
      <set name="armorClass">16</set>
      <set name="cost" currency="gp">75</set>
      <set name="weight">55 lb</set>
    </setters>
  </element>

  <element name="Shield" type="Armor" source="Player's Handbook" id="ID_ARM_SHIELD">
    <setters>
      <set name="category">Shields</set>
      <set name="armor">Shield</set>
      <set name="cost" currency="gp">10</set>
      <set name="weight">6 lb</set>
    </setters>
  </element>

  <element name="Magic Missile" type="Spell" source="Player's Handbook" id="ID_SPL_MAGIC_MISSILE">
    <supports>Wizard</supports>
    <setters>
      <set name="level">1</set>
      <set name="school">Evocation</set>
      <set name="time">1 action</set>
      <set name="range">120 feet</set>
      <set name="duration">Instantaneous</set>
      <set name="isRitual">false</set>
      <set name="isConcentration">false</set>
    </setters>
  </element>

  <element name="Detect Magic" type="Spell" source="Player's Handbook" id="ID_SPL_DETECT_MAGIC">
    <supports>Wizard, Cleric, Bard</supports>
    <setters>
      <set name="level">1</set>
      <set name="school">Divination</set>
      <set name="isRitual">true</set>
      <set name="isConcentration">true</set>
    </setters>
  </element>

  <element name="Bless" type="Spell" source="Player's Handbook" id="ID_SPL_BLESS">
    <supports>Cleric</supports>
    <setters>
      <set name="level">1</set>
      <set name="school">Enchantment</set>
      <set name="isConcentration">true</set>
    </setters>
  </element>

  <element name="Fire Bolt" type="Spell" source="Player's Handbook" id="ID_SPL_FIRE_BOLT">
    <supports>Wizard</supports>
    <setters>
      <set name="level">0</set>
      <set name="school">Evocation</set>
    </setters>
  </element>
</elements>
"""


def _build_fixture_repo(base_dir: Path) -> tuple[ContentRepository, Path]:
    xml_path = base_dir / "elements.xml"
    xml_path.write_text(_FIXTURE_XML, encoding="utf-8")
    repo = ContentRepository()
    repo.load_directory(base_dir)
    return repo, xml_path


class TestNewFeaturesSuite(unittest.TestCase):
    def test_1c_currency_containers_encumbrance_and_starting_gear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = _build_fixture_repo(Path(tmp))
            engine = RulesEngine(repo)

            # Coin deduction across denominations
            ok, updated = deduct_currency({"cp": 0, "sp": 0, "ep": 0, "gp": 20, "pp": 0}, 1550)
            self.assertTrue(ok)
            self.assertEqual(updated["gp"] * 100 + updated["sp"] * 10 + updated["cp"], 450)
            fail, _ = deduct_currency({"cp": 0, "sp": 0, "ep": 0, "gp": 1, "pp": 0}, 500)
            self.assertFalse(fail)

            # Cost parsing
            sword = repo.get("ID_WPN_LONGSWORD")
            self.assertEqual(element_cost_cp(sword), 1500)

            # Containers + Bag of Holding ignores weight; standard 5e Carrying Capacity check
            state = CharacterState(
                race_id="ID_RACE_HUMAN",
                class_id="ID_CLASS_FIGHTER",
                abilities={"strength": 10, "dexterity": 10, "constitution": 10, "intelligence": 10, "wisdom": 10, "charisma": 10},
                inventory=[
                    InventoryItem(element_id="ID_ARM_CHAINMAIL", name="Chain Mail", weight=55.0, container="On Person"),
                    InventoryItem(element_id="ID_WPN_LONGSWORD", name="Vault Sword", weight=100.0, container="Bag of Holding"),
                    InventoryItem(element_id="CUSTOM_TOKEN", name="Lucky Coin", weight=5.0, ignore_weight=True, notes="Gift", charges=2, max_charges=3, custom=True),
                ],
            )
            self.assertTrue(is_container_weightless("Bag of Holding", state))
            self.assertEqual(len(get_character_containers(state)), 3)
            comp = engine.evaluate(state)
            # Human STR 10 + 1 racial = 11 -> cap 165; carried weight 55 lb only -> Normal
            self.assertAlmostEqual(comp.carried_weight, 55.0)
            self.assertEqual(comp.carrying_capacity, 165.0)
            self.assertEqual(comp.encumbrance_status, "Normal")

            # Over Capacity trigger (> 165 lb)
            state.inventory[0].weight = 180.0
            comp_enc = engine.evaluate(state)
            self.assertEqual(comp_enc.encumbrance_status, "Over Capacity")

            # Class starting equipment & gold roll
            pkg, bg_gp = build_starting_equipment("Fighter", "Acolyte", repo)
            self.assertGreaterEqual(len(pkg), 4)
            self.assertEqual(bg_gp, 15)
            rolled = roll_starting_gold("Fighter")
            self.assertGreaterEqual(rolled, 50)

            # Persistence round-trip for custom item fields & containers
            xml_bytes = serialize_character_xml(state, repo, comp_enc)
            restored = parse_character_xml(xml_bytes, repo)
            self.assertEqual(restored.inventory[1].container, "Bag of Holding")
            self.assertTrue(restored.inventory[2].custom)
            self.assertEqual(restored.inventory[2].charges, 2)
            self.assertEqual(restored.inventory[2].notes, "Gift")

    def test_1f_deep_aurora_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = _build_fixture_repo(Path(tmp))
            engine = RulesEngine(repo)

            # Fighter Lv 7 -> default SelectRule picks Champion -> grants Remarkable Athlete (level 7)
            # Prof bonus = +3 -> half:up = 2; strength:misc +2; clamped = 20; fire:resistance; passive inv +2
            state = CharacterState(
                race_id="ID_RACE_HUMAN",
                class_id="ID_CLASS_FIGHTER",
                level=7,
                abilities={"strength": 15, "dexterity": 12, "constitution": 14, "intelligence": 10, "wisdom": 10, "charisma": 10},
                inventory=[
                    InventoryItem(element_id="ID_ARM_CHAINMAIL", name="Chain Mail", equipped=True),
                    InventoryItem(element_id="ID_ARM_SHIELD", name="Shield", equipped=True),
                ],
            )
            comp = engine.evaluate(state)
            # Default archetype Champion granted automatically during evaluation without mutating state
            granted_ids = {el.id for el in comp.granted_elements}
            self.assertIn("ID_ARCH_CHAMPION", granted_ids)
            self.assertIn("ID_FEAT_REMARKABLE", granted_ids)
            # AC from rules: chain mail 16 + shield 2 = 18
            self.assertEqual(comp.armor_class, 18)
            # Half prof up = 2 -> STR score 16 (+3) + 2 misc = +5 save & Athletics, Investigation +2 -> passive inv 12
            self.assertEqual(comp.saving_throws["strength"].bonus, 5)
            self.assertEqual(comp.skills["Athletics"].bonus, 5)
            self.assertEqual(comp.passive_investigation, 12)
            self.assertIn("Fire", comp.damage_resistances)
            self.assertIn("Poison", comp.damage_immunities)
            self.assertIn("Charmed", comp.condition_immunities)
            self.assertIn(60, [v for v in comp.senses.values()])
            # Placeholder resolution & sheet actions
            desc = comp.resolved_descriptions.get("ID_FEAT_REMARKABLE", "")
            self.assertIn("2", desc)
            self.assertIn("20", desc)
            self.assertNotIn("{{", desc)
            self.assertTrue(any(a.name == "Remarkable Athlete" and a.action == "Passive" for a in comp.sheet_actions))

            # Bard Lv 2 Jack of All Trades adds half prof (+1) to skills & initiative
            bard_state = CharacterState(
                class_id="ID_CLASS_BARD",
                level=2,
                abilities={"strength": 10, "dexterity": 14, "constitution": 10, "intelligence": 10, "wisdom": 10, "charisma": 16},
            )
            bard_comp = engine.evaluate(bard_state)
            # DEX +2 + half prof (2//2 = 1) = +3 initiative and Acrobatics
            self.assertEqual(bard_comp.initiative, 3)
            self.assertEqual(bard_comp.skills["Acrobatics"].bonus, 3)

    def test_2_1_pdf_weapon_attack_damage_and_proficiency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = _build_fixture_repo(Path(tmp))
            engine = RulesEngine(repo)
            # Fighter proficient in Martial & Simple; STR 16 (+3), Lv 1 Prof +2
            state = CharacterState(
                race_id="ID_RACE_HUMAN",
                class_id="ID_CLASS_FIGHTER",
                level=1,
                abilities={"strength": 15, "dexterity": 10, "constitution": 12, "intelligence": 10, "wisdom": 10, "charisma": 10},
                inventory=[
                    InventoryItem(element_id="ID_WPN_HANDAXE", name="Handaxe", category="Weapon", equipped=False),
                    InventoryItem(element_id="ID_WPN_LONGSWORD", name="Longsword", category="Weapon", equipped=True),
                ],
            )
            comp = engine.evaluate(state)
            # Equipped Longsword prioritized first
            ordered = _ordered_weapons(state)
            self.assertEqual(ordered[0].name, "Longsword")

            ls = repo.get("ID_WPN_LONGSWORD")
            atk, dmg, _dmg_type = _compute_weapon_attack_and_damage(ordered[0], ls, comp, repo)
            self.assertEqual(atk, 5)
            self.assertEqual(dmg, "1d8+3")

            # Wizard NOT proficient in Martial -> Longsword attack should NOT include +2 proficiency
            wiz = CharacterState(
                class_id="ID_CLASS_WIZARD",
                level=1,
                abilities={"strength": 14, "dexterity": 10, "constitution": 10, "intelligence": 16, "wisdom": 10, "charisma": 10},
                inventory=[InventoryItem(element_id="ID_WPN_LONGSWORD", name="Longsword", category="Weapon", equipped=True)],
            )
            wiz_comp = engine.evaluate(wiz)
            w_atk, w_dmg, _w_type = _compute_weapon_attack_and_damage(wiz.inventory[0], ls, wiz_comp, repo)
            self.assertEqual(w_atk, 2)
            self.assertEqual(w_dmg, "1d8+2")

            # Field map reflects prioritized equipped Longsword in slot 1
            fields, _checks = _build_5e_field_map(state, comp, repo)
            self.assertEqual(fields["Wpn Name"], "Longsword")
            self.assertEqual(fields["Wpn1 AtkBonus"], "+5")

    def test_2_2_fivetools_importer_enhancements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)

            # Spells conversion
            spell_json = {
                "spell": [
                    {
                        "name": "Phantom Shield",
                        "source": "TCE",
                        "level": 2,
                        "school": "A",
                        "time": [{"number": 1, "unit": "reaction"}],
                        "range": {"type": "point", "distance": {"type": "self"}},
                        "components": {"v": True, "s": True, "m": "a glass shard"},
                        "duration": [{"type": "timed", "duration": {"amount": 1, "type": "minute"}, "concentration": True}],
                        "meta": {"ritual": True},
                        "entries": ["Blocks harm."],
                    }
                ]
            }
            s_elems = _convert_spells(spell_json)
            self.assertEqual(len(s_elems), 1)
            (out_dir / "spells.xml").write_text(serialize_homebrew_elements(s_elems), encoding="utf-8")

            # Items conversion
            items_json = {
                "item": [
                    {
                        "name": "Starblade",
                        "source": "DMG",
                        "type": "M",
                        "weaponCategory": "martial",
                        "dmg1": "1d8",
                        "dmg2": "1d10",
                        "dmgType": "S",
                        "property": ["V", "F"],
                        "value": 5000,
                        "weight": 3,
                        "rarity": "rare",
                        "reqAttune": True,
                        "entries": ["A radiant blade."],
                    }
                ]
            }
            i_elems = _convert_items(items_json)
            self.assertEqual(len(i_elems), 1)
            (out_dir / "items.xml").write_text(serialize_homebrew_elements(i_elems), encoding="utf-8")

            # Classes + subclasses conversion
            classes_json = {
                "class": [
                    {
                        "name": "Chronurgist",
                        "source": "EGW",
                        "hd": {"faces": 6},
                        "proficiency": ["int", "wis"],
                        "spellcastingAbility": "int",
                        "casterProgression": "full",
                        "subclassTitle": "Arcane Tradition",
                        "classFeatures": ["Arcane Recovery|Chronurgist|EGW|1"],
                    }
                ],
                "subclass": [
                    {
                        "name": "Timeweaver",
                        "shortName": "Timeweaver",
                        "source": "EGW",
                        "className": "Chronurgist",
                        "classSource": "EGW",
                        "subclassFeatures": ["Chronal Shift|Chronurgist|EGW|Timeweaver|EGW|2"],
                    }
                ],
                "classFeature": [
                    {
                        "name": "Arcane Recovery",
                        "source": "EGW",
                        "className": "Chronurgist",
                        "level": 1,
                        "entries": ["Recover spell slots."],
                    }
                ],
                "subclassFeature": [
                    {
                        "name": "Chronal Shift",
                        "source": "EGW",
                        "className": "Chronurgist",
                        "subclassShortName": "Timeweaver",
                        "level": 2,
                        "entries": ["Force a reroll."],
                    }
                ],
            }
            c_elems = _convert_classes(classes_json)
            self.assertGreaterEqual(len(c_elems), 4)
            (out_dir / "classes.xml").write_text(serialize_homebrew_elements(c_elems), encoding="utf-8")

            repo = ContentRepository()
            repo.load_directory(out_dir)
            spells = repo.of_type("Spell")
            self.assertEqual(len(spells), 1)
            self.assertEqual(spells[0].setters.get("isConcentration"), "true")
            self.assertEqual(spells[0].setters.get("isRitual"), "true")

            arch = repo.of_type("Archetype")
            self.assertEqual(len(arch), 1)
            self.assertIn("Chronurgist", arch[0].supports)
            cls_el = repo.of_type("Class")[0]
            self.assertTrue(
                any(
                    sr.type == "Archetype" and sr.name == "Arcane Tradition" and sr.supports == "Chronurgist"
                    for sr in cls_el.select_rules
                )
            )

            magic_weapons = repo.of_type("Magic Item")
            self.assertEqual(len(magic_weapons), 1)
            self.assertEqual(magic_weapons[0].setters.get("versatile"), "1d10")
            self.assertEqual(magic_weapons[0].setters.get("attunement"), "true")

    def test_3_4_homebrew_xml_editor_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            custom_dir = Path(tmp)
            el = build_homebrew_element(
                {
                    "type": "Feat",
                    "name": "Blade Ward Mastery",
                    "source": "My Campaign",
                    "description": "Gain +1 AC when wielding a blade.",
                    "sheet_action": "Reaction",
                    "sheet_usage": "1/Short Rest",
                    "sheet_description": "Gain +2 AC until your next turn.",
                    "stats": [{"name": "ac:misc", "value": "1"}],
                }
            )
            xml_text = serialize_homebrew_elements([el])
            ok, errs = validate_homebrew_xml(xml_text)
            self.assertTrue(ok, f"Unexpected validation errors: {errs}")
            out_path = save_homebrew_pack(xml_text, custom_dir, "blade_mastery")
            self.assertTrue(out_path.is_file())

            repo = ContentRepository()
            repo.load_directory(custom_dir)
            feats = repo.of_type("Feat")
            self.assertEqual(len(feats), 1)
            self.assertEqual(feats[0].sheet_action, "Reaction")

            bad_ok, _ = validate_homebrew_xml("<not-elements/>")
            self.assertFalse(bad_ok)

    def test_3_6_build_planner(self) -> None:
        _get_app()
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = _build_fixture_repo(Path(tmp))
            engine = RulesEngine(repo)
            state_lv5 = CharacterState(
                name="Aldric",
                race_id="ID_RACE_HUMAN",
                classes=[ClassLevel("ID_CLASS_FIGHTER", 4), ClassLevel("ID_CLASS_BARD", 1)],
                class_id="ID_CLASS_FIGHTER",
                level=5,
            )
            comp_lv5 = engine.evaluate(state_lv5)

            plan = generate_default_plan(state_lv5, repo)
            self.assertEqual(len(plan), 20)
            summary = summarize_build_plan(plan, repo)
            self.assertIn("Fighter", summary["class_split"])

            # Persistence round-trip with build_plan
            state_lv5.build_plan = plan
            save_path = Path(tmp) / "aldric.dnd5e"
            save_dnd5e(state_lv5, repo, comp_lv5, save_path)
            loaded = load_dnd5e(save_path, repo)
            self.assertEqual(len(loaded.build_plan), 20)

            # Verify BuildPlannerDialog rows are tall enough for embedded combo boxes
            dlg = BuildPlannerDialog(state_lv5, comp_lv5, repo)
            try:
                cmb = dlg.tbl_plan.cellWidget(0, 1)
                self.assertIsNotNone(cmb)
                self.assertGreaterEqual(dlg.tbl_plan.rowHeight(0), cmb.sizeHint().height())
            finally:
                dlg.close()

    def test_3_7_portable_bundle_export_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_dir = tmp_path / "core"
            custom_dir = tmp_path / "custom"
            data_dir.mkdir()
            custom_dir.mkdir()
            repo, _ = _build_fixture_repo(data_dir)

            # Custom homebrew feat inside custom_dir
            hb_el = build_homebrew_element(
                {
                    "type": "Feat",
                    "name": "Custom Wind Step",
                    "source": "GM Pack",
                    "stats": [{"name": "speed", "value": "5"}],
                }
            )
            save_homebrew_pack(serialize_homebrew_elements([hb_el]), custom_dir, "wind_step")
            repo.load_directory(custom_dir)

            hb_id = hb_el.get("id")
            state = CharacterState(
                name="Kaelen",
                race_id="ID_RACE_HUMAN",
                class_id="ID_CLASS_FIGHTER",
                level=1,
                selections={"ID_CLASS_FIGHTER::Manual::1": [hb_id]},
                companions=[{"name": "Shadow Wolf", "species": "Wolf", "hp": 11, "max_hp": 11, "ac": 13}],
            )
            engine = RulesEngine(repo)
            comp = engine.evaluate(state)

            bundle_path = tmp_path / f"kaelen{BUNDLE_EXTENSION}"
            manifest = export_character_bundle(state, comp, repo, bundle_path, custom_dirs=[custom_dir])
            self.assertTrue(bundle_path.is_file())
            self.assertEqual(len(manifest["companions"]), 1)
            self.assertEqual(len(manifest["custom_xml"]), 1)

            inspected = inspect_character_bundle(bundle_path)
            self.assertEqual(inspected["character_name"], "Kaelen")

            import_chars = tmp_path / "imported_chars"
            import_custom = tmp_path / "imported_custom"
            res = import_character_bundle(bundle_path, import_chars, import_custom)
            self.assertTrue(res["character_path"].is_file())
            self.assertEqual(len(res["companion_paths"]), 1)
            self.assertEqual(len(res["xml_paths"]), 1)

    def test_2_4_and_2_8_modular_ui_and_spells_ux(self) -> None:
        _get_app()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_dir = tmp_path / "elements"
            custom_dir = tmp_path / "custom"
            chars_dir = tmp_path / "chars"
            data_dir.mkdir()
            custom_dir.mkdir()
            chars_dir.mkdir()
            repo, _ = _build_fixture_repo(data_dir)
            cfg = AppConfig(characters_dir=str(chars_dir), auto_imported_official=True)
            cfg_path = tmp_path / "config.json"
            win = MainWindow(
                repo=repo,
                data_dir=data_dir,
                custom_dir=custom_dir,
                config=cfg,
                config_path=cfg_path,
                auto_sync=False,
            )
            try:
                # 2.8 architectural & test invariants
                self.assertEqual(win.screen_stack.count(), 4)
                self.assertEqual(win.builder_tabs_stack.count(), 10)
                self.assertEqual(win.tbl_spells.columnCount(), 6)
                self.assertEqual(win.tab6_right_tabs.elideMode(), Qt.TextElideMode.ElideNone)
                main_lines = len((Path(__file__).resolve().parent.parent / "aurora_borealis" / "ui" / "main_window.py").read_text().splitlines())
                self.assertLess(main_lines, 900)

                # Set up Wizard 2 / Cleric 2 multiclass caster and verify 2.4 Spellbook / Prepared filter & counts
                win.state = CharacterState(
                    name="Multicaster",
                    race_id="ID_RACE_HUMAN",
                    classes=[ClassLevel("ID_CLASS_WIZARD", 2), ClassLevel("ID_CLASS_CLERIC", 2)],
                    class_id="ID_CLASS_WIZARD",
                    level=4,
                    abilities={"strength": 8, "dexterity": 12, "constitution": 12, "intelligence": 16, "wisdom": 16, "charisma": 10},
                    known_spells=["ID_SPL_MAGIC_MISSILE", "ID_SPL_DETECT_MAGIC", "ID_SPL_BLESS"],
                    prepared_spells=["ID_SPL_BLESS"],
                )
                win._recalculate_and_refresh()

                # Check per-class prepared status badge & limits text
                self.assertIn("Wizard:", win.lbl_spell_limits.text())
                self.assertIn("Cleric:", win.lbl_spell_limits.text())

                # Filter: Prepared Only -> only Bless visible
                idx_prep = win.cmb_known_spell_filter.findData("prepared")
                self.assertGreaterEqual(idx_prep, 0)
                win.cmb_known_spell_filter.setCurrentIndex(idx_prep)
                self.assertEqual(win.tbl_spells.rowCount(), 1)
                self.assertEqual(win.tbl_spells.item(0, 0).text(), "Bless")
                self.assertIn("Prepared", win.tbl_spells.item(0, 4).text())

                # Filter: Spellbook / Unprepared -> Magic Missile & Detect Magic visible
                idx_sb = win.cmb_known_spell_filter.findData("spellbook")
                win.cmb_known_spell_filter.setCurrentIndex(idx_sb)
                self.assertEqual(win.tbl_spells.rowCount(), 2)
                self.assertIn("Spellbook", win.tbl_spells.item(0, 4).text())

                # Filter: Rituals Only -> Detect Magic visible
                idx_rit = win.cmb_known_spell_filter.findData("ritual")
                win.cmb_known_spell_filter.setCurrentIndex(idx_rit)
                self.assertEqual(win.tbl_spells.rowCount(), 1)
                self.assertEqual(win.tbl_spells.item(0, 0).text(), "Detect Magic")

                # Verify table rows are tall/wide enough for QSpinBox widgets (no clipping at 1.0 & 1.5 scale)
                win.state.hp_mode = "rolled"
                win.state.inventory = [
                    InventoryItem(element_id="ID_WPN_LONGSWORD", name="Longsword", category="Weapon", quantity=3)
                ]
                win._recalculate_and_refresh()
                win.show()
                QApplication.processEvents()
                for scale in (1.0, 1.5):
                    win.apply_scale(scale, persist=False)
                    QApplication.processEvents()
                    qty_spin = win.tbl_inventory.cellWidget(0, 2)
                    self.assertIsNotNone(qty_spin)
                    self.assertGreaterEqual(win.tbl_inventory.rowHeight(0), qty_spin.sizeHint().height())
                    self.assertGreaterEqual(win.tbl_inventory.columnWidth(2), qty_spin.minimumWidth())

                    self.assertGreater(win.tbl_hp_rolls.rowCount(), 0)
                    hp_cell = win.tbl_hp_rolls.cellWidget(0, 3)
                    self.assertIsNotNone(hp_cell)
                    hp_spin = hp_cell.findChild(QSpinBox)
                    self.assertIsNotNone(hp_spin)
                    self.assertGreaterEqual(win.tbl_hp_rolls.rowHeight(0), hp_spin.sizeHint().height())
            finally:
                win._dirty = False
                win.close()


if __name__ == "__main__":
    unittest.main()
