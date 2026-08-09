"""Independent test sessions and optional k6/Prometheus/Grafana evidence."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .gitcmd import GitError, git
from .paths import CACHE, atomic_json, read_json, repo_key

TestError = GitError

ALL_PROFILES = ("red", "blue", "reliability", "audit")
PROFILES = {
    "red": "Attack the implementation: abuse cases, hostile inputs, boundary conditions, auth bypasses, and the strongest counterexample.",
    "blue": "Defend the implementation: expected behavior, regressions, recovery, observability, and whether the controls stop the red-team cases.",
    "reliability": "Test load, concurrency, race conditions, deadlocks, idempotency, transaction atomicity, isolation, rollback, and retry behavior.",
    "audit": "Perform security testing and an actionable code review, including dependencies, secrets, permissions, injection, data exposure, and changed tests.",
    "load": "Run or inspect the load test evidence. Check throughput, latency percentiles, failures, saturation, and whether the thresholds are meaningful.",
    "security": "Test security boundaries: authentication, authorization, injection, secrets, dependencies, unsafe defaults, and data exposure.",
    "concurrency": "Test races, deadlocks, lost updates, duplicate work, idempotency, ordering, cancellation, and retry behavior.",
    "transaction": "Test atomicity, isolation, rollback, partial failures, retries, timeouts, and consistency across transaction boundaries.",
    "review": "Review the actual implementation diff and tests. Report only actionable findings with severity, file:line, impact, and a concrete fix.",
}
PROFILES_KO = {
    "red": "구현을 공격적으로 검증하세요. 악의적 입력, 경계값, 권한 우회와 가장 강한 반례를 찾습니다.",
    "blue": "정상 흐름, 회귀, 방어 통제, 복구와 관측 가능성을 검증하고 레드팀 사례가 실제로 차단되는지 확인합니다.",
    "reliability": "부하, 동시성, race/deadlock, 멱등성, 트랜잭션 원자성·격리·롤백·재시도를 검증합니다.",
    "audit": "의존성, 비밀값, 권한, injection, 데이터 노출과 변경된 테스트를 포함해 보안 테스트와 코드 리뷰를 수행합니다.",
    "load": "부하 테스트를 실행하거나 증거를 검토해 처리량, 지연 백분위, 실패, 포화와 임계치의 타당성을 확인합니다.",
    "security": "인증·인가, injection, 비밀값, 의존성, 위험한 기본값과 데이터 노출 경계를 검증합니다.",
    "concurrency": "race, deadlock, 갱신 유실, 중복 실행, 멱등성, 순서, 취소와 재시도를 검증합니다.",
    "transaction": "원자성, 격리, 롤백, 부분 실패, 재시도, timeout과 트랜잭션 경계의 일관성을 검증합니다.",
    "review": "실제 구현 diff와 테스트를 검토하고 심각도·파일:줄·영향·수정 방법이 있는 실행 가능한 문제만 보고합니다.",
}
MAX_PROFILES = 4
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
REPORT_NAME = ".rondo-test/report.md"
REPORT_COMPLETE = "<!-- RONDO_TEST_COMPLETE -->"
K6_IMAGE = "grafana/k6:2.1.0"
PROMETHEUS_IMAGE = "prom/prometheus:v3.12.0"
GRAFANA_IMAGE = "grafana/grafana:13.1.1"
RENDERER_IMAGE = "grafana/grafana-image-renderer:v5.10.3"


@dataclass
class TestRun:
    root: Path
    run_id: str
    base: str
    parent: str
    implementer: str
    implementer_session: str
    started_at: float
    roles: dict[str, dict] = field(default_factory=dict)
    load: dict = field(default_factory=dict)
    tab_id: str = ""
    zellij_session: str = ""
    zellij_socket: str = ""

    def to_json(self) -> dict:
        return {
            "root": str(self.root),
            "run_id": self.run_id,
            "base": self.base,
            "parent": self.parent,
            "implementer": self.implementer,
            "implementer_session": self.implementer_session,
            "started_at": self.started_at,
            "roles": self.roles,
            "load": self.load,
            "tab_id": self.tab_id,
            "zellij_session": self.zellij_session,
            "zellij_socket": self.zellij_socket,
        }

    @classmethod
    def from_json(cls, value: dict) -> "TestRun":
        return cls(
            root=Path(value["root"]),
            run_id=value["run_id"],
            base=value["base"],
            parent=value["parent"],
            implementer=value.get("implementer") or "unknown",
            implementer_session=value.get("implementer_session") or "unknown",
            started_at=float(value.get("started_at") or 0),
            roles=dict(value.get("roles") or {}),
            load=dict(value.get("load") or {}),
            tab_id=str(value.get("tab_id") or ""),
            zellij_session=str(value.get("zellij_session") or ""),
            zellij_socket=str(value.get("zellij_socket") or ""),
        )


def test_home(root: Path) -> Path:
    return CACHE / "test" / repo_key(root)


def state_path(root: Path) -> Path:
    return test_home(root) / "current.json"


def load(root: Path) -> TestRun | None:
    value = read_json(state_path(root))
    return TestRun.from_json(value) if value else None


def save(run: TestRun) -> None:
    atomic_json(state_path(run.root), run.to_json())


def expand_profiles(values: list[str]) -> list[str]:
    requested = values or ["all"]
    expanded: list[str] = []
    for value in requested:
        names = ALL_PROFILES if value == "all" else (value,)
        for name in names:
            if name not in PROFILES:
                raise TestError(f"unknown test profile: {name}")
            if name not in expanded:
                expanded.append(name)
    if len(expanded) > MAX_PROFILES:
        raise TestError(f"choose no more than {MAX_PROFILES} test profiles")
    return expanded


def _git_with_index(root: Path, index: Path, *args: str) -> str:
    env = os.environ | {"GIT_INDEX_FILE": str(index)}
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        timeout=120, env=env,
    )
    if done.returncode:
        raise TestError(done.stderr.strip() or done.stdout.strip())
    return done.stdout.strip()


def freeze_base(root: Path, directory: Path) -> tuple[str, str]:
    """Create an unreferenced commit containing tracked and untracked working files."""
    parent = git(root, "rev-parse", "HEAD").strip()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    index = directory / "snapshot.index"
    index.unlink(missing_ok=True)
    try:
        _git_with_index(root, index, "read-tree", parent)
        _git_with_index(root, index, "add", "-A")
        tree = _git_with_index(root, index, "write-tree")
        base = _git_with_index(
            root, index, "commit-tree", tree, "-p", parent,
            "-m", "Rondo independent test snapshot",
        )
    finally:
        index.unlink(missing_ok=True)
    return base, parent


def start(
    root: Path,
    profiles: list[str],
    implementer: str,
    implementer_session: str,
    testers: list[str],
) -> TestRun:
    if load(root):
        raise TestError("an independent test run is already active")
    profiles = expand_profiles(profiles)
    if not testers:
        raise TestError("choose at least one tester")

    run_id = uuid.uuid4().hex[:8]
    directory = test_home(root) / run_id
    base, parent = freeze_base(root, directory)
    run = TestRun(
        root=root.resolve(), run_id=run_id, base=base, parent=parent,
        implementer=implementer, implementer_session=implementer_session,
        started_at=time.time(),
    )
    made: list[Path] = []
    try:
        for index, profile in enumerate(profiles):
            agent = testers[index % len(testers)]
            worktree = (directory / "worktrees" / profile).resolve()
            worktree.parent.mkdir(parents=True, exist_ok=True)
            git(root, "worktree", "add", "--detach", str(worktree), base)
            made.append(worktree)
            session = uuid.uuid4().hex
            run.roles[profile] = {
                "agent": agent,
                "worktree": str(worktree),
                "session": session,
                "report": str(worktree / REPORT_NAME),
            }
    except TestError:
        for worktree in made:
            git(root, "worktree", "remove", "--force", str(worktree), check=False)
        raise
    save(run)
    return run


def role_prompt(run: TestRun, profile: str, language: str = "en") -> str:
    role = run.roles[profile]
    load_evidence = (
        run.load.get("graph") or run.load.get("log")
        or run.load.get("error") or "not provided"
    )
    if language == "ko":
        return (
            "[Rondo 독립 테스트 세션]\n"
            f"변경할 수 없는 분리 원칙: 구현 세션 {run.implementer_session}({run.implementer})와 "
            f"이 검증 세션 {role['session']}({role['agent']})은 서로 다릅니다. 구현 대화를 재개하거나 재사용하지 마세요.\n"
            "이곳은 폐기 가능한 격리 worktree입니다. 제품 소스를 수정하지 마세요. 임시 테스트 코드가 필요하면 "
            ".rondo-test/ 아래에만 작성하세요. 실제 명령을 실행하고 확인하지 않은 주장을 통과 처리하지 마세요. "
            "`git diff HEAD^ HEAD`로 스냅샷과 부모를 비교할 수 있습니다.\n"
            f"역할: {profile}. {PROFILES_KO[profile]}\n"
            f"부하 테스트 증거: {load_evidence}\n"
            f"최종 보고서를 {role['report']}에 작성하세요. 실행 명령, 관찰 결과, 발견 사항, 남은 위험과 "
            f"주장별 PASS/FAIL/INCONCLUSIVE를 포함하고, 완전히 작성한 뒤 마지막 줄에 {REPORT_COMPLETE}를 "
            "넣으세요. 커밋하거나 push하지 마세요."
        )
    return (
        "[Rondo independent test session]\n"
        f"Immutable separation rule: implementation session {run.implementer_session} "
        f"({run.implementer}) is not this test session {role['session']} ({role['agent']}). "
        "Never resume or reuse the implementation conversation.\n"
        "This is a disposable isolated worktree. Do not modify product source. If temporary test "
        "code is needed, keep it under .rondo-test/. Run real checks and do not treat an unverified "
        "claim as a pass. Compare the snapshot with its parent using `git diff HEAD^ HEAD`.\n"
        f"Role: {profile}. {PROFILES[profile]}\n"
        f"Load evidence: {load_evidence}\n"
        f"Write the final report to {role['report']} with commands, observed results, findings, "
        f"remaining risks, and PASS/FAIL/INCONCLUSIVE per claim. Only when complete, put "
        f"{REPORT_COMPLETE} on the final line. Do not commit or push."
    )


def report_complete(path: str | Path) -> bool:
    try:
        return Path(path).read_text(encoding="utf-8").rstrip().endswith(REPORT_COMPLETE)
    except OSError:
        return False


def changed_outside_test_dir(worktree: Path, base: str = "HEAD") -> list[str]:
    tracked = git(worktree, "diff", "--name-only", base, check=False).splitlines()
    untracked = git(
        worktree, "ls-files", "--others", "--exclude-standard", check=False
    ).splitlines()
    return sorted({
        name for name in tracked + untracked
        if name and not name.replace("\\", "/").startswith(".rondo-test/")
    })


def _remove_worktree(root: Path, worktree: Path) -> None:
    git(root, "worktree", "remove", "--force", str(worktree), check=False)
    if worktree.exists():
        shutil.rmtree(worktree, ignore_errors=True)


def finish(run: TestRun) -> dict:
    reports = test_home(run.root) / "reports" / run.run_id
    reports.mkdir(parents=True, exist_ok=True, mode=0o700)
    results: list[dict] = []
    for profile, role in run.roles.items():
        worktree = Path(role["worktree"])
        source = Path(role["report"])
        target = reports / f"{profile}.md"
        violations = changed_outside_test_dir(worktree, run.base) if worktree.exists() else []
        if source.is_file():
            shutil.copyfile(source, target)
            os.chmod(target, 0o600)
        if violations:
            patch = reports / f"{profile}-violation.patch"
            patch.write_text(
                git(worktree, "diff", "--binary", run.base, check=False),
                encoding="utf-8",
            )
            os.chmod(patch, 0o600)
        results.append({
            "profile": profile,
            "agent": role["agent"],
            "report": str(target) if target.is_file() else "",
            "violations": violations,
        })
        _remove_worktree(run.root, worktree)

    summary = reports / "summary.md"
    lines = [
        "# Rondo independent test report", "",
        f"- Run: `{run.run_id}`",
        f"- Implementer: `{run.implementer}` / session `{run.implementer_session}`",
        "- Rule: implementation session was never used for testing", "",
    ]
    if run.load:
        lines += ["## Load evidence", ""]
        for key in ("status", "target", "summary", "graph", "log"):
            if run.load.get(key):
                lines.append(f"- {key}: `{run.load[key]}`")
        if run.load.get("graph"):
            lines += ["", f"![Grafana load-test graph]({run.load['graph']})"]
        lines.append("")
    lines += ["## Independent sessions", ""]
    for item in results:
        state = "VIOLATION" if item["violations"] else ("REPORTED" if item["report"] else "MISSING")
        lines.append(f"- {item['profile']} · {item['agent']} · **{state}** · {item['report'] or 'no report'}")
        if item["violations"]:
            lines.append(f"  - Product source changed by tester: {', '.join(item['violations'])}")
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(summary, 0o600)
    state_path(run.root).unlink(missing_ok=True)
    git(run.root, "worktree", "prune", check=False)
    return {"summary": str(summary), "results": results}


def abort(run: TestRun) -> None:
    for role in run.roles.values():
        _remove_worktree(run.root, Path(role["worktree"]))
    state_path(run.root).unlink(missing_ok=True)
    git(run.root, "worktree", "prune", check=False)


def allowed_load_url(value: str, allow_remote: bool = False) -> bool:
    if any(character in value for character in "\r\n\0"):
        return False
    parsed = urllib.parse.urlparse(value)
    local = parsed.hostname in LOCAL_HOSTS or bool(
        parsed.hostname and parsed.hostname.endswith(".localhost")
    )
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
        and (local or allow_remote)
    )


def validate_load_options(vus: int, duration: str) -> None:
    if not 1 <= vus <= 1000:
        raise TestError("vus must be between 1 and 1000")
    match = re.fullmatch(r"([1-9][0-9]*)(s|m)", duration)
    seconds = int(match.group(1)) * (60 if match and match.group(2) == "m" else 1) if match else 0
    if not match or seconds > 3600:
        raise TestError("duration must be between 1s and 60m")


def _docker_target(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.hostname not in LOCAL_HOSTS and not (parsed.hostname or "").endswith(".localhost"):
        return value
    host = "host.docker.internal" + (f":{parsed.port}" if parsed.port else "")
    return urllib.parse.urlunparse(parsed._replace(netloc=host))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_load_stack(directory: Path, grafana_port: int) -> None:
    (directory / "provisioning" / "datasources").mkdir(parents=True)
    (directory / "provisioning" / "dashboards").mkdir(parents=True)
    (directory / "dashboards").mkdir()
    (directory / "artifacts").mkdir()
    (directory / "prometheus.yml").write_text(
        "global:\n  scrape_interval: 5s\nscrape_configs:\n"
        "  - job_name: prometheus\n    static_configs:\n      - targets: ['prometheus:9090']\n"
    )
    (directory / "provisioning" / "datasources" / "prometheus.yml").write_text(
        "apiVersion: 1\ndatasources:\n  - name: Prometheus\n    type: prometheus\n"
        "    uid: prometheus\n    access: proxy\n    url: http://prometheus:9090\n    isDefault: true\n"
    )
    (directory / "provisioning" / "dashboards" / "provider.yml").write_text(
        "apiVersion: 1\nproviders:\n  - name: Rondo\n    type: file\n"
        "    options:\n      path: /var/lib/grafana/dashboards\n"
    )
    panels = [
        ("Requests / sec", "sum(rate(k6_http_reqs_total{testid=\"$testid\"}[15s]))"),
        ("HTTP p95 (ms)", "max(k6_http_req_duration_p95{testid=\"$testid\"})"),
        ("Failure rate", "max(k6_http_req_failed_rate{testid=\"$testid\"})"),
        ("Virtual users", "sum(k6_vus{testid=\"$testid\"})"),
    ]
    dashboard = {
        "uid": "rondo-k6", "title": "Rondo k6 evidence", "schemaVersion": 39,
        "time": {"from": "now-15m", "to": "now"},
        "templating": {"list": [{
            "name": "testid", "type": "textbox", "label": "testid", "current": {"text": "", "value": ""}
        }]},
        "panels": [{
            "id": index + 1, "title": title, "type": "timeseries",
            "gridPos": {"h": 8, "w": 12, "x": (index % 2) * 12, "y": (index // 2) * 8},
            "datasource": {"type": "prometheus", "uid": "prometheus"},
            "targets": [{"refId": "A", "expr": expression}],
        } for index, (title, expression) in enumerate(panels)],
    }
    (directory / "dashboards" / "rondo-k6.json").write_text(json.dumps(dashboard))
    (directory / "compose.yml").write_text(f"""services:
  prometheus:
    image: {PROMETHEUS_IMAGE}
    command: [--config.file=/etc/prometheus/prometheus.yml, --web.enable-remote-write-receiver]
    volumes: [./prometheus.yml:/etc/prometheus/prometheus.yml:ro]
  renderer:
    image: {RENDERER_IMAGE}
  grafana:
    image: {GRAFANA_IMAGE}
    ports: [\"127.0.0.1:{grafana_port}:3000\"]
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: \"true\"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer
      GF_ANALYTICS_REPORTING_ENABLED: \"false\"
      GF_ANALYTICS_CHECK_FOR_UPDATES: \"false\"
      GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES: \"false\"
      GF_RENDERING_SERVER_URL: http://renderer:8081/render
      GF_RENDERING_CALLBACK_URL: http://grafana:3000/
    volumes:
      - ./provisioning:/etc/grafana/provisioning:ro
      - ./dashboards:/var/lib/grafana/dashboards:ro
  k6:
    image: {K6_IMAGE}
    depends_on: [prometheus]
    extra_hosts: [\"host.docker.internal:host-gateway\"]
    environment:
      K6_NO_USAGE_REPORT: \"true\"
      K6_PROMETHEUS_RW_SERVER_URL: http://prometheus:9090/api/v1/write
      K6_PROMETHEUS_RW_TREND_STATS: p(90),p(95),p(99),min,max
    volumes:
      - ./script.js:/script.js:ro
      - ./artifacts:/artifacts
""")


def _generated_k6_script() -> str:
    return """import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: Number(__ENV.RONDO_VUS || 10),
  duration: __ENV.RONDO_DURATION || '30s',
  maxRedirects: 0,
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<1000'] },
};

export default function () {
  const response = http.get(__ENV.RONDO_TARGET_URL, { tags: { name: 'rondo-target' } });
  check(response, { 'status below 500': (value) => value.status < 500 });
  sleep(0.1);
}

export function handleSummary(data) {
  return { '/artifacts/summary.json': JSON.stringify(data, null, 2) };
}
"""


def _wait_for_grafana(port: int, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(1)
    raise TestError("Grafana did not become ready")


def run_load(
    run: TestRun,
    target: str | None,
    script: str | None,
    vus: int = 10,
    duration: str = "30s",
    allow_remote: bool = False,
) -> dict:
    validate_load_options(vus, duration)
    if not script and not target:
        raise TestError("load testing requires --url or --script")
    if target and not allowed_load_url(target, allow_remote):
        raise TestError("only localhost is allowed unless --allow-remote is present")
    if script and not allow_remote:
        raise TestError(
            "custom k6 scripts can choose their own targets; inspect the script and pass --allow-remote"
        )
    if shutil.which("docker") is None:
        result = {"status": "missing", "error": "Docker with Compose is required"}
        run.load = result
        save(run)
        return result

    source = None
    if script:
        source = (run.root / script).resolve()
        if run.root.resolve() not in source.parents or not source.is_file():
            raise TestError("load script must be a file inside the repository")

    directory = test_home(run.root) / "load" / run.run_id
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    port = _free_port()
    _write_load_stack(directory, port)
    if source:
        shutil.copyfile(source, directory / "script.js")
    else:
        (directory / "script.js").write_text(_generated_k6_script())

    project = f"rondo{repo_key(run.root)[:8]}{run.run_id}"
    compose = ["docker", "compose", "-p", project, "-f", "compose.yml"]
    log = directory / "artifacts" / "k6.log"
    graph = directory / "artifacts" / "grafana.png"
    summary = directory / "artifacts" / "summary.json"
    output = ""
    status = "failed"
    started = int(time.time() * 1000)
    try:
        up = subprocess.run(
            [*compose, "up", "-d", "prometheus", "renderer", "grafana"],
            cwd=directory, capture_output=True, text=True, timeout=300,
        )
        output += up.stdout + up.stderr
        if up.returncode:
            raise TestError("the observability stack did not start")
        _wait_for_grafana(port)
        env = [
            "-e", f"RONDO_TARGET_URL={_docker_target(target) if target else ''}",
            "-e", f"RONDO_VUS={vus}", "-e", f"RONDO_DURATION={duration}",
        ]
        tested = subprocess.run(
            [*compose, "run", "--rm", *env, "k6", "run", "-o", "experimental-prometheus-rw",
             "--tag", f"testid={run.run_id}", "/script.js"],
            cwd=directory, capture_output=True, text=True, timeout=3900,
        )
        output += tested.stdout + tested.stderr
        status = "passed" if tested.returncode == 0 else "failed"
        time.sleep(6)
        query = urllib.parse.urlencode({
            "orgId": 1, "from": started - 10_000, "to": int(time.time() * 1000) + 10_000,
            "var-testid": run.run_id, "width": 1400, "height": 900, "tz": "UTC",
        })
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/render/d/rondo-k6/rondo-k6?{query}", timeout=120
        ) as response:
            image = response.read()
        if not image.startswith(b"\x89PNG"):
            raise TestError("Grafana did not return a PNG graph")
        graph.write_bytes(image)
        os.chmod(graph, 0o600)
    except (OSError, subprocess.SubprocessError, TestError) as exc:
        status = "failed"
        output += f"\n{exc}\n"
    finally:
        try:
            down = subprocess.run(
                [*compose, "down", "--volumes"], cwd=directory,
                capture_output=True, text=True, timeout=180,
            )
            output += down.stdout + down.stderr
            if down.returncode:
                status = "failed"
                output += "\nFailed to stop the load-test stack cleanly.\n"
        except (OSError, subprocess.SubprocessError) as exc:
            status = "failed"
            output += f"\nFailed to stop the load-test stack: {exc}\n"
        log.write_text(output[-20_000:], encoding="utf-8")
        os.chmod(log, 0o600)

    result = {
        "status": status,
        "target": target or script or "",
        "vus": vus,
        "duration": duration,
        "summary": str(summary) if summary.is_file() else "",
        "graph": str(graph) if graph.is_file() else "",
        "log": str(log),
    }
    run.load = result
    save(run)
    return result
