# 변경 이력

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르며 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 사용합니다.

## [0.14.4] - 2026-08-10

### 수정

- Windows에서 Zellij 서버가 비정상 종료된 뒤 PID 표식만 남은 세션을 안전하게 감지하고 자동 정리
- 고아 세션이 활성 세션처럼 표시되어 `list-panes`가 10초 후 실패하던 문제를 새 세션 자동 생성으로 복구
- 실행 중인 Zellij PID 표식과 링크·비정상 표식은 보존하여 정상 세션이나 임의 파일을 삭제하지 않도록 방어
- 실제 Zellij 서버를 강제 종료한 뒤 같은 작업공간이 자동 복구되는 Windows 회귀 검사 추가

## [0.14.3] - 2026-08-10

### 수정

- Windows 첫 실행부터 각 Zellij 클라이언트의 마우스 클릭을 활성화하고 기본 입력 모드를 `normal`로 고정
- 새 레이아웃에서 상태 표시줄 대신 첫 에이전트 패널에 초점을 지정
- 기존 세션 재연결 시 스크롤·잠금 모드를 해제하고 실제 에이전트 패널로 초점을 이동
- 사용자 전역 Zellij 설정 파일을 만들거나 덮어쓰지 않고 Rondo 실행에만 마우스 옵션 적용

## [0.14.2] - 2026-08-10

### 변경

- 첫 설정 뒤에는 Git 저장소 여부와 관계없이 어느 폴더에서든 `rondo`로 해당 위치의 `agents` 패널에 바로 진입
- 활성·복원 세션 연결 직후 `agents` 탭을 강제로 선택하고 새 레이아웃에서도 에이전트 탭을 우선 표시

### 수정

- Windows 실제 Zellij 검사 뒤 테스트 세션이 남으면 성공 처리하지 않도록 정리 검증 강화

## [0.14.1] - 2026-08-10

### 수정

- Windows Zellij 수명 주기 검증이 성공한 뒤 세션 정리 명령의 종료 코드 때문에 실패로 표시되던 오탐 수정
- PR 검사에서 GitHub가 생성한 임시 merge 커밋 대신 실제 head 커밋의 개인 신원을 검증하도록 변경

## [0.14.0] - 2026-08-10

### 추가

- `rondo open --agents <디렉터리...>`로 한 Zellij 세션 안에 디렉터리별 병렬 에이전트 작업공간 생성
- 종료되거나 사라진 에이전트 패널을 기존 활성 세션에 다시 붙을 때 자동 복구
- `rondo history status|on|off|clear`와 `RONDO_HISTORY=off` 개인정보 제어
- Windows에서도 실제 Zellij 시작·입력 전달·종료 수명주기를 검사하는 E2E
- GitHub 릴리스 자산 빌드 증명과 `THIRD_PARTY_NOTICES.md`

### 변경

- GitHub Actions를 전체 커밋 SHA로 고정하고 릴리스를 draft에서 검증 후 게시
- `rondo doctor --deep`이 실제 에이전트 CLI 실행 옵션과 `gh auth` 상태를 점검
- 자동 작업 이력에는 전달한 프롬프트 원문 대신 작업 메타데이터만 저장

### 보안

- 모든 커밋·태그 신원을 `Yeonwoo Kim <ppupy1209@naver.com>`으로 제한하는 로컬 훅과 CI 검사
- Windows launcher와 Unix 링크가 Rondo 소유가 아닌 기존 명령을 덮어쓰지 않도록 차단

## [0.13.1] - 2026-08-10

### 수정

- 최신 Codex CLI에서 제거된 `--approve-for-me` 대신 `workspace-write` 샌드박스와 현재 승인 옵션을 사용해 Windows 패널이 즉시 종료되는 문제 수정
- Windows launcher가 설치 폴더를 자체 PATH에 추가해 새 터미널의 환경 갱신 여부와 관계없이 함께 설치된 Zellij를 찾도록 변경

## [0.13.0] - 2026-08-10

### 추가

