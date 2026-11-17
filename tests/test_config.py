import copy
import tomllib
from pathlib import Path
from typing import Any

import pytest
from _spec_doc import extra_example, full_example, presets, with_assignment

from aicollab import provider_registry as registry
from aicollab.config import (
    Config,
    ConfigError,
    ConfigIssue,
    ErrorCode,
    load_config,
    parse_config,
    version_checks,
)
from aicollab.provider_registry import VersionStatus

BASE_TOML = """
schema_version = 2
[project]
[providers.claude]
[providers.codex]
[agents.plan]
provider = "claude"
model = "claude-opus-5-5"
[agents.code]
provider = "codex"
model = "gpt-6.1-terra"
[agents.test]
provider = "claude"
model = "claude-sonnet-5-5"
[agents.review]
provider = "codex"
model = "gpt-6-astra"
[roles.planner]
agents = ["plan"]
[roles.coder]
agents = ["code"]
[roles.reviewer]
agents = ["review"]
[pipeline]
flow = "plan-code-review"
[prepare]
dependency_paths = []
[checks]
enabled = false
[git]
[output]
"""

TESTER_ROLE = {"agents": ["test"], "test_paths": ["tests/"]}
PYTEST_CHECK = {"id": "tests", "source": "candidate", "argv": ["pytest"]}


def base() -> dict[str, Any]:
    return tomllib.loads(BASE_TOML)


def flow_with_tester() -> dict[str, Any]:
    data = base()
    data["pipeline"]["flow"] = "plan-code-test-review"
    data["roles"]["tester"] = copy.deepcopy(TESTER_ROLE)
    data["checks"] = {"enabled": True, "commands": [copy.deepcopy(PYTEST_CHECK)]}
    return data


def put(data: dict[str, Any], dotted: str, value: Any) -> dict[str, Any]:
    *parents, last = dotted.split(".")
    node = data
    for key in parents:
        node = node[key]
    node[last] = value
    return data


def drop(data: dict[str, Any], dotted: str) -> dict[str, Any]:
    *parents, last = dotted.split(".")
    node = data
    for key in parents:
        node = node[key]
    del node[last]
    return data


def issues_of(data: dict[str, Any]) -> list[ConfigIssue]:
    with pytest.raises(ConfigError) as info:
        parse_config(data)
    return list(info.value.issues)


def expect(data: dict[str, Any], code: ErrorCode, path: str) -> ConfigIssue:
    issues = issues_of(data)
    found = [i for i in issues if i.code is code and i.path == path]
    assert found, f"{code} {path}가 없다: {[str(i) for i in issues]}"
    return found[0]


# 읽기와 기본값


def test_base_config_is_valid_and_gets_defaults() -> None:
    config = parse_config(base())
    assert config.project.runtime == "windows-native"
    assert config.project.root == ".."
    assert config.project.threat_model == "trusted-local"
    assert config.project.uncommitted_changes == "warn-head"
    assert config.providers["claude"].executable == "claude.exe"
    assert config.providers["codex"].executable == "codex.exe"
    assert config.providers["codex"].auth_expectation == "subscription"
    assert config.agents["plan"].perspective == "general"
    assert config.agents["plan"].effort is None
    assert config.pipeline.max_revision_rounds == 2
    assert config.pipeline.invocation_timeout_seconds == 600
    assert config.pipeline.run_timeout_seconds == 3600
    assert config.pipeline.block_up_to == "P2"
    assert config.git.hooks == "run"
    assert config.output.mode == "branch"
    assert config.output.publish == "push"
    assert config.output.remote == "origin"
    assert config.active_role_names == ("planner", "coder", "reviewer")


def test_wsl2_runtime_uses_executable_names_without_extension() -> None:
    data = base()
    put(data, "project.runtime", "wsl2")
    config = parse_config(data)
    assert config.providers["claude"].executable == "claude"
    assert config.providers["codex"].executable == "codex"


