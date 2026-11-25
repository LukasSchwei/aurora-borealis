"""Self-contained regression tests for GitHub Issues #4, #5, and #6."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from aurora_borealis.config import AppConfig
from aurora_borealis.engine import (
    RulesEngine,
    is_equipment_proficient,
    is_spell_castable_for_character,
)
from aurora_borealis.library import scan_characters_folder
from aurora_borealis.loader import ContentRepository
from aurora_borealis.models import (
    CharacterState,
    ClassLevel,
    Element,
    GrantRule,
    SelectRule,
    SpellcastingInfo,
)
from aurora_borealis.persistence import load_dnd5e
from aurora_borealis.ui.dialogs import MagicGearDialog
from aurora_borealis.ui.main_window import MainWindow


def _populate_repo(repo: ContentRepository, elements: list[Element]) -> None:
    for el in elements:
        repo.by_id[el.id] = el
        repo.by_type[el.type].append(el)
        repo._type_by_id[el.type][el.id] = el
        repo._by_type_name[(el.type.lower(), el.name.lower())] = el
        repo._index_element_metadata(el)
    repo._sync_type_lists_and_caches()


class GitHubIssues456Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    # ------------------------------------------------------------------
    # Issue #5: Windows Setup Wizard
    # ------------------------------------------------------------------
    def test_issue5_windows_setup_wizard_fixes(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent
        wiz_path = root_dir / "installer" / "windows_wizard.ps1"
        inst_path = root_dir / "installer" / "install-windows.ps1"

        wiz_bytes = wiz_path.read_bytes().removeprefix(b"\xef\xbb\xbf")
        self.assertTrue(all(b < 128 for b in wiz_bytes))
        wiz_txt = wiz_bytes.decode("ascii")

        # GroupBox has no UseMnemonic property in WinForms (caused Issue #5 crash)
        self.assertNotIn("GrpContentPacks.UseMnemonic", wiz_txt)
        self.assertIn('GrpContentPacks.Text = "D&&D Content Packs', wiz_txt)
        # Ensure UseMnemonic is never set on any GroupBox
        for line in wiz_txt.splitlines():
            if "UseMnemonic" in line:
                self.assertNotIn("Grp", line)
        # Ensure PS 5.1 ChildProc.Handle & WaitForExit fix is present
        self.assertIn("$Script:ChildProc.Handle", wiz_txt)
        self.assertIn("$Script:ChildProc.WaitForExit()", wiz_txt)

        inst_txt = inst_path.read_text(encoding="utf-8")
        self.assertIn("function Invoke-NativeChecked", inst_txt)
        self.assertIn("Invoke-NativeChecked", inst_txt)

    # ------------------------------------------------------------------
    # Issue #4: Equipment & Spell Proficiency Filters
    # ------------------------------------------------------------------
    def _build_proficiency_repo(self) -> ContentRepository:
        repo = ContentRepository()
        _populate_repo(
            repo,
            [
                Element(
                    id="ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR",
                    name="Armor Proficiency (Light Armor)",
                    type="Proficiency",
                ),
                Element(
                    id="ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR",
                    name="Armor Proficiency (Medium Armor)",
                    type="Proficiency",
                ),
                Element(
                    id="ID_PROFICIENCY_ARMOR_PROFICIENCY_HEAVY_ARMOR",
                    name="Armor Proficiency (Heavy Armor)",
                    type="Proficiency",
                ),
                Element(
                    id="ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS",
                    name="Armor Proficiency (Shields)",
                    type="Proficiency",
                ),
                Element(
                    id="ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS",
                    name="Weapon Proficiency (Simple Weapons)",
                    type="Proficiency",
                ),
                Element(
                    id="ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS",
                    name="Weapon Proficiency (Martial Weapons)",
                    type="Proficiency",
                ),
                Element(
                    id="ID_PROFICIENCY_WEAPON_PROFICIENCY_LONGSWORD",
                    name="Weapon Proficiency (Longsword)",
                    type="Proficiency",
                ),
                Element(
                    id="ID_PROFICIENCY_TOOL_PROFICIENCY_THIEVES_TOOLS",
                    name="Tool Proficiency (Thieves' Tools)",
                    type="Proficiency",
                ),
                # Classes
                Element(
                    id="ID_CLS_WIZARD",
                    name="Wizard",
                    type="Class",
                    setters={"hd": "d6"},
                    spellcasting=SpellcastingInfo(
                        name="Wizard", ability="Intelligence", spell_list="Wizard", prepare=True
                    ),
                    grant_rules=[
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS", level=1),
                    ],
                ),
                Element(
                    id="ID_CLS_PALADIN",
                    name="Paladin",
                    type="Class",
                    setters={"hd": "d10"},
                    spellcasting=SpellcastingInfo(
                        name="Paladin", ability="Charisma", spell_list="Paladin", prepare=True
                    ),
                    grant_rules=[
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_ARMOR_PROFICIENCY_HEAVY_ARMOR", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS", level=1),
                    ],
                ),
                Element(
                    id="ID_CLS_FIGHTER",
                    name="Fighter",
                    type="Class",
                    setters={"hd": "d10"},
                    grant_rules=[
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_ARMOR_PROFICIENCY_LIGHT_ARMOR", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_ARMOR_PROFICIENCY_MEDIUM_ARMOR", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_ARMOR_PROFICIENCY_HEAVY_ARMOR", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_ARMOR_PROFICIENCY_SHIELDS", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_WEAPON_PROFICIENCY_SIMPLE_WEAPONS", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_WEAPON_PROFICIENCY_MARTIAL_WEAPONS", level=1),
                    ],
                ),
                Element(
                    id="ID_CLS_ELF_WIZARD",
                    name="High Elf Fighter-Mage",
                    type="Race",
                    grant_rules=[
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_WEAPON_PROFICIENCY_LONGSWORD", level=1),
                        GrantRule(type="Proficiency", id="ID_PROFICIENCY_TOOL_PROFICIENCY_THIEVES_TOOLS", level=1),
                        GrantRule(type="Spell", id="ID_SP_SACRED_FLAME", level=1),
                    ],
                ),
                # Equipment
                Element(
                    id="ID_WPN_DAGGER",
                    name="Dagger",
                    type="Weapon",
                    supports=["Simple", "Melee"],
                    setters={"damage": "1d4", "damage_type": "piercing"},
                ),
                Element(
                    id="ID_WPN_LONGSWORD",
                    name="Longsword",
                    type="Weapon",
                    supports=["Martial", "Melee"],
                    setters={"damage": "1d8", "damage_type": "slashing"},
                ),
                Element(
                    id="ID_WPN_GREATAXE",
                    name="Greataxe",
                    type="Weapon",
                    supports=["Martial", "Melee"],
                    setters={"damage": "1d12", "damage_type": "slashing"},
                ),
                Element(
                    id="ID_MAG_LONGSWORD_P1",
                    name="+1 Longsword",
                    type="Magic Item",
                    setters={"rarity": "Uncommon", "category": "Weapon"},
                ),
                Element(
                    id="ID_ARM_LEATHER",
                    name="Leather Armor",
                    type="Armor",
                    setters={"armor": "Light", "armorClass": "11"},
                ),
                Element(
                    id="ID_ARM_CHAIN",
                    name="Chain Mail",
                    type="Armor",
                    setters={"armor": "Heavy", "armorClass": "16"},
                ),
                Element(
                    id="ID_ARM_SHIELD",
                    name="Shield",
                    type="Armor",
                    setters={"armor": "Shield", "armorClass": "2"},
                ),
                Element(
                    id="ID_ITEM_THIEVES_TOOLS",
                    name="Thieves' Tools",
                    type="Item",
                    setters={"category": "Tools"},
                ),
                Element(
                    id="ID_ITEM_SMITH_TOOLS",
                    name="Smith's Tools",
                    type="Item",
                    setters={"category": "Artisan's Tools"},
                ),
                Element(
                    id="ID_ITEM_ROPE",
                    name="Hempen Rope (50 feet)",
                    type="Item",
                    setters={"category": "Adventuring Gear"},
                ),
                # Spells
                Element(
                    id="ID_SP_FIRE_BOLT",
                    name="Fire Bolt",
                    type="Spell",
                    supports=["Wizard", "Sorcerer"],
                    setters={"level": "0", "school": "Evocation"},
                ),
                Element(
                    id="ID_SP_MAGIC_MISSILE",
                    name="Magic Missile",
                    type="Spell",
                    supports=["Wizard", "Sorcerer"],
                    setters={"level": "1", "school": "Evocation"},
                ),
                Element(
                    id="ID_SP_FIREBALL",
                    name="Fireball",
                    type="Spell",
                    supports=["Wizard", "Sorcerer"],
                    setters={"level": "3", "school": "Evocation"},
                ),
                Element(
                    id="ID_SP_BLESS",
                    name="Bless",
                    type="Spell",
                    supports=["Cleric", "Paladin"],
                    setters={"level": "1", "school": "Enchantment"},
                ),
                Element(
                    id="ID_SP_SACRED_FLAME",
                    name="Sacred Flame",
                    type="Spell",
                    supports=["Cleric"],
                    setters={"level": "0", "school": "Evocation"},
                ),
            ],
        )
        return repo

    def test_issue4_proficiency_helpers_and_filters(self) -> None:
        repo = self._build_proficiency_repo()
        engine = RulesEngine(repo)

        # Wizard Lv 1 with High Elf Race (Longsword + Thieves' Tools + Sacred Flame racial grant)
        st_wiz = CharacterState(
            name="Lyra",
            race_id="ID_CLS_ELF_WIZARD",
            classes=[ClassLevel("ID_CLS_WIZARD", 1)],
        )
        st_wiz.sync_from_classes()
        comp_wiz = engine.evaluate(st_wiz)

        self.assertIs(is_equipment_proficient(repo.get("ID_WPN_DAGGER"), comp_wiz, repo), True)
        self.assertIs(is_equipment_proficient(repo.get("ID_WPN_LONGSWORD"), comp_wiz, repo), True)
        self.assertIs(is_equipment_proficient(repo.get("ID_MAG_LONGSWORD_P1"), comp_wiz, repo), True)
        self.assertIs(is_equipment_proficient(repo.get("ID_WPN_GREATAXE"), comp_wiz, repo), False)
        self.assertIs(is_equipment_proficient(repo.get("ID_ARM_CHAIN"), comp_wiz, repo), False)
        self.assertIs(is_equipment_proficient(repo.get("ID_ARM_SHIELD"), comp_wiz, repo), False)
        self.assertIs(is_equipment_proficient(repo.get("ID_ITEM_THIEVES_TOOLS"), comp_wiz, repo), True)
        self.assertIs(is_equipment_proficient(repo.get("ID_ITEM_SMITH_TOOLS"), comp_wiz, repo), False)
        self.assertIsNone(is_equipment_proficient(repo.get("ID_ITEM_ROPE"), comp_wiz, repo))

        # Manual proficiency override unlocks Heavy Armor & Greataxe
        st_wiz.set_override("override_proficiencies", True)
        st_wiz.manual_proficiencies = ["Heavy Armor", "Greataxe"]
        comp_wiz_ov = engine.evaluate(st_wiz)
        self.assertIs(is_equipment_proficient(repo.get("ID_ARM_CHAIN"), comp_wiz_ov, repo), True)
        self.assertIs(is_equipment_proficient(repo.get("ID_WPN_GREATAXE"), comp_wiz_ov, repo), True)

        # Spell castability: Lv 1 Wizard can cast Lv 0-1 Wizard spells + racial Sacred Flame, NOT Fireball (Lv 3) or Bless
        self.assertTrue(is_spell_castable_for_character(repo.get("ID_SP_FIRE_BOLT"), comp_wiz))
        self.assertTrue(is_spell_castable_for_character(repo.get("ID_SP_MAGIC_MISSILE"), comp_wiz))
        self.assertTrue(is_spell_castable_for_character(repo.get("ID_SP_SACRED_FLAME"), comp_wiz))
        self.assertFalse(is_spell_castable_for_character(repo.get("ID_SP_FIREBALL"), comp_wiz))
        self.assertFalse(is_spell_castable_for_character(repo.get("ID_SP_BLESS"), comp_wiz))

        # Paladin Lv 1 (5e half-caster has no slots at Lv 1) vs Lv 2 (casts Lv 1 Paladin spells)
        st_pal1 = CharacterState(name="Ser", ruleset="5e", classes=[ClassLevel("ID_CLS_PALADIN", 1)])
        st_pal1.sync_from_classes()
        self.assertFalse(is_spell_castable_for_character(repo.get("ID_SP_BLESS"), engine.evaluate(st_pal1)))
        st_pal2 = CharacterState(name="Ser", ruleset="5e", classes=[ClassLevel("ID_CLS_PALADIN", 2)])
        st_pal2.sync_from_classes()
        self.assertTrue(is_spell_castable_for_character(repo.get("ID_SP_BLESS"), engine.evaluate(st_pal2)))

        # Non-caster Fighter with racial spell
        st_ftr = CharacterState(name="Bram", race_id="ID_CLS_ELF_WIZARD", classes=[ClassLevel("ID_CLS_FIGHTER", 1)])
        st_ftr.sync_from_classes()
        comp_ftr = engine.evaluate(st_ftr)
        self.assertTrue(is_spell_castable_for_character(repo.get("ID_SP_SACRED_FLAME"), comp_ftr))
        self.assertFalse(is_spell_castable_for_character(repo.get("ID_SP_MAGIC_MISSILE"), comp_ftr))

        # GUI MainWindow filters + zero cell widgets + live updates
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
                name="Lyra",
                race_id="ID_CLS_ELF_WIZARD",
                classes=[ClassLevel("ID_CLS_WIZARD", 1)],
            )
            win.state.sync_from_classes()
            win._recalculate_and_refresh()

            # Equipment proficiency filter modes
            def equip_names() -> set[str]:
                return {
                    win.tbl_equip_catalog.item(r, 1).text()
                    for r in range(win.tbl_equip_catalog.rowCount())
                }

            win.cmb_equip_proficiency.setCurrentIndex(win.cmb_equip_proficiency.findData("proficient"))
            self.assertEqual(equip_names(), {"Dagger", "Longsword", "+1 Longsword", "Thieves' Tools"})
            for r in range(win.tbl_equip_catalog.rowCount()):
                for c in range(5):
                    self.assertIsNone(win.tbl_equip_catalog.cellWidget(r, c))

            win.cmb_equip_proficiency.setCurrentIndex(win.cmb_equip_proficiency.findData("usable"))
            self.assertEqual(
                equip_names(),
                {"Dagger", "Longsword", "+1 Longsword", "Thieves' Tools", "Hempen Rope (50 feet)"},
            )

            win.cmb_equip_proficiency.setCurrentIndex(win.cmb_equip_proficiency.findData("not_proficient"))
            self.assertEqual(equip_names(), {"Greataxe", "Leather Armor", "Chain Mail", "Shield", "Smith's Tools"})

            # Spell proficiency / availability filter modes
            def spell_names() -> set[str]:
                return {
                    win.tbl_spell_catalog.item(r, 0).text()
                    for r in range(win.tbl_spell_catalog.rowCount())
                }

            win.cmb_spell_caster.setCurrentIndex(win.cmb_spell_caster.findData("__all__"))
            win.cmb_spell_proficiency.setCurrentIndex(win.cmb_spell_proficiency.findData("castable"))
            self.assertEqual(spell_names(), {"Fire Bolt", "Magic Missile", "Sacred Flame"})
            for r in range(win.tbl_spell_catalog.rowCount()):
                for c in range(4):
                    self.assertIsNone(win.tbl_spell_catalog.cellWidget(r, c))

            win.cmb_spell_proficiency.setCurrentIndex(win.cmb_spell_proficiency.findData("class_list"))
            self.assertEqual(spell_names(), {"Fire Bolt", "Magic Missile", "Fireball", "Sacred Flame"})

            win.cmb_spell_proficiency.setCurrentIndex(win.cmb_spell_proficiency.findData("not_castable"))
            self.assertEqual(spell_names(), {"Fireball", "Bless"})

            # Leveling Wizard to 5 dynamically unlocks Fireball under "castable"
            win.cmb_spell_proficiency.setCurrentIndex(win.cmb_spell_proficiency.findData("castable"))
            win.spn_level.setValue(5)
            self.assertIn("Fireball", spell_names())

            # MagicGearDialog Proficient Only checkbox filters base list
            mg_dlg = MagicGearDialog(repo, computed=win.computed, parent=win)
            mg_dlg.chk_proficient_only.setChecked(True)
            mg_names = {mg_dlg.lst_base.item(i).text() for i in range(mg_dlg.lst_base.count())}
            self.assertEqual(mg_names, {"[Weapon] Dagger", "[Weapon] Longsword"})
            mg_dlg.close()

            win._dirty = False
            win.current_file = p / "chars" / "lyra.dnd5e"
            win.close()

    # ------------------------------------------------------------------
    # Issue #6: Backwards Compatibility with Old Aurora Builder Files
    # ------------------------------------------------------------------
    def test_issue6_legacy_aurora_files_and_append_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            xml_dir = p / "xml"
            xml_dir.mkdir()

            # Core XML + <append id="..."> extension XML (standard Aurora Builder pattern)
            (xml_dir / "core.xml").write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<elements>
  <element name="Elf" type="Race" source="SRD" id="ID_SRD_RACE_ELF">
    <rules>
      <stat name="innate speed" value="30" bonus="base"/>
      <select type="Sub Race" name="Elf Subrace" supports="Elf" number="1" level="1"/>
    </rules>
  </element>
  <element name="High Elf" type="Sub Race" source="PHB" id="ID_WOTC_PHB_SUB_RACE_HIGH_ELF">
    <supports>Elf</supports>
    <rules><stat name="intelligence" value="1"/></rules>
  </element>
  <element name="Acolyte" type="Background" source="SRD" id="ID_SRD_BACKGROUND_ACOLYTE"/>
  <element name="Wizard" type="Class" source="SRD" id="ID_SRD_CLASS_WIZARD">
    <setters><set name="hd">d6</set></setters>
    <spellcasting name="Wizard" ability="Intelligence" prepare="true"><list>Wizard</list></spellcasting>
    <rules>
      <select type="Archetype" name="Arcane Tradition" supports="Arcane Tradition" level="2"/>
      <select type="Ability Score Improvement" name="Ability Score Improvement" level="4" number="1"/>
    </rules>
    <multiclass id="ID_WOTC_PHB_MULTICLASS_WIZARD">
      <rules/>
    </multiclass>
  </element>
  <element name="Fighter" type="Class" source="SRD" id="ID_SRD_CLASS_FIGHTER">
    <setters><set name="hd">d10</set></setters>
    <rules>
      <select type="Ability Score Improvement" name="Ability Score Improvement" level="4" number="1"/>
    </rules>
  </element>
  <element name="School of Evocation" type="Archetype" source="SRD" id="ID_WOTC_PHB_ARCHETYPE_EVOCATION">
    <supports>Arcane Tradition</supports>
  </element>
  <element name="Fireball" type="Spell" source="SRD" id="ID_SRD_SPELL_FIREBALL">
    <supports>Wizard</supports>
    <setters><set name="level">3</set><set name="school">Evocation</set></setters>
  </element>
  <element name="Longsword" type="Weapon" source="SRD" id="ID_SRD_WEAPON_LONGSWORD">
    <setters><set name="weight" lb="3">3 lb.</set><set name="damage">1d8</set></setters>
  </element>
</elements>
""",
                encoding="utf-8",
            )
            (xml_dir / "append.xml").write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<elements>
  <append id="ID_WOTC_PHB_ARCHETYPE_EVOCATION">
    <supports>Expanded Evocation</supports>
    <rules><grant type="Spell" id="ID_SRD_SPELL_FIREBALL" level="2"/></rules>
  </append>
