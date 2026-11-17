"""aicollab: 여러 AI 모델에 역할을 배정해 협업 흐름을 실행하는 CLI."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aicollab")
except PackageNotFoundError:  # 설치하지 않은 소스 트리에서 import한 경우
    __version__ = "0.0.0"
