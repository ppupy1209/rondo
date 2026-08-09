# Rondo

> 하나의 프로젝트, 모든 코딩 에이전트, 끊기지 않는 하나의 작업 흐름.

[English](README.en.md)

Rondo는 Claude Code, Codex, Gemini, Kimi, Grok을 하나의 영속적인 터미널 작업공간에서 실행합니다. 여러 창을 오가는 번거로움을 없애고, 로컬 사용량과 에이전트 간 위임을 화면에 보여주며, Claude 사용량이 바닥나면 진행 중인 일을 Codex로 이어 줍니다.

주요 기능은 다음과 같습니다.

- Git 프로젝트마다 유지되는 하나의 작업공간
- 한국어·영어와 실행할 에이전트를 고르는 선택형 설정
- 최대 4개 패널과 모든 에이전트에 공통 적용되는 승인 모드
- 모든 에이전트 패널에 함께 적용되는 사용자별 설명 수준
- 모델·사용량·인계 상태를 한눈에 보는 공통 상태 표시줄
- `rondo send`를 통한 화면에 보이는 에이전트 간 요청
- 사용자 승인형 프로젝트 기억·재사용 절차와 작업 이력 검색
- Rondo Lens를 통한 화면 요소 단위 프론트엔드 요청
- Rondo Proof를 통한 실행 가능한 증거와 위험 기반 사람 검토 큐
- 구현 세션과 물리적으로 분리되는 레드팀·블루팀·신뢰성·보안 테스트
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

설치가 끝나면 작업할 Git 저장소에서 다음 명령 하나만 실행합니다.

```sh
rondo
```

최초 실행에만 언어·설명 수준·승인 모드·에이전트·인계 전략을 고르고, 저장 직후 패널로 이동합니다. 다음 실행부터는 같은 저장소의 기존 패널로 바로 들어갑니다. 설정을 바꿀 때만 `rondo setup`을 실행하세요.

이미 clone한 저장소에서 설치하려면 macOS/Linux는 `sh install.sh`, Windows PowerShell은 `.\install.ps1`을 실행합니다. 업데이트하거나 설치를 복구할 때도 같은 명령을 다시 실행하면 됩니다.

기존 `ai-tools` 설정은 첫 실행 때 자동 이전합니다. 예전 `ai`, `ai-status`, `claude-statusline` 명령도 호환 별칭으로 계속 동작합니다.

## 빠른 시작

```sh
cd ~/projects/my-project
rondo             # 프로젝트 작업공간 열기 / 다시 붙기
rondo setup       # 저장된 언어·설명·승인·에이전트·인계 설정 변경
rondo audience    # 모든 에이전트의 결과 설명 수준 변경
rondo add         # 에이전트를 선택해 패널 추가
rondo send codex "현재 diff를 검토해 주세요"  # Codex 패널에 입력하고 전송
rondo learn pending  # 에이전트와 사용자가 제안한 프로젝트 지식 검토
rondo recall "인증"  # 승인 지식·작업 이력·최근 Git 커밋 검색
rondo lens        # 화면 요소를 클릭해 해당 맥락만 전달
rondo proof       # 검증 실행 후 위험 기반 검토 패킷 생성
rondo test all --from codex --tester claude  # 구현자와 분리된 독립 테스트
rondo git         # Git 연결·브랜치·PR 정책·리뷰어 확인
rondo doctor      # 설치와 설정 진단
```

처음 `rondo`를 실행하면 setup 선택 화면이 자동으로 열립니다. 방향키로 이동하고, Space로 에이전트를 최대 4개까지 선택하고, Enter로 저장합니다. 이름이나 모드를 직접 입력하지 않으므로 오타가 생기지 않습니다.

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

Rondo가 시작하는 모든 에이전트 패널과 지원되는 복원 세션에는 저장된 단계가 자동 적용됩니다. 열린 Rondo 세션 안에서 `rondo audience`를 실행하면 모든 에이전트 패널에 새 기준이 화면에 보이게 전달되고 이후 답변부터 적용됩니다. 이 브로드캐스트는 에이전트 사용량을 소모할 수 있으므로 Rondo가 대상 패널 수를 먼저 알립니다. 대화형 설정 없이 사용하려면 `RONDO_AUDIENCE=default|nondev|guided`를 지정합니다.