def test_tester_flow_is_valid_and_defaults_apply() -> None:
    config = parse_config(flow_with_tester())
    assert config.active_role_names == ("planner", "coder", "tester", "reviewer")
    assert config.roles["tester"].access == "path-write"
    check = config.checks.commands[0]
    assert (check.trial, check.launcher, check.cwd, check.timeout_seconds) == (
        "not-required",
        "direct",
        ".",
        300,
    )


def test_multiple_reviewers_are_allowed() -> None:
    data = base()
    put(data, "agents.review2", {"provider": "claude", "model": "claude-opus-5-5"})
    put(data, "roles.reviewer.agents", ["review", "review2"])
    assert parse_config(data).roles["reviewer"].agents == ("review", "review2")


def test_load_config_reads_a_toml_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(BASE_TOML, encoding="utf-8")
    assert isinstance(load_config(path), Config)


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(tmp_path / ".aicollab" / "config.toml")
    assert info.value.codes == {ErrorCode.UNREADABLE}


def test_load_config_rejects_invalid_toml_bom_and_non_utf8(tmp_path: Path) -> None:
    cases = {
        "broken.toml": (b"schema_version = [", ErrorCode.INVALID_TOML),
        "bom.toml": (b"\xef\xbb\xbf" + BASE_TOML.encode("utf-8"), ErrorCode.INVALID_TOML),
        "cp949.toml": ("# 설정\nschema_version = 2\n".encode("cp949"), ErrorCode.UNREADABLE),
    }
    for name, (content, code) in cases.items():
        path = tmp_path / name
        path.write_bytes(content)
        with pytest.raises(ConfigError) as info:
            load_config(path)
        assert info.value.codes == {code}, name


# 문서의 예시가 그대로 통과한다


def test_spec_full_example_is_valid() -> None:
    config = parse_config(full_example())
    assert config.pipeline.flow == "plan-code-test-review"
    assert config.checks.commands[0].scratch_paths == (".test-tmp/",)


@pytest.mark.parametrize("name", ["claude-only", "codex-only", "mixed", "mixed-variant"])
def test_presets_validate_and_reference_registry_models(name: str) -> None:
    assignment = presets()[name]
    config = parse_config(with_assignment(assignment))
    assert set(config.roles) == {"planner", "coder", "tester", "reviewer"}
    for agent in config.agents.values():
        assert registry.get_model(agent.provider, agent.model) is not None, agent
        assert agent.provider in config.providers


def test_preset_provider_sets() -> None:
    sets = {name: set(parse_config(with_assignment(a)).providers) for name, a in presets().items()}
    assert sets == {
        "claude-only": {"claude"},
        "codex-only": {"codex"},
        "mixed": {"claude", "codex"},
        "mixed-variant": {"claude", "codex"},
    }


def test_spec_extra_examples_are_valid() -> None:
    node = full_example()
    node["prepare"] = extra_example(0)["prepare"]
    assert parse_config(node).prepare.commands[0].launcher == "node-npm"
    gradle = full_example()
    gradle["checks"] = extra_example(1)["checks"]
    parsed = parse_config(gradle).checks.commands[0]
    assert (parsed.source, parsed.trial, parsed.launcher) == (
        "custom",
        "doctor-once",
        "cmd-wrapper",
    )


# 최소 CLI 버전 미달은 오류가 아니라 경고 정보다(D14)


def test_below_minimum_version_is_a_warning_not_a_config_error() -> None:
    config = parse_config(with_assignment(presets()["claude-only"]))
    checks = {c.model: c for c in version_checks(config, {"claude": "2.1.316"})}
    assert set(checks) == {
        "claude-opus-5-5",
        "claude-fable-5-2",
        "claude-sonnet-5-5",
    }
    assert checks["claude-fable-5-2"].status is VersionStatus.BELOW_MINIMUM
    assert checks["claude-fable-5-2"].warns
    assert checks["claude-fable-5-2"].minimum == "2.1.321"
    assert checks["claude-opus-5-5"].status is VersionStatus.OK
    assert checks["claude-sonnet-5-5"].status is VersionStatus.OK
    assert [c.model for c in checks.values() if c.warns] == ["claude-fable-5-2"]


