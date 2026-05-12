---
name: image-gen
description: "Spawn fresh `codex exec` session to call image_gen (ChatGPT OAuth — no API key). Cross-engine — Claude 가 codex 도구 빌릴 때 + Codex 안에서도 prompt-cache 분리 위해 fresh exec 권장. Triggers — 이미지 만들어줘·그림 그려줘·image_gen·generate/make/create an image. Style-transfer via `-i` ref."
user-invocable: true
---

# /image-gen — Codex image_gen via ChatGPT OAuth

Spawn a fresh `codex exec` session in an empty sandbox dir, ask it to call `image_gen`, then verify the PNG that lands under `~/.codex/generated_images/<session_id>/ig_<hex>.png`. Inspired by `madrobotnet/hermes-codex-imagegen-skill` — Hermes 식 instruction-based skill 패턴.

## Why spawn even when *you* are Codex

이 스킬은 cross-engine 이다 — Claude 에서 호출하면 codex 가 없는 `image_gen` 도구를 빌리는 거고, **Codex 안에서 호출해도 fresh `codex exec` 를 또 띄우는 게 권장**이다. 이유: 메인 세션 안에서 직접 `image_gen` 을 부르면 **OpenAI 의 prompt cache 가 컨텍스트와 묶여서, 같은 프롬프트 결의 후속 호출이 이전 이미지 결과로 끌려가는 현상**이 있다 (알렉스 검증, 2026-05-11) — "이미지 변경이 잘 안 됨". 빈 sandbox + ephemeral 세션을 새로 띄우면 캐시 키가 깨져서 매 호출이 깨끗한 이미지로 분리된다. 즉:

- **Claude → image_gen**: codex CLI 가 image_gen tool 보유자라 codex exec 소환은 필수.
- **Codex → image_gen**: 도구는 같은 세션에서도 부를 수 있지만, *캐시 분리를 위해* fresh codex exec 소환을 권장.

## Preconditions

```bash
which codex && codex --version
codex login status   # must show "Logged in using ChatGPT" or equivalent
codex features list | grep image_generation   # must be `stable true`
```

If any fail, surface the issue to the user and stop.

## Core workflow — 권장: 한 세션 묶기 패턴 (image_gen + chroma + decontam 한 번에)

검증된 사실 (2026-04-26): codex CLI sandbox 는 `magick` / `python3 PIL` 셸 호출이 가능. 한 prompt 안에 image_gen 호출 + 후처리 파이프라인을 넣으면, 손으로 두 단계 나눠 하던 걸 codex 가 한 세션에 끝낸다. 결과로 바로 RGBA PNG (`srgba 4.0`) 가 떨어진다.

```bash
TS=$(date +%s)
TMP=$(mktemp -d /tmp/codex-image-XXXXXX)
DEST=/project/path/asset-name.png   # 최종 RGBA PNG 경로

codex exec \
  --sandbox workspace-write \
  --skip-git-repo-check \
  --ephemeral \
  --color never \
  --add-dir ~/.codex/generated_images \
  -C "$TMP" \
  -o "$TMP/last.txt" \
  - <<PROMPT 2>&1 | tee "$TMP/stdout.log"
다음 두 단계를 정확히 순서대로 실행해줘. 거짓 보고 금지.

[1] image_gen 도구를 정확히 1번 호출해서 다음 프롬프트로 PNG 1장 생성:
"<USER_PROMPT — 반드시 'SOLID FLAT MAGENTA #FF00FF background' 명시>"

[2] image_gen 가 만든 원본 PNG 의 절대 경로를 받은 뒤, 셸로 다음을 그 PNG 에 실행:
- magick "<원본>" -fuzz 35% -transparent magenta $TMP/out.png
- python3 로 $TMP/out.png 를 열어 alpha<240 인 픽셀 중 (R-G>4 AND B-G>4) 인 것을 (g,g,g,a//3) 로 평탄화 후 같은 경로에 저장
- magick identify -format '%[channels]\n' $TMP/out.png 출력해서 srgba 4.0 확인

마지막에 한 줄로 "$TMP/out.png" 만 응답.
PROMPT

# 검증 후 최종 위치로 이동 + 흰 배경 fringe 자가 검증
mv "$TMP/out.png" "$DEST"
python3 - <<PY
from PIL import Image
im = Image.open("$DEST").convert('RGBA')
bg = Image.new('RGBA', im.size, (255,255,255,255))
bg.alpha_composite(im)
bg.convert('RGB').save("/tmp/_check_white.png")
PY
# Read 툴로 /tmp/_check_white.png 열어서 머리카락/외곽 핑크 halo 시각 확인 (필수)
rm -rf "$TMP"
```