## 공통 승인 모드

setup에서 고른 승인 모드는 모든 에이전트의 네이티브 옵션으로 변환됩니다.

| 모드 | 동작 |
|---|---|
| `ask` | 위험한 편집과 명령을 실행하기 전에 사용자에게 확인하는 기본값 |
| `workspace` | Claude `acceptEdits`, Codex `approve-for-me` 등 각 CLI의 작업공간 자동 승인 사용 |

`workspace`는 반복 승인을 줄이지만 Kimi·Grok 등 공급자에 따라 자동 승인되는 명령 범위가 더 넓을 수 있습니다. 신뢰하는 저장소에서만 사용하세요. 샌드박스를 완전히 해제하는 권한 우회 모드는 Rondo에서 제공하지 않습니다. 설정을 바꾸면 다음에 시작하거나 복원되는 모든 에이전트 패널부터 같은 모드가 적용됩니다.

## 화면에 보이는 에이전트 간 위임

`rondo send`는 열려 있는 에이전트 패널을 찾아 대화형 CLI에 메시지를 붙여넣고 Enter까지 전달합니다. 요청은 사용자가 직접 입력했을 때와 같은 위치에 나타나며, 별도의 숨겨진 에이전트 프로세스를 실행하지 않습니다.

```sh
rondo send codex "현재 diff를 검토하고 테스트를 마무리해 주세요"
rondo send claude "제안된 API 설계를 확인해 주세요"
rondo send gemini "다른 구현 방식을 조사해 주세요"
```

Rondo 세션 안에서 대상 패널이 열린 상태로 실행해야 합니다. 각 에이전트도 셸 도구에서 같은 명령을 실행할 수 있으므로 사용자의 직접 요청, 에이전트 간 위임, 자동 인계가 모두 화면에 보이는 하나의 입력 경로를 사용합니다.

전송 전에 패널 화면을 읽어 신뢰·승인·선택 프롬프트가 보이면 아무 키도 누르지 않고 중단합니다. 안전한 화면에서는 메시지를 먼저 붙여넣고 입력란에 실제로 보이는지 확인한 뒤에만 Enter를 보냅니다. 따라서 Rondo가 사용자 대신 폴더 신뢰 여부를 승인하지 않습니다.

## 승인형 프로젝트 기억과 절차

Rondo는 저장소별로 오래 유지할 사실과 반복 가능한 작업 절차를 보관합니다. 사용자와 에이전트 모두 제안할 수 있지만, 제안은 승인 전까지 검색 결과와 에이전트 시작 지침에 절대 포함되지 않습니다. 미승인 원문은 에이전트가 목록이나 `show`로 읽을 수도 없습니다.

```sh
rondo learn memory "공개 API 변경에는 호환성 설명을 남긴다"
rondo learn skill release-check "테스트 보고서를 확인한 뒤 사용자 승인 후 배포한다"
rondo learn pending                 # 승인 대기 목록
rondo learn show a1b2c3d4           # 원문 확인
rondo learn approve a1b2c3d4        # 원문 재표시 + y/N 승인
rondo learn reject a1b2c3d4
rondo learn remove a1b2c3d4         # 승인된 항목 삭제

rondo recall "호환성"               # 승인 지식·Rondo 작업 이력·최근 100개 커밋 검색
rondo recall --id a1b2c3d4          # 절차 원문을 ID로 불러오기
```

승인된 `memory`는 새 에이전트 세션에 제한된 크기로 공유됩니다. `skill`은 이름·ID·첫 줄 요약만 공유하고, 에이전트가 필요할 때 `rondo recall --id ...`로 원문을 불러옵니다. 절차는 참고 텍스트일 뿐 플러그인이나 실행 코드로 활성화되지 않습니다. 이미 열려 있는 세션은 `rondo recall`로 새 항목을 확인할 수 있습니다.

