from __future__ import annotations

import argparse
import json

from autoin.adapters import PywinautoDriver


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump the visible Windows WeChat UIA tree for observer debugging.")
    parser.add_argument("--max-nodes", type=int, default=200)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    driver = PywinautoDriver()
    result = driver.dump_wechat_uia_tree(max_nodes=args.max_nodes)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
