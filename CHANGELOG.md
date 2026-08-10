# 변경 이력

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/), 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [0.15.0] - 2026-08-10

Rondo를 Codex CLI, Claude Code, Gemini CLI의 가벼운 보조 도구로 다시 설계한 호환성 중단 릴리스입니다.

### 추가

- `.rondo/`에 제한된 구조화 맥락을 저장해 Claude -> Codex -> Gemini 작업 연속성 제공
- 명확한 사용량·쿼터 소진을 연속 확인하면 다음 활성 AI로 자동 인계
- 구현 세션과 독립 검증 세션을 ID로 구분하고 자기 검증 차단
- AI 간 메시지, 체크포인트, 인계, 검증 요청·결과를 Relay 탭에 텍스트로 표시
- Windows에서 죽은 Zellij 세션 표식만 제한적으로 복구

### 변경

- 공급자를 Codex, Claude, Gemini 세 개로 제한하고 `rondo setup`에서 추가·제외
- 복합 패널과 대시보드 대신 공급자별 네이티브 Zellij 탭 사용
- 설치 실행 파일을 `rondo`, `rondo-agent-session`, `rondo-relay`로 축소
- `.rondo/`를 공유 `.gitignore`가 아닌 저장소의 `.git/info/exclude`에 등록

### 제거

- 전체 대화 수집과 공급자 사용량 API 스크래핑
- Kimi, Grok, Antigravity 전용 지원
- 작업 저널, 학습, 예약, race, proof, lens, 지원 번들, 자체 업데이트 명령
- 별도 상태 대시보드, 전역 Claude/Gemini 훅과 상태표시

0.15.0 설치기는 0.14.x가 만든 정확히 알려진 Rondo 전역 설정만 백업 후 제거하며 다른 사용자 설정은 보존합니다.

이전 릴리스 기록은 [GitHub Releases](https://github.com/ppupy1209/rondo/releases)에서 확인할 수 있습니다.

[0.15.0]: https://github.com/ppupy1209/rondo/releases/tag/v0.15.0