def test_version_checks_report_unknown_values() -> None:
    config = parse_config(with_assignment(presets()["mixed"]))
    checks = {c.provider: c for c in version_checks(config, {})}
    assert checks["claude"].status is VersionStatus.INSTALLED_UNKNOWN
    codex = [
        c for c in version_checks(config, {"codex": "0.167.0-alpha.3.2"}) if c.provider == "codex"
    ]
    assert codex
    assert all(c.status is VersionStatus.MINIMUM_UNKNOWN for c in codex)
    assert not any(c.warns for c in codex)


def test_version_checks_skip_agents_of_inactive_roles() -> None:
    data = base()
    put(data, "agents.test.model", "claude-fable-5-2")
    # tester 역할이 없는 기본 flow에서는 test agent를 쓰지 않는다.
    models = {c.model for c in version_checks(parse_config(data), {"claude": "2.1.316"})}
    assert "claude-fable-5-2" not in models


def test_version_checks_deduplicate_provider_model_pairs() -> None:
    data = base()
    put(data, "agents.review", {"provider": "claude", "model": "claude-opus-5-5"})
    checks = version_checks(parse_config(data), {"claude": "2.1.316"})
    assert [c.model for c in checks].count("claude-opus-5-5") == 1


# provider와 model


@pytest.mark.parametrize("provider", ["openai", "Claude"])
def test_unknown_provider_table_is_rejected(provider: str) -> None:
    data = base()
    put(data, f"providers.{provider}", {})
    expect(data, ErrorCode.UNKNOWN_REFERENCE, f"providers.{provider}")


def test_gemini_cannot_be_selected() -> None:
    data = base()
    put(data, "providers.gemini", {})
    expect(data, ErrorCode.INVALID_VALUE, "providers.gemini")
    data = base()
    put(data, "agents.plan", {"provider": "gemini", "model": "gemini-3-pro"})
    expect(data, ErrorCode.INVALID_VALUE, "agents.plan.provider")


def test_unknown_agent_provider_is_rejected() -> None:
    data = put(base(), "agents.plan.provider", "openai")
    expect(data, ErrorCode.UNKNOWN_REFERENCE, "agents.plan.provider")


def test_agent_provider_must_have_a_providers_table() -> None:
    data = drop(base(), "providers.codex")
    expect(data, ErrorCode.UNKNOWN_REFERENCE, "agents.code.provider")


@pytest.mark.parametrize(
    "model",
    ["opus", "claude-opus", "fable", "default", "claude-opus-5-5[1m]", "gpt-6-astra", "<model>"],
)
def test_unknown_model_alias_and_placeholder_are_rejected(model: str) -> None:
    data = put(base(), "agents.plan.model", model)
    issue = expect(data, ErrorCode.INVALID_VALUE, "agents.plan.model")
    assert "claude-opus-5-5" in issue.message


def test_agent_requires_provider_and_model() -> None:
    data = drop(drop(base(), "agents.plan.provider"), "agents.plan.model")
    codes = {(i.code, i.path) for i in issues_of(data)}
    assert (ErrorCode.MISSING_KEY, "agents.plan.provider") in codes
    assert (ErrorCode.MISSING_KEY, "agents.plan.model") in codes


CLAUDE_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
CODEX_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]


@pytest.mark.parametrize("effort", CLAUDE_EFFORTS)
def test_claude_effort_names_are_accepted(effort: str) -> None:
    data = put(base(), "agents.plan.effort", effort)
    assert parse_config(data).agents["plan"].effort == effort


@pytest.mark.parametrize("effort", ["xhigh1", "Max", "hgih", "minimal", "none", "ultra"])
def test_claude_effort_typo_or_codex_only_name_is_rejected(effort: str) -> None:
    data = put(base(), "agents.plan.effort", effort)
    issue = expect(data, ErrorCode.INVALID_EFFORT, "agents.plan.effort")
    assert "low, medium, high, xhigh, max" in issue.message


