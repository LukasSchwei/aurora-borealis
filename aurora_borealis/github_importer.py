"""Original-Aurora-compatible GitHub .index and .xml content importer."""

from __future__ import annotations

import re
import shutil
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from lxml import etree

_GITHUB_BLOB_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$",
    re.IGNORECASE,
)

OFFICIAL_AURORA_INDEXES: list[tuple[str, str]] = [
    (
        "Aurora Legacy — Core",
        "https://raw.githubusercontent.com/AuroraLegacy/elements/master/core.index",
    ),
    (
        "Aurora Legacy — Supplements",
        "https://raw.githubusercontent.com/AuroraLegacy/elements/master/supplements.index",
    ),
    (
        "Aurora Legacy — Unearthed Arcana",
        "https://raw.githubusercontent.com/AuroraLegacy/elements/master/unearthed-arcana.index",
    ),
]

_THIRD_PARTY_MARKERS = ("third-party", "3rd-party", "thirdparty", "collaborations")


def is_third_party_path(name_or_url: str) -> bool:
    low = (name_or_url or "").lower()
    return any(marker in low for marker in _THIRD_PARTY_MARKERS)


@dataclass
class IndexRecord:
    slug: str
    name: str
    url: str
    version: str
    author: str
    description: str
    local_dir: str
    file_count: int
    updated_at: str


def normalize_github_url(url: str) -> str:
    """Convert github.com/owner/repo/blob/ref/path URLs to raw.githubusercontent.com."""
    cleaned = (url or "").strip()
    m = _GITHUB_BLOB_RE.match(cleaned)
    if m:
        owner, repo, ref, rel_path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{rel_path}"
    return cleaned


