# rondo race — 같은 과제, 여러 에이전트, 사람이 선택

## 무엇

한 과제를 참가 에이전트마다 **격리된 git worktree** 에서 동시에 시키고, 끝나면 diff 를 나란히
놓고 사람이 하나를 고른다. 나머지는 버린다.

```sh
rondo race "업로드 엔드포인트에 rate limiting 추가"
rondo diff              # 세 결과 요약
rondo diff codex        # 그 결과 전체 diff
rondo take codex        # 채택. 나머지 폐기
```

속도를 위한 팬아웃이 아니다. **선택지를 만드는** 병렬이고, 판단은 사람이 한다.

tmux 로는 원리적으로 안 되고, API 키 기반 오케스트레이터는 실제 돈이 나간다. Rondo 는 이미
결제한 구독으로, 이미 열려 있는 패널에서 한다.

## 명령 표면

| 명령 | 하는 일 |
|---|---|
| `rondo race "<과제>"` | 참가자 선정 → worktree 생성 → race 탭에 패널 띄우고 프롬프트 투입 |
| `rondo race --agents claude,codex` | 참가자 직접 지정 (기본은 한도 여유 있는 전원) |
| `rondo race --status` | 진행 중인 race 요약 |
| `rondo diff [에이전트]` | 결과 비교 / 개별 diff |
| `rondo take <에이전트>` | 채택해서 원본 트리에 반영, 나머지 폐기 |
| `rondo race --abort` | 전부 폐기 |

## 동작

### 1. 참가자 선정

어댑터가 이미 남은 한도를 안다. `Snapshot.live_windows()` 의 최소 `remaining` 이 임계
(기본 10%) 미만이면 자동 제외한다. 상태 바를 만든 이유가 여기서 값을 한다.

```
race 참가자
  claude   5h 28% 남음   참가
  codex    wk 89% 남음   참가
  gemini   5h  4% 남음   제외 (한도 부족)

같은 과제를 2개 에이전트에게 보냅니다. 각자 한도를 소모합니다. [y/N]
```

한도를 N 배로 쓰는 명령이라 **확인을 받는다.** 조용히 태우지 않는다.

### 2. 베이스 고정

race 시작 시점의 트리 상태가 모두의 출발점이다. 커밋되지 않은 변경이 있어도 막지 않는다 —
바이브 코더의 트리는 항상 dirty 하다.

```
base = git stash create        # 커밋 안 된 상태를 커밋 객체로 (트리는 안 건드림)
base = base or HEAD            # 깨끗하면 그냥 HEAD
```

`git stash create` 는 stash 목록에도 안 넣고 작업 트리도 안 건드린다. 객체만 만든다.

### 3. worktree 생성

```
~/.cache/rondo/race/<repo-key>/<run-id>/<agent>
브랜치: rondo/race/<run-id>/<agent>
```

**레포 밖에 만든다.** 안에 두면 에이전트가 자기 worktree 를 소스로 착각한다.

```sh
git worktree add -b rondo/race/<run>/<agent> <경로> <base>
```

### 4. 패널 띄우고 프롬프트 투입

race 전용 탭을 만들고, 에이전트마다 자기 worktree 를 cwd 로 하는 패널을 연다.

```sh
zellij action new-tab --name race --cwd <첫 worktree>
zellij action new-pane --name race-codex --cwd <codex worktree> -- codex-session
```

기존 패널은 건드리지 않는다. 실행 중인 프로세스의 cwd 는 바꿀 수 없고, 원래 세션도 살려둬야
한다.

프롬프트는 `rondo send` 와 같은 경로로 넣는다 — 사람이 친 것과 똑같이 보이고, 숨은 실행이
없다.

### 5. 완료 감지 — 하지 않는다

에이전트가 언제 끝났는지 정확히 알 방법이 없다. 추정하면 틀린다.

