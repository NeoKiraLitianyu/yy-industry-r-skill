from __future__ import annotations

import argparse
import sys
from pathlib import Path


技能目录 = Path(__file__).resolve().parents[1]
if str(技能目录) not in sys.path:
    sys.path.insert(0, str(技能目录))

from yy_industry_research.资料库 import 初始化资料库
from yy_industry_research.索引 import 初始化行业索引


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化全中文行业研究资料库")
    parser.add_argument("--行业", required=True)
    parser.add_argument("--资料库", required=True)
    parser.add_argument("--行业包")
    args = parser.parse_args()
    root = 初始化资料库(args.资料库, args.行业, args.行业包)
    初始化行业索引(root / "行业索引.sqlite")
    print(f"资料库初始化完成：{root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
