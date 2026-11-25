# Aurora Borealis

Cross-platform (Linux & Windows) D&D 5e / 5.5e character builder written in Python 3 + PySide6 (Qt 6).

## Features

- **Character Library**: Scans your OS standard Documents folder (`Aurora Borealis/Characters`, detected via `xdg-user-dir DOCUMENTS` on Linux or `SHGetKnownFolderPath` on Windows) for `.dnd5e`, `.dnd55e`, and `.dndcomp` files, with clickable cards, portraits, favorites, Companions filter, search, and `5e` / `5.5e` / `Companion` badges.
- **Full D&D 5.5e (2024 PHB) Rules & `.dnd55e` Format**: Supports Weapon Masteries, Heavy weapon STR/DEX 13+ checks, Divine/Primal Orders, Lv 3 standardized subclasses, Lv 19+ Epic Boons, 2024 Origin Feats, Exhaustion (0–6), Heroic Inspiration, 2024 prepared spell counts, and automatic `.dnd55e` format persistence alongside full `.dnd5e` compatibility.
- **Animal Forms & Custom Forms**: Includes ~52 Beast & Elemental Wild Shape forms with 5e/5.5e Druid & Circle of the Moon eligibility rules, transformed stat blocks, manual rule overrides, and a **Custom Animal Form** creator/editor.
- **Companions (`.dndcomp`)**: Create companions from templates (Steel Defender, Drake, Primal Companion, Familiar, Steed, Mount, Custom) with owner scaling, edit them in a standalone **Companion Sheet** view, save/load `.dndcomp` files, and export standalone Companion PDFs.
- **Manual Rule Overrides**: Centralized **Rule Overrides** dialog and inline toggles to bypass level, spell, animal form, multiclass prerequisite, mastery, heavy weapon, or companion restrictions when desired.
- **10-Tab Clickable Builder**: Overview, Race / Species, Class, Background, Abilities (`-`/`+`, Point Buy, Standard Array, 4d6 roll), Choices & Feats, Skills & Features, Equipment, Spells, and Details & Notes. New characters start blank so nothing is pre-selected.
- **Multiclassing & Prerequisites**: Combine multiple classes up to total level 20 with per-class level scoping, PHB multiclass prerequisites (with override prompt), `<multiclass>` XML rules + proficiency fallbacks, per-class Hit Dice tracking, and multi-class save/skill rules.
- **Hit Points (Average or Rolled / Manual)**: Choose between fixed average HP or per-level rolled/manual Hit Die values (`1..dX`) with per-level dice rollers and full CON modifier breakdown.
- **Class, Subclass & Multiclass Spell Logic**:
  - Filters spell catalogs by active class & subclass spell lists (including `<spellcasting extend="true">` expanded spell lists and always-prepared Domain/Oath/Circle spells).
  - Combines multiclass spell slots automatically (Full / Half / Half-Up / Third casters) and tracks Warlock Pact Magic separately.
  - Supports 1/3-caster subclasses (e.g. Eldritch Knight, Arcane Trickster) both solo and multiclassed.
- **Guided 5-Step Level-Up Wizard**: Step through **1. Class & HP**, **2. Features & Choices**, **3. ASI / Feat**, **4. Spells**, and **5. Review Before/After Diff** before applying a level up.
- **Official 5e & 5.5e PDF Export**:
  - **5e**: Fills the official 3-page D&D 5e AcroForm character sheet via `qpdf` (or `pypdf` pure-Python fallback on Windows).
  - **5.5e (2024)**: Renders a vector overlay onto the official 2-page 2024 D&D character sheet via `qpdf --overlay` (or `pypdf` pure-Python fallback).
- **Aurora Legacy & 5e.tools Content Importers**:
  - Automatically syncs official Aurora Legacy GitHub indexes (`core.index`, `supplements.index`, `unearthed-arcana.index`), skipping 3rd-party files.
  - Imports **5e.tools** JSON datasets (from GitHub or a local `data/` folder) into Aurora XML with class spell tags.
  - Detects duplicate elements across sources and prioritizes official books over SRD.
- **Standard OS Storage**:
  - **Linux**: `~/.local/share/aurora-borealis/` and `~/.config/aurora-borealis/config.json`.
  - **Windows**: `%LOCALAPPDATA%\Aurora Borealis\` and `%APPDATA%\Aurora Borealis\config.json`.

## Installing & Running on Linux

Launch the graphical **Linux Setup Wizard** (supports both **Install / Repair** and **Uninstall**, directory picker, system dependency checks, optional **Aurora Legacy** & **5e.tools** content pack download during install, desktop entry & `.dnd5e`/`.dnd55e`/`.dndcomp` file associations):

```bash
./setup-wizard-linux.sh
```

Or run the headless CLI installer directly (add `--install-aurora-legacy` and/or `--install-5etools` to pre-download content):

```bash
./install-linux.sh
```

Run directly from the repo after dependencies are installed:

```bash
./aurora-borealis
```

To install only the desktop entry & MIME associations for the current folder:

```bash
./install-desktop.sh
```

To uninstall on Linux via CLI (keeps your characters in Documents; add `--purge-config` to also clear config/caches):

```bash
./uninstall-linux.sh
```

## Installing & Running on Windows

Double-click **`setup-wizard-windows.bat`** to launch the graphical **Windows Setup Wizard** (supports both **Install / Repair** and **Uninstall**, target directory picker, optional **Aurora Legacy** & **5e.tools** content pack download during install, Desktop shortcut, `.dnd5e`/`.dnd55e`/`.dndcomp` associations, and automatic Python/7-Zip check via `winget`).

Or double-click **`install-windows.bat`** (headless PowerShell installer) / run in PowerShell (with optional `-InstallAuroraLegacy` / `-InstallFiveTools`):

```powershell
.\install-windows.ps1 -CreateDesktopShortcut -RegisterFileAssociations
```

Launch anytime via the Start Menu, Desktop shortcut, `aurora-borealis.bat`, or `.\aurora-borealis.ps1`.
To uninstall on Windows (keeps your characters), use **Settings → Apps → Aurora Borealis**, run the **Aurora Borealis Setup Wizard** from the Start Menu, or run `.\uninstall-windows.ps1` (`-PurgeConfig` optionally clears config/cache).

For a standalone `.exe` / Inno Setup Windows installer bundle (`AuroraBorealis-Setup.exe`), see `packaging/windows/build-windows-installer.ps1`.

## Optional CLI Flags

- `--sync-official` — Sync official Aurora Legacy GitHub indexes.
- `--sync-5etools` — Download & convert 5e.tools JSON data from GitHub.
- `--import-5etools-dir /path/to/5etools/data` — Convert a local 5e.tools folder.
- `--open path/to/character.dnd5e` — Open a character directly.
