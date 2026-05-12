#!/usr/bin/env python3
"""
Phase 0.5 — same thread, 3 turns, accumulating PNGs.
Tests continuation: turn 1 carries full character spec; turns 2/3 are short nudges.
If thread context truly persists, turns 2/3 should preserve style without re-specifying.
"""
import json, subprocess, select, os, time, glob, shutil

BASE = os.path.expanduser('~/.claude/skills/my-agent-girlfriend/assets/base/base-character-v1-approved.png')
SPIKE_DIR = os.path.expanduser('~/.claude/skills/my-agent-girlfriend/output/renders/app-server-spike')
GEN_DIR = os.path.expanduser('~/.codex/generated_images')

class Client:
    def __init__(self):
        self.p = subprocess.Popen(
            ['codex','app-server','--listen','stdio://'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=1, text=True)
        self.next_id = 1
    def send(self, method, params=None):
        rid = self.next_id; self.next_id += 1
        msg = {"jsonrpc":"2.0","id":rid,"method":method}
        if params is not None: msg["params"] = params
        self.p.stdin.write(json.dumps(msg)+'\n'); self.p.stdin.flush()
        return rid
    def pump_until_response(self, rid, timeout=20):
        end = time.time()+timeout
        while time.time() < end:
            ready,_,_ = select.select([self.p.stdout],[],[],1)
            if not ready: continue
            line = self.p.stdout.readline()
            if not line: break
            try: msg = json.loads(line)
            except: continue
            if msg.get('id') == rid: return msg
        return None
    def pump_until_thread_idle(self, thread_id, timeout=240):
        """End-of-turn detection: wait for thread/status/changed to idle, OR token-usage update + extended quiet."""
        end = time.time()+timeout
        last_event = time.time()
        saw_status_idle = False
        events = []
        while time.time() < end:
            ready,_,_ = select.select([self.p.stdout],[],[],1)
            if not ready:
                # 5s of silence after token-usage/account/rateLimits → consider turn done
                if events and (time.time() - last_event) > 5:
                    last_methods = [e.get('method') for e in events[-6:]]
                    if any('hook/completed' in (m or '') for m in last_methods) or any('tokenUsage' in (m or '') for m in last_methods):
                        return events
                continue
            line = self.p.stdout.readline()
            if not line: break
            try: msg = json.loads(line)
            except: continue
            events.append(msg)
            last_event = time.time()
            m = msg.get('method','')
            if m == 'thread/status/changed':
                params = msg.get('params',{}) or {}
                st = params.get('status',{}).get('type') if isinstance(params.get('status'), dict) else params.get('status')
                if st == 'idle':
                    saw_status_idle = True
            if saw_status_idle and m in ('hook/completed','thread/tokenUsage/updated','account/rateLimits/updated'):
                # consider done after seeing idle status + closure events
                # but allow more events to flush
                pass
        return events
    def close(self):
        try: self.p.stdin.close()
        except: pass
        self.p.terminate()
        try: self.p.wait(timeout=3)
        except: self.p.kill()

def find_new_pngs(thread_id, since_ts):
    pat = os.path.join(GEN_DIR, thread_id, 'ig_*.png')
    return sorted([f for f in glob.glob(pat) if os.path.getmtime(f) > since_ts], key=os.path.getmtime)

def run_turn(c, thread_id, prompt, base=None, label=''):
    print(f'\n>>> turn: {label}')
    started_at = time.time()
    inp = []
    if base:
        inp.append({"type":"localImage","path":base})
    inp.append({"type":"text","text":prompt})
    rid = c.send("turn/start", {"threadId":thread_id, "input":inp})
    ack = c.pump_until_response(rid, timeout=10)
    print(f'    ack: {(ack.get("result") or {}).get("turn",{}).get("id","?")}')
    events = c.pump_until_thread_idle(thread_id, timeout=240)
    duration = time.time() - started_at
    new_pngs = find_new_pngs(thread_id, started_at - 1)
    print(f'    duration: {duration:.1f}s, events: {len(events)}, new pngs: {len(new_pngs)}')
    return new_pngs, duration, events

def main():
    c = Client()
    try:
        # initialize
        rid = c.send("initialize", {"clientInfo":{"name":"kuma-spike-cont","version":"0.0.1"}})
        c.pump_until_response(rid)

        # thread/start
        rid = c.send("thread/start", {
            "approvalPolicy":"never",
            "sandboxPolicy":{"mode":"workspace-write"},
            "cwd":"/tmp",
        })
        r = c.pump_until_response(rid, timeout=15)
        thread = r.get('result',{}).get('thread',{})
        thread_id = thread.get('id')
        print(f'thread_id = {thread_id}')

        # Turn 1 — full character spec + idle pose, with base ref
        prompt1 = (
            'Use the image_gen tool to generate exactly one anime illustration. '
            'Reference image attached for style anchor. Print the absolute path of the generated PNG on the LAST line.\n\n'
            'Character: long red hair, white short-sleeve top with soft V-neck, blue floral skirt, '
            '2D anime illustration, wholesome non-sexualized, half-body shot (waist up), '
            'transparent or solid white background.\n\n'
            'Pose: idle baseline — relaxed neutral standing, hands relaxed at sides, gentle neutral smile, '
            'eyes looking forward at viewer.\n\n'
            'Output: 1024x1280 portrait. NO speech bubble, NO text overlay. '
            'Remember this character spec — I will request more variations of the same character in follow-up turns.'
        )
        pngs1, t1, _ = run_turn(c, thread_id, prompt1, base=BASE, label='1-idle (full spec)')

        # Turn 2 — short nudge only, NO base ref, NO style respec — relies on thread context
        prompt2 = (
            'Now generate the same character in a different pose: emotionally crying while covering mouth — '
            'right hand pressed gently against the mouth, eyebrows pulled together with sadness, '
            'eyes welling up with visible tears, mouth hidden behind hand, body slightly hunched in restrained sob, '
            'face flushed light pink. Same style and outfit as before. NO speech bubble.'
        )
        pngs2, t2, _ = run_turn(c, thread_id, prompt2, base=None, label='2-crying-mouth-cover (short nudge)')

        # Turn 3 — short nudge only, again no base ref, no style respec
        prompt3 = (
            'Now generate the same character in a tehepero / akanbe pose: hands tucked behind the back, '
            'body leaning slightly forward, head tilted forward with chin slightly down, eyes glanced upward toward viewer, '
            'one eye winked closed, small pink tongue stuck out playfully, light playful pink blush. '
            'Wholesome, modest V-neckline (no chest emphasis). Same style and outfit as before. NO speech bubble.'
        )
        pngs3, t3, _ = run_turn(c, thread_id, prompt3, base=None, label='3-tehepero (short nudge)')

        # Copy last PNG of each turn into spike dir
        results = {}
        for label, dst, pngs, dur in [
            ('idle', '05-idle-app-server-thread.png', pngs1, t1),
            ('crying', '06-crying-mouth-cover-app-server-thread.png', pngs2, t2),
            ('tehepero', '07-tehepero-app-server-thread.png', pngs3, t3),
        ]:
            if pngs:
                shutil.copy(pngs[-1], os.path.join(SPIKE_DIR, dst))
                results[label] = {'dst': dst, 'src': pngs[-1], 'duration_s': round(dur,1)}
                print(f'COPIED {label}: {pngs[-1]} -> {dst}')
            else:
                results[label] = {'dst': None, 'duration_s': round(dur,1), 'note': 'no png produced'}
                print(f'WARN {label}: no png produced')

        # Save summary
        with open('/tmp/codex-app-server-continuation.json','w') as f:
            json.dump({
                'thread_id': thread_id,
                'session_path': thread.get('path'),
                'turns': results,
            }, f, ensure_ascii=False, indent=2)
        print('\n=== summary ===')
        print(json.dumps(results, ensure_ascii=False, indent=2))

    finally:
        c.close()

if __name__ == '__main__':
    main()
