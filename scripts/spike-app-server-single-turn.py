#!/usr/bin/env python3
"""
Codex app-server JSON-RPC stdio spike — verify thread-based image_gen pattern.

Phase 0.4 — start daemon, initialize, thread/start, turn/start with text+localImage.
Capture turn-completed notification + locate generated PNG.
"""
import json, subprocess, select, sys, os, time, glob

BASE = os.path.expanduser('~/.claude/skills/my-agent-girlfriend/assets/base/base-character-v1-approved.png')
SPIKE_DIR = os.path.expanduser('~/.claude/skills/my-agent-girlfriend/output/renders/app-server-spike')
GEN_DIR = os.path.expanduser('~/.codex/generated_images')

def open_daemon():
    return subprocess.Popen(
        ['codex', 'app-server', '--listen', 'stdio://'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=1, text=True
    )

class Client:
    def __init__(self, p):
        self.p = p
        self.next_id = 1
        self.pending = {}  # id -> response
        self.notifications = []
    def send(self, method, params=None):
        rid = self.next_id; self.next_id += 1
        msg = {"jsonrpc":"2.0","id":rid,"method":method}
        if params is not None: msg["params"] = params
        self.p.stdin.write(json.dumps(msg)+'\n'); self.p.stdin.flush()
        return rid
    def notify(self, method, params=None):
        msg = {"jsonrpc":"2.0","method":method}
        if params is not None: msg["params"] = params
        self.p.stdin.write(json.dumps(msg)+'\n'); self.p.stdin.flush()
    def pump(self, timeout=120, until_id=None, until_method=None, verbose=False):
        end = time.time()+timeout
        while time.time() < end:
            ready,_,_ = select.select([self.p.stdout],[],[],1)
            if not ready: continue
            line = self.p.stdout.readline()
            if not line: break
            try:
                msg = json.loads(line)
            except:
                if verbose: print('non-json:', line[:200]);
                continue
            if 'id' in msg and ('result' in msg or 'error' in msg):
                self.pending[msg['id']] = msg
                if verbose: print(f'<- response id={msg["id"]} keys={list(msg.get("result",{}))[:5] if "result" in msg else "ERROR"}')
                if until_id is not None and msg['id'] == until_id:
                    return msg
            elif 'method' in msg:
                self.notifications.append(msg)
                m = msg['method']
                if verbose: print(f'<- notify {m}')
                if until_method is not None and m == until_method:
                    return msg
        return None

def main():
    p = open_daemon()
    c = Client(p)
    out = {}
    try:
        # 1) initialize
        rid = c.send("initialize", {"clientInfo":{"name":"kuma-spike","version":"0.0.1"}})
        r = c.pump(timeout=10, until_id=rid)
        out['initialize'] = r
        print('=== initialize ===', json.dumps(r.get('result',{}), ensure_ascii=False)[:300])

        # 2) thread/start — set sandbox to workspace-write so post-processing magick can write
        cwd = '/tmp'
        rid = c.send("thread/start", {
            "approvalPolicy": "never",
            "sandboxPolicy": {"mode": "workspace-write"},
            "cwd": cwd,
        })
        r = c.pump(timeout=15, until_id=rid)
        out['thread_start'] = r
        thread = r.get('result',{}).get('thread',{})
        thread_id = thread.get('id')
        print('=== thread/start ===', f'thread_id={thread_id}')

        if not thread_id:
            print('!! thread_start failed; full response:', json.dumps(r, ensure_ascii=False)[:600])
            return

        # 3) turn/start — first image (idle)
        prompt_idle = (
            'Use the image_gen tool to generate exactly one anime illustration. Then print the absolute '
            'path of the generated PNG on the LAST line of your message.\n\n'
            'Style baseline (preserve from the attached reference image):\n'
            '- Long red hair, white short-sleeve top with soft V-neck, blue floral skirt\n'
            '- 2D anime illustration, wholesome non-sexualized\n'
            '- Half-body shot (waist up), facing forward\n'
            '- Transparent or solid white background\n\n'
            'Pose: idle baseline — relaxed neutral standing, hands relaxed at sides, gentle neutral smile, '
            'eyes looking forward at viewer. NO speech bubble, NO text.\n\n'
            'Output: 1024x1280 portrait.'
        )
        rid = c.send("turn/start", {
            "threadId": thread_id,
            "input": [
                {"type":"localImage", "path": BASE},
                {"type":"text", "text": prompt_idle}
            ],
        })
        # turn/start returns immediately; result includes turn_id/runId. notifications stream until completion.
        r = c.pump(timeout=10, until_id=rid)
        out['turn_start_idle'] = r
        print('=== turn/start (idle) ack ===', json.dumps(r.get('result',{}), ensure_ascii=False)[:400])

        # 4) wait for completion notification
        completed = c.pump(timeout=180, until_method="turn/completed", verbose=True)
        out['turn_completed_idle'] = completed
        print('=== turn/completed (idle) ===', json.dumps(completed, ensure_ascii=False)[:600] if completed else 'TIMEOUT')

        # 5) locate generated PNG (latest in ~/.codex/generated_images/{thread_id}/)
        time.sleep(1)
        candidates = sorted(glob.glob(os.path.expanduser(f'{GEN_DIR}/{thread_id}/ig_*.png')), key=os.path.getmtime, reverse=True)
        if candidates:
            src = candidates[0]
            dst = f'{SPIKE_DIR}/04-idle-app-server.png'
            import shutil; shutil.copy(src, dst)
            print(f'=== copied: {src} -> {dst}')
        else:
            # fallback: search all generated_images recently
            all_imgs = sorted(glob.glob(os.path.expanduser(f'{GEN_DIR}/*/ig_*.png')), key=os.path.getmtime, reverse=True)
            print('=== no images in thread dir; latest 3 anywhere:', all_imgs[:3])

    finally:
        try: p.stdin.close()
        except: pass
        p.terminate()
        try: p.wait(timeout=3)
        except: p.kill()
        # dump stderr
        try:
            err = p.stderr.read()
            if err:
                print('=== stderr (last 800) ===', err[-800:])
        except: pass
    # save outcome
    with open('/tmp/codex-app-server-spike.json', 'w') as f:
        json.dump({k: (v if isinstance(v,(dict,list,str,int,float,bool)) else str(v)) for k,v in out.items()}, f, ensure_ascii=False, indent=2, default=str)
    print('=== outcome saved /tmp/codex-app-server-spike.json')

if __name__ == '__main__':
    main()