@pytest.mark.parametrize("effort", CODEX_EFFORTS)
def test_codex_models_without_a_model_list_use_the_provider_list(effort: str) -> None:
    # gpt-6.1-terra는 모델별 목록이 없으므로 minimal과 none도 정적으로 허용한다.
    data = put(base(), "agents.code.effort", effort)
    assert parse_config(data).agents["code"].effort == effort


def test_codex_provider_list_rejects_unknown_names() -> None:
    expect(
        put(base(), "agents.code.effort", "bogus-effort"),
        ErrorCode.INVALID_EFFORT,
        "agents.code.effort",
    )


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_gpt_6_astra_accepts_its_verified_efforts(effort: str) -> None:
    assert parse_config(put(base(), "agents.review.effort", effort))


@pytest.mark.parametrize("effort", ["minimal", "none"])
def test_gpt_6_astra_model_list_overrides_the_provider_list(effort: str) -> None:
    issue = expect(
        put(base(), "agents.review.effort", effort),
        ErrorCode.INVALID_EFFORT,
        "agents.review.effort",
    )
    assert "gpt-6-astra" in issue.message


def test_effort_type_and_empty_value() -> None:
    expect(put(base(), "agents.plan.effort", 3), ErrorCode.INVALID_TYPE, "agents.plan.effort")
    expect(put(base(), "agents.plan.effort", ""), ErrorCode.INVALID_VALUE, "agents.plan.effort")


def test_effort_is_optional() -> None:
    assert parse_config(base()).agents["plan"].effort is None


def test_effort_is_checked_with_the_provider_list_when_the_model_is_wrong() -> None:
    # 모델 오류와 effort 오류를 따로 알린다. 모델 오류 때문에 effort가 막히지는 않는다.
    data = put(put(base(), "agents.plan.model", "opus"), "agents.plan.effort", "xhigh")
    paths = {i.path for i in issues_of(data)}
    assert "agents.plan.model" in paths
    assert "agents.plan.effort" not in paths


def test_perspective_choices() -> None:
    assert parse_config(put(base(), "agents.plan.perspective", "security"))
    expect(
        put(base(), "agents.plan.perspective", "random"),
        ErrorCode.INVALID_VALUE,
        "agents.plan.perspective",
    )


def test_agent_id_format() -> None:
    data = base()
    data["agents"]["Plan"] = data["agents"].pop("plan")
    put(data, "roles.planner.agents", ["Plan"])
    expect(data, ErrorCode.INVALID_VALUE, "agents.Plan")


# 역할 수와 참조


def test_missing_required_roles() -> None:
    for role in ("planner", "coder", "reviewer"):
        expect(drop(base(), f"roles.{role}"), ErrorCode.MISSING_KEY, f"roles.{role}")


def test_tester_is_required_only_in_tester_flow() -> None:
    assert "tester" not in parse_config(base()).roles
    expect(drop(flow_with_tester(), "roles.tester"), ErrorCode.MISSING_KEY, "roles.tester")


@pytest.mark.parametrize("role", ["planner", "coder"])
def test_planner_and_coder_take_exactly_one_agent(role: str) -> None:
    data = put(base(), f"roles.{role}.agents", ["plan", "code"])
    expect(data, ErrorCode.INVALID_COUNT, f"roles.{role}.agents")
    expect(put(base(), f"roles.{role}.agents", []), ErrorCode.INVALID_COUNT, f"roles.{role}.agents")


def test_tester_takes_exactly_one_agent() -> None:
    data = put(flow_with_tester(), "roles.tester.agents", ["test", "plan"])
    expect(data, ErrorCode.INVALID_COUNT, "roles.tester.agents")


def test_reviewer_needs_at_least_one_agent() -> None:
    expect(
        put(base(), "roles.reviewer.agents", []), ErrorCode.INVALID_COUNT, "roles.reviewer.agents"
    )


