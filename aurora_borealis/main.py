"""Entrypoint for Aurora Borealis."""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config import load_config, save_config
from .extractor import extract_msi_assets
from .fivetools_importer import import_5etools_directory, import_5etools_from_github
from .github_importer import install_official_aurora_content
from .loader import ContentRepository
from .paths import get_config_path, get_custom_dir, get_elements_dir, get_templates_dir
from .platform_utils import configure_windows_app_id, is_windows
from .ui.main_window import MainWindow
from .ui.ui_helpers import install_global_wheel_filter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MSI_PATH = PROJECT_ROOT / "Aurora Setup.msi"
BUNDLED_TEMPLATES_DIR = Path(__file__).resolve().parent / "assets" / "templates"


def ensure_bundled_templates(templates_dir: Path) -> int:
    """Copy bundled PDF templates into user templates_dir if not already present."""
    templates_dir = Path(templates_dir)
    if not BUNDLED_TEMPLATES_DIR.is_dir():
        return 0
    templates_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in sorted(BUNDLED_TEMPLATES_DIR.glob("*.pdf")):
        dst = templates_dir / src.name
        if not dst.is_file():
            shutil.copy2(src, dst)
            copied += 1
    return copied


def ensure_elements_extracted(
    elements_dir: Path,
    templates_dir: Path,
    msi_path: Path,
) -> int:
    ensure_bundled_templates(templates_dir)
    xml_files = list(elements_dir.glob("*.xml")) if elements_dir.is_dir() else []
    if xml_files and (templates_dir / "dnd5e_sheet.pdf").is_file():
        return len(xml_files)
    if msi_path.is_file():
        xml_count, _pdf_count = extract_msi_assets(msi_path, elements_dir, templates_dir)
        return xml_count
    return len(xml_files)


def main(argv: Optional[list[str]] = None) -> int:
    configure_windows_app_id()
    parser = argparse.ArgumentParser(
        description="Aurora Borealis — Cross-Platform (Linux & Windows) D&D 5e / 5.5e Character Builder"
    )
    parser.add_argument(
        "--extract-msi",
        nargs="?",
        const=str(DEFAULT_MSI_PATH),
        metavar="MSI_PATH",
        help="Extract embedded XML data and 5e PDF template from Aurora Setup.msi and exit",
    )
    parser.add_argument(
        "--sync-official",
        action="store_true",
        help="Download official Aurora Legacy GitHub indexes (excluding 3rd-party) and exit",
    )
    parser.add_argument(
        "--sync-5etools",
        action="store_true",
        help="Download and convert 5e.tools JSON data from GitHub and exit",
    )
    parser.add_argument(
        "--import-5etools-dir",
        metavar="DIR",
        help="Convert a local 5e.tools data/ directory into Aurora XMLs and exit",
    )
    parser.add_argument(
        "--no-auto-import",
        action="store_true",
        help="Disable automatic background sync of official Aurora Legacy GitHub content",
    )
    parser.add_argument("--open", metavar="FILE", help="Open a .dnd5e character file on startup")
    parser.add_argument(
        "--data-dir",
        default=str(get_elements_dir()),
        help="Directory for Aurora XML elements",
    )
    args = parser.parse_args(argv)

    elements_dir = Path(args.data_dir)
    custom_dir = get_custom_dir()
    templates_dir = get_templates_dir()
    config_path = get_config_path()
    msi_path = Path(args.extract_msi) if args.extract_msi else DEFAULT_MSI_PATH

    if args.extract_msi is not None:
        xml_count, pdf_count = extract_msi_assets(msi_path, elements_dir, templates_dir)
        print(f"Extracted {xml_count} XML files and {pdf_count} PDF template(s) to {elements_dir.parent}")
        return 0

    cfg = load_config(config_path)

    if args.sync_official:
        records = install_official_aurora_content(custom_dir, progress_cb=print)
        by_slug = {r.get("slug", ""): r for r in cfg.installed_indexes}
        for rec in records:
            by_slug[rec.slug] = asdict(rec)
        cfg.installed_indexes = list(by_slug.values())
        cfg.auto_imported_official = True
        save_config(cfg, config_path)
        print(f"Synced {len(records)} official Aurora Legacy indexes into {custom_dir}")
        return 0

    if args.sync_5etools:
        rec = import_5etools_from_github(custom_dir, progress_cb=print)
        by_slug = {r.get("slug", ""): r for r in cfg.installed_indexes}
        by_slug[rec.slug] = asdict(rec)
        cfg.installed_indexes = list(by_slug.values())
        save_config(cfg, config_path)
        print(f"Imported 5e.tools data ({rec.file_count} XML files) into {custom_dir}")
        return 0

    if args.import_5etools_dir:
        rec = import_5etools_directory(Path(args.import_5etools_dir), custom_dir, progress_cb=print)
        by_slug = {r.get("slug", ""): r for r in cfg.installed_indexes}
        by_slug[rec.slug] = asdict(rec)
        cfg.installed_indexes = list(by_slug.values())
        save_config(cfg, config_path)
        print(f"Imported local 5e.tools data ({rec.file_count} XML files) into {custom_dir}")
        return 0

    ensure_elements_extracted(elements_dir, templates_dir, DEFAULT_MSI_PATH)

    repo = ContentRepository()
    repo.load_directory(elements_dir)
    if custom_dir.is_dir():
        repo.load_directory(custom_dir)
    for cdir in cfg.custom_dirs:
        repo.load_directory(Path(cdir))

    app = QApplication.instance() or QApplication(sys.argv)
    if is_windows():
        app.setStyle("Fusion")
    install_global_wheel_filter(app)
    app.setApplicationName("Aurora Borealis")
    assets_dir = Path(__file__).resolve().parent / "assets"
    icon_path = assets_dir / ("aurora-borealis.ico" if is_windows() else "aurora-borealis.svg")
    if not icon_path.is_file():
        icon_path = assets_dir / "aurora-borealis.svg"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    win = MainWindow(
        repo=repo,
        data_dir=elements_dir,
        msi_path=DEFAULT_MSI_PATH if DEFAULT_MSI_PATH.is_file() else None,
        initial_file=Path(args.open) if args.open else None,
        custom_dir=custom_dir,
        templates_dir=templates_dir,
        config=cfg,
        config_path=config_path,
        auto_sync=not args.no_auto_import,
    )
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
