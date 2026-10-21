#!/usr/bin/env python3
"""Build a deterministic ZIP from an explicit set of paths and verify it."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile


DEFAULT_EXCLUDES = (
    ".git/*",
    "*/.git/*",
    "__pycache__/*",
    "*/__pycache__/*",
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.bak",
    "*.log",
    ".DS_Store",
    "Thumbs.db",
    "tmp/*",
    "tmp_*/*",
    "*/tmp/*",
    "*/tmp_*/*",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def excluded(relative: str, patterns: list[str]) -> bool:
    path = PurePosixPath(relative)
    return any(path.match(pattern) or fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def collect_files(source: Path, includes: list[str], patterns: list[str], output: Path) -> list[Path]:
    found: dict[str, Path] = {}
    for raw in includes:
        rel = PurePosixPath(raw.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"Unsafe include path: {raw}")
        candidate = (source / Path(*rel.parts)).resolve()
        if not inside(candidate, source):
            raise ValueError(f"Include escapes source root: {raw}")
        if not candidate.exists():
            raise FileNotFoundError(f"Included path does not exist: {raw}")
        paths = [candidate] if candidate.is_file() else sorted(p for p in candidate.rglob("*") if p.is_file())
        for path in paths:
            if path.is_symlink():
                raise ValueError(f"Symlinks are not packaged: {path}")
            if path.resolve() == output:
                continue
            relative = path.relative_to(source).as_posix()
            if not excluded(relative, patterns):
                found[relative] = path
    if not found:
        raise ValueError("No files remain after include and exclude processing")
    return [found[key] for key in sorted(found)]


def write_zip(source: Path, output: Path, files: list[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            mode = 0o755 if os.access(path, os.X_OK) else 0o644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as handle:
                archive.writestr(info, handle.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def verify_zip(output: Path, expected: list[str]) -> None:
    with zipfile.ZipFile(output, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Archive contains duplicate member names")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Archive contains unsafe path: {name}")
        if names != expected:
            raise ValueError("Archive member list does not match the collected file set")
        broken = archive.testzip()
        if broken:
            raise ValueError(f"Archive CRC check failed: {broken}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Staging root that defines archive-relative paths")
    parser.add_argument("--include", action="append", required=True, help="Relative file or directory; repeat as needed")
    parser.add_argument("--exclude", action="append", default=[], help="Additional glob to exclude")
    parser.add_argument("--output", required=True, type=Path, help="Output ZIP path")
    parser.add_argument("--label", default="", help="Version or candidate label stored in the manifest")
    parser.add_argument("--manifest-output", type=Path, help="Manifest path; defaults beside the ZIP")
    parser.add_argument("--hash-output", type=Path, help="SHA256 path; defaults beside the ZIP")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_dir():
        raise NotADirectoryError(f"Source is not a directory: {source}")

    patterns = list(DEFAULT_EXCLUDES) + args.exclude
    files = collect_files(source, args.include, patterns, output)
    members = [path.relative_to(source).as_posix() for path in files]
    write_zip(source, output, files)
    verify_zip(output, members)

    manifest = {
        "label": args.label,
        "archive": output.name,
        "file_count": len(files),
        "files": [
            {"path": path.relative_to(source).as_posix(), "size": path.stat().st_size, "sha256": sha256_file(path)}
            for path in files
        ],
    }
    manifest_path = (args.manifest_output or Path(str(output) + ".manifest.json")).resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    package_hash = sha256_file(output)
    hash_path = (args.hash_output or Path(str(output) + ".sha256")).resolve()
    hash_path.parent.mkdir(parents=True, exist_ok=True)
    hash_path.write_text(f"{package_hash}  {output.name}\n", encoding="utf-8")

    print(f"Built: {output}")
    print(f"Files: {len(files)}")
    print(f"SHA256: {package_hash}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
