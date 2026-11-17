"""회사별 모델 목록과 모델별 최소 CLI 버전.

값은 docs/02-config-spec.md의 registry JSON과 같아야 하며 tests/test_provider_registry.py가
비교한다. 모델 ID와 최소 버전은 이 모듈 한 곳에만 둔다(AGENTS.md).

`enabled`는 메뉴 선택 대상이라는 뜻이다. 계정 제공과 실행 성공을 뜻하지 않는다.
`min_cli_version`은 CLI가 그 모델 ID를 인식하는 첫 버전이다(D14). 설치 버전이 이보다 낮아도
모델을 막지 않고 경고 정보(`VersionCheck`)로만 알린다.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

REGISTRY_VERSION = 1
VERIFIED_ON = "2026-11-17"
UNKNOWN_VERSION = "unknown"


@dataclass(frozen=True, slots=True)
class Model:
    id: str
    min_cli_version: str


@dataclass(frozen=True, slots=True)
class Provider:
    id: str
    menu_order: int
    enabled: bool
    models: tuple[Model, ...]
    # 실행 파일 이름에서 확장자를 뺀 값. 선택할 수 없는 회사는 None이다.
    cli_name: str | None
    sources: tuple[str, ...]


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        id="claude",
        menu_order=1,
        enabled=True,
        models=(
            Model("claude-opus-5-5", "2.1.280"),
            Model("claude-fable-5-2", "2.1.321"),
            Model("claude-sonnet-5-5", "2.1.284"),
            Model("claude-haiku-5-5", "2.1.293"),
        ),
        cli_name="claude",
        sources=(
            "https://platform.claude.com/docs/en/models/overview",
            "https://code.claude.com/docs/en/model-config",
        ),
    ),
    Provider(
        id="codex",
        menu_order=2,
        enabled=True,
        models=(
            Model("gpt-6-astra", UNKNOWN_VERSION),
            Model("gpt-6.1-sol", UNKNOWN_VERSION),
            Model("gpt-6.1-terra", UNKNOWN_VERSION),
            Model("gpt-6-luna", UNKNOWN_VERSION),
        ),
        cli_name="codex",
        sources=("https://learn.chatgpt.com/docs/models",),
    ),
    Provider(id="gemini", menu_order=3, enabled=False, models=(), cli_name=None, sources=()),
)


def get_provider(provider_id: str) -> Provider | None:
    return next((p for p in PROVIDERS if p.id == provider_id), None)


def get_model(provider_id: str, model_id: str) -> Model | None:
    provider = get_provider(provider_id)
    if provider is None:
        return None
    return next((m for m in provider.models if m.id == model_id), None)


def enabled_providers() -> tuple[Provider, ...]:
    return tuple(sorted((p for p in PROVIDERS if p.enabled), key=lambda p: p.menu_order))


def to_dict() -> dict[str, Any]:
    """docs/02-config-spec.md의 registry JSON과 같은 모양으로 돌려준다."""
    return {
        "registry_version": REGISTRY_VERSION,
        "providers": [
            {
                "id": p.id,
                "menu_order": p.menu_order,
                "enabled": p.enabled,
                "models": [{"id": m.id, "min_cli_version": m.min_cli_version} for m in p.models],
            }
            for p in PROVIDERS
        ],
    }


class VersionStatus(StrEnum):
    OK = "ok"
    # 설치 버전이 최소 버전보다 낮다. 설정 오류가 아니라 경고 대상이다.
    BELOW_MINIMUM = "below-minimum"
    # registry에 최소 버전이 없다. 버전 성공이 아니며 별도 기능 probe가 필요하다.
    MINIMUM_UNKNOWN = "minimum-unknown"
    # 설치 버전을 알 수 없다(찾지 못했거나 해석하지 못함).
    INSTALLED_UNKNOWN = "installed-unknown"


@dataclass(frozen=True, slots=True)
class VersionCheck:
    """경고 판정에 필요한 값. doctor가 경고 표시와 probe 판정에 쓴다."""

    provider: str
    model: str
    installed: str | None
    minimum: str
    status: VersionStatus

    @property
    def warns(self) -> bool:
        return self.status is VersionStatus.BELOW_MINIMUM


# (숫자 부분, 사전 배포 여부)
_Parsed = tuple[tuple[int, ...], bool]

_VERSION_PATTERN = re.compile(r"^v?(\d+(?:\.\d+)*)(-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def _parse_version(text: str) -> _Parsed | None:
    match = _VERSION_PATTERN.match(text.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split(".")), match.group(2) is not None


def _is_below(installed: _Parsed, minimum: _Parsed) -> bool:
    width = max(len(installed[0]), len(minimum[0]))
    left = installed[0] + (0,) * (width - len(installed[0]))
    right = minimum[0] + (0,) * (width - len(minimum[0]))
    if left != right:
        return left < right
    # 숫자 부분이 같으면 사전 배포(-alpha 등)가 정식 배포보다 낮다.
    return installed[1] and not minimum[1]


def check_model_version(provider_id: str, model_id: str, installed: str | None) -> VersionCheck:
    """설치된 CLI 버전을 모델의 최소 버전과 비교한다. 미달이어도 예외를 내지 않는다."""
    model = get_model(provider_id, model_id)
    if model is None:
        raise ValueError(f"registry에 없는 모델: {provider_id}/{model_id}")
    minimum = model.min_cli_version

    def result(status: VersionStatus) -> VersionCheck:
        return VersionCheck(provider_id, model_id, installed, minimum, status)

    if minimum == UNKNOWN_VERSION:
        return result(VersionStatus.MINIMUM_UNKNOWN)
    minimum_parsed = _parse_version(minimum)
    if minimum_parsed is None:
        raise ValueError(f"registry의 최소 버전을 해석하지 못함: {model_id} {minimum!r}")
    installed_parsed = None if installed is None else _parse_version(installed)
    if installed_parsed is None:
        return result(VersionStatus.INSTALLED_UNKNOWN)
    if _is_below(installed_parsed, minimum_parsed):
        return result(VersionStatus.BELOW_MINIMUM)
    return result(VersionStatus.OK)