검증된 결과 (treasure-chest test): codex 한 세션에서 image_gen 호출 → magick chroma key → PIL decontam → `srgba 4.0` 1122x1402 출력 완료. 흰 배경 합성에서 fringe 0 픽셀.

**왜 한 세션 묶기가 더 나은가**: (1) codex 가 자신이 만든 PNG 의 *진짜 경로* 를 직접 magick 에 넘기므로 hallucinated path 사고 0. (2) prompt 안에서 magick `srgba 4.0` 출력까지 강제하므로 실패 시 codex 가 즉시 알림. (3) 손 작업 단계 줄어 사고 표면 축소.

**언제 분리 워크플로우를 쓰나**: (a) reference 이미지 (`-i`) 가 여러 장이라 prompt 가 복잡해 디버깅 필요, (b) 같은 원본을 여러 fuzz 로 비교, (c) image_gen 결과 자체를 먼저 눈으로 검수 후 후처리 결정. 이때 아래 ## Manual workflow 절차 사용.

---

## Manual workflow (디버깅·실험용 분리 단계)

### 1. Snapshot timestamp + temp workspace

```bash
TS=$(date +%s)
TMP=$(mktemp -d /tmp/codex-image-XXXXXX)
```

### 2. Run codex exec (sandbox + ephemeral + writable gen dir)

The decisive flag combo:

- `--sandbox workspace-write` — image_gen needs to write its PNG.
- `--add-dir ~/.codex/generated_images` — **required on this system**: `workspace-write` 의 디폴트 writable 셋(workdir, /tmp, $TMPDIR, ~/.codex/memories)에 generated_images 가 안 들어가서, 빠뜨리면 codex 가 silent 실패한다. 검증된 사실.
- `--skip-git-repo-check` — 빈 sandbox 라 git repo 없음.
- `--ephemeral` — 세션 파일 안 남김.
- `-C "$TMP"` — codex 의 작업 디렉토리. 빈 dir 이라 만질 게 없음 → 코드 작업으로 폭주 안 함.
- `-o "$TMP/last.txt"` — codex 의 마지막 메시지 (검증용, 거짓 경로 가능하므로 신뢰 X).
- `-i <ref-image>` (반복 가능) — style/character reference. codex 가 attach 해서 모델에 보여줌.

기본 호출:

```bash
codex exec \
  --sandbox workspace-write \
  --skip-git-repo-check \
  --ephemeral \
  --color never \
  --add-dir ~/.codex/generated_images \
  -C "$TMP" \
  -o "$TMP/last.txt" \
  - <<'PROMPT' 2>&1 | tee "$TMP/stdout.log"
image_gen 도구를 정확히 1번 호출해서 다음 프롬프트의 이미지를 1장 생성해줘.
호출 성공하면 결과 파일 경로를 한 줄로 응답. 실패하면 에러 메시지 원문 그대로. 거짓 완료 보고 금지.
파일 생성/수정/삭제, 셸 명령, 코드 작성 금지.

프롬프트:
<USER_PROMPT_HERE>
PROMPT
```

reference 이미지가 있으면 `-i /abs/path/ref1.png -i /abs/path/ref2.png` 를 옵션 위치에 추가.