승인·거절·삭제는 대화형 사용자 터미널에서만 가능하며, Rondo 안에서는 현재 프로세스가 `shell` 탭에 있는지도 확인합니다. 에이전트 패널, race 탭, 파이프·스크립트 실행에서는 거부합니다. 제안은 2,000자, 승인 기억은 총 4,000자, 절차는 16개로 제한하고, 일반적인 비밀값·프롬프트 주입·파괴 명령 패턴과 보이지 않는 제어 문자를 저장 전에 차단합니다. 여러 에이전트의 동시 쓰기는 저장소별 잠금으로 직렬화하며, 손상되거나 심볼릭 링크로 바뀐 상태 파일은 사용하지 않습니다.

검색 이력에는 Rondo가 만든 짧은 작업 이벤트와 Git 커밋 제목만 들어가며 Claude·Codex·Gemini 대화 원문을 수집하지 않습니다. 데이터는 네트워크 서비스 없이 `~/.cache/rondo/knowledge/`에 비공개 권한으로 저장됩니다. 같은 운영체제 사용자 권한을 이미 가진 악성 프로세스를 격리하는 비밀 저장소는 아니므로 토큰·비밀번호 같은 민감정보는 기록하지 마세요.

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

Rondo는 변경 파일을 낮음·중간·높음으로 분류합니다. 인증, 권한, 결제, 마이그레이션, 보안, 배포 경로와 선언한 scope 밖의 변경은 고위험이며 여러 이유가 겹치면 모두 표시합니다. 변경 줄 수에 따라 검토 시간을 계산하고, `__pycache__`, `dist`, `build`, `node_modules`, `.venv`, `target` 같은 생성물은 제외합니다. 변경이 하나도 없으면 승인 후보가 아니라 `변경 없음`으로 표시합니다. Python unittest, npm test/lint, Gradle, Cargo, Go 검증은 프로젝트 파일을 보고 자동으로 찾으며 `--check "명령"`으로 작업별 검증을 추가할 수 있습니다.

독립 reviewer는 기존 구현 대화를 이어받지 않는 새 패널에서 실행됩니다. Codex는 read-only sandbox, Claude는 plan 권한으로 열리고 구현 코드를 수정하지 않은 채 실제 diff와 증거에서 가장 강한 반례를 찾도록 요청받습니다. `ready`는 자동 승인이 아니라 검토 후보라는 뜻이며, 인증·결제·DB 등 고위험 변경은 항상 사람 검토 큐에 남습니다.

작업 의도와 Proof 패킷은 `~/.cache/rondo/proof/`에 권한 `0600`으로 저장되며 Git에 포함되지 않습니다. 검증 출력에는 프로젝트 데이터가 포함될 수 있으므로 패킷을 외부에 공유하기 전에는 내용을 확인하세요.

## Race·스냅샷·복원

```sh
rondo race "두 가지 구현안을 비교" --agents claude,codex
rondo race --status                 # 진행 상태
rondo diff codex                    # 특정 결과 diff
rondo take codex                    # 선택한 결과 적용
rondo race --abort                  # 결과 폐기, patch는 보존

rondo snap "리팩터링 전"
rondo undo --list                   # 스냅샷 ID 확인
rondo undo a1b2c3d4                 # 해당 ID로 복원, 변경 경로 표시 후 확인
rondo undo --steps 2 --yes          # 두 단계 전으로 비대화형 복원
```

`undo`는 커밋 이력을 바꾸지 않고 작업 트리만 복원합니다. 추적하지 않는 파일도 변경 대상에 포함되므로 기본적으로 사전 목록과 `y/N` 확인을 요구하며, 자동화에서만 `--yes`를 명시하세요. 복원 직전 상태도 새 스냅샷으로 보존됩니다.

## 구현자와 분리된 독립 테스트

Rondo의 테스트 원칙은 설정으로 끄거나 완화할 수 없습니다.