- `rondo open <디렉터리...>`로 여러 작업 디렉터리를 한 Zellij 터미널의 영속적인 병렬 탭에서 열고 다시 연결하는 기능
- 같은 이름의 디렉터리 구분, 중복 경로 제거, 존재하지 않는 경로의 사전 차단

## [0.12.4] - 2026-08-10

### 수정

- Windows 설치 파일의 SHA-256 계산이 일시적으로 결과를 반환하지 않을 때 재시도하고, 원격 설치 스크립트를 독립된 스크립트 블록으로 실행하도록 변경

## [0.12.3] - 2026-08-10

### 수정

- Windows PowerShell 5.1에서 한 줄 설치 스크립트가 빈 `Version` 기본값 검증에 실패하는 문제 수정

## [0.12.2] - 2026-08-10

### 수정

- Python 3.12 이상에서 안전한 tar `data` 필터를 명시해 Python 3.14 설치 경고 제거

## [0.12.1] - 2026-08-10

### 추가

- Command Center의 하루 단위 Rondo 최신 릴리스 확인과 오프라인 재시도 캐시
- 설정된 에이전트와 Zellij의 실제 로컬 버전 표시
- 작업 트리가 깨끗할 때 검증된 Rondo 업데이트를 다음 행동으로 추천

### 변경

- GitHub 저장소를 공개해 인증 없는 macOS·Linux·Windows 설치를 지원
- 외부 에이전트 CLI는 자동 업데이트하지 않고 설치된 버전만 표시하도록 경계를 명시

## [0.12.0] - 2026-08-10

### 추가

- 저장소 목표, 변경, 승인 대기, 예약 작업, 독립 테스트, race, Proof를 합쳐 다음 작업을 추천하는 Command Center
- `rondo status`와 Rondo shell 메뉴의 추천 작업 우선 표시
- 검증된 버전 릴리스의 `rondo update`, 한 세대 `rollback`, 설정 보존형 `uninstall`
- 원문·경로·원격 URL·환경변수를 제외한 `rondo support-bundle`
- 별도 프로세스 상태 지속성과 강제 잠금 종료 복구 E2E
- 실제 Zellij 입력 표시, 제출, 강제 종료 후 재시작 E2E
- Git 태그와 CLI 버전 일치 검사, macOS/Linux·Windows 릴리스 자산, SHA-256 목록을 만드는 릴리스 workflow

### 변경

- Rondo 설치 자산과 Zellij 0.44.3을 고정 버전 URL에서 내려받고 SHA-256을 확인
- 소스 체크아웃 설치와 관리형 릴리스 설치를 명시적으로 분리
- CI가 단위 테스트뿐 아니라 실제 Zellij 세션 수명주기를 검증

### 보안

- 관리형 설치 marker, 심볼릭 링크 및 비관리 디렉터리 덮어쓰기 거부
- 제거 전 전체 대상 사전 검증과 Rondo가 소유한 launcher·hook만 제거
- 진단 묶음은 허용 목록 기반 메타데이터만 기록하고 기존 파일을 덮어쓰지 않음

[0.14.4]: https://github.com/ppupy1209/rondo/releases/tag/v0.14.4
[0.14.3]: https://github.com/ppupy1209/rondo/releases/tag/v0.14.3
[0.14.2]: https://github.com/ppupy1209/rondo/releases/tag/v0.14.2
[0.14.1]: https://github.com/ppupy1209/rondo/releases/tag/v0.14.1
[0.14.0]: https://github.com/ppupy1209/rondo/releases/tag/v0.14.0
[0.13.1]: https://github.com/ppupy1209/rondo/releases/tag/v0.13.1
[0.13.0]: https://github.com/ppupy1209/rondo/releases/tag/v0.13.0
[0.12.4]: https://github.com/ppupy1209/rondo/releases/tag/v0.12.4
[0.12.3]: https://github.com/ppupy1209/rondo/releases/tag/v0.12.3
[0.12.2]: https://github.com/ppupy1209/rondo/releases/tag/v0.12.2
[0.12.1]: https://github.com/ppupy1209/rondo/releases/tag/v0.12.1
[0.12.0]: https://github.com/ppupy1209/rondo/releases/tag/v0.12.0