def test_duplicate_agent_in_one_role_is_rejected() -> None:
    data = put(base(), "roles.reviewer.agents", ["review", "review"])
    expect(data, ErrorCode.DUPLICATE_ID, "roles.reviewer.agents")


def test_role_must_reference_existing_agent() -> None:
    data = put(base(), "roles.coder.agents", ["nobody"])
    expect(data, ErrorCode.UNKNOWN_REFERENCE, "roles.coder.agents")


def test_unknown_role_name_is_rejected() -> None:
    data = put(base(), "roles.architect", {"agents": ["plan"]})
    expect(data, ErrorCode.UNKNOWN_KEY, "roles.architect")


def test_role_agents_must_be_a_string_array() -> None:
    expect(put(base(), "roles.coder.agents", "code"), ErrorCode.INVALID_TYPE, "roles.coder.agents")
    expect(put(base(), "roles.coder.agents", [1]), ErrorCode.INVALID_TYPE, "roles.coder.agents[0]")


def test_role_access_only_accepts_the_role_policy() -> None:
    assert parse_config(put(base(), "roles.coder.access", "workspace-write"))
    expect(
        put(base(), "roles.coder.access", "read-only"),
        ErrorCode.INVALID_VALUE,
        "roles.coder.access",
    )


def test_test_paths_belong_to_tester_only() -> None:
    expect(
        put(base(), "roles.coder.test_paths", ["tests/"]),
        ErrorCode.UNKNOWN_KEY,
        "roles.coder.test_paths",
    )


# 키와 타입


def test_unknown_keys_are_rejected_at_every_level() -> None:
    expect(put(base(), "extra", 1), ErrorCode.UNKNOWN_KEY, "extra")
    expect(put(base(), "project.extra", 1), ErrorCode.UNKNOWN_KEY, "project.extra")
    expect(put(base(), "pipeline.extra", 1), ErrorCode.UNKNOWN_KEY, "pipeline.extra")
    expect(
        put(base(), "providers.claude.extra", 1), ErrorCode.UNKNOWN_KEY, "providers.claude.extra"
    )
    expect(put(base(), "agents.plan.extra", 1), ErrorCode.UNKNOWN_KEY, "agents.plan.extra")
    expect(put(base(), "git.extra", 1), ErrorCode.UNKNOWN_KEY, "git.extra")


def test_v1_dirty_policy_is_rejected_without_conversion() -> None:
    data = put(base(), "project.dirty_policy", "warn")
    issue = expect(data, ErrorCode.UNKNOWN_KEY, "project.dirty_policy")
    assert "uncommitted_changes" in issue.message


@pytest.mark.parametrize("value", ["2", 2.0, True, None])
def test_schema_version_must_be_integer_two(value: Any) -> None:
    data = base()
    if value is None:
        drop(data, "schema_version")
        expect(data, ErrorCode.MISSING_KEY, "schema_version")
    else:
        expect(put(data, "schema_version", value), ErrorCode.INVALID_TYPE, "schema_version")


def test_other_schema_versions_are_rejected() -> None:
    expect(put(base(), "schema_version", 1), ErrorCode.INVALID_VALUE, "schema_version")
    expect(put(base(), "schema_version", 3), ErrorCode.INVALID_VALUE, "schema_version")


def test_required_tables() -> None:
    for table in (
        "project",
        "providers",
        "agents",
        "roles",
        "pipeline",
        "prepare",
        "checks",
        "git",
        "output",
    ):
        expect(drop(base(), table), ErrorCode.MISSING_KEY, table)


def test_table_type_is_checked() -> None:
    expect(put(base(), "project", "x"), ErrorCode.INVALID_TYPE, "project")
    expect(put(base(), "agents.plan", "x"), ErrorCode.INVALID_TYPE, "agents.plan")


