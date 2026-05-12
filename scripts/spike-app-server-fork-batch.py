#!/usr/bin/env python3
"""
Phase 0.6 — codex app-server thread/fork batch.
Verify: 1 parent thread (character spec lock) + N forks (different pose nudge each, parallel image_gen).
Compare: serial (1 thread, N turns) vs fork (1 + N parallel) latency.
"""
import json, subprocess, select, os, time, glob, shutil, threading
from collections import defaultdict

BASE = os.path.expanduser('~/.claude/skills/my-agent-girlfriend/assets/base/base-character-v1-approved.png')
OUT_DIR = os.path.expanduser('~/Documents/workspace/personal/my-agent-girlfriend-core/spikes/codex-app-server')
GEN_DIR = os.path.expanduser('~/.codex/generated_images')

POSES = [
    ('wave-hello',   'wave hello pose — right hand raised in a friendly wave at chest level, palm facing viewer, fingers spread, bright cheerful smile, eyes looking at viewer warmly'),
    ('thumbs-up',    'thumbs-up pose — right hand making a clear thumbs-up gesture in front of the body, confident encouraging smile, slight head tilt'),
    ('peace-V',      'peace-V sign pose — right hand making a V (peace) sign next to the cheek, playful happy smile with eyes slightly squinted in joy, fingers cleanly visible'),
    ('thinking-chin', 'thinking pose — right hand bent up with index finger lightly resting on chin, head tilted slightly to the side, eyebrows pulled together a little, eyes looking up-left in contemplation'),
    ('heart-hands',  'heart-hands pose — both hands raised together at chest height forming a small heart shape with fingers, soft loving smile, light pink blush on cheeks, eyes looking sweetly at viewer'),
]

CHAR_SPEC_LOCK = (
    'You will be asked to generate multiple anime illustrations of the same character. '
    'Memorize this character spec precisely:\n\n'
    '- Long red hair, white short-sleeve top with soft V-neck, blue floral skirt\n'
    '- 2D anime illustration, wholesome non-sexualized\n'
    '- Half-body shot (waist up), facing forward\n'
    '- Transparent or solid white background\n'
    '- 1024x1280 portrait, NO speech bubble, NO text overlay\n'
    'Reference image attached for visual anchor.\n\n'
    'For now, just acknowledge with the single word "Acknowledged." Do NOT call image_gen yet. '
    'The actual image generation will happen in follow-up forked threads.'
)

def pose_prompt(pose_desc):
    return (
        f'Generate one image of the same character (already specified in this thread context). '
        f'Pose: {pose_desc}. '
        f'Use image_gen tool now. Print absolute path of the PNG on the LAST line.'
    )

