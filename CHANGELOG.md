# 변경 이력

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르며 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 사용합니다.

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

[0.12.3]: https://github.com/ppupy1209/rondo/releases/tag/v0.12.3
[0.12.2]: https://github.com/ppupy1209/rondo/releases/tag/v0.12.2
[0.12.1]: https://github.com/ppupy1209/rondo/releases/tag/v0.12.1
[0.12.0]: https://github.com/ppupy1209/rondo/releases/tag/v0.12.0
