# Aurora Borealis

Native Linux D&D 5e / 5.5e character builder written in Python 3 + PySide6 (Qt 6).

## Features

- **Character Library**: Scans your OS standard Documents folder (`Aurora Borealis/Characters`, detected via `xdg-user-dir DOCUMENTS` / `XDG_DOCUMENTS_DIR`) for `.dnd5e` files, with clickable cards, portraits, favorites, search, and `5e` / `5.5e` badges.
- **10-Tab Clickable Builder**: Overview, Race / Species, Class, Background, Abilities (`-`/`+`, Point Buy, Standard Array, 4d6 roll), Choices & Feats, Skills & Features, Equipment, Spells, and Details & Notes. New characters start blank so nothing is pre-selected.
- **Official 5e & 5.5e PDF Export**:
  - **5e**: Fills the official 3-page D&D 5e AcroForm character sheet via `qpdf`.
  - **5.5e (2024)**: Renders a vector overlay onto the official 2-page 2024 D&D character sheet via `qpdf --overlay`.
- **Aurora Legacy & 5e.tools Content Importers**:
  - Automatically syncs official Aurora Legacy GitHub indexes (`core.index`, `supplements.index`, `unearthed-arcana.index`), skipping 3rd-party files.
  - Imports **5e.tools** JSON datasets (from GitHub or a local `data/` folder) into Aurora XML.
  - Detects duplicate elements across sources and prioritizes official books over SRD.
- **Standard Linux Storage**: Extracted SRD XMLs, custom/5e.tools XMLs, and PDF templates are stored in `~/.local/share/aurora-borealis/`, and settings in `~/.config/aurora-borealis/config.json`.

## Running

```bash
./aurora-borealis
```

Optional CLI flags:
- `./aurora-borealis --sync-official` — Sync official Aurora Legacy GitHub indexes.
- `./aurora-borealis --sync-5etools` — Download & convert 5e.tools JSON data from GitHub.
- `./aurora-borealis --import-5etools-dir /path/to/5etools/data` — Convert a local 5e.tools folder.
- `./aurora-borealis --open path/to/character.dnd5e` — Open a character directly.

To install a desktop menu launcher (`~/.local/share/applications/aurora-borealis.desktop`):

```bash
./install-desktop.sh
```
