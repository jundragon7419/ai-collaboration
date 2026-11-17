import json

import pytest
from _spec_doc import code_blocks, registry_table, section

from aicollab import provider_registry as registry
from aicollab.provider_registry import VersionStatus, check_model_version


def test_registry_matches_spec_json() -> None:
    doc = json.loads(code_blocks(section("provider registry와 최소 버전"), "json")[0])
    assert registry.to_dict() == doc


def test_registry_matches_spec_table() -> None:
    from_registry = {(p.id, m.id): m.min_cli_version for p in registry.PROVIDERS for m in p.models}
    assert from_registry == registry_table()


def test_model_ids_are_full_ids_without_duplicates() -> None:
    ids = [m.id for p in registry.PROVIDERS for m in p.models]
    assert len(ids) == len(set(ids)) == 8
    assert not {"opus", "sonnet", "haiku", "fable", "default"} & set(ids)


def test_enabled_providers_follow_menu_order_and_exclude_gemini() -> None:
    assert [p.id for p in registry.enabled_providers()] == ["claude", "codex"]
    gemini = registry.get_provider("gemini")
    assert gemini is not None
    assert not gemini.enabled
    assert gemini.models == ()


def test_lookup() -> None:
    assert registry.get_model("claude", "claude-fable-5-2") is not None
    assert registry.get_model("claude", "gpt-6-astra") is None
    assert registry.get_model("openai", "gpt-6-astra") is None
    assert registry.get_provider("claude") is not None
    assert registry.get_provider("openai") is None


def test_fable_below_minimum_is_a_warning_not_an_error() -> None:
    check = check_model_version("claude", "claude-fable-5-2", "2.1.316")
    assert check.status is VersionStatus.BELOW_MINIMUM
    assert check.warns
    assert (check.installed, check.minimum) == ("2.1.316", "2.1.321")


@pytest.mark.parametrize(
    ("model", "installed", "status"),
    [
        ("claude-opus-5-5", "2.1.316", VersionStatus.OK),
        ("claude-fable-5-2", "2.1.321", VersionStatus.OK),
        ("claude-fable-5-2", "2.2.0", VersionStatus.OK),
        ("claude-fable-5-2", "3.0", VersionStatus.OK),
        # 숫자로 비교한다. 문자열 비교면 "2.1.9"가 더 크다.
        ("claude-opus-5-5", "2.1.9", VersionStatus.BELOW_MINIMUM),
        ("claude-opus-5-5", "v2.1.280", VersionStatus.OK),
        # 사전 배포는 같은 번호의 정식 배포보다 낮다.
        ("claude-fable-5-2", "2.1.321-beta.1", VersionStatus.BELOW_MINIMUM),
        ("claude-fable-5-2", None, VersionStatus.INSTALLED_UNKNOWN),
        ("claude-fable-5-2", "Claude Code 2.1.316", VersionStatus.INSTALLED_UNKNOWN),
        ("claude-fable-5-2", "", VersionStatus.INSTALLED_UNKNOWN),
    ],
)
def test_claude_version_status(model: str, installed: str | None, status: VersionStatus) -> None:
    assert check_model_version("claude", model, installed).status is status


@pytest.mark.parametrize("installed", ["0.167.0-alpha.3.2", None, "garbage"])
def test_unknown_minimum_is_reported_as_unknown(installed: str | None) -> None:
    check = check_model_version("codex", "gpt-6-astra", installed)
    assert check.status is VersionStatus.MINIMUM_UNKNOWN
    assert check.minimum == "unknown"
    assert not check.warns


def test_unregistered_model_raises() -> None:
    with pytest.raises(ValueError, match="registry"):
        check_model_version("claude", "opus", "2.1.316")
