"""명령줄 진입점. 하위 명령은 각 기능 이슈에서 추가한다."""

import argparse
from collections.abc import Sequence

from aicollab import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aicollab",
        description="여러 AI 모델에 역할을 배정하고 공식 CLI를 호출해 협업 흐름을 실행한다.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
