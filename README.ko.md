# Rondo

> 하나의 프로젝트, 모든 코딩 에이전트, 끊기지 않는 하나의 작업 흐름.

[English](README.md)

Rondo는 Claude Code, Codex, Gemini, Kimi, Grok을 하나의 영속적인 터미널 작업공간에서 실행합니다. 여러 창을 오가는 번거로움을 없애고, 로컬 사용량과 에이전트 간 위임을 화면에 보여주며, Claude 사용량이 바닥나면 진행 중인 일을 Codex로 이어 줍니다.

주요 기능은 다음과 같습니다.

- Git 프로젝트마다 유지되는 하나의 작업공간
- 한국어·영어와 실행할 에이전트를 고르는 선택형 설정
- 모든 에이전트 패널에 함께 적용되는 사용자별 설명 수준
- 모델·사용량·인계 상태를 한눈에 보는 공통 상태 표시줄
- `rondo send`를 통한 화면에 보이는 에이전트 간 요청
- Rondo Lens를 통한 화면 요소 단위 프론트엔드 요청
- Rondo Proof를 통한 실행 가능한 증거와 위험 기반 사람 검토 큐
- 사용량 한도에서 동작하는 선택형 Claude → Codex 연속 작업

별도 서버·계정·API 키가 필요 없는 로컬 우선 도구입니다. 각 CLI가 이미 내 컴퓨터에 저장한 상태만 읽습니다.

## 설치

### macOS / Linux

```sh
curl -fsSL https://raw.githubusercontent.com/ppupy1209/rondo/main/install.sh | sh
```

필요한 런타임은 Python 3.10 이상뿐입니다. 설치 프로그램이 Rondo와 Zellij를 내려받고 `~/.local/bin`에 명령을 만든 뒤 셸 `PATH`까지 등록합니다.

### Windows

PowerShell을 열고 다음 한 줄을 실행합니다.

```powershell
irm https://raw.githubusercontent.com/ppupy1209/rondo/main/install.ps1 | iex
```

Windows 설치 프로그램이 Rondo와 네이티브 Zellij를 내려받습니다. Python 3.10 이상이 없으면 WinGet으로 Python도 설치합니다. WSL은 필요하지 않습니다. 설치 후 새 터미널을 여세요.

운영체제와 관계없이 실제로 사용할 에이전트 CLI를 하나 이상 설치하면 됩니다. 모든 지원 CLI를 설치할 필요는 없으며, setup에서 현재 설치된 에이전트를 자동으로 찾습니다.

설치가 끝나면 다음 두 명령을 실행합니다.

```sh
rondo setup
rondo
```

이미 clone한 저장소에서 설치하려면 macOS/Linux는 `sh install.sh`, Windows PowerShell은 `.\install.ps1`을 실행합니다. 업데이트하거나 설치를 복구할 때도 같은 명령을 다시 실행하면 됩니다.

기존 `ai-tools` 설정은 첫 실행 때 자동 이전합니다. 예전 `ai`, `ai-status`, `claude-statusline` 명령도 호환 별칭으로 계속 동작합니다.

## 빠른 시작

```sh
cd ~/projects/my-project
rondo             # 프로젝트 작업공간 열기 / 다시 붙기
rondo setup       # 언어·설명 수준·에이전트·인계 전략 선택
rondo audience    # 모든 에이전트의 결과 설명 수준 변경
rondo add         # 에이전트를 선택해 패널 추가
rondo send codex "현재 diff를 검토해 주세요"  # Codex 패널에 입력하고 전송
rondo lens        # 화면 요소를 클릭해 해당 맥락만 전달
rondo proof       # 검증 실행 후 위험 기반 검토 패킷 생성
rondo doctor      # 설치와 설정 진단
```

`rondo setup`에서는 이름을 직접 입력하지 않습니다. 방향키로 이동하고, Space로 선택하고, Enter로 저장합니다. 오타로 잘못된 모델이나 설명 수준을 입력할 여지가 없습니다.

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

## 사용자 수준에 맞춘 설명

Rondo는 코드 품질, 권한, 구현 방식은 바꾸지 않고 모든 에이전트가 결과를 설명하는 깊이만 같은 수준으로 맞춥니다.

