# Rondo 기여 안내

Rondo 0.15의 범위는 의도적으로 작습니다. 변경은 Codex·Claude·Gemini의 네이티브 CLI, 프로젝트별 맥락 인계, 명확한 쿼터 소진 시 전환, 독립 검증, 공개 Relay 메시지 중 하나를 직접 개선해야 합니다. 별도 대시보드, 모델 API 라우터, 작업 저널, 예약 실행, 범용 자동화는 다시 추가하지 않습니다.

## 커밋 신원

새 커밋과 annotated tag는 다음 신원만 사용합니다.

```sh
git config user.name "yeonwoo"
git config user.email "ppupy1209@naver.com"
git config core.hooksPath .githooks
```

커밋 전 `python3 scripts/check_identity.py --current`, CI에서는 전체 이력을 `--all`로 검사합니다. 기존 `Yeonwoo Kim <ppupy1209@naver.com>` 커밋은 이전 신원으로 인정하지만 새 커밋에는 사용할 수 없습니다. GitHub 리베이스 병합도 프로필명 `yeonwoo`로 기록되므로 같은 정책을 만족합니다. 다른 이름이나 이메일이 포함된 커밋은 받지 않습니다.

## 확인 절차

```sh
python3 -m py_compile bin/rondo bin/rondo-agent-session bin/rondo-relay lib/rondo/core.py lib/rondo/cleanup.py
python3 -m unittest discover -s tests -v
sh -n install.sh
```

Windows 설치 변경은 `install.ps1` 로컬 설치와 새 PowerShell에서의 `rondo --version`까지 확인합니다. 구현 세션은 개발 중 테스트를 실행할 수 있지만 최종 검증과 리뷰는 구현에 참여하지 않은 다른 AI 또는 새 세션이 맡아야 합니다.

테스트 fixture와 오류 출력에는 토큰, 로컬 사용자 경로, 회사 정보, 실제 프롬프트를 넣지 않습니다. 사용자에게 보이는 동작, 실패 시 복구, Windows/macOS/Linux 차이가 있으면 PR 설명과 `CHANGELOG.md`에 함께 기록합니다.