### 3. Extract session id from stdout, then verify the actual PNG

Codex 의 stdout 에 한 줄로 들어옴: `session id: <uuid>`. 그 UUID 로 정확한 디렉토리 검색.

```bash
SID=$(grep -oE 'session id: [a-f0-9-]+' "$TMP/stdout.log" | awk '{print $3}' | tail -1)
NEW_PNG=$(find ~/.codex/generated_images/"$SID" -type f -name 'ig_*.png' 2>/dev/null | head -1)
```

Fallback (session id 못 찾으면): mtime 기반.

```bash
NEW_PNG=$(find ~/.codex/generated_images -type f -name 'ig_*.png' -newermt "@$TS" 2>/dev/null | sort | tail -1)
```

**codex 의 응답 텍스트에 적힌 경로는 LLM 환각 가능. 절대 신뢰 X. 파일 시스템 존재 여부만 신뢰.**

### 4. Move/copy to project asset path

```bash
cp "$NEW_PNG" /project/path/asset-name.png
# or
mv "$NEW_PNG" /project/path/asset-name.png
```

### 5. Cleanup

```bash
rm -rf "$TMP"
```

## Style-transfer pattern (캐릭터/화풍 일관성)

기존 자산과 화풍 맞출 때 reference 이미지 첨부:

```bash
codex exec ... \
  -i /project/assets/style-reference.png \
  -i /project/assets/character-reference.png \
  ...
  - <<'PROMPT'
첨부한 두 장의 painterly 화풍/캐릭터를 정확히 일치시켜서 image_gen 으로 X 1장 생성.
- 동일 라이팅, 동일 디테일 밀도, 동일 캔버스 비율
- 캐릭터 디자인은 두번째 ref 와 동일
PROMPT
```

같은 캐릭터의 다른 포즈 (idle / attack / win 시리즈) 가 필요하면:
1. **idle 한 장 먼저** 생성
2. **그 idle 을 ref 로** attack/win 생성 → 캐릭터 일관성 보장

## Pitfalls

- **silent 실패 = `--sandbox workspace-write` 누락**. 디폴트 `read-only` sandbox 면 codex 가 image_gen 등록 안 함 → tool call 자체가 안 일어나고 `codex` 빈 응답만 나옴. 검증 단서: `sandbox: read-only` 가 stdout 헤더에 찍히면 무조건 워크스페이스-라이트로 다시. (검증: `--sandbox workspace-write` 명시 후 같은 prompt 로 호출 즉시 image_gen 호출됨.)
- **silent 실패 = `--add-dir` 누락**. `workspace-write` 만으로는 generated_images writable 아님. 이 시스템에서 검증된 핵심 단서.
- **codex 응답의 거짓 경로**. 응답에 `/tmp/<sandbox>/generated_image.png` 또는 `~/.codex/generated_images/<random-uuid>.png` 같은 경로가 적혀도 실제로는 `<session-id>/ig_<hex>.png` 패턴이 진짜. 파일 시스템으로만 검증. (검증: 거짓 경로 `find` 0 hit, session-id 디렉토리에서 `ig_<hex>.png` 발견.)
- **bwrap loopback / sandbox introspection 에러 무시**. codex 가 이미지 만든 후 sandbox 내부 검사하다 `RTM_NEWADDR` 같은 에러 출력해도 실패 아님. 파일 존재 여부만 봄.
- **모델은 `gpt-5.5` 기본**. reasoning 시간 30~90초. `--model <name>` 으로 가벼운 모델 쓸 수 있지만 image_gen tool 등록 보장 X — 검증 필요.
- **프로젝트 디렉토리에서 `-C` 없이 호출 절대 금지**. codex 가 프로젝트 컨텍스트 보고 코드 작업으로 폭주함 (실제 사고 사례 있음).
- **Read 툴은 알파 채널 PNG 를 배경색처럼 렌더한다**. magenta chroma key 후 Read 로 보면 마젠타 배경처럼 보여서 "투명 안 됐다" 착시. 진짜 검증은 `magick identify -format '%[channels]'` → `srgba 4.0` 이면 알파 있음.