> 구현에 사용한 에이전트 세션은 테스트에 사용하지 않습니다. 같은 종류의 에이전트를 선택해도 기존 대화를 재개하지 않고 새 세션에서 검증합니다.

예를 들어 Codex가 구현했다면 다음 두 방식이 모두 가능합니다.

```sh
rondo test all --from codex --tester claude  # Codex 구현 → 새 Claude 세션 검증
rondo test all --from codex --tester codex   # Codex 구현 → 새 Codex 세션 검증
```

에이전트 패널 안에서 실행하면 구현자와 구현 세션 ID를 자동으로 기록합니다. shell 탭에서 실행할 때는 `--from codex`처럼 구현자를 지정합니다. `--tester`를 생략하면 선택 화면이 열리며 여러 에이전트를 고르면 역할별로 순환 배정됩니다.

`all`은 최대 4개 패널 원칙에 맞춰 서로 대화를 공유하지 않는 네 개의 격리 세션을 만듭니다.

| 역할 | 검증 범위 |
|---|---|
| `red` | 악의적 입력, 경계값, 권한 우회, 가장 강한 반례 |
| `blue` | 정상 흐름, 회귀, 방어 통제, 복구와 관측 가능성 |
| `reliability` | 부하, 동시성, race/deadlock, 멱등성, 트랜잭션·롤백·격리 |
| `audit` | 보안, 의존성, 비밀값, 권한, injection, 실제 diff 코드 리뷰 |

필요한 범위만 `rondo test security`, `rondo test concurrency`, `rondo test transaction`, `rondo test review`처럼 실행할 수도 있습니다. 모든 검증자는 현재 변경분을 담은 별도 Git worktree에서 시작합니다. 임시 테스트 코드는 `.rondo-test/`에만 작성하고 제품 코드는 수정하지 않도록 지시됩니다. `rondo test finish` 때 제품 코드 변경이 발견되면 검증 위반으로 기록되며 원본 작업 트리에는 반영되지 않습니다.

```sh
rondo test status    # 역할별 보고서 작성 상태
rondo test finish    # 모든 보고서 완료 후 수집·위반 확인·테스트 탭/worktree 정리
rondo test abort     # 테스트 중단과 격리 worktree 정리
```

### k6·Prometheus·Grafana 부하 테스트

Docker와 Docker Compose가 있으면 Rondo가 일회용 k6·Prometheus·Grafana·Grafana Image Renderer 스택을 열고, 테스트가 끝난 뒤 대시보드 PNG와 k6 결과를 증거 패킷에 남깁니다.

```sh
rondo test load --from codex --tester claude \
  --url http://localhost:8080/api/health --vus 20 --duration 30s

rondo test reliability --from claude --tester codex \
  --script tests/load.js --duration 2m --allow-remote
```

기본 생성 스크립트는 GET 요청만 보내고 redirect를 따라가지 않으며 VU는 1~1000, 실행 시간은 최대 60분으로 제한됩니다. localhost만 기본 허용되고 원격 주소는 대상 시스템의 허가를 받은 뒤 `--allow-remote`를 명시해야 합니다. 저장소 안의 자체 k6 스크립트는 대상 주소를 Rondo가 확실히 판별할 수 없으므로, 내용을 직접 확인한 뒤 `--script ... --allow-remote`로만 실행할 수 있습니다. 관측 도구의 사용량 전송과 업데이트 확인은 꺼져 있습니다. Grafana 그래프, summary JSON, 실행 로그와 독립 에이전트 보고서는 `~/.cache/rondo/test/`에 비공개로 보관됩니다. 버전을 고정한 스택은 캡처 후 자동으로 종료되고 볼륨도 제거됩니다.

## Git·PR·에이전트 코드 리뷰

Git 정책은 전역 설정이 아니라 현재 저장소의 `.git/config`에 저장되므로 프로젝트마다 다르게 유지됩니다.

