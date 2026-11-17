"""설정 파일(.aicollab/config.toml) 읽기와 정적 검증.

docs/02-config-spec.md에서 시점이 "정적"인 규칙과 값 자체로 판정할 수 있는 규칙을 검사한다.
실행 파일 존재, Git root 일치, WSL 배포판, 절대 경로 같은 doctor와 run 규칙은 여기서 하지 않는다.
오류는 처음 하나에서 멈추지 않고 모두 모아 `ConfigError`로 알린다. 값을 추측해 고치지 않는다.
최소 CLI 버전 미달은 오류가 아니다. `version_checks()`가 경고 정보로 돌려준다(D14).
"""

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from aicollab import provider_registry as registry

SCHEMA_VERSION = 2
CONFIG_RELATIVE_PATH = Path(".aicollab") / "config.toml"

TESTER_FLOW = "plan-code-test-review"
FLOWS = ("plan-code-review", TESTER_FLOW)
RUNTIMES = ("windows-native", "wsl2")
PERSPECTIVES = ("general", "adversarial", "spec", "security")
BLOCK_LEVELS = ("P0", "P1", "P2", "P3", "P4", "P5")
LAUNCHERS = ("direct", "node-npm", "node-npx", "cmd-wrapper")
CHECK_SOURCES = ("candidate", "custom")
PUBLISH_MODES = ("push", "draft-pr")
# 역할별 기본 접근 정책(설계 제안). 이 값만 허용한다.
ROLE_ACCESS = {
    "planner": "read-only",
    "coder": "workspace-write",
    "tester": "path-write",
    "reviewer": "read-only",
}

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")
_BAD_PATH_CHARS = frozenset('<>"|?*') | frozenset(chr(i) for i in range(32))
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
# D15: cmd-wrapper 인자에 허용하지 않는 문자
_CMD_UNSAFE_CHARS = frozenset('%^&|"<>!\r\n')


class ErrorCode(StrEnum):
    UNREADABLE = "unreadable"
    INVALID_TOML = "invalid-toml"
    MISSING_KEY = "missing-key"
    UNKNOWN_KEY = "unknown-key"
    INVALID_TYPE = "invalid-type"
    INVALID_VALUE = "invalid-value"
    DUPLICATE_ID = "duplicate-id"
    UNKNOWN_REFERENCE = "unknown-reference"
    INVALID_COUNT = "invalid-count"
    INVALID_PATH = "invalid-path"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class ConfigIssue:
    code: ErrorCode
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message} [{self.code}]"


