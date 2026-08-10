# Rondo

Rondo는 Codex CLI, Claude Code, Gemini CLI를 대체하지 않습니다. 세 도구를 그대로 사용하면서 한 프로젝트의 작업 맥락을 이어 주고, 사용량 제한 시 다른 AI로 넘기며, 구현과 최종 검증을 분리하는 작은 보조 도구입니다.

## 핵심 기능

- Codex, Claude, Gemini만 지원하며 `rondo setup`에서 자유롭게 켜고 끌 수 있습니다.
- 프로젝트별 `.rondo/context.md`에 목표, 체크포인트, 변경 요약, 인계와 검증 결과만 기록합니다.
- 확실한 사용량·쿼터 소진 문구가 두 번 확인되면 다음 활성 AI에 자동으로 인계합니다.
- 구현에 참여한 세션은 자기 작업의 최종 검증 결과를 승인할 수 없습니다.
- AI 사이의 체크포인트, 메시지, 인계, 검증 요청은 Relay 탭에 텍스트로 모두 표시됩니다.

전체 대화, AI의 내부 추론, 공급자 인증정보는 수집하지 않습니다. 별도 서버나 모델 API도 사용하지 않습니다.

## 설치

먼저 사용할 공식 CLI 중 하나 이상을 설치하고 로그인하세요.

- `codex` - OpenAI Codex CLI
- `claude` - Anthropic Claude Code
- `gemini` - Google Gemini CLI

Windows PowerShell:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/ppupy1209/rondo/v0.15.3/install.ps1))) -Version v0.15.3
```

macOS / Linux:

```sh
curl -fsSL https://raw.githubusercontent.com/ppupy1209/rondo/v0.15.3/install.sh | RONDO_VERSION=v0.15.3 sh
```

설치기는 Python 3.10 이상을 확인하고 Zellij 0.44.3을 검증된 SHA-256으로 설치합니다. AI 공급자 CLI는 설치하거나 업데이트하지 않습니다.

## 처음 사용하기

어느 프로젝트 디렉터리에서든 실행합니다.

```text
rondo
```

첫 실행에서 방향키로 이동하고 `Space`로 AI를 선택·해제한 뒤 `Enter`로 완료합니다. AI 이름을 직접 입력할 필요가 없습니다. 이후에는 `rondo`만 입력하면 같은 프로젝트의 Rondo 화면으로 바로 들어갑니다.

AI가 두 개면 `Agents` 탭에서 좌우로 배치합니다. 세 개면 첫 AI는 왼쪽의 큰 패널, 나머지 둘은 오른쪽 위아래 패널로 배치해 각 CLI의 읽을 공간을 확보합니다. 마우스로 패널을 누르거나 `Ctrl+p`를 누른 뒤 방향키로 AI를 이동할 수 있습니다. `Ctrl+p` 다음 `f`로 현재 패널을 확대하거나 복원합니다.

Relay는 별도 탭이며 `Ctrl+t`를 누른 뒤 방향키로 전환합니다. 하단의 Zellij 상태 표시줄에서 현재 사용할 수 있는 단축키를 확인할 수 있습니다. 세션을 유지하고 나가려면 `Ctrl+o` 다음 `d`, AI와 세션을 모두 종료하려면 `Ctrl+q`를 누릅니다. Rondo는 글꼴 호환성이 높은 단순 UI, 기본 모드 `normal`, 마우스 `on`으로 시작합니다.

macOS와 Linux에서는 Rondo 전용 짧은 Zellij 소켓 경로를 사용합니다. 프로젝트 경로나 시스템 임시 경로가 길어도 `session name must be less than 0 characters` 오류가 발생하지 않습니다.

## 권장 흐름

Claude에서 일을 시작한 예입니다.

```text
rondo task "로그인 API 구현"
# Claude가 작업 중 핵심 상태를 남김
rondo checkpoint "로그인 API 구현 완료, 통합 테스트가 남음"
rondo next codex
```

Codex는 `.rondo/context.md`를 읽고 이어서 작업합니다. 준비가 끝나면 구현 세션에서 다음을 실행합니다.

```text
rondo request-review gemini
```

Gemini의 독립 세션은 테스트와 리뷰 후 결과를 기록합니다.

```text
rondo review pass "단위·통합 테스트 통과, 차단 이슈 없음"
```

구현 세션에서 같은 명령을 실행하면 Rondo가 거부합니다. 같은 공급자라도 새 세션 ID라면 독립 검증자로 사용할 수 있습니다.

## 명령

```text
rondo                         AI 분할 패널과 Relay 열기
rondo setup                   사용할 AI 변경
rondo context on|off          맥락 공유 켜기/끄기
rondo task "목표"             작업 목표 기록
rondo checkpoint "요약"       이어갈 핵심 상태 기록
rondo next [AI] ["요약"]      다음 AI로 인계
rondo message <AI> "메시지"   공개 메시지 전달
rondo request-review [AI]     독립 검증 요청
rondo review pass|fail "요약" 검증 결과 기록
rondo status                  현재 상태 확인
```

## 프로젝트 데이터

Rondo는 프로젝트 루트에 다음 파일을 만듭니다.

```text
.rondo/
  config.json       활성 AI, 맥락 공유, 자동 인계 설정
  state.json        작업·세션·체크포인트·검증 상태
  context.md        최대 32 KiB의 구조화된 인계 맥락
  messages.jsonl    최대 1 MiB의 공개 Relay 메시지
  layout.kdl        현재 프로젝트의 탭 구성
```

`/.rondo/`는 해당 저장소의 `.git/info/exclude`에만 추가됩니다. 팀 저장소의 `.gitignore`는 바꾸지 않으며 기본적으로 커밋되지 않습니다. `rondo context off`는 `context.md`를 지우고 이후 생성을 멈춥니다. Relay 메시지와 최소 세션 상태는 기능 동작을 위해 남습니다.

토큰처럼 보이는 값은 저장 전에 가리지만 `.rondo`는 비밀 저장소가 아닙니다. 메시지와 체크포인트에 비밀번호, 토큰, 개인정보를 넣지 마세요.

## 자동 인계의 범위

Rondo는 화면에서 명확한 사용량·쿼터 소진 문구를 연속 두 번 확인한 경우에만 자동 인계합니다. 일반 오류, 네트워크 실패, 사용자의 종료, 모호한 종료 코드는 자동 인계하지 않습니다. 대상 AI가 승인·신뢰·선택 화면을 기다리면 입력을 강제로 보내지 않고 Relay에 메시지만 남깁니다.

## 업그레이드

0.15.0 설치기는 0.14.x가 만든 Rondo 전용 전역 훅과 상태표시 항목만 제거합니다. 기존 Claude/Gemini 설정 파일은 먼저 `.rondo-v014.bak`으로 백업하며 다른 훅과 설정은 보존합니다. 이전의 `ai`, `handoff`, `race`, `proof`, 상태 대시보드 실행 파일은 설치 경로에서 제거됩니다.

## 개발

```sh
python3 -m py_compile bin/rondo bin/rondo-agent-session bin/rondo-relay lib/rondo/core.py lib/rondo/cleanup.py
python3 -m unittest discover -s tests -v
sh -n install.sh
```

라이선스는 [MIT](LICENSE)이며, 설치되는 Zellij 고지 사항은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 있습니다. 보안 제보 방법은 [SECURITY.md](SECURITY.md)를 확인하세요.
