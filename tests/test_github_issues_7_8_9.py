"""Self-contained regression tests for GitHub Issues #7, #8, and #9."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QApplication

from aurora_borealis.companions import CompanionAction, CompanionState, CompanionTrait, export_companion_pdf
from aurora_borealis.config import AppConfig
from aurora_borealis.engine import RulesEngine
from aurora_borealis.loader import ContentRepository
from aurora_borealis.models import CharacterState, ClassLevel, Element, GrantRule, InventoryItem
from aurora_borealis.pdf_export import (
    _compute_acroform_da,
    _fill_pdf_form_pypdf,
    _fit_text_layout,
    _helvetica_text_width,
    _wrap_helvetica_lines,
    export_character_pdf,
    fill_pdf_form_qpdf,
    format_proficiencies,
    format_proficiency_label,
)
from aurora_borealis.platform_utils import is_windows
from aurora_borealis.ui.companion_view import CompanionEditorView
from aurora_borealis.ui.level_up_wizard import LevelUpWizardDialog
from aurora_borealis.ui.main_window import MainWindow


def _populate_repo(repo: ContentRepository, elements: list[Element]) -> None:
    for el in elements:
        repo.by_id[el.id] = el
        repo.by_type[el.type].append(el)
        repo._type_by_id[el.type][el.id] = el
        repo._by_type_name[(el.type.lower(), el.name.lower())] = el
        repo._index_element_metadata(el)
    repo._sync_type_lists_and_caches()


def _build_test_repo() -> ContentRepository:
    repo = ContentRepository()
    _populate_repo(
        repo,
        [
            Element(id="ID_RACE_HUMAN", name="Human", type="Race"),
            Element(id="ID_BG_SAGE", name="Sage", type="Background"),
            Element(id="ID_ALIGN_NG", name="Neutral Good", type="Alignment"),
            Element(
                id="ID_CLASS_FTR",
                name="Fighter",
                type="Class",
                setters={"hd": "d10"},
            ),
            Element(
                id="ID_CLASS_WIZ",
                name="Wizard",
                type="Class",
                setters={"hd": "d6", "spellcastingAbility": "Intelligence", "spellcastingProgression": "Full"},
            ),
            Element(
                id="ID_PROF_STUDDED",
                name="Armor Proficiency (Studded)",
                type="Proficiency",
            ),
            Element(
                id="ID_PROF_LONGSWORD",
                name="Weapon Proficiency (Longsword)",
                type="Proficiency",
            ),
            Element(
                id="ID_PROF_THIEVES",
                name="Tool Proficiency (Thieves' Tools)",
                type="Proficiency",
            ),
            Element(
                id="ID_WPN_SUPER",
                name="Dragon-Slaying Greatsword of Unyielding Radiance",
                type="Weapon",
                supports=["Heavy", "Two-Handed", "Martial"],
                setters={"damage": "2d6 + 2d8 radiant", "damage_type": "slashing", "weight": "6 lb."},
            ),
            Element(
                id="ID_SP_LONG",
                name="Mordenkainen's Magnificent Dimensional Anchor",
                type="Spell",
                supports=["Wizard"],
                setters={"level": "1", "time": "1 action", "range": "Self (30-foot-radius sphere)"},
            ),
            Element(
                id="ID_FEAT_LONG",
                name="Extraordinarily Verbose Master Tactician of the Northern Citadel",
                type="Feat",
            ),
            Element(
                id="ID_CF_EXTRA",
                name="Tactical Mastery and Relentless Vanguard Maneuvers",
                type="Class Feature",
            ),
        ],
    )
    return repo


class GitHubIssues789Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    # ------------------------------------------------------------------
    # Issue #7: Number alignment / left padding in QSpinBox input fields
    # ------------------------------------------------------------------
    def test_issue7_spinbox_left_padding_matches_line_edit_and_keeps_steppers_centered(self) -> None:
        repo = _build_test_repo()
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
            win.state.inventory = [InventoryItem(element_id="ID_WPN_SUPER", name="Longsword", category="Weapon", quantity=3)]
            win._recalculate_and_refresh()
            win.show()
            self.app.processEvents()

            win.txt_overview_name.setCursorPosition(0)
            le_x = win.txt_overview_name.cursorRect().x()

            # Left-aligned spinboxes (XP, Currency, Exhaustion, dynamic inventory qty_spin)
            qty_spin = win.tbl_inventory.cellWidget(0, 2)
            self.assertIsNotNone(qty_spin)
            for spn in (win.spn_xp, win.spn_exhaustion, win.cur_spins["gp"], qty_spin):
                self.assertGreaterEqual(spn.lineEdit().textMargins().left(), 8)
                spn.lineEdit().setCursorPosition(0)
                spn_x = spn.lineEdit().x() + spn.lineEdit().cursorRect().x()
                self.assertLessEqual(abs(spn_x - le_x), 4, f"SpinBox {spn} text x={spn_x} vs QLineEdit x={le_x}")

            # Centered steppers must preserve 0 margins and center alignment
            for stepper in (win.spn_level, *win.ab_spinboxes.values()):
                self.assertEqual(stepper.objectName(), "StepperSpin")
                self.assertEqual(stepper.lineEdit().textMargins().left(), 0)
                self.assertTrue(bool(stepper.alignment() & Qt.AlignmentFlag.AlignHCenter))

            # LevelUpWizardDialog & CompanionEditorView spinboxes
            wiz = LevelUpWizardDialog(win.state, repo, win.engine, parent=win)
            wiz.show()
            self.app.processEvents()
            self.assertGreaterEqual(wiz.spn_hp_roll.lineEdit().textMargins().left(), 8)
            wiz.close()

            comp_view = CompanionEditorView()
            comp_view.show()
            self.app.processEvents()
            self.assertGreaterEqual(comp_view.spn_ac.lineEdit().textMargins().left(), 8)
            self.assertGreaterEqual(comp_view.spn_owner_lvl.lineEdit().textMargins().left(), 8)
            comp_view.close()

            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()

    # ------------------------------------------------------------------
    # Issue #9: Level-Up Wizard ASI +2 hides secondary ability selector
    # ------------------------------------------------------------------
    def test_issue9_level_up_wizard_hides_secondary_ability_for_plus2(self) -> None:
        repo = _build_test_repo()
        engine = RulesEngine(repo)
        state = CharacterState(
            name="Aldric",
            ruleset="5e",
            classes=[ClassLevel(class_id="ID_CLASS_FTR", level=3)],
            abilities={
                "strength": 15,
                "dexterity": 12,
                "constitution": 14,
                "intelligence": 10,
                "wisdom": 10,
                "charisma": 8,
            },
        )
        state.sync_from_classes()

        wiz = LevelUpWizardDialog(state, repo, engine)
        wiz.show()
        wiz._go_to_page(2)
        self.app.processEvents()

        self.assertTrue(wiz.rad_asi.isChecked())
        self.assertTrue(wiz.rad_asi_2.isChecked())
        self.assertTrue(wiz.asi_secondary_wrap.isHidden())
        self.assertTrue(wiz.lbl_asi_b.isHidden())
        self.assertTrue(wiz.cmb_asi_b.isHidden())
        self.assertIn("+2", wiz.lbl_asi_a.text())

        # Switching to +1 / +1 reveals secondary ability controls
        wiz.rad_asi_11.setChecked(True)
        self.app.processEvents()
        self.assertFalse(wiz.asi_secondary_wrap.isHidden())
        self.assertFalse(wiz.lbl_asi_b.isHidden())
        self.assertFalse(wiz.cmb_asi_b.isHidden())
        self.assertTrue(wiz.cmb_asi_b.isEnabled())
        self.assertIn("+1", wiz.lbl_asi_a.text())

        # Switching back to +2 hides them again
        wiz.rad_asi_2.setChecked(True)
        self.app.processEvents()
        self.assertTrue(wiz.asi_secondary_wrap.isHidden())
        self.assertTrue(wiz.lbl_asi_b.isHidden())
        self.assertTrue(wiz.cmb_asi_b.isHidden())
        wiz.close()

    # ------------------------------------------------------------------
    # Issue #8: PDF export scaling & concise proficiency labels
    # ------------------------------------------------------------------
    def test_issue8_proficiency_label_cleaning(self) -> None:
        self.assertEqual(format_proficiency_label("Armor Proficiency (Studded)"), "Studded")
        self.assertEqual(format_proficiency_label("armor proficiency (studded)"), "studded")
        self.assertEqual(format_proficiency_label("Weapon Proficiency (Simple Weapons)"), "Simple Weapons")
        self.assertEqual(format_proficiency_label("Tool Proficiency (Vehicles (Land))"), "Vehicles (Land)")
        self.assertEqual(format_proficiency_label("Shield Proficiency"), "Shield")
        self.assertEqual(format_proficiency_label("Light Armor"), "Light Armor")

        cleaned = format_proficiencies(
            [
                "Armor Proficiency (Studded)",
                "armor proficiency (studded)",
                "Weapon Proficiency (Longsword)",
                "Tool Proficiency (Thieves' Tools)",
            ]
        )
        self.assertEqual(cleaned, ["Studded", "Longsword", "Thieves' Tools"])

    def test_issue8_acroform_5e_and_companion_pdf_scale_to_fit_rects(self) -> None:
        repo = _build_test_repo()
        engine = RulesEngine(repo)
        long_features = [
            Element(
                id=f"ID_CF_{i}",
                name=f"Heroic Combat Technique {i} of the Ancient Order",
                type="Class Feature",
            )
            for i in range(1, 35)
        ]
        ftr_grants = [
            GrantRule(type="Proficiency", id="ID_PROF_STUDDED"),
            GrantRule(type="Proficiency", id="ID_PROF_LONGSWORD"),
            GrantRule(type="Proficiency", id="ID_PROF_THIEVES"),
            GrantRule(type="Feat", id="ID_FEAT_LONG"),
            *[GrantRule(type="Class Feature", id=f"ID_CF_{i}") for i in range(1, 35)],
        ]
        repo.by_id["ID_CLASS_FTR"].grant_rules.extend(ftr_grants)
        _populate_repo(repo, long_features)

        state = CharacterState(
            name="Bartholomew Maximilian von Aurelius the Undefeated",
            player_name="Lukas",
            ruleset="5e",
            race_id="ID_RACE_HUMAN",
            background_id="ID_BG_SAGE",
            alignment_id="ID_ALIGN_NG",
            classes=[ClassLevel(class_id="ID_CLASS_FTR", level=10), ClassLevel(class_id="ID_CLASS_WIZ", level=5)],
            inventory=[
                InventoryItem(
                    element_id="ID_WPN_SUPER",
                    name="Dragon-Slaying Greatsword of Unyielding Radiance",
                    category="Weapon",
                    quantity=1,
                    magic_bonus=3,
                )
            ],
            known_spells=["ID_SP_LONG"],
            backstory="\n".join(f"Chapter {i}: A very long chronicle of heroic deeds across the realm." for i in range(1, 30)),
        )
        state.sync_from_classes()
        comp = engine.evaluate(state)

        with tempfile.TemporaryDirectory() as tmp:
            p5e = Path(tmp) / "hero_5e.pdf"
            export_character_pdf(state, comp, repo, p5e)
            self.assertTrue(p5e.is_file())

            probe = subprocess.run(
                ["qpdf", "--json", "--json-key=acroform", "--json-key=qpdf", str(p5e)],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(probe.stdout)
            objs = data["qpdf"][1]

            profs_val = ""
            checked_fields: dict[str, tuple[str, float, float, bool]] = {}
            for f in data["acroform"]["fields"]:
                fn = f.get("fullname", "")
                vd = objs.get("obj:" + f.get("object", ""), {}).get("value", {})
                v = str(vd.get("/V") or "")
                if v.startswith("u:"):
                    v = v[2:]
                da = str(vd.get("/DA") or "")
                if da.startswith("u:"):
                    da = da[2:]
                rect = vd.get("/Rect")
                if fn == "ProficienciesLang":
                    profs_val = v
                if v and rect and len(rect) == 4 and da:
                    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s+Tf", da)
                    if m:
                        pt = float(m.group(1))
                        rw = abs(float(rect[2]) - float(rect[0]))
                        rh = abs(float(rect[3]) - float(rect[1]))
                        ff = int(vd.get("/Ff") or 0)
                        checked_fields[fn] = (v, pt, rw if not (ff & 4096) else rh, bool(ff & 4096))

            # Concise proficiency labels (no "Armor Proficiency (...)")
            self.assertIn("Studded", profs_val)
            self.assertNotIn("Armor Proficiency", profs_val)
            self.assertNotIn("Weapon Proficiency", profs_val)
            self.assertNotIn("Tool Proficiency", profs_val)

            # Long weapon/name/feature fields must shrink from 12pt/8pt so they fit their rects
            self.assertLess(checked_fields["Wpn Name"][1], 12.0)
            self.assertLess(checked_fields["Wpn1 Damage"][1], 12.0)
            self.assertLess(checked_fields["Features and Traits"][1], 8.0)
            self.assertLess(checked_fields["Backstory"][1], 8.0)

            for fn, (val, pt, dim, is_ml) in checked_fields.items():
                if not is_ml:
                    self.assertLessEqual(
                        _helvetica_text_width(val, pt),
                        max(4.0, dim - 2.5),
                        f"5e field {fn!r} overflowed width at {pt}pt",
                    )

            # Companion AcroForm PDF scaling
            companion = CompanionState(
                name="Sir Barnaby Featherstone the Magnificent Owl-Drake",
                companion_type="Artificer Steel Guardian",
                creature_type="Construct / Elemental",
                owner_name="Bartholomew Maximilian von Aurelius",
                owner_level=15,
                speed="40 ft., fly 60 ft. (hover)",
                traits=[
                    CompanionTrait(f"Trait {i}", "Provides tactical advantage and elemental warding within 30 feet.")
                    for i in range(1, 16)
                ],
                actions=[
                    CompanionAction(
                        "Force-Empowered Arcane Rend of Doom",
                        "Spell Attack",
                        "1d8+3 force + 2d6 radiant",
                        "Melee Weapon Attack with additional shockwave damage to adjacent enemies.",
                    )
                ],
                notes="\n".join(f"Detail note line {i} for companion chronicle." for i in range(1, 15)),
            )
            pcomp = Path(tmp) / "comp.pdf"
            export_companion_pdf(companion, pcomp)
            self.assertTrue(pcomp.is_file())

            cprobe = subprocess.run(
                ["qpdf", "--json", "--json-key=acroform", "--json-key=qpdf", str(pcomp)],
                capture_output=True,
                text=True,
                check=True,
            )
            cdata = json.loads(cprobe.stdout)
            cobjs = cdata["qpdf"][1]
            c_das: dict[str, tuple[str, float, float, float, bool]] = {}
            for f in cdata["acroform"]["fields"]:
                fn = f.get("fullname", "")
                vd = cobjs.get("obj:" + f.get("object", ""), {}).get("value", {})
                v = str(vd.get("/V") or "")
                if v.startswith("u:"):
                    v = v[2:]
                da = str(vd.get("/DA") or "")
                if da.startswith("u:"):
                    da = da[2:]
                rect = vd.get("/Rect")
                if v and rect and len(rect) == 4 and da:
                    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s+Tf", da)
                    if m:
                        ff = int(vd.get("/Ff") or 0)
                        c_das[fn] = (
                            v,
                            float(m.group(1)),
                            abs(float(rect[2]) - float(rect[0])),
                            abs(float(rect[3]) - float(rect[1])),
                            bool(ff & 4096),
                        )

            self.assertLess(c_das["Text1"][1], 14.0)
            self.assertLess(c_das["Text55.0"][1], 7.5)
            self.assertLess(c_das["Text59"][1], 7.5)
            self.assertLess(c_das["Text54"][1], 7.5)
            for fn, (val, pt, rw, rh, is_ml) in c_das.items():
                if not is_ml:
                    self.assertLessEqual(
                        _helvetica_text_width(val, pt),
                        max(4.0, rw - 2.5),
                        f"Companion field {fn!r} overflowed width at {pt}pt",
                    )
                else:
                    lines, _ = _wrap_helvetica_lines(val, pt, max(4.0, rw - 5.0))
                    self.assertLessEqual(len(lines) * pt * 1.24, max(4.0, rh - 2.0))

    def test_issue8_55e_overlay_pdf_tall_box_shrink_and_proficiencies(self) -> None:
        font_family = "Arial" if is_windows() else "Sans Serif"
        huge_block = "\n".join(f"• Feature Name {i}: Extended description text" for i in range(1, 35))
        pt, fitted = _fit_text_layout(huge_block, w=175.0, h=140.0, size=7.5, wrap=True, min_size=4.0)
        self.assertLess(pt, 4.0)
        f = QFont(font_family)
        f.setPointSizeF(pt)
        fm = QFontMetricsF(f)
        lines = fitted.split("\n")
        total_h = max(0, len(lines) - 1) * fm.lineSpacing() + fm.height()
        self.assertLessEqual(total_h, 141.0)

        repo = _build_test_repo()
        repo.by_id["ID_CLASS_FTR"].grant_rules.extend(
            [
                GrantRule(type="Proficiency", id="ID_PROF_STUDDED"),
                GrantRule(type="Feat", id="ID_FEAT_LONG"),
            ]
        )
        engine = RulesEngine(repo)
        state = CharacterState(
            name="Vaelora 2024",
            ruleset="5.5e",
            race_id="ID_RACE_HUMAN",
            background_id="ID_BG_SAGE",
            classes=[ClassLevel(class_id="ID_CLASS_FTR", level=6)],
            backstory=huge_block,
        )
        state.sync_from_classes()
        comp = engine.evaluate(state)
        with tempfile.TemporaryDirectory() as tmp:
            out_pdf = Path(tmp) / "vaelora_55e.pdf"
            export_character_pdf(state, comp, repo, out_pdf)
            self.assertTrue(out_pdf.is_file())
            self.assertTrue(out_pdf.read_bytes().startswith(b"%PDF"))

    def test_all_pdfs_scale_font_down_without_truncation_or_overflow(self) -> None:
        from PySide6.QtCore import QMarginsF, QRectF, QSizeF
        from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter

        font_family = "Arial" if is_windows() else "Sans Serif"

        # 1. 5.5e overlay layout never truncates with ellipsis and scales below 2.5pt to fit exact boundingRect
        chapters = "\n".join(
            f"Chapter {i}: A remarkably detailed chronicle of heroic deeds across the realm."
            for i in range(1, 51)
        )
        with tempfile.TemporaryDirectory() as tmp:
            probe_pdf = Path(tmp) / "probe.pdf"
            writer = QPdfWriter(str(probe_pdf))
            writer.setResolution(300)
            writer.setPageSize(QPageSize(QSizeF(612, 792), QPageSize.Unit.Point))
            writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
            dpi_s = writer.logicalDpiY() / 72.0

            pt, fitted = _fit_text_layout(
                chapters,
                w=175.8,
                h=137.3,
                size=7.5,
                wrap=True,
                device=writer,
                align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            )
            self.assertLess(pt, 2.5)
            self.assertNotIn("…", fitted)
            self.assertIn("Chapter 1:", fitted)
            self.assertIn("Chapter 50:", fitted)
            f = QFont(font_family)
            f.setPointSizeF(pt)
            fm = QFontMetricsF(f, writer)
            br = fm.boundingRect(
                QRectF(0.0, 0.0, 175.8 * dpi_s, 1e7),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                fitted,
            )
            self.assertLessEqual(br.height() / dpi_s, 137.3)
            self.assertLessEqual(br.width() / dpi_s, 175.8)

            # 2. Extreme single-line text scales below 2.5pt instead of clipping
            ultra_single = "Bartholomew Maximilian von Aurelius the Undefeated Sovereign of the Northern Wastes"
            s_pt, s_fitted = _fit_text_layout(ultra_single, w=65.0, h=14.0, size=9.0, wrap=False, device=writer)
            self.assertLess(s_pt, 2.5)
            self.assertEqual(s_fitted, ultra_single)
            sf = QFont(font_family)
            sf.setPointSizeF(s_pt)
            sfm = QFontMetricsF(sf, writer)
            self.assertLessEqual(sfm.horizontalAdvance(s_fitted) / dpi_s, 65.0)

        # 3. AcroForm /DA scales down smoothly below 1.5pt for huge text, accounts for bold & borders
        da_single = _compute_acroform_da(
            ultra_single,
            rect=[0.0, 0.0, 55.0, 14.0],
            is_multiline=False,
            base_da="/HeBo 12 Tf 0 g",
            border_w=1.0,
        )
        m_single = re.search(r"([0-9]+(?:\.[0-9]+)?)\s+Tf", da_single)
        self.assertIsNotNone(m_single)
        pt_single = float(m_single.group(1))
        self.assertLess(pt_single, 1.5)
        self.assertLessEqual(_helvetica_text_width(ultra_single, pt_single, bold=True), 50.0)

        huge_multi = "\n".join(f"Line {i}: Extended inventory and feature catalog entry." for i in range(1, 140))
        da_multi = _compute_acroform_da(
            huge_multi,
            rect=[0.0, 0.0, 120.0, 140.0],
            is_multiline=True,
            base_da="/Helv 8 Tf 0 g",
            border_w=1.0,
        )
        m_multi = re.search(r"([0-9]+(?:\.[0-9]+)?)\s+Tf", da_multi)
        self.assertIsNotNone(m_multi)
        pt_multi = float(m_multi.group(1))
        self.assertLess(pt_multi, 1.5)
        ml_lines, ml_ov = _wrap_helvetica_lines(huge_multi, pt_multi, 112.0)
        self.assertFalse(ml_ov)
        self.assertLessEqual(len(ml_lines) * pt_multi * 1.35, 134.0)

        # 4. AcroForm fill (qpdf + pypdf when installed) scales down and clears DoNotScroll
        tpl_5e = Path(__file__).resolve().parent.parent / "aurora_borealis" / "assets" / "templates" / "dnd5e_sheet.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            qpdf_out = Path(tmp) / "qpdf_5e.pdf"
            fill_pdf_form_qpdf(
                tpl_5e,
                {"Wpn Name": ultra_single, "Backstory": chapters},
                set(),
                qpdf_out,
            )
            self.assertTrue(qpdf_out.is_file())
            probe = subprocess.run(
                ["qpdf", "--json", "--json-key=acroform", "--json-key=qpdf", str(qpdf_out)],
                capture_output=True,
                text=True,
                check=True,
            )
            pdata = json.loads(probe.stdout)
            pobjs = pdata["qpdf"][1]
            qfound: dict[str, tuple[str, int]] = {}
            for f in pdata["acroform"]["fields"]:
                fn = f.get("fullname", "")
                if fn in ("Wpn Name", "Backstory"):
                    vd = pobjs.get("obj:" + f.get("object", ""), {}).get("value", {})
                    da_s = str(vd.get("/DA") or "")
                    if da_s.startswith("u:"):
                        da_s = da_s[2:]
                    qfound[fn] = (da_s, int(vd.get("/Ff") or 0))
            self.assertIn("Wpn Name", qfound)
            self.assertIn("Backstory", qfound)
            self.assertEqual(qfound["Wpn Name"][1] & (1 << 23), 0)
            self.assertEqual(qfound["Backstory"][1] & (1 << 23), 0)
            self.assertTrue(bool(qfound["Backstory"][1] & 4096))
            self.assertLess(float(re.search(r"([0-9]+(?:\.[0-9]+)?)\s+Tf", qfound["Wpn Name"][0]).group(1)), 3.0)
            self.assertLessEqual(float(re.search(r"([0-9]+(?:\.[0-9]+)?)\s+Tf", qfound["Backstory"][0]).group(1)), 4.5)

            try:
                from pypdf import PdfReader
            except ImportError:
                PdfReader = None
            if PdfReader is not None:
                pypdf_out = Path(tmp) / "pypdf_5e.pdf"
                _fill_pdf_form_pypdf(
                    tpl_5e,
                    {"Wpn Name": ultra_single, "Backstory": chapters},
                    set(),
                    pypdf_out,
                )
                self.assertTrue(pypdf_out.is_file())
                reader = PdfReader(str(pypdf_out))
                found: dict[str, tuple[str, int]] = {}
                for page in reader.pages:
                    for annot_ref in page.get("/Annots") or []:
                        annot = annot_ref.get_object()
                        name = str(annot.get("/T") or "")
                        if name in ("Wpn Name", "Backstory"):
                            found[name] = (str(annot.get("/DA") or ""), int(annot.get("/Ff") or 0))
                self.assertEqual(found["Wpn Name"][1] & (1 << 23), 0)
                self.assertEqual(found["Backstory"][1] & (1 << 23), 0)
                self.assertTrue(bool(found["Backstory"][1] & 4096))
                self.assertLess(float(re.search(r"([0-9]+(?:\.[0-9]+)?)\s+Tf", found["Wpn Name"][0]).group(1)), 3.0)
                self.assertLessEqual(float(re.search(r"([0-9]+(?:\.[0-9]+)?)\s+Tf", found["Backstory"][0]).group(1)), 4.5)


if __name__ == "__main__":
    unittest.main()