## Transparent background 는 native 지원 안 됨 (codex CLI 0.124 / 0.125 둘 다 검증)

검증 사실 (재확인 0.125.0-alpha.3, 2026-04-26): prompt 에 "TRANSPARENT (alpha channel)", "RGBA", "no background fill", "no checkerboard" 모두 명시 + "거짓 보고 금지" 까지 박아도 결과는 동일하게 **RGB 3-채널 + 흰-회색 (corner 220~252) 배경 PNG**. PIL `mode='RGB', has_alpha=False`. magick `srgb 3.0`.

이건 모델 한계이며 prompt engineering 으로 해결 불가. **항상 chroma 배경 + 후처리 우회 사용**.

Read 툴이 흰 배경 PNG 를 체커보드처럼 표시해서 transparent 로 착시 발생 — 항상 `python3 -c "from PIL import Image; print(Image.open(p).mode)"` 또는 `magick identify -format '%[channels]'` 으로 진짜 알파 채널 여부 확인.

→ NPC/캐릭터 sprite 처럼 외곽이 transparent 여야 하면 **magick floodfill 후처리 필수**:

```bash
W=$(magick identify -format "%[width]" "$SRC")
H=$(magick identify -format "%[height]" "$SRC")
magick "$SRC" -alpha set -fuzz 8% \
  -fill none \
  -draw "color 0,0 floodfill" \
  -draw "color $((W-1)),0 floodfill" \
  -draw "color 0,$((H-1)) floodfill" \
  -draw "color $((W-1)),$((H-1)) floodfill" \
  "$DEST"
```

### Fuzz 가이드 — 캐릭터 의상 색에 따라 다름

| fuzz | 결과 |
|---|---|
| 18% (원래 시작값) | 가장자리 회색 잔여 거의 없음. **단 흰 ruff/cravat/셔츠 의상이면 connected pixel chain 으로 의상까지 점프해서 윤곽선만 남는 사고** (실제 magistrate NPC 사고). |
| 8% (안전 기본값) | 외곽 회색 (220~235) 만 빠지고 의상 흰 (240+) 보존. **첫 시도 권장값**. |
| 5% 이하 | 의상 보존 더 안전, 외곽 회색 안티앨리어싱 약간 잔여 가능. |

검증: 처리 후 `magick identify -format '%[channels]'` 로 srgba 4.0 확인 + Read 툴로 시각 확인 (의상 일부가 빠지지 않았는지).

### Chroma key (그린/마젠타 키) — floodfill 보다 우선 권장

캐릭터/NPC 처럼 머리카락 highlights, 투명 천, 흰 의상 등이 있으면 floodfill 은 위험. 대신 **prompt 에 솔리드 chroma 배경 명시 → magick `-transparent` 한 줄**이 머리카락 사이 highlights 까지 보존하면서 깔끔.

| chroma | prompt 예시 | 안전한 fuzz | 언제 |
|---|---|---|---|
| `#FF00FF` 마젠타 | "solid flat MAGENTA #FF00FF background, hair highlights warm amber/gold ONLY, never near-magenta" | 12% | 사람/NPC. 머리카락/피부/의상에 마젠타 거의 없음. **첫 시도 권장**. |
| `#00FF00` 그린 | "chroma key green #00FF00 background" | 18% | 검/금속/가죽 위주 sprite. 그린 톤 의상은 피해야 함. |

```bash
# 마젠타 케이스 (인물 NPC 표준)
magick "$SRC" -fuzz 12% -transparent "magenta" "$DEST"
# 그린 케이스 (검 든 sprite 등)
magick "$SRC" -fuzz 18% -transparent "#00FF00" "$DEST"
```

검증: `magick identify -format '%[channels] %wx%h\n' "$DEST"` → `srgba 4.0 ...` 면 알파 OK. (Read 툴은 마젠타 배경처럼 보여줘도 신뢰 X.)