**사람이 보고 있다.** `rondo diff` 를 사람이 칠 때의 현재 상태를 비교한다. human-in-the-loop
설계와도 맞는다. 자동 감지는 넣지 않는다.

### 6. 비교

에이전트는 대개 커밋하지 않는다. 그래서 커밋이 아니라 **작업 트리**를 본다.

```sh
git -C <wt> add -A -n          # untracked 포함 목록 (인덱스는 안 건드림)
git -C <wt> diff <base>        # 추적 파일 변경
```

```
race 4f2a · base 90de79a · "업로드 엔드포인트에 rate limiting 추가"

  claude   3 files  +142 -18    12분
  codex    2 files  +88  -6      7분
  gemini   5 files  +310 -44    15분

rondo diff codex    전체 diff
rondo take codex    채택
```

### 7. 채택

```sh
git -C <wt> add -A
git -C <wt> commit -m "race/<agent>"     # worktree 브랜치에만
git -C <wt> format-patch <base>..HEAD --stdout > <patch>
git -C <원본> apply -3 <patch>            # 충돌 시 3-way
```

원본 트리에는 **커밋하지 않고 변경만 얹는다.** 커밋 여부는 사람이 정한다.

채택 후 전 worktree 제거 + 브랜치 삭제.

## 안전

- **원본 트리는 race 중 아무도 안 건드린다.** worktree 격리가 핵심 안전장치다.
  단, 에이전트가 절대 경로로 원본을 건드리는 것까지는 막을 수 없다 — 문서로 경고한다.
- race 도중 원본 트리를 직접 수정하지 말 것. `take` 의 `apply -3` 가 충돌한다.
- 한도 N 배 소모는 시작 전에 확인받는다.
- `--abort` 와 `take` 는 worktree 를 지운다. 지우기 전에 patch 를 `~/.cache/rondo/race/`
  에 남겨서, 잘못 눌러도 복구할 수 있게 한다.

## 상태 파일

```
~/.cache/rondo/race/<repo-key>/
  current.json      run-id · base · 과제 · 참가자 · worktree 경로 · 시작 시각
  <run-id>/         worktree 들
  patches/          take·abort 시점의 patch (복구용)
```

## 구현 경계 (1차)

**넣는다**

- worktree 생성·정리
- 참가자 선정 (한도 기준) + 확인 프롬프트
- 패널 생성 + 프롬프트 투입
- diff 요약 / 개별 diff
- take (patch apply) / abort
- 고아 worktree 청소를 `rondo doctor` 에 추가

**안 넣는다 (필요해지면)**

- 자동 완료 감지
- 테스트 자동 실행 (`--verify "npm test"` 는 2차)
- 채택 통계 (`rondo stats` 로 따로)
- 재시도·이어하기

## 코드 배치

git 부분은 순수 함수라 테스트가 쉽다. `bin/rondo` 에는 배선만 둔다.

```
lib/rondo/race.py     worktree 생성/정리 · base 고정 · diff 요약 · patch 적용
bin/rondo             서브커맨드 배선 (race / diff / take)
tests/test_race.py    임시 레포로 전 과정
```

`lib/` 는 새 파일이라 다른 세션 작업과 충돌하지 않는다. `bin/rondo` 배선은 트리가 정리된 뒤에
붙인다.

## 테스트 계획

임시 git 레포를 만들어 실제 worktree 로 검증한다. 에이전트 실행은 mock — 대신 worktree 에
파일을 직접 써서 "에이전트가 작업한 상태" 를 만든다.

- dirty 트리에서 시작해도 base 가 고정된다
- worktree 가 레포 밖에 생기고, 원본 트리가 그대로다
- 커밋하지 않은 에이전트 결과도 diff 에 잡힌다 (untracked 포함)
- take 가 원본에 변경만 얹고 커밋하지 않는다
- take 후 worktree·브랜치가 사라진다
- abort 가 전부 지우고 patch 는 남긴다
- 원본이 그 사이 바뀌었을 때 `apply -3` 가 충돌을 알린다