```sh
rondo git                                      # 연결·브랜치·정책·리뷰어 확인
rondo git connect https://github.com/me/app.git # Git 초기화 또는 origin 연결
rondo git policy                               # direct | pr | review 선택
rondo git reviewers                            # 최대 4개 리뷰 에이전트 선택
```

| 정책 | 동작 |
|---|---|
| `direct` | 현재 브랜치에서 직접 작업 허용 |
| `pr` | 기능 브랜치와 Pull Request 사용 |
| `review` | draft PR을 만들고 독립 에이전트 코드 리뷰 후 병합 |

`pr` 또는 `review` 정책은 모든 에이전트의 시작 지침에도 들어가므로 에이전트마다 다른 Git 방식을 제안하지 않습니다. 커밋된 기능 브랜치에서 다음 명령으로 push와 PR 생성을 한 번에 할 수 있습니다.

```sh
rondo pr "로그인 오류 화면 개선"
rondo code-review all       # 설정한 에이전트가 실제 diff를 각각 읽기 전용 검토
rondo code-review codex     # 한 에이전트만 검토
```

`review` 정책의 `rondo pr`은 draft PR을 만들고, Rondo 세션 안이라면 설정된 reviewer를 자동으로 엽니다. 리뷰 패널은 구현 대화를 이어받지 않으며 Claude는 plan, Codex는 read-only 등 각 CLI의 읽기 전용 모드로 실행됩니다. PR 생성에는 로그인된 GitHub CLI `gh`가 필요합니다.

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
7. `rondo test`가 현재 작업 트리를 커밋이나 인덱스 변경 없이 스냅샷으로 고정하고, 구현 대화를 재사용하지 않는 별도 worktree·세션에서 역할별 검증을 시작합니다.
8. 지원되는 종료 훅과 래퍼가 세션 종료 후 선택적인 Git 핸드오프 로그를 갱신합니다.
9. Claude 사용량이 임계치에 닿으면 로컬 인계 패킷을 준비하고 기존 Codex 패널로 전달할 수 있습니다.

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

`auto`는 setup에서 명시적으로 골라야만 켜지며 Codex 패널이 선택되어 있어야 합니다. Rondo가 해당 패널에 인계 요청을 직접 입력하고, 사용자가 Enter를 누른 것처럼 전송합니다. Codex가 신뢰·승인 화면에서 대기 중이면 자동 전송을 멈추고 모드를 `ready`로 낮춥니다. 요청이 가리키는 비공개 패킷에는 현재 의도, Git 상태, 안전 계약이 들어 있습니다.

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
| `rondo` | 최초 설정 후 현재 프로젝트 세션 열기 / 이후 바로 붙기 |
| `rondo setup` | 언어·설명 수준·승인·최대 4개 패널·인계 모드 변경 |
| `rondo audience [default\|nondev\|guided]` | 모든 에이전트의 결과 설명 수준 변경 |
| `rondo add [agent]` | 패널 추가, 인자를 생략하면 선택 화면 표시 |
| `rondo send <agent> <message>` | 대상 패널에 보이는 요청을 입력하고 전송 |
| `rondo task <목표> [옵션]` | 인수 조건·금지 조건·scope·검증 명령 기록 |
| `rondo learn memory\|skill ...` | 저장소 기억·재사용 절차를 승인 대기로 제안 |
| `rondo learn pending\|show\|approve\|reject\|remove` | 프로젝트 지식의 사용자 승인 수명주기 관리 |
| `rondo recall [검색어\|--id ID]` | 승인 지식·작업 이벤트·최근 Git 이력 검색 |
| `rondo proof [--reviewer 에이전트]` | 검증 실행 후 독립 검토 패킷 생성 |
| `rondo review [--budget 2m]` | 시간 예산 안에서 고위험 사람 판단부터 표시 |
| `rondo git [명령]` | Git 연결 상태와 저장소별 PR·reviewer 정책 관리 |
| `rondo code-review [agent\|all]` | 에이전트별 독립 읽기 전용 코드 리뷰 실행 |
| `rondo test [프로필] [옵션]` | 구현 세션과 분리된 레드·블루·신뢰성·보안 테스트 실행 |
| `rondo pr [제목]` | 현재 기능 브랜치를 push하고 정책에 맞는 PR 생성 |
| `rondo handoff [메모]` | 다른 PC로 옮길 `.rondo/handoff.md` 생성 |
| `rondo resume [claude\|codex]` | 작업공간을 열고 선택한 에이전트에 인계 전달 |
| `rondo lens [URL]` | 화면 요소를 클릭하고 확인 후 해당 맥락만 전달 |
| `rondo race <과제> [옵션]` | 여러 격리 worktree에서 같은 과제 실행 |
| `rondo diff [agent]` / `rondo take <agent>` | race 결과 비교 / 선택 적용 |
| `rondo snap [라벨]` | 현재 작업 트리 스냅샷 생성 |
| `rondo undo [ID\|--steps N] [--yes]` | 대상과 변경 경로를 확인한 뒤 작업 트리 복원 |
| `rondo kill [세션]` | 현재 프로젝트 또는 지정한 Rondo 세션 종료 |
| `rondo clean` | 삭제된 저장소의 로컬 캐시 정리 |
| `rondo language` | 한국어 / English 변경 |
| `rondo relay [off\|ready\|auto]` | 인계 전략 확인 / 변경 |
| `rondo continue` | 대기 중인 인계를 기존 Codex 패널로 전달 |
| `rondo doctor` | zellij·에이전트·설정 점검 |
| `rondo -l` | Rondo 세션만 필터링해 목록 표시 |
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
  approval       ask | workspace
  panels         선택한 에이전트 이름 (최대 4개)
  relay          off | ready | auto
  threshold      남은 사용량 임계치 (기본 1)