class ConfigError(Exception):
    """설정이 규칙에 어긋난다. `issues`에 어긋난 항목이 모두 들어 있다."""

    def __init__(self, issues: Sequence[ConfigIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("\n".join(str(issue) for issue in self.issues))

    @property
    def codes(self) -> frozenset[ErrorCode]:
        return frozenset(issue.code for issue in self.issues)


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    root: str
    run_root: str | None
    runtime: str
    wsl_distribution: str | None
    threat_model: str
    uncommitted_changes: str


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    id: str
    executable: str
    auth_expectation: str


@dataclass(frozen=True, slots=True)
class AgentConfig:
    id: str
    provider: str
    model: str
    # 값 검증은 하지 않는다. 모델별 허용 effort는 결정 전이다(이슈 #10 댓글 참고).
    effort: str | None
    perspective: str


@dataclass(frozen=True, slots=True)
class RoleConfig:
    name: str
    agents: tuple[str, ...]
    access: str
    test_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    flow: str
    max_revision_rounds: int
    invocation_timeout_seconds: int
    run_timeout_seconds: int
    block_up_to: str


@dataclass(frozen=True, slots=True)
class CommandConfig:
    id: str
    argv: tuple[str, ...]
    cwd: str
    launcher: str
    timeout_seconds: int
    success_exit_codes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CheckCommandConfig(CommandConfig):
    source: str
    trial: str
    scratch_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrepareConfig:
    network: str
    commands: tuple[CommandConfig, ...]
    dependency_paths: tuple[str, ...]
    manifest_paths: tuple[str, ...]
    on_lock_change: str
    on_dependency_change: str


@dataclass(frozen=True, slots=True)
class ChecksConfig:
    enabled: bool
    network: str
    commands: tuple[CheckCommandConfig, ...]


@dataclass(frozen=True, slots=True)
class GitConfig:
    hooks: str
    interactive_signing: str
    on_no_change: str


@dataclass(frozen=True, slots=True)
class OutputConfig:
    mode: str
    publish: str
    remote: str
    base_branch: str | None
    github_repo: str | None


@dataclass(frozen=True, slots=True)
class Config:
    schema_version: int
    project: ProjectConfig
    providers: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]
    roles: dict[str, RoleConfig]
    pipeline: PipelineConfig
    prepare: PrepareConfig
    checks: ChecksConfig
    git: GitConfig
    output: OutputConfig

    @property
    def active_role_names(self) -> tuple[str, ...]:
        """flow에서 실제로 실행하는 역할. tester는 tester flow에서만 활성이다."""
        if self.pipeline.flow == TESTER_FLOW:
            return ("planner", "coder", "tester", "reviewer")
        return ("planner", "coder", "reviewer")

    @property
    def active_agent_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for name in self.active_role_names:
            role = self.roles.get(name)
            if role is not None:
                ids.extend(a for a in role.agents if a not in ids)
        return tuple(ids)


def version_checks(
    config: Config, installed: Mapping[str, str | None]
) -> tuple[registry.VersionCheck, ...]:
    """활성 agent가 쓰는 (회사, 모델)마다 설치 CLI 버전을 최소 버전과 비교한다.

    `installed`는 회사 ID별 설치 버전이다. 없거나 None이면 설치 버전을 모르는 것으로 본다.
    미달은 오류가 아니므로 예외를 내지 않는다.
    """
    seen: set[tuple[str, str]] = set()
    checks: list[registry.VersionCheck] = []
    for agent_id in config.active_agent_ids:
        agent = config.agents[agent_id]
        key = (agent.provider, agent.model)
        if key not in seen:
            seen.add(key)
            checks.append(
                registry.check_model_version(agent.provider, agent.model, installed.get(key[0]))
            )
    return tuple(checks)


def load_config(path: str | Path) -> Config:
    """TOML 파일을 읽어 검증한다. 규칙에 어긋나면 `ConfigError`를 낸다."""
    shown = str(path)
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise _single(ErrorCode.UNREADABLE, shown, f"파일을 읽지 못했다: {exc.strerror}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _single(ErrorCode.UNREADABLE, shown, "UTF-8 파일이 아니다") from exc
    if text.startswith("﻿"):
        raise _single(ErrorCode.INVALID_TOML, shown, "BOM이 있다. BOM 없는 UTF-8로 저장해야 한다")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise _single(ErrorCode.INVALID_TOML, shown, f"TOML 문법 오류: {exc}") from exc
    return parse_config(data)


def parse_config(data: Mapping[str, Any]) -> Config:
    """이미 읽은 TOML 값을 검증한다. 규칙에 어긋나면 `ConfigError`를 낸다."""
    return _Validator().run(data)


def _single(code: ErrorCode, path: str, message: str) -> ConfigError:
    return ConfigError([ConfigIssue(code, path, message)])


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _choices_text(choices: Sequence[str]) -> str:
    return ", ".join(choices)


def _path_problem(value: str, *, allow_dot: bool) -> str | None:
    """저장소 안의 상대 경로 규칙. 어긋나면 이유를 돌려준다."""
    if any(ch in _BAD_PATH_CHARS for ch in value):
        return "사용할 수 없는 문자가 있다"
    if value.startswith(("/", "\\")):
        return "절대 경로, UNC, device 경로는 쓸 수 없다"
    if _DRIVE_PATTERN.match(value):
        return "drive 경로와 drive-relative 경로는 쓸 수 없다"
    parts = _segments(value)
    if ".." in parts:
        return "상위 경로(..)로 벗어날 수 없다"
    if not parts:
        return None if allow_dot else "저장소 전체를 가리킬 수 없다"
    for part in re.split(r"[\\/]+", value):
        if part in ("", "."):
            continue
        if part.endswith((" ", ".")) or part.split(".")[0].upper() in _RESERVED_NAMES:
            return f"Windows에서 쓸 수 없는 이름이다: {part!r}"
    return None


def _segments(value: str) -> tuple[str, ...]:
    return tuple(p.casefold() for p in re.split(r"[\\/]+", value) if p not in ("", "."))


def _overlaps(left: str, right: str) -> bool:
    a, b = _segments(left), _segments(right)
    shorter = min(len(a), len(b))
    return a[:shorter] == b[:shorter]


class _Validator:
    def __init__(self) -> None:
        self.issues: list[ConfigIssue] = []

    # 읽기 도구

    def add(self, code: ErrorCode, path: str, message: str) -> None:
        self.issues.append(ConfigIssue(code, path, message))

    def table(
        self, data: Mapping[str, Any], key: str, path: str, *, required: bool
    ) -> Mapping[str, Any] | None:
        full = _join(path, key)
        if key not in data:
            if required:
                self.add(ErrorCode.MISSING_KEY, full, "필수 table이 없다")
            return None
        value = data[key]
        if not isinstance(value, dict):
            self.add(ErrorCode.INVALID_TYPE, full, "table이어야 한다")
            return None
        return value

    def keys(self, data: Mapping[str, Any], path: str, allowed: Sequence[str]) -> None:
        for key in data:
            if key in allowed:
                continue
            message = "알 수 없는 키다"
            if path == "project" and key == "dirty_policy":
                message = "v2에서는 project.uncommitted_changes다. 값을 자동으로 바꾸지 않는다"
            self.add(ErrorCode.UNKNOWN_KEY, _join(path, key), message)

    def _string(
        self,
        data: Mapping[str, Any],
        key: str,
        path: str,
        *,
        choices: Sequence[str] | None,
        required: bool,
    ) -> str | None:
        full = _join(path, key)
        if key not in data:
            if required:
                self.add(ErrorCode.MISSING_KEY, full, "필수 키가 없다")
            return None
        value = data[key]
        if not isinstance(value, str):
            self.add(ErrorCode.INVALID_TYPE, full, "문자열이어야 한다")
            return None
        if value == "":
            self.add(ErrorCode.INVALID_VALUE, full, "빈 문자열은 쓸 수 없다")
            return None
        if choices is not None and value not in choices:
            self.add(
                ErrorCode.INVALID_VALUE,
                full,
                f"{value!r}는 허용하지 않는다. 허용: {_choices_text(choices)}",
            )
            return None
        return value

    def string(
        self,
        data: Mapping[str, Any],
        key: str,
        path: str,
        default: str,
        choices: Sequence[str] | None = None,
    ) -> str:
        value = self._string(data, key, path, choices=choices, required=False)
        return default if value is None else value

    def required_string(
        self,
        data: Mapping[str, Any],
        key: str,
        path: str,
        choices: Sequence[str] | None = None,
    ) -> str:
        value = self._string(data, key, path, choices=choices, required=True)
        return "" if value is None else value

    def optional_string(self, data: Mapping[str, Any], key: str, path: str) -> str | None:
        return self._string(data, key, path, choices=None, required=False)

    def integer(
        self, data: Mapping[str, Any], key: str, path: str, default: int, minimum: int
    ) -> int:
        if key not in data:
            return default
        full = _join(path, key)
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, int):
            self.add(ErrorCode.INVALID_TYPE, full, "정수여야 한다")
            return default
        if value < minimum:
            self.add(ErrorCode.INVALID_VALUE, full, f"{minimum} 이상이어야 한다")
            return default
        return value

    def boolean(self, data: Mapping[str, Any], key: str, path: str, default: bool) -> bool:
        if key not in data:
            return default
        value = data[key]
        if not isinstance(value, bool):
            self.add(ErrorCode.INVALID_TYPE, _join(path, key), "true 또는 false여야 한다")
            return default
        return value

    def string_list(
        self,
        data: Mapping[str, Any],
        key: str,
        path: str,
        *,
        default: tuple[str, ...] | None,
        min_items: int = 0,
    ) -> tuple[str, ...]:
        """문자열 배열. default가 None이면 필수 키다."""
        full = _join(path, key)
        if key not in data:
            if default is None:
                self.add(ErrorCode.MISSING_KEY, full, "필수 키가 없다")
                return ()
            return default
        value = data[key]
        if not isinstance(value, list):
            self.add(ErrorCode.INVALID_TYPE, full, "문자열 배열이어야 한다")
            return default or ()
        items: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str) or item == "":
                self.add(
                    ErrorCode.INVALID_TYPE, f"{full}[{index}]", "비어 있지 않은 문자열이어야 한다"
                )
            else:
                items.append(item)
        if len(value) < min_items:
            self.add(ErrorCode.INVALID_COUNT, full, f"{min_items}개 이상 필요하다")
        return tuple(items)

    def path_list(
        self,
        data: Mapping[str, Any],
        key: str,
        path: str,
        *,
        default: tuple[str, ...] | None,
        min_items: int = 0,
    ) -> tuple[str, ...]:
        full = _join(path, key)
        items = self.string_list(data, key, path, default=default, min_items=min_items)
        for item in items:
            problem = _path_problem(item, allow_dot=False)
            if problem is not None:
                self.add(ErrorCode.INVALID_PATH, full, f"{item!r}: {problem}")
        for index, item in enumerate(items):
            if any(_segments(item) == _segments(other) for other in items[:index]):
                self.add(
                    ErrorCode.INVALID_PATH,
                    full,
                    f"{item!r}: 같은 경로가 중복돼 있다(대소문자 차이 포함)",
                )
        return items

    def directory(self, data: Mapping[str, Any], key: str, path: str, default: str) -> str:
        value = self.string(data, key, path, default)
        problem = _path_problem(value, allow_dot=True)
        if problem is not None:
            self.add(ErrorCode.INVALID_PATH, _join(path, key), f"{value!r}: {problem}")
        return value

    def identifier(self, value: str, path: str) -> bool:
        if _ID_PATTERN.match(value):
            return True
        self.add(ErrorCode.INVALID_VALUE, path, f"ID는 [a-z][a-z0-9_-]* 형식이어야 한다: {value!r}")
        return False

    # 검증

    def run(self, data: Mapping[str, Any]) -> Config:
        self.keys(
            data,
            "",
            ("schema_version", "project", "providers", "agents", "roles")
            + ("pipeline", "prepare", "checks", "git", "output"),
        )
        schema_version = self._schema_version(data)
        project = self._project(data)
        providers = self._providers(data, project.runtime)
        agents = self._agents(data, providers)
        pipeline = self._pipeline(data)
        roles = self._roles(data, agents, pipeline.flow)
        prepare = self._prepare(data)
        checks = self._checks(data, pipeline, roles, prepare)
        git = self._git(data)
        output = self._output(data)
        config = Config(
            schema_version,
            project,
            providers,
            agents,
            roles,
            pipeline,
            prepare,
            checks,
            git,
            output,
        )
        self._cross_checks(config)
        if self.issues:
            raise ConfigError(self.issues)
        return config

    def _schema_version(self, data: Mapping[str, Any]) -> int:
        if "schema_version" not in data:
            self.add(ErrorCode.MISSING_KEY, "schema_version", "필수 키가 없다")
            return SCHEMA_VERSION
        value = data["schema_version"]
        if isinstance(value, bool) or not isinstance(value, int):
            self.add(ErrorCode.INVALID_TYPE, "schema_version", "정수여야 한다")
        elif value != SCHEMA_VERSION:
            self.add(
                ErrorCode.INVALID_VALUE,
                "schema_version",
                f"{SCHEMA_VERSION}만 지원한다. 다른 버전의 값을 자동으로 바꾸지 않는다",
            )
        return SCHEMA_VERSION

    def _project(self, data: Mapping[str, Any]) -> ProjectConfig:
        table = self.table(data, "project", "", required=True) or {}
        path = "project"
        self.keys(
            table,
            path,
            ("root", "run_root", "runtime", "wsl_distribution", "threat_model")
            + ("uncommitted_changes",),
        )
        return ProjectConfig(
            root=self.string(table, "root", path, ".."),
            run_root=self.optional_string(table, "run_root", path),
            runtime=self.string(table, "runtime", path, "windows-native", RUNTIMES),
            wsl_distribution=self.optional_string(table, "wsl_distribution", path),
            threat_model=self.string(
                table, "threat_model", path, "trusted-local", ("trusted-local",)
            ),
            uncommitted_changes=self.string(
                table, "uncommitted_changes", path, "warn-head", ("warn-head",)
            ),
        )

    def _providers(self, data: Mapping[str, Any], runtime: str) -> dict[str, ProviderConfig]:
        table = self.table(data, "providers", "", required=True) or {}
        providers: dict[str, ProviderConfig] = {}
        for provider_id, raw in table.items():
            path = f"providers.{provider_id}"
            known = registry.get_provider(provider_id)
            if known is None:
                self.add(ErrorCode.UNKNOWN_REFERENCE, path, "registry에 없는 회사다")
            elif not known.enabled:
                self.add(
                    ErrorCode.INVALID_VALUE, path, "선택할 수 없는 회사다(registry에서 비활성)"
                )
            if not isinstance(raw, dict):
                self.add(ErrorCode.INVALID_TYPE, path, "table이어야 한다")
                continue
            self.keys(raw, path, ("executable", "auth_expectation"))
            default_executable = ""
            if known is not None and known.cli_name is not None:
                suffix = ".exe" if runtime == "windows-native" else ""
                default_executable = known.cli_name + suffix
            providers[provider_id] = ProviderConfig(
                id=provider_id,
                executable=self.string(raw, "executable", path, default_executable),
                auth_expectation=self.string(
                    raw, "auth_expectation", path, "subscription", ("subscription",)
                ),
            )
        return providers

    def _agents(
        self, data: Mapping[str, Any], providers: Mapping[str, ProviderConfig]
    ) -> dict[str, AgentConfig]:
        table = self.table(data, "agents", "", required=True) or {}
        agents: dict[str, AgentConfig] = {}
        for agent_id, raw in table.items():
            path = f"agents.{agent_id}"
            self.identifier(agent_id, path)
            if not isinstance(raw, dict):
                self.add(ErrorCode.INVALID_TYPE, path, "table이어야 한다")
                continue
            self.keys(raw, path, ("provider", "model", "effort", "perspective"))
            provider_id = self.required_string(raw, "provider", path)
            model_id = self.required_string(raw, "model", path)
            self._check_agent_model(path, provider_id, model_id, providers)
            agents[agent_id] = AgentConfig(
                id=agent_id,
                provider=provider_id,
                model=model_id,
                effort=self.optional_string(raw, "effort", path),
                perspective=self.string(raw, "perspective", path, "general", PERSPECTIVES),
            )
        return agents

    def _check_agent_model(
        self,
        path: str,
        provider_id: str,
        model_id: str,
        providers: Mapping[str, ProviderConfig],
    ) -> None:
        if provider_id == "":
            return
        known = registry.get_provider(provider_id)
        if known is None:
            self.add(ErrorCode.UNKNOWN_REFERENCE, f"{path}.provider", "registry에 없는 회사다")
            return
        if not known.enabled:
            self.add(ErrorCode.INVALID_VALUE, f"{path}.provider", "선택할 수 없는 회사다")
            return
        if provider_id not in providers:
            self.add(
                ErrorCode.UNKNOWN_REFERENCE,
                f"{path}.provider",
                f"providers.{provider_id} table이 없다",
            )
        if model_id != "" and registry.get_model(provider_id, model_id) is None:
            names = _choices_text([m.id for m in known.models])
            self.add(
                ErrorCode.INVALID_VALUE,
                f"{path}.model",
                f"{model_id!r}는 registry에 없다. 전체 모델 ID만 쓸 수 있다: {names}",
            )

    def _pipeline(self, data: Mapping[str, Any]) -> PipelineConfig:
        table = self.table(data, "pipeline", "", required=True) or {}
        path = "pipeline"
        self.keys(
            table,
            path,
            ("flow", "max_revision_rounds", "invocation_timeout_seconds")
            + ("run_timeout_seconds", "block_up_to"),
        )
        return PipelineConfig(
            flow=self.required_string(table, "flow", path, FLOWS),
            max_revision_rounds=self.integer(table, "max_revision_rounds", path, 2, 0),
            invocation_timeout_seconds=self.integer(
                table, "invocation_timeout_seconds", path, 600, 1
            ),
            run_timeout_seconds=self.integer(table, "run_timeout_seconds", path, 3600, 1),
            block_up_to=self.string(table, "block_up_to", path, "P2", BLOCK_LEVELS),
        )

    def _roles(
        self, data: Mapping[str, Any], agents: Mapping[str, AgentConfig], flow: str
    ) -> dict[str, RoleConfig]:
        table = self.table(data, "roles", "", required=True) or {}
        self.keys(table, "roles", tuple(ROLE_ACCESS))
        roles: dict[str, RoleConfig] = {}
        for name, default_access in ROLE_ACCESS.items():
            required = name != "tester" or flow == TESTER_FLOW
            raw = self.table(table, name, "roles", required=required)
            if raw is None:
                continue
            path = f"roles.{name}"
            allowed = ("agents", "access") + (("test_paths",) if name == "tester" else ())
            self.keys(raw, path, allowed)
            agent_ids = self.string_list(raw, "agents", path, default=None, min_items=1)
            self._check_role_agents(name, path, agent_ids, agents)
            test_paths: tuple[str, ...] = ()
            if name == "tester":
                test_paths = self.path_list(
                    raw, "test_paths", path, default=("tests/",), min_items=1
                )
            roles[name] = RoleConfig(
                name=name,
                agents=agent_ids,
                access=self.string(raw, "access", path, default_access, (default_access,)),
                test_paths=test_paths,
            )
        return roles

    def _check_role_agents(
        self, name: str, path: str, agent_ids: tuple[str, ...], agents: Mapping[str, AgentConfig]
    ) -> None:
        full = f"{path}.agents"
        if name != "reviewer" and len(agent_ids) > 1:
            self.add(
                ErrorCode.INVALID_COUNT,
                full,
                f"{name}는 정확히 1명이어야 한다(추가 배정은 reviewer만)",
            )
        for index, agent_id in enumerate(agent_ids):
            if agent_id in agent_ids[:index]:
                self.add(ErrorCode.DUPLICATE_ID, full, f"같은 agent가 중복돼 있다: {agent_id!r}")
            elif agent_id not in agents:
                self.add(ErrorCode.UNKNOWN_REFERENCE, full, f"agents.{agent_id}가 없다")

    def _prepare(self, data: Mapping[str, Any]) -> PrepareConfig:
        table = self.table(data, "prepare", "", required=True) or {}
        path = "prepare"
        self.keys(
            table,
            path,
            ("network", "commands", "dependency_paths", "manifest_paths")
            + ("on_lock_change", "on_dependency_change"),
        )
        return PrepareConfig(
            network=self.string(table, "network", path, "allowed", ("allowed",)),
            commands=self._prepare_commands(table, path),
            dependency_paths=self.path_list(table, "dependency_paths", path, default=None),
            manifest_paths=self.path_list(table, "manifest_paths", path, default=()),
            on_lock_change=self.string(table, "on_lock_change", path, "stop", ("stop",)),
            on_dependency_change=self.string(
                table, "on_dependency_change", path, "stop", ("stop",)
            ),
        )

    def _command_items(
        self, table: Mapping[str, Any], path: str
    ) -> list[tuple[str, Mapping[str, Any]]]:
        full = _join(path, "commands")
        raw_list = table.get("commands", [])
        if not isinstance(raw_list, list):
            self.add(ErrorCode.INVALID_TYPE, full, "table 배열이어야 한다")
            return []
        items: list[tuple[str, Mapping[str, Any]]] = []
        for index, raw in enumerate(raw_list):
            item = f"{full}[{index}]"
            if isinstance(raw, dict):
                items.append((item, raw))
            else:
                self.add(ErrorCode.INVALID_TYPE, item, "table이어야 한다")
        return items

    def _command(
        self,
        raw: Mapping[str, Any],
        item: str,
        default_timeout: int,
        seen: set[str],
        extra_keys: tuple[str, ...],
    ) -> CommandConfig:
        """prepare와 checks 명령이 공유하는 키를 읽는다."""
        self.keys(
            raw,
            item,
            ("id", "argv", "cwd", "launcher", "timeout_seconds", "success_exit_codes") + extra_keys,
        )
        command_id = self.required_string(raw, "id", item)
        if command_id != "" and self.identifier(command_id, f"{item}.id"):
            if command_id in seen:
                self.add(ErrorCode.DUPLICATE_ID, f"{item}.id", f"ID가 중복됐다: {command_id!r}")
            seen.add(command_id)
        launcher = self.string(raw, "launcher", item, "direct", LAUNCHERS)
        argv = self.string_list(raw, "argv", item, default=None, min_items=1)
        if launcher == "cmd-wrapper":
            self._check_cmd_wrapper(f"{item}.argv", argv)
        return CommandConfig(
            id=command_id,
            argv=argv,
            cwd=self.directory(raw, "cwd", item, "."),
            launcher=launcher,
            timeout_seconds=self.integer(raw, "timeout_seconds", item, default_timeout, 1),
            success_exit_codes=self._exit_codes(raw, item),
        )

    def _prepare_commands(self, table: Mapping[str, Any], path: str) -> tuple[CommandConfig, ...]:
        seen: set[str] = set()
        return tuple(
            self._command(raw, item, 900, seen, ())
            for item, raw in self._command_items(table, path)
        )

    def _check_commands(
        self, table: Mapping[str, Any], path: str
    ) -> tuple[CheckCommandConfig, ...]:
        seen: set[str] = set()
        commands: list[CheckCommandConfig] = []
        for item, raw in self._command_items(table, path):
            base = self._command(raw, item, 300, seen, ("source", "trial", "scratch_paths"))
            source = self.required_string(raw, "source", item, CHECK_SOURCES)
            trial_default = "doctor-once" if source == "custom" else "not-required"
            commands.append(
                CheckCommandConfig(
                    id=base.id,
                    argv=base.argv,
                    cwd=base.cwd,
                    launcher=base.launcher,
                    timeout_seconds=base.timeout_seconds,
                    success_exit_codes=base.success_exit_codes,
                    source=source,
                    trial=self.string(raw, "trial", item, trial_default, (trial_default,)),
                    scratch_paths=self.path_list(raw, "scratch_paths", item, default=()),
                )
            )
        return tuple(commands)

    def _exit_codes(self, raw: Mapping[str, Any], path: str) -> tuple[int, ...]:
        key = "success_exit_codes"
        if key not in raw:
            return (0,)
        value = raw[key]
        full = _join(path, key)
        if not isinstance(value, list) or any(
            isinstance(v, bool) or not isinstance(v, int) for v in value
        ):
            self.add(ErrorCode.INVALID_TYPE, full, "정수 배열이어야 한다")
        elif value != [0]:
            self.add(ErrorCode.INVALID_VALUE, full, "제안 명세에서는 [0]만 허용한다")
        return (0,)

    def _check_cmd_wrapper(self, path: str, argv: tuple[str, ...]) -> None:
        """D15: 경로에 공백이 없고 인자에 쓸 수 없는 문자가 없을 때만 cmd-wrapper를 허용한다."""
        if not argv:
            return
        if any(ch.isspace() for ch in argv[0]):
            self.add(ErrorCode.INVALID_VALUE, path, "cmd-wrapper의 wrapper 경로에 공백이 있다(D15)")
        for arg in argv[1:]:
            bad = sorted(set(arg) & _CMD_UNSAFE_CHARS)
            if bad:
                self.add(
                    ErrorCode.INVALID_VALUE,
                    path,
                    f"cmd-wrapper 인자에 쓸 수 없는 문자가 있다: {arg!r}(D15)",
                )

    def _checks(
        self,
        data: Mapping[str, Any],
        pipeline: PipelineConfig,
        roles: Mapping[str, RoleConfig],
        prepare: PrepareConfig,
    ) -> ChecksConfig:
        table = self.table(data, "checks", "", required=True) or {}
        path = "checks"
        self.keys(table, path, ("enabled", "network", "commands"))
        enabled = self.boolean(table, "enabled", path, True)
        commands = self._check_commands(table, path)
        if enabled and not commands:
            self.add(
                ErrorCode.INVALID_COUNT,
                "checks.commands",
                "enabled=true이면 검사 명령이 하나 이상 필요하다",
            )
        if not enabled and pipeline.flow == TESTER_FLOW:
            self.add(ErrorCode.CONFLICT, "checks.enabled", "tester flow에서는 false로 둘 수 없다")
        tester = roles.get("tester")
        protected = (tester.test_paths if tester else ()) + prepare.manifest_paths
        for index, command in enumerate(commands):
            where = f"checks.commands[{index}]"
            if command.timeout_seconds > pipeline.run_timeout_seconds:
                self.add(
                    ErrorCode.CONFLICT,
                    f"{where}.timeout_seconds",
                    "pipeline.run_timeout_seconds 이하여야 한다",
                )
            for scratch in command.scratch_paths:
                if any(_overlaps(scratch, other) for other in protected):
                    self.add(
                        ErrorCode.INVALID_PATH,
                        f"{where}.scratch_paths",
                        f"{scratch!r}가 test 경로나 lock 경로와 겹친다",
                    )
        return ChecksConfig(
            enabled=enabled,
            network=self.string(table, "network", path, "blocked", ("blocked",)),
            commands=commands,
        )

    def _git(self, data: Mapping[str, Any]) -> GitConfig:
        table = self.table(data, "git", "", required=True) or {}
        path = "git"
        self.keys(table, path, ("hooks", "interactive_signing", "on_no_change"))
        return GitConfig(
            hooks=self.string(table, "hooks", path, "run", ("run",)),
            interactive_signing=self.string(
                table, "interactive_signing", path, "stop-before-commit", ("stop-before-commit",)
            ),
            on_no_change=self.string(
                table, "on_no_change", path, "finish-without-commit", ("finish-without-commit",)
            ),
        )

    def _output(self, data: Mapping[str, Any]) -> OutputConfig:
        table = self.table(data, "output", "", required=True) or {}
        path = "output"
        self.keys(table, path, ("mode", "publish", "remote", "base_branch", "github_repo"))
        repo = self.optional_string(table, "github_repo", path)
        if repo is not None and not _REPO_PATTERN.match(repo):
            self.add(ErrorCode.INVALID_VALUE, "output.github_repo", "OWNER/REPO 형식이어야 한다")
        return OutputConfig(
            mode=self.string(table, "mode", path, "branch", ("branch",)),
            publish=self.string(table, "publish", path, "push", PUBLISH_MODES),
            remote=self.string(table, "remote", path, "origin"),
            base_branch=self.optional_string(table, "base_branch", path),
            github_repo=repo,
        )

    def _cross_checks(self, config: Config) -> None:
        if config.pipeline.invocation_timeout_seconds > config.pipeline.run_timeout_seconds:
            self.add(
                ErrorCode.CONFLICT,
                "pipeline.run_timeout_seconds",
                "invocation_timeout_seconds 이상이어야 한다",
            )
        used = {config.agents[a].provider for a in config.active_agent_ids if a in config.agents}
        if config.project.runtime == "wsl2" and used and "claude" not in used:
            self.add(
                ErrorCode.CONFLICT,
                "project.runtime",
                "flow가 Codex만 쓰면 wsl2를 쓸 수 없다",
            )
