# 어댑터 계층

## 왜

Rondo 는 각 CLI 가 로컬에 남긴 파일을 읽는다. 그 파일들은 전부 **문서화되지 않은 내부 구조**다.

```
~/.codex/state_5.sqlite            threads.thread_source, threads.model
~/.codex/sessions/**/*.jsonl       rate_limits.primary.used_percent
~/.gemini/antigravity-cli/…/*.db   protobuf blob 안의 모델명 문자열
Claude statusLine JSON             rate_limits.five_hour.used_percentage
```

벤더가 올리면 조용히 깨진다. 실제로 겪은 것들:

- `immutable=1` 로 SQLite 를 열었더니 WAL 을 통째로 무시해 방금 만든 세션이 안 보였다.
- `threads` 최신 행이 서브에이전트(`codex-auto-review`) 여서 엉뚱한 모델이 떴다.
- 한도 값을 프로젝트별로 캐시해 다른 레포에서 영영 안 나왔다.

셋 다 **화면에 `-` 만 뜨고 이유는 어디에도 안 나왔다.** 그게 이 계층이 푸는 문제다.

그리고 같은 벤더 지식이 세 파일에 흩어져 있었다.

| 개념 | 중복 |
|---|---|
| Claude `five_hour` / `used_percentage` | `ai-status`, `rondo-claude-status`, `rondo-relay` |
| `battery()` | `ai-status`, `rondo-claude-status` |
| `repo_key()` | 3곳 |
| `setting()` | 4곳 |

## 규칙

> **벤더 경로·스키마·필드 이름을 아는 코드는 그 벤더의 어댑터 하나뿐이다.**

화면·릴레이·doctor 는 `Snapshot` 만 본다. 벤더가 `used_percent` 로 주든 `remaining` 으로 주든
어댑터 경계에서 **남은 비율**로 통일한다. 화면이 남은 양만 그리기 때문이다.

## 구조

```
lib/rondo/
  model.py            Window · Snapshot · Check
  paths.py            CACHE · CONFIG · repo_key · setting · atomic_json
  registry.py         어댑터 목록 + 벤더 버전 지문
  adapters/
    base.py           Adapter 기반 클래스
    codex.py          state_5.sqlite + rollout
    claude.py         statusLine payload + 공유 한도 캐시
    gemini.py         대화 DB(모델) + agy -p /usage(한도)
    kimi.py grok.py   (예정) 패널 존재만
```

`bin/` 스크립트는 심볼릭 링크로 설치되므로 경로를 이렇게 잡는다.

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
```

## 값

```python
Window(label="5h", remaining=28.0, resets_at=1786244381.0)   # 항상 '남은' 비율
Snapshot(agent="codex", model="gpt-5.6-sol xhigh",
         windows=[...], age=0.0, source="state_5.sqlite + rollout", error=None)
Check(capability="limits", ok=True, detail="rollout rate_limits · 1개 창")
```

- `age` — 바탕 데이터가 쓰인 뒤 흐른 초. `0` 이면 실시간. Claude 한도처럼 CLI 가 그려줄 때만
  갱신되는 값은 이 값으로 `6m전` 을 붙인다.
- `error` — 못 읽은 이유. **빈 값과 고장을 구분하려고 있다.**

## Adapter

```python
class Adapter:
    name, binary, pane_command
    capabilities: tuple[str, ...]        # "model" | "limits" | "transcript"

    def installed(self) -> bool
    def version(self) -> str | None      # 지문용. 실패해도 예외 없음
    def snapshot(self, root) -> Snapshot # 읽기 실패는 error 로, 예외는 안 던진다
    def diagnose(self, root) -> list[Check]