class Daemon:
    def __init__(self):
        self.p = subprocess.Popen(
            ['codex','app-server','--listen','stdio://'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=1, text=True)
        self.next_id = 1
        self.lock = threading.Lock()
        self.responses = {}
        self.notifications_by_thread = defaultdict(list)
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()
    def _read_loop(self):
        for line in self.p.stdout:
            if not line: break
            try: msg = json.loads(line)
            except: continue
            if 'id' in msg and ('result' in msg or 'error' in msg):
                self.responses[msg['id']] = msg
            elif 'method' in msg:
                params = msg.get('params') or {}
                tid = None
                if isinstance(params, dict):
                    tid = params.get('threadId') or (params.get('thread') or {}).get('id') or (params.get('turn') or {}).get('threadId')
                self.notifications_by_thread[tid or '_global'].append(msg)
    def send(self, method, params=None):
        with self.lock:
            rid = self.next_id; self.next_id += 1
        msg = {"jsonrpc":"2.0","id":rid,"method":method}
        if params is not None: msg["params"] = params
        with self.lock:
            self.p.stdin.write(json.dumps(msg)+'\n'); self.p.stdin.flush()
        return rid
    def wait_response(self, rid, timeout=30):
        end = time.time()+timeout
        while time.time() < end:
            if rid in self.responses: return self.responses[rid]
            time.sleep(0.05)
        return None
    def wait_thread_idle(self, thread_id, timeout=240, quiet_after=8):
        """Wait until thread events stop arriving for `quiet_after` seconds."""
        last_count = -1
        last_change = time.time()
        end = time.time()+timeout
        while time.time() < end:
            n = len(self.notifications_by_thread.get(thread_id, []))
            if n != last_count:
                last_count = n
                last_change = time.time()
            elif time.time() - last_change > quiet_after and n > 0:
                return n
            time.sleep(0.5)
        return last_count
    def close(self):
        try: self.p.stdin.close()
        except: pass
        self.p.terminate()
        try: self.p.wait(timeout=3)
        except: self.p.kill()

def find_pngs(thread_id, since):
    pat = os.path.join(GEN_DIR, thread_id, 'ig_*.png')
    return sorted([f for f in glob.glob(pat) if os.path.getmtime(f) > since], key=os.path.getmtime)

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    d = Daemon()
    summary = {'phases': []}
    try:
        # init
        rid = d.send("initialize", {"clientInfo":{"name":"kuma-fork-spike","version":"0.0.1"}})
        d.wait_response(rid, timeout=10)

        # parent thread/start
        rid = d.send("thread/start", {
            "approvalPolicy":"never",
            "sandboxPolicy":{"mode":"workspace-write"},
            "cwd":"/tmp",
        })
        r = d.wait_response(rid, timeout=15)
        parent_id = r['result']['thread']['id']
        print(f'parent thread = {parent_id}')

        # Turn 1 — character spec lock (acknowledge only, no image_gen)
        t0 = time.time()
        rid = d.send("turn/start", {
            "threadId": parent_id,
            "input": [
                {"type":"localImage","path":BASE},
                {"type":"text","text":CHAR_SPEC_LOCK},
            ],
        })
        d.wait_response(rid, timeout=10)
        d.wait_thread_idle(parent_id, timeout=120, quiet_after=8)
        t_ack = time.time() - t0
        print(f'parent turn 1 (ack) duration: {t_ack:.1f}s')
        summary['phases'].append({'step':'parent-ack','duration_s':round(t_ack,1)})

        # Fork × N (sequential send, requests are async)
        fork_ids = []
        t0 = time.time()
        fork_rids = []
        for label, _ in POSES:
            rid = d.send("thread/fork", {"threadId": parent_id})
            fork_rids.append((label, rid))
        for label, rid in fork_rids:
            r = d.wait_response(rid, timeout=15)
            if r and 'result' in r:
                fid = r['result']['thread']['id']
                fork_ids.append((label, fid))
                print(f'fork {label} = {fid}')
            else:
                print(f'fork {label} FAILED: {r}')
        t_forks = time.time() - t0
        summary['phases'].append({'step':'fork-create','count':len(fork_ids),'duration_s':round(t_forks,1)})

        # Send turn/start to all forks back-to-back (parallel image_gen)
        t0 = time.time()
        turn_rids = []
        for label, fid in fork_ids:
            pose_desc = next(p[1] for p in POSES if p[0] == label)
            rid = d.send("turn/start", {
                "threadId": fid,
                "input": [{"type":"text","text": pose_prompt(pose_desc)}],
            })
            turn_rids.append((label, fid, rid))
        for label, fid, rid in turn_rids:
            d.wait_response(rid, timeout=15)
        t_dispatch = time.time() - t0
        print(f'all turn/start dispatched in {t_dispatch:.1f}s')

        # Wait for each fork to finish (parallel)
        results = {}
        per_fork_start = time.time()
        for label, fid, _ in turn_rids:
            n_events = d.wait_thread_idle(fid, timeout=300, quiet_after=8)
            pngs = find_pngs(fid, per_fork_start - 60)
            t_done = time.time() - per_fork_start
            if pngs:
                dst = os.path.join(OUT_DIR, f'08-fork-{label}.png')
                shutil.copy(pngs[-1], dst)
                results[label] = {'png': dst, 'src': pngs[-1], 'events': n_events, 't_done_s': round(t_done,1)}
                print(f'  {label}: ✓ {os.path.basename(pngs[-1])} (t={t_done:.0f}s, events={n_events})')
            else:
                results[label] = {'png': None, 'events': n_events, 't_done_s': round(t_done,1), 'note':'no png'}
                print(f'  {label}: ✗ no PNG (t={t_done:.0f}s, events={n_events})')

        t_batch = time.time() - per_fork_start
        summary['phases'].append({'step':'fork-batch','duration_s':round(t_batch,1),'success':sum(1 for v in results.values() if v.get('png'))})
        summary['parent_thread'] = parent_id
        summary['fork_threads'] = [(l,f) for l,f in fork_ids]
        summary['poses'] = results

        with open('/tmp/codex-fork-batch.json','w') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print('\n=== summary ===')
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        d.close()

if __name__ == '__main__':
    main()
