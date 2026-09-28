"""Check local Markdown links in the maintained documentation tree."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "README.md", ROOT / "PROJECT_STATUS.md"]
SOURCES.extend((ROOT / "docs" / "current").rglob("*.md"))
SOURCES.extend((ROOT / "docs" / "product").rglob("*.md"))
SOURCES.extend((ROOT / "docs" / "development").rglob("*.md"))
SOURCES.append(ROOT / "docs" / "README.md")
SOURCES.append(ROOT / "docs" / "archive" / "README.md")
SOURCES.append(ROOT / "docs" / "archive" / "migrations" / "README.md")
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


def main() -> int:
    broken: list[str] = []
    for source in SOURCES:
        for target in LINK.findall(source.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            path = (source.parent / target.split("#", 1)[0]).resolve()
            if not path.exists():
                broken.append(f"{source.relative_to(ROOT)} -> {target}")
    for item in broken:
        print(item)
    print(f"Checked {len(SOURCES)} documents; broken local links: {len(broken)}")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