**왜 floodfill 보다 우선인가**: floodfill 은 외곽에서 시작해서 connected pixel chain 으로 번지므로 머리카락 사이 갭 / 흰 의상까지 침투할 수 있음 (실제 magistrate 흰 ruff 사고, 비비안 머리카락 흰 highlights 사고). chroma key 는 픽셀 색 매치만 보고 위치 무관 → 캐릭터 안쪽으로 안 번짐.

### ⚠ `magick -transparent` 의 가장 큰 함정 — alpha 만 깎고 RGB 는 마젠타 그대로 남김

**검증된 진짜 사고 원인 (2026-04-26, 비비안 NPC, 사용자 4회 격분):**

`magick "$SRC" -fuzz 35% -transparent magenta "$DEST"` 후, transparent area (alpha=0) 픽셀의 **RGB 채널은 (255, 0, 255) 마젠타가 그대로 보존된다**. ImageMagick 은 알파만 0 으로 만들고 RGB 는 안 건드림.

PIL 검사:
```
{'alpha=255 magenta': 0, 'alpha 1..254 magenta': 0}     # 본체에 마젠타 0
transparent area still has magenta RGB (sampled 1/16): 28995   # 그러나 transparent 영역엔 마젠타 RGB 살아있음
```

대부분 viewer/브라우저는 alpha=0 이면 RGB 무시 → 문제 안 보임. **하지만 다음 환경에선 마젠타가 누설**:
- 일부 브라우저/캔버스의 alpha-premultiplication 합성 모드
- 이미지 다운스케일링 시 인접 alpha 픽셀과 RGB 가 보간 → 가장자리 마젠타 halo
- macOS 스크린샷 도구 / 일부 picker / Read 툴
- CSS `filter: drop-shadow` / `mask-image`

→ **alpha=0 픽셀의 RGB 도 반드시 (0,0,0) 으로 청소해야 함.** 비비안에서 460,778 픽셀 / 마지스트레이트에서 482,917 픽셀이 stale 마젠타 RGB 상태로 살아있었음.

```python
for y in range(H):
    for x in range(W):
        r, g, b, a = px[x, y]
        if a == 0 and (r or g or b):
            px[x, y] = (0, 0, 0, 0)   # transparent area RGB 청소
```

또는 ImageMagick 한 줄:
```bash
magick "$SRC" -channel RGBA -alpha set \
  \( +clone -channel A -threshold 1 \) -compose CopyOpacity -composite \
  -background black -alpha background \
  "$DEST"
```

**이 청소를 안 하면 chroma key + decontamination 다 해도 사용자 화면에 마젠타가 계속 비친다. 절대 빠뜨리지 마.**

### Decontamination pass — chroma key 후에도 fringe 가 보일 때 필수 후처리

검증된 사실: `magick -fuzz 35% -transparent magenta` 조차도 머리카락/모자 외곽의 anti-aliased 픽셀에 마젠타가 섞인 RGBA 를 남긴다. **검은 배경 위 합성에선 안 보이고, 흰 배경 위 합성에서만 핑크 halo 로 떠 보인다.** 사용자가 town 의 밝은 painting 배경 위에서만 "아직도 빨개" 라고 격분 (실제 사고, 두 차례).

원인 (3-단계):
1. chroma key (`-transparent magenta`) 는 fuzz 안에 든 색만 알파=0. 외곽 anti-alias 픽셀 (R, B 둘 다 G 보다 살짝 높은 핑크-tint) 은 fuzz 못 통과 → alpha 살짝만 깎인 채 RGB 마젠타-tint 살아남음.
2. PIL "opaque magenta 0 픽셀" 검사 통과해도, **반투명** 핑크 fringe 가 살아있다.
3. 어두운 배경에 합성하면 fringe 가 어둠에 묻혀 안 보임. 밝은 배경에 합성해야 핑크 halo 가 드러남. **검증은 반드시 흰 배경 합성으로**.

