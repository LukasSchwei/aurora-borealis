<p align="center">
  <img src="aurora_borealis/assets/aurora-borealis-banner.png" alt="Aurora Borealis" width="640" />
</p>

# Aurora Borealis

Cross-platform (**Linux & Windows**) **D&D 5e (2014) & D&D 5.5e (2024)** character and companion builder written in Python 3 + PySide6 (Qt 6).

---

## Features

- **Character & Companion Library**: Scans your OS standard Documents folder (`Aurora Borealis/Characters`, detected via `xdg-user-dir DOCUMENTS` on Linux or `SHGetKnownFolderPath` on Windows) for `.dnd5e`, `.dnd55e`, and `.dndcomp` files, featuring portrait cards, favorites, Companions filter, search, and `5e` / `5.5e` / `Companion` badges.
- **Full D&D 5.5e (2024 PHB) Rules & `.dnd55e` Format**: Supports Weapon Masteries, Heavy weapon STR/DEX 13+ checks, Divine/Primal Orders, Level 3 standardized subclasses, Level 19+ Epic Boons, 2024 Origin Feats, Exhaustion (0–6), Heroic Inspiration, 2024 prepared spell counts, and automatic `.dnd55e` persistence alongside `.dnd5e`.
- **Backwards Compatibility with Legacy Aurora Builder Files**: Opens original Aurora Builder `.dnd5e` character sheets (including `registered`-only elements, cross-pack ID resolution, multiclass `rndhp`, `<display-properties><portrait>`, `<build><appearance>`, equipment adorners, legacy roleplay notes, and XML `<append id="...">` extensions).
- **Proficiency Filters for Equipment & Spells**:
  - **Equipment Catalog**: Filter by *All Proficiency*, *Proficient Only*, *Proficient & General Gear*, or *Not Proficient* (including inside the *Magic / Infused Armor & Weapons* dialog), alongside type, category, and rarity filters.
  - **Spell Catalog**: Filter by *All Availability*, *Proficient / Castable Only*, *Class List (Any Level)*, or *Not Castable*, alongside class, level, school, and Ritual/Concentration filters.
- **Magic / Infused Gear & Attunement Rules**: Create `+1`/`+2`/`+3` magic or Artificer-infused armor, shields, and weapons and enforce standard attunement limits (3 items, scaling up to 6 for high-level Artificers, with manual toggle).
- **Animal Forms & Custom Forms**: ~52 Beast & Elemental Wild Shape forms with 5e/5.5e Druid & Circle of the Moon eligibility rules, transformed stat blocks, manual rule overrides, and a **Custom Animal Form** creator/editor.
- **Companions (`.dndcomp`) & Companion Sheet PDFs**: Create companions from templates (Steel Defender, Drake, Primal Companion, Familiar, Steed, Mount, Custom) with owner scaling, edit them in the standalone **Companion Sheet** view, save `.dndcomp` files, and export official AcroForm Companion PDFs.
- **10-Tab Clickable Builder**: Overview, Race / Species, Class, Background, Abilities (`-`/`+`, Point Buy, Standard Array, 4d6 roll), Choices & Feats, Skills & Features, Equipment, Spells, and Details & Notes. New characters start blank so nothing is pre-selected.
- **Multiclassing, Rolled HP & Spellcasting**: Combine classes up to level 20 with PHB prerequisites (and manual override), per-level Average or Rolled HP tracking, combined multiclass spell slots, Warlock Pact Magic, and 1/3-caster subclasses (Eldritch Knight, Arcane Trickster).
- **Guided 5-Step Level-Up Wizard**: Step through **1. Class & HP**, **2. Features & Choices**, **3. ASI / Feat**, **4. Spells** (with spell swapping), and **5. Review Before/After Diff** before applying a level up.
- **Manual Rule Overrides, Themes & UI Scaling**: Centralized **Rule Overrides** dialog, Dark/Light theme toggle, and 5 named UI zoom stages (`80%` – `120%`).
- **Official 5e, 5.5e & Companion PDF Export**:
  - **5e**: Fills the bundled 3-page D&D 5e AcroForm character sheet via `qpdf` (or `pypdf` pure-Python fallback).
  - **5.5e (2024)**: Renders a vector overlay onto the bundled 2-page 2024 D&D character sheet via `qpdf --overlay` (or `pypdf` fallback).
  - **Companion**: Fills the bundled AcroForm `companion_sheet.pdf`.
