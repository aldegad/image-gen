#!/usr/bin/env python3
"""
Phase 0.8 — codex exec parallel spawn (N processes, no thread API).
Most direct test of dramatic time saving for game-asset batch generation.
Each process is independent (no character lock via thread context — relies on base ref + full prompt).
"""
import os, subprocess, time, glob, shutil, threading, tempfile

BASE = os.path.expanduser('~/.claude/skills/my-agent-girlfriend/assets/base/base-character-v1-approved.png')
OUT_DIR = os.path.expanduser('~/Documents/workspace/personal/my-agent-girlfriend-core/spikes/codex-app-server')
GEN_DIR = os.path.expanduser('~/.codex/generated_images')

POSES = [
    ('wave-hello',   'right hand raised in friendly wave at chest, palm to viewer, fingers spread, bright smile'),
    ('thumbs-up',    'right hand making clear thumbs-up at chest, confident smile, slight head tilt'),
    ('peace-V',      'right hand making V (peace) sign next to cheek, playful happy smile, eyes squinted in joy'),
    ('thinking-chin', 'right hand index finger lightly on chin, head tilted, brows pulled together, eyes up-left in contemplation'),
    ('heart-hands',  'both hands together at chest height forming small heart with fingers, soft loving smile, light pink blush'),
]

CHAR_COMMON = (
    'Use image_gen to generate exactly one image. Print absolute path of the PNG on the LAST line.\n\n'
    'Style (preserve from attached reference):\n'
    '- Long red hair, white V-neck top, blue floral skirt\n'
    '- 2D anime, wholesome non-sexualized, half-body shot, facing forward\n'
    '- 1024x1280 portrait, NO speech bubble, NO text\n\n'
)

results = {}
result_lock = threading.Lock()

def run_one(label, pose_desc):
    started = time.time()
    tmp = tempfile.mkdtemp(prefix='codex-image-')
    prompt = CHAR_COMMON + f'Pose: {pose_desc}.'
    cmd = [
        'codex','exec',
        '--skip-git-repo-check',
        '-C', tmp,
        '-o', os.path.join(tmp,'last.txt'),
        '--add-dir', os.path.expanduser('~/.codex/generated_images'),
        '-i', BASE,
        '--', prompt,
    ]
    try:
        cp = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=240)
        duration = time.time() - started
        # find latest PNG belonging to this run (by mtime > started)
        pngs = sorted(
            [f for f in glob.glob(os.path.join(GEN_DIR,'*','ig_*.png')) if os.path.getmtime(f) > started],
            key=os.path.getmtime,
        )
        if pngs:
            dst = os.path.join(OUT_DIR, f'09-parallel-{label}.png')
            shutil.copy(pngs[-1], dst)
            with result_lock:
                results[label] = {'png': dst, 'src': pngs[-1], 'duration_s': round(duration,1), 'rc': cp.returncode}
            print(f'  [{label}] ✓ {duration:.1f}s rc={cp.returncode} -> {os.path.basename(dst)}')
        else:
            with result_lock:
                results[label] = {'png': None, 'duration_s': round(duration,1), 'rc': cp.returncode, 'note':'no png'}
            print(f'  [{label}] ✗ {duration:.1f}s rc={cp.returncode} (no png)')
    except subprocess.TimeoutExpired:
        with result_lock:
            results[label] = {'png': None, 'duration_s': 240, 'note':'timeout'}
        print(f'  [{label}] timeout 240s')

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    threads = []
    t0 = time.time()
    for label, pose in POSES:
        t = threading.Thread(target=run_one, args=(label, pose), daemon=False)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    total = time.time() - t0
    print(f'\n=== TOTAL elapsed: {total:.1f}s for {len(POSES)} parallel ===')
    success = sum(1 for v in results.values() if v.get('png'))
    print(f'success: {success}/{len(POSES)}')
    import json
    with open('/tmp/codex-parallel-batch.json','w') as f:
        json.dump({'total_s': round(total,1), 'success': success, 'results': results}, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
