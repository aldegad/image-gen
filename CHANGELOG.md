# Changelog

## 1.1.0 — 2026-06-18

codex v0.140.0 대응: `image_gen` 출력 추출 방식 전환.

- **원인**: codex ≤0.125 는 `image_gen` 결과를 `~/.codex/generated_images/<session_id>/ig_<hex>.png` 디스크 파일로 저장했고, 이 스킬은 그 파일을 `find` 로 검증했다. codex 0.140.0 은 그 파일을 더 이상 쓰지 않는다 — 이미지는 세션 rollout jsonl 의 `image_generation_call.result` 인라인 base64 로만 온다. 옛 `find ig_*.png` 검증은 항상 0 hit → codex 가 "image_gen 결과 PNG의 파일시스템 절대 경로를 확인할 수 없습니다" 로 끝나며 스킬이 silent 하게 깨져 있었다 (image_gen·ChatGPT OAuth 인증 자체는 정상이었음 — `codex login status` = `Logged in using ChatGPT`, `image_generation stable true`).
- **추가**: `scripts/extract_imagegen.py` — 세션 id(또는 rollout 경로)에서 `image_generation_call.result` base64 를 결정론적으로 디코드해 PNG 로 기록하고 PNG magic 을 검증한다. 결과가 없으면 non-zero 로 실패한다 (No Silent Fallback).
- **변경**: codex exec 흐름에서 `--ephemeral` 제거(세션 jsonl 보존 필요), 생성 후 세션파일 직접 청소로 ephemeral 청결성 복원. `-o "$TMP/last.txt"` 의존 제거. codex 프롬프트는 "생성만"(저장·셸·코드·경로보고 금지)으로 축소.
- **문서**: `SKILL.md` Core/Manual workflow·Pitfalls·Verification checklist, `README.md` 를 인라인-추출 모델로 갱신.
- **검증**: 사과·레몬·딸기(불투명) + 파란 슬라임(투명: 생성→추출→chroma → `mode=RGBA`, `stale_transparent_rgb_pixels=0`) end-to-end 통과 (codex-cli 0.140.0, 2026-06-18).

## 1.0.0

초기 릴리스 — Hermes 식 instruction-based `image_gen` 스킬 (`codex exec` + ChatGPT OAuth, `~/.codex/generated_images/<sid>/ig_*.png` 파일 검증 방식).