- **Aurora Legacy & 5e.tools Content Importers**: Syncs official Aurora Legacy GitHub indexes (`core.index`, `supplements.index`, `unearthed-arcana.index`, excluding 3rd-party files) and converts **5e.tools** JSON datasets (from GitHub or a local `data/` folder) into Aurora XML with duplicate detection and source priority.

---

## Requirements

- **Python** `3.10+`
- **Python packages** (installed automatically by the setup wizards / `pyproject.toml`):
  - `PySide6 >= 6.5`
  - `lxml >= 4.9`
  - `pypdf >= 4.0`
- **Optional system tools**:
  - `qpdf` (faster native AcroForm/overlay PDF export on Linux; `pypdf` fallback works without it)
  - `7z` (extracting embedded data from an existing `Aurora Setup.msi` if desired)

---

## Installing & Running on Linux

Launch the graphical **Linux Setup Wizard** (supports **Install / Repair** and **Uninstall**, directory picker, system dependency checks, optional **Aurora Legacy** & **5e.tools** content pack download during setup, desktop entry & `.dnd5e`/`.dnd55e`/`.dndcomp` file associations):

```bash
./setup-wizard-linux.sh
```

Or run the headless CLI installer directly (add `--install-aurora-legacy` and/or `--install-5etools` to pre-download content):

```bash
./installer/install-linux.sh
```

Run directly from the repository:

```bash
./aurora-borealis
```

Install only the desktop entry & MIME associations for the current folder:

```bash
./installer/install-linux.sh --desktop-only
```

Uninstall via CLI (keeps your saved characters in Documents; add `--purge-config` to also remove config and caches):

```bash
./installer/uninstall-linux.sh
```

---

## Installing & Running on Windows

Double-click **`setup-wizard-windows.bat`** to launch the graphical **Windows Setup Wizard** (supports **Install / Repair** and **Uninstall**, target directory picker, optional **Aurora Legacy** & **5e.tools** content pack download, Desktop shortcut, `.dnd5e`/`.dnd55e`/`.dndcomp` file associations, and automatic Python/7-Zip check via `winget`).

Or run the PowerShell installer directly (with optional `-InstallAuroraLegacy` / `-InstallFiveTools`):

```powershell
.\installer\install-windows.ps1 -CreateDesktopShortcut -RegisterFileAssociations
```

Launch anytime via the Start Menu, Desktop shortcut, or `aurora-borealis.bat`.
To uninstall on Windows (keeps your saved characters in Documents), use **Settings → Apps → Aurora Borealis**, run **Aurora Borealis Setup Wizard** from the Start Menu, or run `.\installer\uninstall-windows.ps1` (`-PurgeConfig` optionally clears config/cache).

---

## Optional CLI Flags & Shortcuts

- `--sync-official` — Sync official Aurora Legacy GitHub indexes and exit.
- `--sync-5etools` — Download & convert 5e.tools JSON data from GitHub and exit.
- `--import-5etools-dir /path/to/5etools/data` — Convert a local 5e.tools `data/` folder and exit.
- `--extract-msi [MSI_PATH]` — Extract XML data and the 5e PDF template from `Aurora Setup.msi` and exit.
- `--no-auto-import` — Disable automatic background sync of official Aurora Legacy content on startup.
- `--open path/to/character.dnd5e` — Open a `.dnd5e`, `.dnd55e`, or `.dndcomp` file directly on startup.

**Keyboard shortcuts:** `Ctrl+N` (New Character), `Ctrl+O` (Open), `Ctrl+S` (Save), `Ctrl+Shift+S` (Save As), `Ctrl+P` (Export PDF).

---

## Data & Configuration Paths

- **Linux**: `~/.local/share/aurora-borealis/` and `~/.config/aurora-borealis/config.json`
- **Windows**: `%LOCALAPPDATA%\Aurora Borealis\` and `%APPDATA%\Aurora Borealis\config.json`
- **Characters**: `<OS Documents>/Aurora Borealis/Characters/`

---

## Running Tests

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest \
  tests/test_github_issues_4_5_6.py \
  tests/test_ui_and_rule_bugfixes.py \
  tests/test_55e_spells_forms_companions_perf.py \
  tests/test_multiclass_hp_spells_levelup_windows.py \
  tests/test_github_and_library.py -v
```
