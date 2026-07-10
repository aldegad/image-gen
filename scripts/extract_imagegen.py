#!/usr/bin/env python3
"""Extract the inline base64 PNG that `image_gen` writes into a codex session rollout.

codex CLI v0.140.0 (built-in `image_gen` / `.system/imagegen` skill) no longer
persists a discrete `~/.codex/generated_images/<session>/ig_<hex>.png` file in
`codex exec` runs. Instead the generated image is returned **inline** as a
base64 `result` field on the `image_generation_call` response_item inside the
session rollout jsonl at `~/.codex/sessions/YYYY/MM/DD/rollout-*-<SID>.jsonl`.

v0.144.1 renamed that record: the inline base64 now arrives on an event_msg of
type `image_generation_end` (fields: status, revised_prompt, result, saved_path),
and the function_call is `name=imagegen ns=image_gen`. The inline `result` is
still the truth we decode; `saved_path` is not trusted (it reintroduces the
path-hallucination surface the inline decode was built to remove).

This decodes that inline result deterministically (no reliance on the codex
model to find a path) and writes a verified PNG to <dest>.

Usage:
    extract_imagegen.py <session_jsonl | session_id> <dest.png> [--index=N] [--all]

- arg1 may be a path to the rollout jsonl, OR a bare session id (uuid) which is
  resolved under ~/.codex/sessions.
- Default: write the LAST image_generation_call result (one image_gen call ->
  exactly one result). --index=N picks the Nth (0-based). --all writes every
  result as <dest stem>-0.png, <dest stem>-1.png, ...

Exits non-zero with a clear message if no image result is found (No Silent
Fallback: never claim success without a real decoded PNG).
"""
import sys
import json
import base64
import glob
import os

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def resolve_session(arg: str) -> str:
    if os.path.isfile(arg):
        return arg
    # treat as session id -> find rollout
    home = os.path.expanduser("~/.codex/sessions")
    hits = glob.glob(f"{home}/**/rollout-*{arg}*.jsonl", recursive=True)
    if not hits:
        sys.exit(f"extract_imagegen: no rollout jsonl found for session '{arg}' under {home}")
    # newest first
    hits.sort(key=os.path.getmtime, reverse=True)
    return hits[0]


# codex 가 인라인 base64 를 실어 보내는 rollout 레코드 타입.
# v0.140.0: response_item `image_generation_call`
# v0.144.1: event_msg   `image_generation_end` (+ status, saved_path)
# 두 형식을 모두 읽는다 — 폴백이 아니라 버전별 캐노니컬 레코드라 둘 다 1급이다.
RESULT_TYPES = ("image_generation_call", "image_generation_end")


def collect_results(session_path: str):
    results = []
    with open(session_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = d.get("payload", {}) or {}
            if p.get("type") not in RESULT_TYPES or not p.get("result"):
                continue
            status = p.get("status")
            if status is not None and status != "completed":
                sys.exit(
                    f"extract_imagegen: image_gen call ended with status={status!r} in {session_path}"
                )
            results.append(p["result"])
    return results


def write_png(b64: str, dest: str):
    raw = base64.b64decode(b64)
    if raw[:8] != PNG_MAGIC:
        sys.exit(f"extract_imagegen: decoded data for {dest} is not a PNG (magic mismatch)")
    with open(dest, "wb") as f:
        f.write(raw)
    print(f"OK {dest} {len(raw)} bytes")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if len(args) < 2:
        sys.exit(__doc__)
    session_arg, dest = args[0], args[1]
    index = None
    do_all = "--all" in flags
    for fl in flags:
        if fl.startswith("--index"):
            # supports --index=N or --index N (latter falls into args, so prefer =)
            if "=" in fl:
                index = int(fl.split("=", 1)[1])

    session_path = resolve_session(session_arg)
    results = collect_results(session_path)
    if not results:
        sys.exit(
            f"extract_imagegen: no {' / '.join(RESULT_TYPES)} result in {session_path}\n"
            "  -> image_gen may not have been called, or codex changed its session format."
        )

    if do_all:
        stem, ext = os.path.splitext(dest)
        for i, b64 in enumerate(results):
            write_png(b64, f"{stem}-{i}{ext or '.png'}")
        return

    pick = index if index is not None else len(results) - 1
    if pick < 0 or pick >= len(results):
        sys.exit(f"extract_imagegen: index {pick} out of range (found {len(results)} image result(s))")
    write_png(results[pick], dest)


if __name__ == "__main__":
    main()
