# Rondo에 기여하기

Rondo는 의존성을 늘리기보다 Python 표준 라이브러리와 각 CLI의 공개 인터페이스를 우선합니다. 변경은 macOS, Linux, Windows 동작과 로컬 우선·보이는 위임·사용자 승인 경계를 유지해야 합니다.

## 개발 흐름

1. issue에서 문제와 사용자 결과를 먼저 합의합니다.
2. 한 변경은 한 목적에 집중하고 테스트를 함께 추가합니다.
3. 아래 검증을 실행합니다.

```sh
PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
sh -n install.sh bin/ai bin/rondo-status bin/claude-statusline bin/*-session bin/handoff
PYTHONUTF8=1 python3 tests/zellij_smoke.py  # zellij가 설치된 macOS/Linux
```

Windows PowerShell에서는 `$env:PYTHONUTF8=1`을 먼저 설정하고 `python -m unittest discover -s tests -v`와 `./tests/zellij_windows_smoke.ps1`을 실행합니다. Windows 설치 변경은 GitHub Actions의 Windows job까지 확인합니다. 새 다운로드는 고정 버전, 해시 검증, 안전한 임시 경로, 실패 시 복구를 갖춰야 합니다.

이 저장소의 커밋 author·committer와 annotated tag tagger는 모두 `Yeonwoo Kim <ppupy1209@naver.com>`이어야 합니다. 처음 clone한 뒤 `git config user.name "Yeonwoo Kim"`, `git config user.email "ppupy1209@naver.com"`, `git config core.hooksPath .githooks`를 설정하세요. CI와 저장소 훅이 다른 신원을 거부합니다.

## Pull Request

- 사용자에게 보이는 동작과 실패 시 복구 방법을 설명합니다.
- 보안 경계나 저장 형식이 바뀌면 `SECURITY.md` 또는 관련 문서를 갱신합니다.
- 대화 원문, 실제 사용자 경로, 토큰, 공급자 세션 데이터를 fixture로 커밋하지 않습니다.
- 기능 변경은 `CHANGELOG.md`의 다음 릴리스 항목에 남깁니다.
