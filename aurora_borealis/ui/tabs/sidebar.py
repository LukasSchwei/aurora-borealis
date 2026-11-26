"""Left builder summary sidebar mixin."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...engine import class_display_summary
from ...models import ABILITIES, ABILITY_ABBR
from ..dialogs import pixmap_from_portrait
from ..widgets.item_icons import _fmt_mod


class SidebarMixin:
    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        self.sidebar_panel = panel
        panel.setMinimumWidth(265)
        panel.setMaximumWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 6, 10)
        layout.setSpacing(8)

        header_card = QFrame()
        header_card.setObjectName("SidebarCard")
        hc_row = QHBoxLayout(header_card)
        self.btn_rail_portrait = QPushButton("Add\nPhoto")
        self.btn_rail_portrait.setObjectName("RailPortraitBtn")
        self.btn_rail_portrait.setFixedSize(64, 64)
        self.btn_rail_portrait.clicked.connect(self._pick_character_portrait)
        self.lbl_rail_portrait = QLabel("")
        self.lbl_rail_portrait.setObjectName("PortraitFrame")
        self.lbl_rail_portrait.setFixedSize(64, 64)
        self.lbl_rail_portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_rail_portrait.hide()

        name_col = QVBoxLayout()
        self.lbl_char_name = QLabel("New Adventurer")
        self.lbl_char_name.setObjectName("CharTitle")
        self.lbl_char_name.setWordWrap(True)
        self.lbl_char_sub = QLabel("Level 1")
        self.lbl_char_sub.setObjectName("CharSubtitle")
        self.lbl_char_sub.setWordWrap(True)
        name_col.addWidget(self.lbl_char_name)
        name_col.addWidget(self.lbl_char_sub)

        hc_row.addWidget(self.btn_rail_portrait)
        hc_row.addWidget(self.lbl_rail_portrait)
        hc_row.addLayout(name_col, 1)
        layout.addWidget(header_card)

        combat_card = QFrame()
        combat_card.setObjectName("SidebarCard")
        grid = QGridLayout(combat_card)
        self.stat_labels: dict[str, QLabel] = {}
        stat_defs = [
            ("hp", "Max HP", 0, 0),
            ("ac", "Armor Class", 0, 1),
            ("init", "Initiative", 1, 0),
            ("speed", "Speed", 1, 1),
            ("prof", "Proficiency", 2, 0),
            ("pp", "Passive Perc.", 2, 1),
        ]
        for key, title, r, c in stat_defs:
            box = QVBoxLayout()
            val_lbl = QLabel("0")
            val_lbl.setObjectName("StatValue")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt_lbl = QLabel(title)
            txt_lbl.setObjectName("StatLabel")
            txt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(val_lbl)
            box.addWidget(txt_lbl)
            grid.addLayout(box, r, c)
            self.stat_labels[key] = val_lbl
        layout.addWidget(combat_card)

        ab_card = QFrame()
        ab_card.setObjectName("SidebarCard")
        ab_grid = QGridLayout(ab_card)
        self.sidebar_ab_labels: dict[str, QLabel] = {}
        for idx, ab in enumerate(ABILITIES):
            r, c = divmod(idx, 2)
            box = QVBoxLayout()
            name_lbl = QLabel(ABILITY_ABBR[ab])
            name_lbl.setObjectName("StatLabel")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl = QLabel("10 (+0)")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setStyleSheet("font-weight:bold;")
            box.addWidget(name_lbl)
            box.addWidget(val_lbl)
            ab_grid.addLayout(box, r, c)
            self.sidebar_ab_labels[ab] = val_lbl
        layout.addWidget(ab_card)

        self.spell_rail_card = QFrame()
        self.spell_rail_card.setObjectName("SidebarCard")
        sp_l = QVBoxLayout(self.spell_rail_card)
        self.lbl_rail_spell_title = QLabel("Spellcasting")
        self.lbl_rail_spell_title.setObjectName("AccentText")
        self.lbl_rail_spell_body = QLabel("None")
        self.lbl_rail_spell_body.setWordWrap(True)
        self.lbl_rail_spell_body.setObjectName("MutedText")
        sp_l.addWidget(self.lbl_rail_spell_title)
        sp_l.addWidget(self.lbl_rail_spell_body)
        layout.addWidget(self.spell_rail_card)

        layout.addStretch()
        return panel

    def _sync_sidebar(self) -> None:
        race_el = self.repo.get(self.state.race_id)
        cls_summary = class_display_summary(self.state, self.repo)
        sub_parts = [f"Lv {self.state.level}" if not cls_summary else "", race_el.name if race_el else "", cls_summary]
        sub = " ".join(p for p in sub_parts if p).strip() or f"Lv {self.state.level}"
        self.lbl_char_name.setText(self.state.name or "New Adventurer")
        self.lbl_char_sub.setText(sub)
        self.lbl_top_name.setText(self.state.name or "New Adventurer")
        self.lbl_top_sub.setText(sub)
        self.lbl_top_ruleset.setText(self.state.ruleset or "5e")

        pix = pixmap_from_portrait(self.state.portrait_base64, self.state.portrait_path, size=64)
        if pix:
            self.lbl_rail_portrait.setPixmap(pix)
            self.lbl_rail_portrait.show()
            self.btn_rail_portrait.hide()
        else:
            self.lbl_rail_portrait.hide()
            self.btn_rail_portrait.show()

        c = self.computed
        self.stat_labels["hp"].setText(str(c.max_hp))
        self.stat_labels["ac"].setText(str(c.armor_class))
        self.stat_labels["init"].setText(_fmt_mod(c.initiative))
        self.stat_labels["speed"].setText(f"{c.speed} ft")
        if len(c.speeds) > 1:
            self.stat_labels["speed"].setToolTip(
                " | ".join(f"{k.capitalize()}: {v} ft" for k, v in c.speeds.items())
            )
        else:
            self.stat_labels["speed"].setToolTip("")
        self.stat_labels["prof"].setText(f"+{c.proficiency_bonus}")
        self.stat_labels["pp"].setText(str(c.passive_perception))
        self.stat_labels["pp"].setToolTip(
            f"Perc {c.passive_perception} | Inv {c.passive_investigation} | Ins {c.passive_insight}"
        )

        for ab in ABILITIES:
            tot = c.ability_totals[ab]
            mod = _fmt_mod(c.ability_modifiers[ab])
            self.sidebar_ab_labels[ab].setText(f"{tot} ({mod})")

        if c.spellcasting:
            sc = c.spellcasting
            slots_txt = ", ".join(f"L{k}:{v}" for k, v in sorted(sc.slots.items())) or "Cantrips"
            if sc.pact_slots and sc.slots != sc.pact_slots:
                pact_txt = ", ".join(f"L{k}:{v}" for k, v in sorted(sc.pact_slots.items()))
                slots_txt = f"{slots_txt} | Pact {pact_txt}"
            if len(sc.casters) > 1:
                ab_lbl = "/".join(ABILITY_ABBR.get(x.ability.lower(), x.ability[:3].upper()) for x in sc.casters)
                dc_lbl = "/".join(str(x.save_dc) for x in sc.casters)
                atk_lbl = "/".join(_fmt_mod(x.attack_bonus) for x in sc.casters)
            else:
                ab_lbl = sc.ability[:3].upper()
                dc_lbl = str(sc.save_dc)
                atk_lbl = _fmt_mod(sc.attack_bonus)
            self.lbl_rail_spell_title.setText(f"Spellcasting ({ab_lbl})")
            self.lbl_rail_spell_body.setText(
                f"Save DC: {dc_lbl}  •  Attack: {atk_lbl}\nSlots: {slots_txt}"
            )
            self.spell_rail_card.show()
        else:
            self.spell_rail_card.hide()