</elements>
""",
                encoding="utf-8",
            )

            repo = ContentRepository()
            repo.load_directory(xml_dir)
            evoc = repo.get("ID_WOTC_PHB_ARCHETYPE_EVOCATION")
            self.assertIsNotNone(evoc)
            assert evoc is not None
            self.assertIn("Expanded Evocation", evoc.supports)
            self.assertTrue(any(g.id == "ID_SRD_SPELL_FIREBALL" for g in evoc.grant_rules))

            # Realistic legacy Aurora Builder .dnd5e file:
            # - registered="..." without id="..." on Race/Class/Background/Multiclass
            # - cross-pack PHB IDs resolved against loaded SRD elements
            # - <display-properties><portrait><local>/<base64>
            # - <build><appearance> directly under <build>
            # - Multiclass Lv 5 (Fighter 1 / Wizard 4) with rndhp and repeated ASI picks
            # - <equipment> with attunement="true", <details><name>, <items><adorner name="Weapon, +2" />
            # - <magic><spellcasting name="Wizard"><spells><spell id="ID_WOTC_PHB_SPELL_FIREBALL" />
            legacy_file = p / "old_aurora_hero.dnd5e"
            legacy_file.write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<character version="0.2">
  <display-properties favorite="true">
    <name>Alden Oldfile</name>
    <race>Elf</race>
    <class>Fighter / Wizard</class>
    <background>Acolyte</background>
    <level>5</level>
    <portrait>
      <local>/tmp/old_portrait.png</local>
      <base64>QUJD</base64>
    </portrait>
  </display-properties>
  <build>
    <input>
      <name>Alden Oldfile</name>
      <player-name>Lukas</player-name>
      <experience>6500</experience>
      <gender>Male</gender>
      <faith>Mystra</faith>
      <background-story>Studied at Candlekeep.</background-story>
      <background-traits>Curious scholar.</background-traits>
      <organization>
        <name>Harpers</name>
        <allies>Elminster</allies>
      </organization>
      <notes>
        <note column="left">Old journal entry.</note>
      </notes>
      <currency>
        <copper>4</copper><silver>5</silver><electrum>0</electrum><gold>120</gold><platinum>2</platinum>
      </currency>
    </input>
    <appearance>
      <age>120</age>
      <height>5'10"</height>
      <weight>150 lb</weight>
      <eyes>Blue</eyes>
      <skin>Fair</skin>
      <hair>Silver</hair>
    </appearance>
    <abilities>
      <strength>14</strength><dexterity>14</dexterity><constitution>13</constitution>
      <intelligence>15</intelligence><wisdom>10</wisdom><charisma>8</charisma>
    </abilities>
    <elements>
      <element type="Option" registered="ID_INTERNAL_OPTION_ROLLED_HP" />
      <element type="Race" name="Elf" registered="ID_WOTC_PHB_RACE_ELF">
        <element type="Sub Race" name="High Elf" registered="ID_WOTC_PHB_SUB_RACE_HIGH_ELF" />
      </element>
      <element type="Background" name="Acolyte" registered="ID_WOTC_PHB_BACKGROUND_ACOLYTE" />
      <element type="Class" name="Fighter" registered="ID_WOTC_PHB_CLASS_FIGHTER" rndhp="9" />
      <element type="Level" name="1" rndhp="9" />
      <element type="Level" name="2" class="ID_WOTC_PHB_MULTICLASS_WIZARD" rndhp="5">
        <element type="Multiclass" name="Wizard" registered="ID_WOTC_PHB_MULTICLASS_WIZARD" rndhp="5,4,6,3" />
      </element>
      <element type="Level" name="3" class="ID_WOTC_PHB_MULTICLASS_WIZARD" rndhp="4">
        <element type="Archetype" name="School of Evocation" registered="ID_WOTC_PHB_ARCHETYPE_EVOCATION" />
      </element>
      <element type="Level" name="4" class="ID_WOTC_PHB_MULTICLASS_WIZARD" rndhp="6" />
      <element type="Level" name="5" class="ID_WOTC_PHB_MULTICLASS_WIZARD" rndhp="3">
        <element type="Ability Score Improvement" registered="ID_WOTC_PHB_ASI_INTELLIGENCE" />
        <element type="Ability Score Improvement" registered="ID_WOTC_PHB_ASI_INTELLIGENCE" />
      </element>
    </elements>
    <equipment>
      <storage>
        <item identifier="ID_WOTC_PHB_WEAPON_LONGSWORD" name="Longsword" amount="1" equipped="true" attunement="true">
          <details><name>Sunblade Replica</name></details>
          <items><adorner name="Weapon, +2" /></items>
        </item>
      </storage>
    </equipment>
    <magic>
      <spellcasting name="Wizard" ability="Intelligence">
        <spells>
          <spell name="Fireball" id="ID_WOTC_PHB_SPELL_FIREBALL" prepared="true" />
        </spells>
      </spellcasting>
    </magic>
  </build>
</character>
""",
                encoding="utf-8",
            )

            loaded = load_dnd5e(legacy_file, repo)
            self.assertEqual(loaded.name, "Alden Oldfile")
            self.assertEqual(loaded.race_id, "ID_SRD_RACE_ELF")
            self.assertEqual(loaded.background_id, "ID_SRD_BACKGROUND_ACOLYTE")
            self.assertEqual(loaded.level, 5)
            self.assertEqual([(c.class_id, c.level) for c in loaded.classes], [("ID_SRD_CLASS_FIGHTER", 1), ("ID_SRD_CLASS_WIZARD", 4)])
            self.assertEqual(loaded.hp_mode, "rolled")
            self.assertEqual(loaded.hp_rolls, {1: 9, 2: 5, 3: 4, 4: 6, 5: 3})
            self.assertEqual(loaded.portrait_path, "/tmp/old_portrait.png")
            self.assertEqual(loaded.portrait_base64, "QUJD")
            self.assertEqual(loaded.age, "120")
            self.assertEqual(loaded.eyes, "Blue")
            self.assertEqual(loaded.hair, "Silver")
            self.assertEqual(loaded.backstory, "Studied at Candlekeep.")
            self.assertIn("Old journal entry.", loaded.notes)
            self.assertIn("Personality Traits: Curious scholar.", loaded.notes)
            self.assertIn("Organization: Harpers", loaded.notes)

            # Sub Race, Archetype, and ASI selections reconstructed
            all_sel_vals = [v for vals in loaded.selections.values() for v in vals]
            self.assertIn("ID_WOTC_PHB_SUB_RACE_HIGH_ELF", all_sel_vals)
            self.assertIn("ID_WOTC_PHB_ARCHETYPE_EVOCATION", all_sel_vals)
            self.assertIn("ID_AURORA_ASI_PLUS2_INTELLIGENCE", all_sel_vals)

            # Equipment adorner + attunement + custom name + weight fallback
            self.assertEqual(len(loaded.inventory), 1)
            inv = loaded.inventory[0]
            self.assertEqual(inv.element_id, "ID_SRD_WEAPON_LONGSWORD")
            self.assertEqual(inv.name, "Sunblade Replica")
            self.assertEqual(inv.magic_bonus, 2)
            self.assertTrue(inv.attuned)
            self.assertAlmostEqual(inv.weight, 3.0)

            # Spells resolved cross-pack with spell_sources inferred from <spellcasting name="Wizard">
            self.assertIn("ID_SRD_SPELL_FIREBALL", loaded.known_spells)
            self.assertIn("ID_SRD_SPELL_FIREBALL", loaded.prepared_spells)
            self.assertEqual(loaded.spell_sources.get("ID_SRD_SPELL_FIREBALL"), "ID_SRD_CLASS_WIZARD")

            # Library scanner also reads nested portrait & favorite from legacy files
            summaries = scan_characters_folder(p)
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].portrait_base64, "QUJD")
            self.assertEqual(summaries[0].portrait_path, "/tmp/old_portrait.png")
            self.assertTrue(summaries[0].favorite)

            # Evaluating loaded state produces expected totals (INT 15 + 1 High Elf + 2 ASI = 18)
            comp = RulesEngine(repo).evaluate(loaded)
            self.assertEqual(comp.ability_totals["intelligence"], 18)


if __name__ == "__main__":
    unittest.main()