def test_pipeline_value_types_and_ranges() -> None:
    expect(
        put(base(), "pipeline.max_revision_rounds", True),
        ErrorCode.INVALID_TYPE,
        "pipeline.max_revision_rounds",
    )
    expect(
        put(base(), "pipeline.max_revision_rounds", "2"),
        ErrorCode.INVALID_TYPE,
        "pipeline.max_revision_rounds",
    )
    expect(
        put(base(), "pipeline.max_revision_rounds", -1),
        ErrorCode.INVALID_VALUE,
        "pipeline.max_revision_rounds",
    )
    assert (
        parse_config(put(base(), "pipeline.max_revision_rounds", 0)).pipeline.max_revision_rounds
        == 0
    )
    expect(
        put(base(), "pipeline.invocation_timeout_seconds", 0),
        ErrorCode.INVALID_VALUE,
        "pipeline.invocation_timeout_seconds",
    )
    expect(put(base(), "pipeline.flow", "plan-only"), ErrorCode.INVALID_VALUE, "pipeline.flow")
    expect(drop(base(), "pipeline.flow"), ErrorCode.MISSING_KEY, "pipeline.flow")
    expect(
        put(base(), "pipeline.block_up_to", "P6"), ErrorCode.INVALID_VALUE, "pipeline.block_up_to"
    )


def test_run_timeout_must_cover_one_invocation() -> None:
    data = put(
        put(base(), "pipeline.invocation_timeout_seconds", 700), "pipeline.run_timeout_seconds", 600
    )
    expect(data, ErrorCode.CONFLICT, "pipeline.run_timeout_seconds")


@pytest.mark.parametrize(
    ("dotted", "value"),
    [
        ("project.threat_model", "untrusted"),
        ("project.uncommitted_changes", "include"),
        ("project.runtime", "linux"),
        ("providers.claude.auth_expectation", "api-key"),
        ("prepare.network", "blocked"),
        ("prepare.on_lock_change", "update"),
        ("prepare.on_dependency_change", "reprepare"),
        ("git.hooks", "skip"),
        ("git.interactive_signing", "off"),
        ("git.on_no_change", "empty-commit"),
        ("output.mode", "patch"),
        ("output.publish", "merge"),
    ],
)
def test_decided_values_accept_only_the_decision(dotted: str, value: str) -> None:
    expect(put(base(), dotted, value), ErrorCode.INVALID_VALUE, dotted)


def test_output_github_repo_format() -> None:
    assert parse_config(put(base(), "output.github_repo", "jundragon7419/ai-collaboration"))
    expect(
        put(base(), "output.github_repo", "ai-collaboration"),
        ErrorCode.INVALID_VALUE,
        "output.github_repo",
    )


def test_runtime_wsl2_is_rejected_for_codex_only_flow() -> None:
    data = with_assignment(presets()["codex-only"])
    put(data, "project.runtime", "wsl2")
    expect(data, ErrorCode.CONFLICT, "project.runtime")
    claude = with_assignment(presets()["claude-only"])
    put(claude, "project.runtime", "wsl2")
    assert parse_config(claude).project.runtime == "wsl2"


def test_all_problems_are_collected_at_once() -> None:
    data = put(base(), "agents.plan.model", "opus")
    put(data, "roles.coder.agents", ["nobody"])
    put(data, "pipeline.flow", "nope")
    paths = {i.path for i in issues_of(data)}
    assert {"agents.plan.model", "roles.coder.agents", "pipeline.flow"} <= paths


# prepare와 checks


def test_prepare_requires_dependency_paths_key() -> None:
    expect(
        drop(base(), "prepare.dependency_paths"), ErrorCode.MISSING_KEY, "prepare.dependency_paths"
    )


def test_prepare_commands_and_duplicate_ids() -> None:
    command = {"id": "deps", "argv": ["uv.exe", "sync", "--locked"]}
    data = put(base(), "prepare.commands", [command])
    parsed = parse_config(data).prepare.commands[0]
    assert parsed.argv == ("uv.exe", "sync", "--locked")
    assert (parsed.timeout_seconds, parsed.cwd, parsed.launcher) == (900, ".", "direct")
    data = put(base(), "prepare.commands", [command, dict(command)])
    expect(data, ErrorCode.DUPLICATE_ID, "prepare.commands[1].id")