해결: chroma key 후 PIL 로 두 단계 처리 — 의상/본체 (alpha=255) 는 절대 안 건드리고, **alpha < 240 인 외곽 anti-alias 픽셀만** 핑크끼면 RGB 를 grey 화 + alpha 1/3 로.

```bash
python3 - <<'PY'
from PIL import Image
p = "/path/to/asset.png"
im = Image.open(p).convert('RGBA')
px = im.load()
W, H = im.size
killed = 0
for y in range(H):
    for x in range(W):
        r, g, b, a = px[x, y]
        # alpha=255 본체와 alpha=0 배경은 절대 안 건드림
        if a == 0 or a >= 240:
            continue
        # 핑크/마젠타-tint anti-alias: R 과 B 둘 다 G 보다 4 이상 높음
        # 와인-레드 의상 (R↑ G↓ B↓) 은 B<G 라 자동 제외
        if (r - g) > 4 and (b - g) > 4:
            # 완전 평탄화: R=G=B=G (grey), alpha 1/3 로 깎기
            px[x, y] = (g, g, g, a // 3)
            killed += 1
im.save(p)
print("fringe killed:", killed)
PY
```

검증 절차 (이걸 안 하면 사고 또 남):

```bash
# 흰 배경에 합성해서 fringe 가 진짜 사라졌는지 *눈으로* 확인
python3 - <<'PY'
from PIL import Image
im = Image.open("/path/to/asset.png").convert('RGBA')
bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
bg.alpha_composite(im)
bg.convert('RGB').save("/tmp/check-white.png")
PY
# 그 다음 Read 툴로 /tmp/check-white.png 열어서 머리카락/모자 외곽 핑크 halo 검사
```

검증된 결과 (lisboa-magistrate, vivian): 약 1000~1400 fringe 픽셀 중성화. 흰 배경 합성 후 잔여 핑크 0 픽셀.

