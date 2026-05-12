#!/usr/bin/env python3
"""
Phase 0.7 — fork debug. Single fork, explicit cwd/sandbox inherit.
Tests two hypotheses for why Phase 0.6 fork batch produced no PNG:
  H1: fork didn't inherit cwd/sandbox → image_gen blocked by sandbox
  H2: parent ack-only turn meant image_gen tool not registered in thread → fork can't call it

Strategy: parent does ONE image_gen call first (so tool is exercised in thread history),
then fork once with explicit cwd/sandbox, then fork attempts a different pose.
Ensures wait_thread_idle uses long quiet_after so we don't bail before image_gen completes.
"""
import json, subprocess, select, os, time, glob, shutil, threading
from collections import defaultdict

BASE = os.path.expanduser('~/.claude/skills/my-agent-girlfriend/assets/base/base-character-v1-approved.png')
OUT_DIR = os.path.expanduser('~/Documents/workspace/personal/my-agent-girlfriend-core/spikes/codex-app-server')
GEN_DIR = os.path.expanduser('~/.codex/generated_images')

class Daemon:
    def __init__(self):
        self.p = subprocess.Popen(['codex','app-server','--listen','stdio://'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=1, text=True)
        self.next_id = 1
        self.lock = threading.Lock()
        self.responses = {}
        self.notifications_by_thread = defaultdict(list)
        self.last_event_ts = defaultdict(lambda: 0)
        threading.Thread(target=self._reader, daemon=True).start()
    def _reader(self):
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
                    tid = (params.get('threadId')
                           or (params.get('thread') or {}).get('id')
                           or (params.get('turn') or {}).get('threadId'))
                key = tid or '_global'
                self.notifications_by_thread[key].append(msg)
                self.last_event_ts[key] = time.time()
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
    def wait_idle(self, thread_id, quiet_after=20, timeout=300):
        """Wait until no events for thread_id in the last `quiet_after` seconds AND at least one event seen."""
        end = time.time()+timeout
        while time.time() < end:
            n = len(self.notifications_by_thread.get(thread_id, []))
            last = self.last_event_ts.get(thread_id, 0)
            if n > 0 and last > 0 and (time.time() - last) > quiet_after:
                return n
            time.sleep(0.5)
        return -1
    def close(self):
        try: self.p.stdin.close()
        except: pass
        self.p.terminate()
        try: self.p.wait(timeout=3)
        except: self.p.kill()

def find_pngs(thread_id, since_ts):
    pat = os.path.join(GEN_DIR, thread_id, 'ig_*.png')
    return sorted([f for f in glob.glob(pat) if os.path.getmtime(f) > since_ts], key=os.path.getmtime)

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    d = Daemon()
    summary = {}
    try:
        rid = d.send("initialize", {"clientInfo":{"name":"kuma-fork-debug","version":"0.0.1"}})
        d.wait_response(rid, 10)

        # 1) parent — start with explicit sandbox + cwd
        rid = d.send("thread/start", {
            "approvalPolicy":"never",
            "sandboxPolicy":{"mode":"workspace-write"},
            "cwd":"/tmp",
        })
        r = d.wait_response(rid, 15)
        parent_id = r['result']['thread']['id']
        print(f'parent={parent_id}')
        summary['parent'] = parent_id

        # 2) parent turn 1 — REAL image_gen so tool gets exercised in thread history
        prompt_parent = (
            'Use image_gen to generate one anime illustration. Print absolute PNG path on the LAST line.\n\n'
            'Style: long red hair, white V-neck top, blue floral skirt, 2D anime, half-body, 1024x1280.\n'
            'Pose: idle baseline — relaxed standing, neutral smile, hands at sides.\n'
            'NO text, NO speech bubble.'
        )
        t0 = time.time()
        rid = d.send("turn/start", {
            "threadId": parent_id,
            "input": [{"type":"localImage","path":BASE},{"type":"text","text":prompt_parent}],
        })
        d.wait_response(rid, 10)
        d.wait_idle(parent_id, quiet_after=15, timeout=240)
        t_parent = time.time() - t0
        parent_pngs = find_pngs(parent_id, t0 - 1)
        print(f'parent turn done {t_parent:.1f}s, parent PNGs={len(parent_pngs)}')
        if parent_pngs:
            shutil.copy(parent_pngs[-1], os.path.join(OUT_DIR, '10-fork-debug-parent.png'))
        summary['parent_turn'] = {'duration_s': round(t_parent,1), 'png_count': len(parent_pngs)}

        # 3) fork once — explicit cwd/sandbox
        rid = d.send("thread/fork", {
            "threadId": parent_id,
            "approvalPolicy":"never",
            "sandboxPolicy":{"mode":"workspace-write"},
            "cwd":"/tmp",
        })
        r = d.wait_response(rid, 15)
        fork_id = r['result']['thread']['id']
        print(f'fork={fork_id}')
        summary['fork'] = fork_id

        # 4) fork turn — pose nudge only
        prompt_fork = (
            'Generate the same character in a different pose: '
            'right hand making a clear thumbs-up at chest, confident smile, slight head tilt. '
            'Use image_gen tool now. Print absolute PNG path on the LAST line.'
        )
        t0 = time.time()
        rid = d.send("turn/start", {
            "threadId": fork_id,
            "input": [{"type":"text","text":prompt_fork}],
        })
        d.wait_response(rid, 10)
        d.wait_idle(fork_id, quiet_after=15, timeout=240)
        t_fork = time.time() - t0
        fork_pngs = find_pngs(fork_id, t0 - 1)
        print(f'fork turn done {t_fork:.1f}s, fork PNGs={len(fork_pngs)}')
        if fork_pngs:
            shutil.copy(fork_pngs[-1], os.path.join(OUT_DIR, '11-fork-debug-thumbs-up.png'))
        summary['fork_turn'] = {'duration_s': round(t_fork,1), 'png_count': len(fork_pngs)}

        with open('/tmp/codex-fork-debug.json','w') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print('\n=== summary ===')
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        d.close()

if __name__ == '__main__':
    main()