def test_command_argv_must_be_a_non_empty_string_array() -> None:
    expect(
        put(base(), "prepare.commands", [{"id": "d"}]),
        ErrorCode.MISSING_KEY,
        "prepare.commands[0].argv",
    )
    expect(
        put(base(), "prepare.commands", [{"id": "d", "argv": []}]),
        ErrorCode.INVALID_COUNT,
        "prepare.commands[0].argv",
    )
    expect(
        put(base(), "prepare.commands", [{"id": "d", "argv": "uv sync"}]),
        ErrorCode.INVALID_TYPE,
        "prepare.commands[0].argv",
    )


def test_command_success_exit_codes_accept_only_zero() -> None:
    command = {"id": "d", "argv": ["x"], "success_exit_codes": [0, 1]}
    expect(
        put(base(), "prepare.commands", [command]),
        ErrorCode.INVALID_VALUE,
        "prepare.commands[0].success_exit_codes",
    )
    command["success_exit_codes"] = ["0"]
    expect(
        put(base(), "prepare.commands", [command]),
        ErrorCode.INVALID_TYPE,
        "prepare.commands[0].success_exit_codes",
    )


def test_command_launcher_and_cwd() -> None:
    command = {"id": "d", "argv": ["x"], "launcher": "powershell"}
    expect(
        put(base(), "prepare.commands", [command]),
        ErrorCode.INVALID_VALUE,
        "prepare.commands[0].launcher",
    )
    command = {"id": "d", "argv": ["x"], "cwd": "../outside"}
    expect(
        put(base(), "prepare.commands", [command]),
        ErrorCode.INVALID_PATH,
        "prepare.commands[0].cwd",
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["my wrapper.cmd"],
        ["gradlew.bat", "a&b"],
        ["gradlew.bat", "%PATH%"],
        ["gradlew.bat", 'say "hi"'],
        ["gradlew.bat", "a^b"],
    ],
)
def test_cmd_wrapper_restrictions(argv: list[str]) -> None:
    command = {"id": "w", "argv": argv, "launcher": "cmd-wrapper"}
    expect(
        put(base(), "prepare.commands", [command]),
        ErrorCode.INVALID_VALUE,
        "prepare.commands[0].argv",
    )
    ok = {"id": "w", "argv": ["gradlew.bat", "--offline", "test"], "launcher": "cmd-wrapper"}
    assert parse_config(put(base(), "prepare.commands", [ok]))


def test_checks_enabled_needs_a_command() -> None:
    data = put(base(), "checks", {"enabled": True})
    expect(data, ErrorCode.INVALID_COUNT, "checks.commands")
    assert parse_config(put(base(), "checks", {"enabled": False}))


def test_checks_cannot_be_disabled_in_tester_flow() -> None:
    expect(put(flow_with_tester(), "checks.enabled", False), ErrorCode.CONFLICT, "checks.enabled")


def test_checks_network_is_blocked_only() -> None:
    expect(
        put(flow_with_tester(), "checks.network", "allowed"),
        ErrorCode.INVALID_VALUE,
        "checks.network",
    )


def test_check_command_source_and_trial() -> None:
    data = flow_with_tester()
    put(data, "checks.commands", [{"id": "t", "argv": ["x"]}])
    expect(data, ErrorCode.MISSING_KEY, "checks.commands[0].source")
    custom = {"id": "t", "argv": ["x"], "source": "custom"}
    parsed = parse_config(put(flow_with_tester(), "checks.commands", [custom])).checks.commands[0]
    assert parsed.trial == "doctor-once"
    for trial in ("passed", "pending", "not-required"):
        data = put(flow_with_tester(), "checks.commands", [dict(custom, trial=trial)])
        expect(data, ErrorCode.INVALID_VALUE, "checks.commands[0].trial")
    candidate = dict(PYTEST_CHECK, trial="doctor-once")
    expect(
        put(flow_with_tester(), "checks.commands", [candidate]),
        ErrorCode.INVALID_VALUE,
        "checks.commands[0].trial",
    )
    expect(
        put(flow_with_tester(), "checks.commands", [dict(PYTEST_CHECK, source="magic")]),
        ErrorCode.INVALID_VALUE,
        "checks.commands[0].source",
    )