```

`snapshot()` 은 절대 예외를 올리지 않는다. 상태 바는 5초마다 도는 루프고, 한 벤더의 고장이
다른 패널 표시를 죽이면 안 된다.

## 버전 지문 — 조용한 고장 잡기

`registry.check_fingerprint(adapter, root)` 가 `~/.cache/rondo/adapters.json` 에
`{벤더: {version, ok: [되는 capability]}}` 를 기록한다.

벤더 버전이 바뀌었는데 되던 capability 가 빠지면 문장을 돌려준다.

```
codex 0.147.0 → 0.150.0: 'limits' 를 더 못 읽습니다 (rollout 에 rate_limits 없음 — 스키마 변경 가능)
```

이 세션 중에도 codex 가 0.144 → 0.147 로 올라갔다. 다음번엔 사용자가 이유를 안다.

## 테스트 두 층

**픽스처 테스트** (`tests/test_adapters.py`) — CLI 없이 CI 에서 돈다. 임시 SQLite 와 rollout
을 만들어 검증한다.

- 서브에이전트 행이 안 골라진다
- 다른 레포 행이 안 섞인다
- `used_percent` → `remaining` 뒤집힘이 맞다
- `secondary` 가 없어도 오류가 아니다
- **필드 이름이 바뀌면 빈 값이 아니라 "스키마 변경 가능" 이 나온다**
- 지문이 회귀를 잡는다

이 테스트가 이미 버그를 하나 잡았다. `"rate_limits": {` 처럼 값 앞에 공백이 있으면
`raw_decode` 가 실패했다. 지금 codex 는 compact 로 쓰지만 거기 기댈 이유가 없다.

**라이브 테스트** — 설치된 CLI 로 실제 파일을 읽는다. CI 에선 건너뛰고 개발 기계에서 돈다.

```sh
python3 -m unittest tests.test_adapters      # 픽스처, 항상
rondo doctor --deep                          # 라이브, 설치된 것만
```

`--deep` 출력 예:

```
벤더 데이터 점검
  claude 2.1.226 (Claude Code)
    ✗ model      이 레포의 캐시 없음/오래됨
    ✗ limits     rate_limits 없음 — 구독 계정으로 메시지를 한 번 보내야 실린다
  codex codex-cli 0.147.0
    ✓ model      threads.model
    ✓ limits     rollout rate_limits · 1개 창
  ! 벤더 업데이트로 깨진 항목: codex 0.147.0 → 0.150.0: 'limits' 를 더 못 읽습니다
```

회귀가 있으면 **종료 코드 1** 이라 CI 나 스크립트에서 잡을 수 있다. 설치 누락(`doctor_hint`)과
벤더 회귀는 원인이 달라 안내 문구를 섞지 않는다.

## 옮기는 순서

기존 파일을 한 번에 갈아엎지 않는다. 어댑터를 먼저 세우고 호출부를 하나씩 옮긴다.

1. ~~`lib/rondo/model.py`, `adapters/base.py`, `registry.py`~~ (완료)
2. ~~`adapters/codex.py` + 계약 테스트~~ (완료)
3. ~~`adapters/claude.py` — 세 곳의 파싱을 하나로~~ (완료)
4. ~~`adapters/gemini.py` — 대화 DB 스크래핑과 `/usage` 캐시~~ (완료)
5. ~~`bin/ai-status` 를 렌더러로만 남긴다~~ (완료 — 419줄 → 178줄, 벤더 지식 0)
6. ~~`rondo doctor --deep` 에 어댑터 진단 + 지문 경고 연결~~ (완료)
7. `kimi` / `grok` 어댑터는 그 CLI 가 로컬에 상태를 남기기 시작하면 추가

3번을 하면서 실제로 어긋나 있던 것이 드러났다. `seven_day` 라벨이 `ai-status` 와
`rondo-claude-status` 에서는 `wk`, `rondo-relay` 에서는 `7d` 였다. 이제 `WINDOW_KEYS` 한 줄이
정한다.

## 어댑터 추가하기

`lib/rondo/adapters/<이름>.py` 에 `Adapter` 를 상속하고 `adapters/__init__.py` 와
`registry._ADAPTERS` 에 등록한다. 파일 하나와 픽스처 테스트가 기여 단위다.