| 단계 | 설명 방식 |
|---|---|
| `default` | 각 에이전트의 평소 응답 방식 유지 |
| `nondev` | 실제 결과부터 쉬운 말로 설명하고, 필요한 용어·구체적인 예시·간단한 흐름을 함께 제공 |
| `guided` | 일반 개발 지식은 있다고 보고, 낯선 기술의 역할·동작 원리·선택 이유·핵심 트레이드오프를 보강 |

setup에서 선택하거나 다음 명령으로 바꿀 수 있습니다.

```sh
rondo audience nondev
rondo audience guided
rondo audience default
```

Rondo가 시작하는 모든 에이전트 패널과 지원되는 복원 세션에는 저장된 단계가 자동 적용됩니다. 열린 Rondo 세션 안에서 `rondo audience`를 실행하면 모든 에이전트 패널에 새 기준이 화면에 보이게 전달되고 이후 답변부터 적용됩니다. 대화형 설정 없이 사용하려면 `RONDO_AUDIENCE=default|nondev|guided`를 지정합니다.

## 화면에 보이는 에이전트 간 위임

`rondo send`는 열려 있는 에이전트 패널을 찾아 대화형 CLI에 메시지를 붙여넣고 Enter까지 전달합니다. 요청은 사용자가 직접 입력했을 때와 같은 위치에 나타나며, 별도의 숨겨진 에이전트 프로세스를 실행하지 않습니다.

```sh
rondo send codex "현재 diff를 검토하고 테스트를 마무리해 주세요"
rondo send claude "제안된 API 설계를 확인해 주세요"
rondo send gemini "다른 구현 방식을 조사해 주세요"
```

Rondo 세션 안에서 대상 패널이 열린 상태로 실행해야 합니다. 각 에이전트도 셸 도구에서 같은 명령을 실행할 수 있으므로 사용자의 직접 요청, 에이전트 간 위임, 자동 인계가 모두 화면에 보이는 하나의 입력 경로를 사용합니다.

## Rondo Lens

Lens는 눈으로 보고 내린 프론트엔드 요청을 선택한 요소 범위의 프롬프트로 바꿉니다. Rondo의 shell 탭에서 실행한 뒤 별도로 열린 브라우저에서 바꾸고 싶은 요소를 가리켜 클릭합니다.

```sh
rondo lens                              # 기본 주소: http://localhost:3000/
rondo lens http://localhost:5173/
rondo lens https://staging.example.com --allow-remote
```

가리키는 즉시 요소가 강조되고, 클릭하면 선택되며, Esc로 취소할 수 있습니다. 이어서 터미널에서 명령과 받을 에이전트를 선택합니다. 전송 전에는 URL, 선택자, 포함 데이터, 받는 에이전트를 보여주고 `y/N`으로 다시 확인합니다. 에이전트 패널에는 사용자의 명령과 요소 맥락 파일 경로가 직접 입력되어 전송 과정을 볼 수 있습니다.

맥락 파일에는 선택 요소 주변의 부분 스크린샷, 정리된 DOM과 화면 텍스트, 필요한 계산 스타일, 접근성 정보만 들어갑니다. 폼 입력값은 DOM에서 제거하고 스크린샷을 찍는 순간에도 가립니다. 쿠키, 브라우저 저장소, 자격증명, 전체 화면은 읽지 않습니다. 기본 허용 범위는 localhost이며 원격 페이지는 `--allow-remote`를 명시해야 합니다.

Lens는 격리된 Chrome, Chromium 또는 Microsoft Edge 프로필을 열고 선택이 끝나면 임시 프로필을 삭제합니다. 브라우저를 자동으로 찾지 못하면 `RONDO_BROWSER=/브라우저/실행파일/경로`를 지정할 수 있습니다.

## Rondo Proof

Proof는 전체 diff를 사람에게 넘기는 대신, 작업 의도와 실행 결과를 비교해 사람이 판단해야 할 항목만 추립니다.

```sh
rondo task "로그인 오류 메시지 개선" \
  --accept "잘못된 비밀번호일 때 오류가 보인다" \
  --accept "기존 로그인 성공 동작은 유지된다" \
  --avoid "인증 API는 변경하지 않는다" \
  --scope web

rondo proof                    # 검증 실행 + 증거 패킷 생성
rondo review --budget 2m       # 2분 안에 볼 고위험 항목부터 표시
rondo proof --reviewer codex   # 별도 읽기 전용 Codex 검증 패널 실행
```