~/.cache/rondo/
  layout.kdl     생성된 zellij 레이아웃
  audience/      로컬 agent 파일을 사용하는 CLI용 비공개 시작 지침
  claude.*       로컬 표시 캐시
  lens/          비공개 요소 맥락 파일과 부분 스크린샷
  proof/         비공개 작업 의도, 증거 패킷, 검토 큐
  knowledge/     저장소별 승인 기억·절차와 짧은 작업 이벤트
  test/          독립 테스트 worktree 상태, 보고서, k6 결과와 Grafana 캡처
  relay/         비공개 인계 패킷과 전달 로그
```

저장소별 `rondo.prPolicy`와 `rondo.reviewers`는 `.git/config`에 보관됩니다. 대화형 화면 없이 설정하려면 `rondo setup` 실행 전에 `RONDO_LANG=ko|en`, `RONDO_AUDIENCE=default|nondev|guided`, `RONDO_APPROVAL=ask|workspace`, `RONDO_PANELS=claude,codex,...`, `RONDO_RELAY=off|ready|auto`를 지정합니다.

텔레메트리는 없습니다. Rondo는 자격증명을 저장하지 않으며 프로젝트 지식을 만들기 위해 에이전트 대화 원문을 수집하지 않습니다. 인계 패킷에는 대화 일부가 포함될 수 있으므로, 명시적인 동작 없이 공급자 간 내용 공유를 원하지 않으면 기본 `ready` 모드를 사용하세요.

## 개발 및 검증

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/rondo bin/rondo-agent-session bin/rondo-lens bin/rondo-relay bin/rondo-claude-status bin/ai-status
sh -n install.sh bin/ai bin/rondo-status bin/*-session
```

GitHub Actions에서 macOS, Linux, Windows의 Python 테스트와 설치 smoke test를 실행합니다.

### 내부 문서

- [어댑터 계층](docs/adapters.md) — 각 CLI가 로컬에 남긴 파일을 읽는 방식
- [rondo race](docs/race.md) — 같은 과제를 여러 에이전트에게 시키고 하나를 고르는 흐름
- [실사용 감사 · 2026-08-09](docs/audit-2026-08-09.md) — 0.7.0 전체 명령 실행 결과와 개선 항목

## 라이선스

MIT
