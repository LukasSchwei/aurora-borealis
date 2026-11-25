"""Extract embedded Aurora XML element files and 5e PDF template from Aurora Setup.msi."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Optional

from lxml import etree

from .platform_utils import find_executable, is_windows, subprocess_no_window_kwargs

XML_START_RE = re.compile(rb"<\?xml[^>]*\?>\s*<elements\b")
PDF_START_RE = re.compile(rb"%PDF-1\.[0-7]")


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned or "elements"


def _extract_exe_bytes(msi_path: Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="aurora_extract_") as tmpdir:
        seven_z = find_executable("7z")
        if seven_z:
            proc = subprocess.run(
                [seven_z, "x", "-y", f"-o{tmpdir}", str(msi_path), "Aurora_Builder.exe"],
                capture_output=True,
                text=True,
                check=False,
                **subprocess_no_window_kwargs(),
            )
            exe_path = Path(tmpdir) / "Aurora_Builder.exe"
            if proc.returncode == 0 and exe_path.is_file():
                return exe_path.read_bytes()
            if not is_windows():
                raise RuntimeError(
                    f"Failed to extract Aurora_Builder.exe from {msi_path}: "
                    f"{proc.stderr.strip() or proc.stdout.strip()}"
                )

        if is_windows():
            proc = subprocess.run(
                ["msiexec", "/a", str(msi_path), "/qn", f"TARGETDIR={tmpdir}"],
                capture_output=True,
                text=True,
                check=False,
                **subprocess_no_window_kwargs(),
            )
            if proc.returncode == 0:
                for found in Path(tmpdir).rglob("Aurora_Builder.exe"):
                    if found.is_file():
                        return found.read_bytes()
            raise RuntimeError(
                f"Failed to extract Aurora_Builder.exe from {msi_path}. "
                "Install 7-Zip (7z.exe) or ensure msiexec administrative extraction succeeds."
            )

        raise RuntimeError(
            f"Failed to extract Aurora_Builder.exe from {msi_path}: 7z executable not found."
        )


def _extract_xml_from_bytes(data: bytes, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    parser = etree.XMLParser(recover=True, remove_comments=False)

    written = 0
    seen_hashes: set[bytes] = set()
    for match in XML_START_RE.finditer(data):
        start = match.start()
        end = data.find(b"</elements>", start)
        if end == -1:
            continue
        raw_xml = data[start : end + len(b"</elements>")]
        if raw_xml in seen_hashes:
            continue
        seen_hashes.add(raw_xml)

        try:
            root = etree.fromstring(raw_xml, parser=parser)
        except etree.XMLSyntaxError:
            continue
        if root is None or root.tag != "elements":
            continue

        elements = root.findall("element")
        if not elements:
            continue

        type_counts = Counter(el.get("type", "elements") for el in elements)
        dominant_type = type_counts.most_common(1)[0][0]
        written += 1
        filename = f"{written:02d}_{_slugify(dominant_type)}.xml"
        out_path = output_dir / filename
        xml_bytes = etree.tostring(
            root,
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=False,
        )
        out_path.write_bytes(xml_bytes)

    return written


def _extract_official_5e_pdf_from_bytes(data: bytes, templates_dir: Path) -> int:
    templates_dir.mkdir(parents=True, exist_ok=True)
    starts = [m.start() for m in PDF_START_RE.finditer(data)]
    saved = 0
    qpdf_exe = find_executable("qpdf")
    with tempfile.TemporaryDirectory(prefix="aurora_pdf_") as tmpdir:
        for idx, start in enumerate(starts):
            nxt = starts[idx + 1] if idx + 1 < len(starts) else len(data)
            region = data[start : min(nxt, start + 2_500_000)]
            end = region.rfind(b"%%EOF")
            if end == -1:
                continue
            chunk = region[: end + 5]
            if len(chunk) < 100_000:
                continue
            probe_path = Path(tmpdir) / f"probe_{idx}.pdf"
            probe_path.write_bytes(chunk)

            if qpdf_exe:
                proc = subprocess.run(
                    [qpdf_exe, "--json", "--json-key=acroform", "--json-key=pages", str(probe_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                    **subprocess_no_window_kwargs(),
                )
                if proc.returncode != 0:
                    continue
                try:
                    info = json.loads(proc.stdout)
                except Exception:
                    continue
                pages = info.get("pages", [])
                fields = info.get("acroform", {}).get("fields", [])
                names = {f.get("fullname", "") for f in fields}
                if len(pages) == 3 and "ClassLevel" in names and "CharacterName" in names:
                    (templates_dir / "dnd5e_sheet.pdf").write_bytes(chunk)
                    saved = 1
                    break
            else:
                matched = False
                try:
                    from pypdf import PdfReader

                    reader = PdfReader(str(probe_path))
                    fields = reader.get_fields() or {}
                    if len(reader.pages) == 3 and "ClassLevel" in fields and "CharacterName" in fields:
                        matched = True
                except Exception:
                    if b"ClassLevel" in chunk and b"CharacterName" in chunk:
                        matched = True
                if matched:
                    (templates_dir / "dnd5e_sheet.pdf").write_bytes(chunk)
                    saved = 1
                    break
    return saved


def extract_msi_elements(msi_path: Path, output_dir: Path) -> int:
    """Extract all embedded <elements> XML documents from an Aurora MSI installer."""
    msi_path = Path(msi_path)
    output_dir = Path(output_dir)
    if not msi_path.is_file():
        raise FileNotFoundError(f"MSI file not found: {msi_path}")
    data = _extract_exe_bytes(msi_path)
    return _extract_xml_from_bytes(data, output_dir)


def extract_msi_assets(
    msi_path: Path,
    elements_dir: Path,
    templates_dir: Optional[Path] = None,
) -> tuple[int, int]:
    """Extract embedded XML elements and the official 5e fillable PDF from Aurora Setup.msi."""
    msi_path = Path(msi_path)
    if not msi_path.is_file():
        raise FileNotFoundError(f"MSI file not found: {msi_path}")
    data = _extract_exe_bytes(msi_path)
    xml_count = _extract_xml_from_bytes(data, Path(elements_dir))
    pdf_count = 0
    if templates_dir is not None:
        pdf_count = _extract_official_5e_pdf_from_bytes(data, Path(templates_dir))
    return xml_count, pdf_count