Rondo는 변경 파일을 낮음·중간·높음으로 분류합니다. 인증, 권한, 결제, 마이그레이션, 보안, 배포 경로와 선언한 scope 밖의 변경은 고위험입니다. 문서와 테스트만 바뀌면 낮은 위험으로 취급합니다. Python unittest, npm test/lint, Gradle, Cargo, Go 검증은 프로젝트 파일을 보고 자동으로 찾으며 `--check "명령"`으로 작업별 검증을 추가할 수 있습니다.

독립 reviewer는 기존 구현 대화를 이어받지 않는 새 패널에서 실행됩니다. Codex는 read-only sandbox, Claude는 plan 권한으로 열리고 구현 코드를 수정하지 않은 채 실제 diff와 증거에서 가장 강한 반례를 찾도록 요청받습니다. `ready`는 자동 승인이 아니라 검토 후보라는 뜻이며, 인증·결제·DB 등 고위험 변경은 항상 사람 검토 큐에 남습니다.

작업 의도와 Proof 패킷은 `~/.cache/rondo/proof/`에 권한 `0600`으로 저장되며 Git에 포함되지 않습니다. 검증 출력에는 프로젝트 데이터가 포함될 수 있으므로 패킷을 외부에 공유하기 전에는 내용을 확인하세요.

## Handoff와 Resume

어디에서 이어서 작업하는지에 따라 복원 방법이 다릅니다.

### 같은 PC, 재부팅한 경우 포함

같은 저장소에서 다시 `rondo`를 실행하면 됩니다. Rondo가 저장된 zellij 작업공간을 되살리고, Claude Code는 `--continue`, Codex는 `resume --last`로 그 디렉터리의 최근 대화를 이어갑니다. 저장된 대화가 없는 에이전트는 새 대화로 시작합니다.

### 다른 PC

A PC에서 작업을 마치기 전에 벤더에 종속되지 않는 인계 파일을 만듭니다.

```sh
rondo handoff "로그인 테스트를 마무리하고 현재 diff를 검토"
git add .rondo/handoff.md
git commit -m "docs: Rondo 인계 추가"
git push
```

B PC에서 clone 또는 pull한 다음 실행합니다.

```sh
rondo resume codex       # 또는: rondo resume claude
```

선택한 패널에 `.rondo/handoff.md`를 읽으라는 요청이 화면에 보이게 전달됩니다. 이 파일에는 사용자가 적은 메모, origin, 브랜치, HEAD, 작업 트리 파일명·통계, 최근 커밋만 들어갑니다. Rondo는 벤더의 대화 원문, 인증정보, 로컬 경로를 Git에 넣지 않습니다. 커밋하지 않은 코드는 다른 PC로 넘어가지 않으므로 실제 변경분과 인계 파일을 함께 커밋하고 푸시해야 합니다.

## 동작 방식

