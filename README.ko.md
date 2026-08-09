# Rondo

> 하나의 프로젝트, 모든 코딩 에이전트, 끊기지 않는 하나의 작업 흐름.

[English](README.md)

Rondo는 Claude Code, Codex, Gemini, Kimi, Grok을 하나의 영속적인 터미널 작업공간에서 실행합니다. 여러 창을 오가는 번거로움을 없애고, 로컬 사용량과 에이전트 간 위임을 화면에 보여주며, Claude 사용량이 바닥나면 진행 중인 일을 Codex로 이어 줍니다.

주요 기능은 다음과 같습니다.

- Git 프로젝트마다 유지되는 하나의 작업공간
- 한국어·영어와 실행할 에이전트를 고르는 선택형 설정
- 모델·사용량·인계 상태를 한눈에 보는 공통 상태 표시줄
- `rondo send`를 통한 화면에 보이는 에이전트 간 요청
- 사용량 한도에서 동작하는 선택형 Claude → Codex 연속 작업

별도 서버·계정·API 키가 필요 없는 로컬 우선 도구입니다. 각 CLI가 이미 내 컴퓨터에 저장한 상태만 읽습니다.

## 설치

필수 환경은 macOS 또는 Linux, Python 3.10+, Git, [zellij](https://zellij.dev/) 0.44 이상입니다.

```sh
git clone https://github.com/ppupy1209/rondo.git ~/rondo
sh ~/rondo/install.sh
rondo setup
```

설치는 `~/.local/bin`에 symlink를 만듭니다. 이후에는 `git -C ~/rondo pull`만 하면 즉시 업데이트됩니다. `~/.local/bin`이 `PATH`에 있어야 합니다.

기존 `ai-tools` 설정은 첫 실행 때 자동 이전합니다. 예전 `ai`, `ai-status`, `claude-statusline` 명령도 호환 별칭으로 계속 동작합니다.

기존 clone에서 이번 변경을 pull했다면 새 `rondo*` 명령의 symlink를 추가하기 위해 `sh ~/ai-tools/install.sh`을 한 번 실행하세요. 로컬 clone 디렉터리 이름은 `ai-tools` 그대로 두어도 됩니다.

## 빠른 시작

```sh
cd ~/projects/my-project
rondo             # 프로젝트 작업공간 열기 / 다시 붙기
rondo setup       # 언어·에이전트·인계 전략 선택
rondo add         # 에이전트를 선택해 패널 추가
rondo send codex "현재 diff를 검토해 주세요"  # Codex 패널에 입력하고 전송
rondo doctor      # 설치와 설정 진단
```

`rondo setup`에서는 이름을 직접 입력하지 않습니다. 방향키로 이동하고, Space로 선택하고, Enter로 저장합니다. 오타로 잘못된 모델을 입력할 여지가 없습니다.

```text
┌────────────────────────────────────────────────────┐
│ claude 42%   codex 88%   gemini 61%   인계 준비   │
├────────────────────────┬───────────────────────────┤
│                        │          codex            │
│        claude          ├───────────────────────────┤
│                        │          gemini           │
└────────────────────────┴───────────────────────────┘
  탭: agents | shell
```

첫 번째 에이전트는 왼쪽 절반을 쓰고 나머지는 오른쪽에 세로로 쌓입니다. 터미널을 닫거나 디태치해도 zellij 세션은 계속 살아 있습니다.

## 화면에 보이는 에이전트 간 위임

`rondo send`는 열려 있는 에이전트 패널을 찾아 대화형 CLI에 메시지를 붙여넣고 Enter까지 전달합니다. 요청은 사용자가 직접 입력했을 때와 같은 위치에 나타나며, 별도의 숨겨진 에이전트 프로세스를 실행하지 않습니다.

```sh
rondo send codex "현재 diff를 검토하고 테스트를 마무리해 주세요"
rondo send claude "제안된 API 설계를 확인해 주세요"
rondo send gemini "다른 구현 방식을 조사해 주세요"
```

Rondo 세션 안에서 대상 패널이 열린 상태로 실행해야 합니다. 각 에이전트도 셸 도구에서 같은 명령을 실행할 수 있으므로 사용자의 직접 요청, 에이전트 간 위임, 자동 인계가 모두 화면에 보이는 하나의 입력 경로를 사용합니다.

## 동작 방식

1. `rondo`가 현재 Git 루트를 찾아 프로젝트별 zellij 세션 하나에 연결합니다.
2. `~/.config/rondo/panels`에 저장된 선택으로 레이아웃을 만들고, 같은 작업 트리에서 각 CLI를 실행합니다.
3. `rondo-status`가 5초마다 로컬 CLI 상태를 읽어 실제로 열린 패널만 표시합니다.
4. `rondo send`가 Rondo 패널 이름으로 대상을 찾아 zellij를 통해 보이는 요청을 전달합니다.
5. 지원되는 종료 훅과 래퍼가 세션 종료 후 선택적인 Git 핸드오프 로그를 갱신합니다.
6. Claude 사용량이 임계치에 닿으면 로컬 인계 패킷을 준비하고 기존 Codex 패널로 전달할 수 있습니다.

벤더의 채팅 세션 자체를 합치는 방식은 아닙니다. 대신 실제 프로젝트 디렉터리, Git 상태, 영속적인 터미널, 작은 벤더 중립 인계 패킷을 공유합니다.

## Continuity Relay

Claude Code는 로컬 status line 명령에 현재 모델, 사용 한도, 세션 ID, 대화 기록 경로를 전달합니다. Rondo는 활성 한도 중 하나가 남은 사용량 1% 이하가 될 때 이 신호를 사용합니다.

```sh
rondo relay             # 현재 모드와 대기 중인 패킷 확인
rondo relay ready       # 패킷만 준비하고 사용자의 실행을 기다림 (기본값)
rondo relay auto        # 기존 Codex 패널로 즉시 인계
rondo relay off         # 사용량만 표시
rondo continue          # 대기 중인 인계를 기존 Codex 패널로 전달
```

연속성 패킷에는 다음이 들어갑니다.

- 최근 사용자·Claude 메시지의 제한된 일부
- 브랜치, HEAD, 작업 트리 상태, diff 통계, 최근 커밋
- 현재 diff를 먼저 확인하고, 이미 끝난 작업을 반복하지 않고, 결과를 검증하라는 인계 계약

패킷은 `~/.cache/rondo/relay/` 아래에 권한 `0600`으로 저장됩니다. 흔한 토큰 형식은 마스킹하고, Claude 세션과 사용량 리셋 구간별로 중복 실행을 차단하며, Git에는 커밋하지 않습니다. `ready` 모드에서는 `rondo continue`를 실행하기 전까지 Codex로 아무 내용도 보내지 않습니다.

`auto`는 setup에서 명시적으로 골라야만 켜지며 Codex 패널이 선택되어 있어야 합니다. Rondo가 해당 패널에 인계 요청을 직접 입력하고, 사용자가 Enter를 누른 것처럼 전송합니다. 요청이 가리키는 비공개 패킷에는 현재 의도, Git 상태, 안전 계약이 들어 있습니다.

## 지원 에이전트

| 패널 | 실행 파일 | 상태 출처 |
|---|---|---|
| Claude Code | `claude` | Claude status-line JSON |
| Codex CLI | `codex` | 로컬 thread SQLite와 rollout 사용량 스냅샷 |
| Gemini / Antigravity | `agy` | 로컬 대화 DB와 `/usage` 출력 캐시 |
| Kimi Code | `kimi` | 패널 실행 여부만 표시 |
| Grok Build | `grok` | 패널 실행 여부만 표시 |

Rondo는 저장된 자격증명을 읽거나 벤더 API를 직접 호출하지 않습니다. Gemini 패널이 열려 있을 때만 Gemini 자체의 `agy -p "/usage"`를 최대 10분에 한 번 백그라운드에서 실행합니다.

## 주요 명령

| 명령 | 기능 |
|---|---|
| `rondo` | 현재 프로젝트 세션 열기 / 붙기 |
| `rondo setup` | 언어·패널·인계 모드 선택 |
| `rondo add [agent]` | 패널 추가, 인자를 생략하면 선택 화면 표시 |
| `rondo send <agent> <message>` | 대상 패널에 보이는 요청을 입력하고 전송 |
| `rondo language` | 한국어 / English 변경 |
| `rondo relay [off\|ready\|auto]` | 인계 전략 확인 / 변경 |
| `rondo continue` | 대기 중인 인계를 기존 Codex 패널로 전달 |
| `rondo doctor` | zellij·에이전트·설정 점검 |
| `rondo -l` | 살아 있는 세션 목록 |
| `handoff --init` | 저장소에 선택적인 Git 핸드오프 로그 활성화 |

zellij 안에서는 `Ctrl+p`+방향키로 패널 이동, `Ctrl+t`+방향키로 탭 이동, `Ctrl+o` 다음 `d`로 디태치합니다.

## 선택적인 Git 핸드오프 로그

저장소에서 `handoff --init`을 실행하면 `docs/handoff.md`가 생깁니다. 에이전트 세션이 끝날 때 직전 핸드오프 이후의 커밋 제목을 기록합니다. 최신 20개만 활성 섹션에 두고, 오래된 항목은 지우지 않고 archive로 옮깁니다.

대상 탐색 순서는 `$HANDOFF_FILE`, `docs/collab/status.md`, `docs/handoff.md`입니다. 이 파일이 없는 저장소는 건드리지 않습니다.

## 설정과 개인정보

```text
~/.config/rondo/
  language       ko | en
  panels         선택한 에이전트 이름
  relay          off | ready | auto
  threshold      남은 사용량 임계치 (기본 1)

~/.cache/rondo/
  layout.kdl     생성된 zellij 레이아웃
  claude.*       로컬 표시 캐시
  relay/         비공개 인계 패킷과 전달 로그
```

대화형 화면 없이 설정하려면 `rondo setup` 실행 전에 `RONDO_LANG=ko|en`, `RONDO_PANELS=claude,codex,...`, `RONDO_RELAY=off|ready|auto`를 지정합니다.

텔레메트리는 없습니다. Rondo는 자격증명을 저장하지 않습니다. 인계 패킷에는 대화 일부가 포함될 수 있으므로, 명시적인 동작 없이 공급자 간 내용 공유를 원하지 않으면 기본 `ready` 모드를 사용하세요.

## 개발 및 검증

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/rondo bin/rondo-relay bin/rondo-claude-status bin/ai-status
sh -n install.sh bin/ai bin/rondo-status bin/*-session
```

## 라이선스

MIT
