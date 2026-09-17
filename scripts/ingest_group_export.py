"""P2-B：从群导出文本生成待确认候选（草稿，不连 QQ）。"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest group export text into pending candidates")
    parser.add_argument("path", type=Path, help="Exported group chat text file")
    args = parser.parse_args()
    if not args.path.is_file():
        raise SystemExit(f"file not found: {args.path}")
    raise SystemExit("P2-B: implement clean → extract → pending queue")


if __name__ == "__main__":
    main()