**그린 키 (#00FF00) 의 경우**: G 가 높고 R/B 낮은 fringe → 조건을 `(g - r) > 4 and (g - b) > 4` 로 바꿔서 같은 logic 적용 (RGB 평탄화는 r 또는 b 기준).

**캐시 함정**: 후처리 다 끝나도 사용자 브라우저가 옛날 PNG 캐싱 중이면 fringe 가 그대로 보인다. md5 변경을 보여주고 DevTools → Network → "Disable cache" 또는 시크릿 창 안내. 단, **캐시 탓하기 전에 반드시 흰 배경 합성으로 자체 검증** 먼저. (실제 사고: 캐시 문제라고 안내했는데 진짜로 fringe 가 살아있었음.)

### Floodfill 폴백 (chroma 배경 명시 못 했을 때만)

## Batch / Continuation modes (검증 2026-04-28)

기본은 위 single-shot codex exec 패턴. 다음 두 시나리오에서는 별도 모드 — `~/.claude/skills/image-gen/scripts/` 의 spike 스크립트들을 참조 구현으로 사용한다.

### A. Batch parallel — 게임 에셋 다량 / 카드뉴스 시리즈

같은 캐릭터/스타일을 다른 pose 또는 다른 표정으로 N 장 동시 생성. 매 호출이 독립이고 character lock 은 base ref 첨부 + 동일 prompt 토대로 유지.

- 참조: `scripts/spike-codex-exec-parallel.py` — N 개 `codex exec` process 동시 spawn (Python `threading`).
- **ChatGPT image_gen 동시성 한계 ≈ 4** (실측 2026-04-28). 5번째부터 quota 대기로 ~150s 추가.
- 시간 단축: 5장 sequential ~375s vs 4-동시 parallel ~230s = ~38%. 50장 단위 batch 면 sequential ~62분 vs parallel ~16분 (약 4배).
- 패턴:
  ```bash
  # parallel 4 (concurrency cap = 4)
  for pose in poses; do
    codex exec --skip-git-repo-check -C $tmp_per --add-dir ~/.codex/generated_images -i $base -- "$prompt_with_pose" </dev/null &
  done
  wait
  ```
- character lock: base ref `-i $base` 첨부 매번 + prompt 에 동일 style 명시 매번. thread context 없음.

### B. Continuation thread — 반복 수정 / 한 캐릭터 시리즈

알렉스가 이미지 한 장 보고 "더 어둡게", "각도 달리", "표정 바꿔" 식 자연어 후속 수정. 같은 thread 안에서 turn 1 = full character spec + base ref attach, turn 2~N = short pose nudge 만. thread context 가 character/style 자동 보존.

- 참조: `scripts/spike-app-server-continuation.py` — `codex app-server --listen stdio://` daemon + JSON-RPC `thread/start` + 다중 `turn/start`.
- **검증된 동작** (Phase 0.5): turn 2/3 에서 base ref + style respec 안 박았는데도 character lock 유지 ✓
- Token 절감 ~85% (full prompt 매번 → short nudge 만)
- thread session disk 저장: `~/.codex/sessions/YYYY/MM/DD/rollout-<thread_id>.jsonl`. `thread/resume` 으로 다음 세션 이어가기 가능.
- core 패턴 (Python pseudo):
  ```python
  daemon = subprocess.Popen(['codex','app-server','--listen','stdio://'], ...)
  send("initialize", {...})
  thread_id = send("thread/start", {"approvalPolicy":"never","sandboxPolicy":{"mode":"workspace-write"},"cwd":"/tmp"})
  # turn 1 — full spec + base ref
  send("turn/start", {"threadId":thread_id, "input":[{"type":"localImage","path":base},{"type":"text","text":FULL_PROMPT}]})
  # ... wait for turn idle ...
  # turn 2~N — short nudge only, no base ref, no style respec
  send("turn/start", {"threadId":thread_id, "input":[{"type":"text","text":"Now generate same character with <pose nudge>"}]})
  ```

### C. Fork batch — 미동작 (검증 결과)

Symphony SPEC 의 `thread/fork` 패턴 + 동시 image_gen 시도했지만 **현재 codex CLI 0.125.0-alpha.3 에서 미동작** (Phase 0.6, 0.7 — 0/N PNG). image_gen tool 이 fork thread 에 inherit 안 되거나 daemon sequential 처리 한계. 알파 버전 이슈 가능성. Codex CLI 정식 release 후 재검증 가치 있음. 현재는 batch 가 필요하면 A (parallel exec) 사용.

### 모드 선택 가이드

| 시나리오 | 모드 |
|---|---|
| 단발 1장 | default single codex exec (이 문서 위) |
| N장 다량 batch (게임 에셋, 카드뉴스) | A. Batch parallel |
| 1장 + 후속 자연어 수정 (반복 수정) | B. Continuation thread |
| N장 batch + character lock 둘 다 | A 사용 (lock 은 base ref 로 유지). C (fork) 미동작 |

## When NOT to use

- Hermes / 다른 agent 의 native 이미지 백엔드가 있으면 그쪽 우선.
- 이미 cmux 에 떠있는 codex 팀메이트(다람이/쭈니)가 idle 이면 위임 가능 — 근데 그 팀메이트가 사용자 작업 흐름의 일부면 끼어들지 말 것.
- 기존 이미지 편집/리터칭 — image_gen 은 생성 전용.
- SVG/캔버스로 그릴 수 있는 단순 도형.

## Verification checklist

- [ ] `codex login status` 활성
- [ ] `--add-dir ~/.codex/generated_images` 포함
- [ ] `-C $TMP` 빈 sandbox dir
- [ ] session id stdout 에 출력됨
- [ ] `find ~/.codex/generated_images/$SID -name 'ig_*.png'` 결과 존재
- [ ] (선택) `Read` 로 PNG 미리보기 → 프롬프트와 매칭 확인