1. `rondo`가 현재 Git 루트를 찾고 `origin` 주소와 로컬 clone 경로를 조합해 프로젝트별 zellij 세션 하나에 연결합니다.
2. `~/.config/rondo/panels`에 저장된 선택으로 레이아웃을 만들고, 같은 작업 트리에서 각 CLI를 실행합니다. 재부팅 후에는 저장된 zellij 세션과 지원되는 벤더 대화를 다시 엽니다.
3. `rondo-status`가 5초마다 로컬 CLI 상태를 읽어 실제로 열린 패널만 표시합니다.
4. `rondo send`가 Rondo 패널 이름으로 대상을 찾아 zellij를 통해 보이는 요청을 전달합니다.
5. `rondo lens`가 선택한 화면 요소 하나를 비공개 로컬 패킷으로 만들고 확인 후에만 전달합니다.
6. `rondo proof`가 자동으로 검증을 실행하고 위험도를 분류해, 해결되지 않은 판단만 사람 검토 큐에 남깁니다.
7. 지원되는 종료 훅과 래퍼가 세션 종료 후 선택적인 Git 핸드오프 로그를 갱신합니다.
8. Claude 사용량이 임계치에 닿으면 로컬 인계 패킷을 준비하고 기존 Codex 패널로 전달할 수 있습니다.

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
| `rondo setup` | 언어·설명 수준·패널·인계 모드 선택 |
| `rondo audience [default\|nondev\|guided]` | 모든 에이전트의 결과 설명 수준 변경 |
| `rondo add [agent]` | 패널 추가, 인자를 생략하면 선택 화면 표시 |
| `rondo send <agent> <message>` | 대상 패널에 보이는 요청을 입력하고 전송 |
| `rondo task <목표> [옵션]` | 인수 조건·금지 조건·scope·검증 명령 기록 |
| `rondo proof [--reviewer 에이전트]` | 검증 실행 후 독립 검토 패킷 생성 |
| `rondo review [--budget 2m]` | 시간 예산 안에서 고위험 사람 판단부터 표시 |
| `rondo handoff [메모]` | 다른 PC로 옮길 `.rondo/handoff.md` 생성 |
| `rondo resume [claude\|codex]` | 작업공간을 열고 선택한 에이전트에 인계 전달 |
| `rondo lens [URL]` | 화면 요소를 클릭하고 확인 후 해당 맥락만 전달 |
| `rondo language` | 한국어 / English 변경 |
| `rondo relay [off\|ready\|auto]` | 인계 전략 확인 / 변경 |
| `rondo continue` | 대기 중인 인계를 기존 Codex 패널로 전달 |
| `rondo doctor` | zellij·에이전트·설정 점검 |
| `rondo -l` | 살아 있는 세션 목록 |
| `handoff --init` | macOS/Linux에서 선택적인 Git 핸드오프 로그 활성화 |

zellij 안에서는 `Ctrl+p`+방향키로 패널 이동, `Ctrl+t`+방향키로 탭 이동, `Ctrl+o` 다음 `d`로 디태치합니다.

## 선택적인 커밋 이력 로그

위의 PC 간 `rondo handoff`와는 별도 기능입니다. macOS/Linux에서 `handoff --init`을 실행하면 `docs/handoff.md`가 생기고, 에이전트 세션이 끝날 때 직전 핸드오프 이후의 커밋 제목을 기록합니다. 최신 20개만 활성 섹션에 두고 오래된 항목은 지우지 않고 archive로 옮깁니다. 이 선택형 셸 로그는 Windows에 설치하지 않지만 `rondo handoff`와 `rondo resume`은 Windows에서도 동작합니다.

대상 탐색 순서는 `$HANDOFF_FILE`, `docs/collab/status.md`, `docs/handoff.md`입니다. 이 파일이 없는 저장소는 건드리지 않습니다.

## 설정과 개인정보

```text
~/.config/rondo/
  language       ko | en
  audience       default | nondev | guided
  panels         선택한 에이전트 이름
  relay          off | ready | auto
  threshold      남은 사용량 임계치 (기본 1)

~/.cache/rondo/
  layout.kdl     생성된 zellij 레이아웃
  audience/      로컬 agent 파일을 사용하는 CLI용 비공개 시작 지침
  claude.*       로컬 표시 캐시
  lens/          비공개 요소 맥락 파일과 부분 스크린샷
  proof/         비공개 작업 의도, 증거 패킷, 검토 큐
  relay/         비공개 인계 패킷과 전달 로그
```

대화형 화면 없이 설정하려면 `rondo setup` 실행 전에 `RONDO_LANG=ko|en`, `RONDO_AUDIENCE=default|nondev|guided`, `RONDO_PANELS=claude,codex,...`, `RONDO_RELAY=off|ready|auto`를 지정합니다.

텔레메트리는 없습니다. Rondo는 자격증명을 저장하지 않습니다. 인계 패킷에는 대화 일부가 포함될 수 있으므로, 명시적인 동작 없이 공급자 간 내용 공유를 원하지 않으면 기본 `ready` 모드를 사용하세요.

## 개발 및 검증

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/rondo bin/rondo-agent-session bin/rondo-lens bin/rondo-relay bin/rondo-claude-status bin/ai-status
sh -n install.sh bin/ai bin/rondo-status bin/*-session
```

GitHub Actions에서 macOS, Linux, Windows의 Python 테스트와 설치 smoke test를 실행합니다.

## 라이선스

MIT
