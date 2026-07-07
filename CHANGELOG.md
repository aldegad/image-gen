# Changelog

## 1.2.0 — 2026-07-07

크로마 키 분기 게이트 + 본문 히스토리 격리.

- **SKILL.md 최상단에 크로마 키 분기 게이트(BLOCKING) 추가**: 소재 주요 색 먼저 확인 → 핑크·보라·자주·마젠타 계열 소재는 그린 `#00FF00`, 녹색/청록 소재는 마젠타 `#FF00FF`, 둘 다 있으면 더 중요한 소재에서 먼 키 + 변환 후 두 색 보존 확인 필수. 계기: solvell 에셋 재작업에서 핑크 씨앗봉투·보라 별꽃을 마젠타 키로 생성해 sprite-gen 추출에서 소재가 탈색된 실사고 (2026-07-07; 추출 쪽 수정은 sprite-gen v1.10.1). 본문 중간의 마젠타 "첫 시도 권장" 서술이 게이트와 충돌하던 것도 정리 — 키 선택 SSoT 는 게이트 표.
- **사고 서사를 본문에서 CHANGELOG 부록으로 격리** (skill-hook-authoring 규칙): 본문은 현재-진실 규칙만 남기고, 아래 부록에 사건 기록을 보존.

### 부록 — 실사고 기록 (본문에서 이동)

- **2026-04-26 비비안 NPC (사용자 4회 격분)**: `magick -fuzz 35% -transparent magenta` 후 transparent 영역에 stale 마젠타 RGB 가 남는 함정 — 비비안 460,778 픽셀, 리스보아 마지스트레이트 482,917 픽셀이 alpha=0 인 채 RGB (255,0,255) 로 살아있었고, 다운스케일 보간·premultiply 합성 환경에서 마젠타가 누설됐다. alpha=0 픽셀 RGB (0,0,0) 청소 규칙의 유래.
- **Magistrate 흰 ruff / 비비안 흰 highlights**: floodfill 18% fuzz 가 connected chain 으로 흰 의상·머리카락 highlights 까지 침투해 윤곽선만 남긴 사고. floodfill 대신 chroma key 우선 규칙의 유래.
- **핑크 halo 2회**: 어두운 배경에선 안 보이던 반투명 핑크 fringe 가 밝은 painting 배경에서만 드러나 "아직도 빨개" 재작업 — 흰 배경 합성 검증 의무화의 유래. 한 번은 브라우저 캐시 문제로 안내했는데 실제로 fringe 가 살아있었다 — "캐시 탓 전에 자체 검증" 규칙의 유래. decontamination pass 검증치(lisboa-magistrate·vivian 약 1000~1400 픽셀 중성화)도 이 사고들에서 나왔다.

## 1.1.1 — 2026-06-19

- **정리**: codex ≤0.125 출력 모델과 개인 로컬 fixture 경로에 묶인 `scripts/spike-*.py` 탐색 파일을 제거했다. batch/continuation 설명은 `SKILL.md` 의 인라인 캐노니컬 패턴만 유지한다.
- **패키징**: Pillow 요구사항을 `requirements.txt` 로 명시했다.
- **테스트**: `scripts/extract_imagegen.py` 에 fixture 기반 `unittest` regression 테스트를 추가했다. 기본 last-result 선택, `--index`, `--all`, no-result failure, non-PNG failure 를 검증한다.

## 1.1.0 — 2026-06-18

codex v0.140.0 대응: `image_gen` 출력 추출 방식 전환.

- **원인**: codex ≤0.125 는 `image_gen` 결과를 `~/.codex/generated_images/<session_id>/ig_<hex>.png` 디스크 파일로 저장했고, 이 스킬은 그 파일을 `find` 로 검증했다. codex 0.140.0 은 그 파일을 더 이상 쓰지 않는다 — 이미지는 세션 rollout jsonl 의 `image_generation_call.result` 인라인 base64 로만 온다. 옛 `find ig_*.png` 검증은 항상 0 hit → codex 가 "image_gen 결과 PNG의 파일시스템 절대 경로를 확인할 수 없습니다" 로 끝나며 스킬이 silent 하게 깨져 있었다 (image_gen·ChatGPT OAuth 인증 자체는 정상이었음 — `codex login status` = `Logged in using ChatGPT`, `image_generation stable true`).
- **추가**: `scripts/extract_imagegen.py` — 세션 id(또는 rollout 경로)에서 `image_generation_call.result` base64 를 결정론적으로 디코드해 PNG 로 기록하고 PNG magic 을 검증한다. 결과가 없으면 non-zero 로 실패한다 (No Silent Fallback).
- **변경**: codex exec 흐름에서 `--ephemeral` 제거(세션 jsonl 보존 필요), 생성 후 세션파일 직접 청소로 ephemeral 청결성 복원. `-o "$TMP/last.txt"` 의존 제거. codex 프롬프트는 "생성만"(저장·셸·코드·경로보고 금지)으로 축소.
- **문서**: `SKILL.md` Core/Manual workflow·Pitfalls·Verification checklist, `README.md` 를 인라인-추출 모델로 갱신.
- **검증**: 사과·레몬·딸기(불투명) + 파란 슬라임(투명: 생성→추출→chroma → `mode=RGBA`, `stale_transparent_rgb_pixels=0`) end-to-end 통과 (codex-cli 0.140.0, 2026-06-18).

## 1.0.0

초기 릴리스 — Hermes 식 instruction-based `image_gen` 스킬 (`codex exec` + ChatGPT OAuth, `~/.codex/generated_images/<sid>/ig_*.png` 파일 검증 방식).