def fetch_url_bytes(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Aurora-Borealis/0.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "custom_content"


def _safe_rel_path(raw_name: str, fallback_url: str, root_base_url: str = "") -> Path:
    parsed_url = urllib.parse.urlparse(fallback_url)
    candidate = ""
    if root_base_url:
        parsed_base = urllib.parse.urlparse(root_base_url)
        if parsed_url.netloc == parsed_base.netloc and parsed_url.path.startswith(parsed_base.path):
            candidate = parsed_url.path[len(parsed_base.path) :].lstrip("/")

    if not candidate:
        candidate = (raw_name or "").strip().replace("\\", "/")
    if not candidate:
        candidate = Path(parsed_url.path).name or "elements.xml"

    parts: list[str] = []
    for raw_part in candidate.replace("\\", "/").split("/"):
        cleaned = re.sub(r'[<>:"|?*]', "_", raw_part).strip()
        if cleaned in ("", ".", ".."):
            continue
        if len(cleaned) == 2 and cleaned[1] == ":":
            continue
        parts.append(cleaned)
    if not parts:
        parts = ["elements.xml"]
    rel = Path(*parts)
    if rel.suffix.lower() != ".xml":
        rel = rel.with_suffix(".xml")
    return rel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def install_from_url(
    url: str,
    custom_root: Path,
    progress_cb: Optional[Callable[[str], None]] = None,
    fetcher: Callable[[str], bytes] = fetch_url_bytes,
    exclude_third_party: bool = True,
) -> IndexRecord:
    """Install an Aurora .index or direct .xml file from a URL into custom_root."""
    norm_url = normalize_github_url(url)
    if not norm_url:
        raise ValueError("URL must not be empty")

    custom_root = Path(custom_root)
    custom_root.mkdir(parents=True, exist_ok=True)
    parser = etree.XMLParser(recover=True, remove_comments=True)

    if progress_cb:
        progress_cb(f"Fetching {norm_url}...")
    root_bytes = fetcher(norm_url)
    try:
        root = etree.fromstring(root_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Invalid XML returned from {norm_url}: {exc}") from exc

    if root is None:
        raise ValueError(f"Empty or unreadable XML from {norm_url}")

    tag = (root.tag or "").lower()
    if tag == "elements":
        direct_dir = custom_root / "direct"
        direct_dir.mkdir(parents=True, exist_ok=True)
        parsed = urllib.parse.urlparse(norm_url)
        fname = _safe_rel_path(Path(parsed.path).name, norm_url).name
        dest = direct_dir / fname
        dest.write_bytes(
            etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=False)
        )
        if progress_cb:
            progress_cb(f"Installed direct XML file {fname}")
        return IndexRecord(
            slug=f"direct_{_slugify(Path(fname).stem)}",
            name=Path(fname).stem,
            url=norm_url,
            version="1.0",
            author="",
            description=f"Direct XML from {norm_url}",
            local_dir=str(dest),
            file_count=1,
            updated_at=_now_iso(),
        )

    if tag != "index":
        raise ValueError(f"Unsupported Aurora XML root <{root.tag}>; expected <index> or <elements>")

    info = root.find("info")
    name = (info.findtext("name") if info is not None else None) or Path(
        urllib.parse.urlparse(norm_url).path
    ).stem
    name = name.strip() or "Aurora Index"
    description = ((info.findtext("description") if info is not None else None) or "").strip()
    author = ((info.findtext("author") if info is not None else None) or "").strip()
    update_node = info.find("update") if info is not None else None
    version = (update_node.get("version") if update_node is not None else None) or "1.0"

    slug = _slugify(name)
    target_dir = custom_root / slug
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    root_base_url = norm_url.rsplit("/", 1)[0] + "/"

    visited_urls: set[str] = set()
    downloaded_count = 0

    def process_index(idx_url: str, idx_root: etree._Element) -> None:
        nonlocal downloaded_count
        if idx_url in visited_urls:
            return
        visited_urls.add(idx_url)

        files_node = idx_root.find("files")
        if files_node is None:
            return
        for fnode in files_node.findall("file"):
            raw_furl = (fnode.get("url") or "").strip()
            raw_fname = (fnode.get("name") or "").strip()
            if not raw_furl:
                continue
            furl = normalize_github_url(urllib.parse.urljoin(idx_url, raw_furl))
            if exclude_third_party and (
                is_third_party_path(raw_fname) or is_third_party_path(furl)
            ):
                if progress_cb:
                    progress_cb(f"Skipping 3rd-party entry: {raw_fname or furl}")
                continue
            if furl in visited_urls:
                continue

            if progress_cb:
                progress_cb(f"Downloading {raw_fname or furl}...")
            payload = fetcher(furl)
            try:
                child_root = etree.fromstring(payload, parser=parser)
            except etree.XMLSyntaxError:
                continue
            if child_root is None:
                continue

            child_tag = (child_root.tag or "").lower()
            if child_tag == "index" or furl.lower().endswith(".index"):
                if child_tag == "index":
                    process_index(furl, child_root)
                continue

            if child_tag == "elements":
                rel = _safe_rel_path(raw_fname, furl, root_base_url)
                out_path = target_dir / rel
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(
                    etree.tostring(
                        child_root, encoding="utf-8", xml_declaration=True, pretty_print=False
                    )
                )
                downloaded_count += 1

    process_index(norm_url, root)
    if progress_cb:
        progress_cb(f"Installed '{name}' ({downloaded_count} XML files)")

    return IndexRecord(
        slug=slug,
        name=name,
        url=norm_url,
        version=version.strip(),
        author=author,
        description=description,
        local_dir=str(target_dir),
        file_count=downloaded_count,
        updated_at=_now_iso(),
    )


def update_index(
    record: IndexRecord,
    custom_root: Path,
    progress_cb: Optional[Callable[[str], None]] = None,
    fetcher: Callable[[str], bytes] = fetch_url_bytes,
    exclude_third_party: bool = True,
) -> IndexRecord:
    """Re-fetch an installed index or direct XML from its source URL."""
    return install_from_url(
        record.url,
        custom_root=custom_root,
        progress_cb=progress_cb,
        fetcher=fetcher,
        exclude_third_party=exclude_third_party,
    )


def install_official_aurora_content(
    custom_root: Path,
    progress_cb: Optional[Callable[[str], None]] = None,
    fetcher: Callable[[str], bytes] = fetch_url_bytes,
) -> list[IndexRecord]:
    """Install official Aurora & Aurora Legacy indexes, excluding 3rd-party content."""
    records: list[IndexRecord] = []
    for label, idx_url in OFFICIAL_AURORA_INDEXES:
        if progress_cb:
            progress_cb(f"Syncing {label}...")
        rec = install_from_url(
            idx_url,
            custom_root=custom_root,
            progress_cb=progress_cb,
            fetcher=fetcher,
            exclude_third_party=True,
        )
        records.append(rec)
    return records


def remove_index(record: IndexRecord) -> None:
    """Remove an installed index directory or direct XML file from disk."""
    target = Path(record.local_dir)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    elif target.is_file():
        target.unlink(missing_ok=True)
