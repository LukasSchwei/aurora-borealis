"""Self-contained regression tests for v0.2.1 patch fixes."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QPushButton

from aurora_borealis.config import AppConfig
from aurora_borealis.engine import RulesEngine
from aurora_borealis.loader import ContentRepository, evaluate_boolean_expr
from aurora_borealis.models import CharacterState, Element, SelectRule
from aurora_borealis.ui.character_select import CharacterSelectView
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


class Patch021Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def _build_repo(self) -> ContentRepository:
        repo = ContentRepository()
        _populate_repo(
            repo,
            [
                Element(
                    id="ID_INTERNAL_RACIAL_TRAIT_SMALL",
                    name="Small",
                    type="Racial Trait",
                    source="Internal",
                ),
                Element(
                    id="ID_INTERNAL_RACIAL_TRAIT_MEDIUM",
                    name="Medium",
                    type="Racial Trait",
                    source="Internal",
                ),
                Element(
                    id="ID_INTERNAL_RACIAL_TRAIT_LARGE",
                    name="Large",
                    type="Racial Trait",
                    source="Internal",
                ),
                Element(
                    id="ID_CUSTOM_TRAIT_A",
                    name="Extraordinarily Long Custom Racial Trait Name That Would Stretch Non-Expanding Combos",
                    type="Racial Trait",
                    supports=["CustomLongOptions"],
                ),
                Element(
                    id="ID_CUSTOM_TRAIT_B",
                    name="Another Super Long Heritage Option From Imported Supplement XML",
                    type="Racial Trait",
                    supports=["CustomLongOptions"],
                ),
                Element(
                    id="ID_RACE_HUMAN_2024",
                    name="Human (2024)",
                    type="Race",
                    source="Player's Handbook 2024",
                    select_rules=[
                        SelectRule(
                            type="Racial Trait",
                            name="Size (Human)",
                            number=1,
                            level=1,
                            supports="ID_INTERNAL_RACIAL_TRAIT_SMALL|ID_INTERNAL_RACIAL_TRAIT_MEDIUM",
                        )
                    ],
                ),
                Element(
                    id="ID_RACE_LONG_NAME",
                    name="Hobgoblin of the Astral Feywild Enclave (Expanded Custom Edition)",
                    type="Race",
                    source="Custom Homebrew XML",
                    select_rules=[
                        SelectRule(
                            type="Racial Trait",
                            name="Size (Custom)",
                            number=1,
                            level=1,
                            supports="ID_INTERNAL_RACIAL_TRAIT_SMALL|ID_INTERNAL_RACIAL_TRAIT_MEDIUM",
                        ),
                        SelectRule(
                            type="Racial Trait",
                            name="Ancestral Gift",
                            number=1,
                            level=1,
                            supports="CustomLongOptions",
                        ),
                    ],
                ),
                Element(
                    id="ID_CLS_FTR",
                    name="Fighter",
                    type="Class",
                    setters={"hd": "d10"},
                ),
            ],
        )
        return repo

    def test_single_pipe_and_ampersand_boolean_expr_size_selection(self) -> None:
        tokens_small = {"id_internal_racial_trait_small"}
        tokens_medium = {"id_internal_racial_trait_medium"}
        tokens_large = {"id_internal_racial_trait_large"}
        expr = "ID_INTERNAL_RACIAL_TRAIT_SMALL|ID_INTERNAL_RACIAL_TRAIT_MEDIUM"

        self.assertTrue(evaluate_boolean_expr(expr, lambda t: t.lower() in tokens_small))
        self.assertTrue(evaluate_boolean_expr(expr, lambda t: t.lower() in tokens_medium))
        self.assertFalse(evaluate_boolean_expr(expr, lambda t: t.lower() in tokens_large))

        and_expr = "ID_A&ID_B"
        self.assertTrue(evaluate_boolean_expr(and_expr, lambda t: t in ("ID_A", "ID_B")))
        self.assertFalse(evaluate_boolean_expr(and_expr, lambda t: t == "ID_A"))

        repo = self._build_repo()
        matches = repo.find_matching("Racial Trait", expr)
        self.assertEqual(sorted(el.name for el in matches), ["Medium", "Small"])

        engine = RulesEngine(repo)
        st = CharacterState(name="Aria", race_id="ID_RACE_HUMAN_2024")
        comp = engine.evaluate(st)
        size_sels = [s for s in comp.active_selections if "Size" in s.rule.name]
        self.assertEqual(len(size_sels), 1)
        self.assertEqual(sorted(name for _oid, name in size_sels[0].options), ["Medium", "Small"])

    def test_selecting_race_does_not_resize_window(self) -> None:
        repo = self._build_repo()
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
            win.show_builder()
            win._switch_builder_tab(1)
            win.show()
            self.app.processEvents()

            for start_size in (QSize(1520, 940), QSize(1700, 1000)):
                win.resize(start_size)
                self.app.processEvents()
                initial = QSize(win.size())
                initial_mh = QSize(win.minimumSizeHint())

                win.tab_race._on_select_id("ID_RACE_HUMAN_2024")
                self.app.processEvents()
                self.assertEqual(win.size(), initial)
                self.assertEqual(win.minimumSizeHint(), initial_mh)
                self.assertLessEqual(win.tab_race.minimumSizeHint().width(), 600)

                win.tab_race._on_select_id("ID_RACE_LONG_NAME")
                self.app.processEvents()
                self.assertEqual(win.size(), initial)
                self.assertEqual(win.minimumSizeHint(), initial_mh)
                self.assertLessEqual(win.tab_race.minimumSizeHint().width(), 600)

            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()

    def test_pointing_hand_cursor_on_buttons(self) -> None:
        repo = self._build_repo()
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
            self.app.processEvents()

            for btn in win.findChildren(QPushButton):
                expected = (
                    Qt.CursorShape.PointingHandCursor
                    if btn.isEnabled()
                    else Qt.CursorShape.ArrowCursor
                )
                self.assertEqual(
                    btn.cursor().shape(),
                    expected,
                    f"Button {btn.objectName() or btn.text()!r} has cursor {btn.cursor().shape()}",
                )

            # Disabled transition switches cursor to ArrowCursor, re-enabling restores PointingHandCursor
            win.btn_level_up.setEnabled(False)
            self.app.processEvents()
            self.assertEqual(win.btn_level_up.cursor().shape(), Qt.CursorShape.ArrowCursor)
            win.btn_level_up.setEnabled(True)
            self.app.processEvents()
            self.assertEqual(win.btn_level_up.cursor().shape(), Qt.CursorShape.PointingHandCursor)

            wiz = LevelUpWizardDialog(win.state, repo, win.engine, parent=win)
            wiz.show()
            self.app.processEvents()
            for btn in wiz.findChildren(QPushButton):
                if btn.isEnabled():
                    self.assertEqual(btn.cursor().shape(), Qt.CursorShape.PointingHandCursor)
            wiz.close()

            comp_view = CompanionEditorView()
            comp_view.show()
            self.app.processEvents()
            for btn in comp_view.findChildren(QPushButton):
                if btn.isEnabled():
                    self.assertEqual(btn.cursor().shape(), Qt.CursorShape.PointingHandCursor)
            comp_view.close()

            sel_view = CharacterSelectView()
            sel_view.show()
            self.app.processEvents()
            for btn in sel_view.findChildren(QPushButton):
                if btn.isEnabled():
                    self.assertEqual(btn.cursor().shape(), Qt.CursorShape.PointingHandCursor)
            sel_view.close()

            win._dirty = False
            win.current_file = p / "dummy.dnd5e"
            win.close()


if __name__ == "__main__":
    unittest.main()