def test_check_command_ids_must_be_unique() -> None:
    data = put(flow_with_tester(), "checks.commands", [PYTEST_CHECK, dict(PYTEST_CHECK)])
    expect(data, ErrorCode.DUPLICATE_ID, "checks.commands[1].id")


def test_check_timeout_cannot_exceed_run_timeout() -> None:
    command = dict(PYTEST_CHECK, timeout_seconds=7200)
    data = put(flow_with_tester(), "checks.commands", [command])
    expect(data, ErrorCode.CONFLICT, "checks.commands[0].timeout_seconds")


@pytest.mark.parametrize("scratch", ["tests/tmp/", "TESTS", "uv.lock"])
def test_scratch_cannot_overlap_test_or_lock_paths(scratch: str) -> None:
    data = put(flow_with_tester(), "prepare.manifest_paths", ["pyproject.toml", "uv.lock"])
    put(data, "checks.commands", [dict(PYTEST_CHECK, scratch_paths=[scratch])])
    expect(data, ErrorCode.INVALID_PATH, "checks.commands[0].scratch_paths")
    ok = put(
        flow_with_tester(), "checks.commands", [dict(PYTEST_CHECK, scratch_paths=[".test-tmp/"])]
    )
    assert parse_config(ok)


@pytest.mark.parametrize(
    "bad",
    [
        "../x",
        "tests/../../x",
        "/abs",
        "\\rooted",
        "C:\\x",
        "C:x",
        "\\\\server\\share",
        "\\\\?\\C:\\x",
        ".",
        "",
        "a<b",
        "a|b",
        "con",
        "tests/NUL.txt",
        "trailing.",
        "trailing /x",
    ],
)
def test_test_paths_reject_escape_and_windows_special_paths(bad: str) -> None:
    data = put(flow_with_tester(), "roles.tester.test_paths", [bad])
    issues = issues_of(data)
    assert any(i.path.startswith("roles.tester.test_paths") for i in issues), bad


def test_test_paths_reject_same_path_with_different_case_or_separator() -> None:
    for paths in (["tests/", "TESTS"], ["tests/unit", "tests\\unit"], ["a", "a/"]):
        data = put(flow_with_tester(), "roles.tester.test_paths", paths)
        expect(data, ErrorCode.INVALID_PATH, "roles.tester.test_paths")


def test_test_paths_default_and_minimum() -> None:
    data = flow_with_tester()
    drop(data, "roles.tester.test_paths")
    assert parse_config(data).roles["tester"].test_paths == ("tests/",)
    expect(
        put(flow_with_tester(), "roles.tester.test_paths", []),
        ErrorCode.INVALID_COUNT,
        "roles.tester.test_paths",
    )


def test_dependency_and_manifest_paths_are_checked() -> None:
    expect(
        put(base(), "prepare.dependency_paths", ["."]),
        ErrorCode.INVALID_PATH,
        "prepare.dependency_paths",
    )
    expect(
        put(base(), "prepare.dependency_paths", ["../venv"]),
        ErrorCode.INVALID_PATH,
        "prepare.dependency_paths",
    )
    expect(
        put(base(), "prepare.manifest_paths", ["C:\\x\\uv.lock"]),
        ErrorCode.INVALID_PATH,
        "prepare.manifest_paths",
    )
    assert parse_config(put(base(), "prepare.dependency_paths", [".venv/", "node_modules/"]))


def test_config_issue_text_includes_path_and_code() -> None:
    issue = expect(put(base(), "pipeline.flow", "x"), ErrorCode.INVALID_VALUE, "pipeline.flow")
    assert str(issue).startswith("pipeline.flow: ")
    assert str(issue).endswith("[invalid-value]")
