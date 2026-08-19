#!/usr/bin/env python3
import json, subprocess, time, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECK_DIR = ROOT / 'engine-tests' / 'decks'
RESULT_DIR = ROOT / 'engine-tests' / 'results'
RESULT_DIR.mkdir(parents=True, exist_ok=True)


def parse_dck(path: Path):
    section = None
    commanders, main = [], []
    for raw in path.read_text().splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith('[') and s.endswith(']'):
            section = s.lower()
            continue
        if not s[0].isdigit() or ' ' not in s:
            continue
        count_s, name = s.split(' ', 1)
        count = int(count_s)
        name = name.split('|', 1)[0].strip()
        target = commanders if section == '[commander]' else main if section == '[main]' else None
        if target is not None:
            target.extend([name] * count)
    cards = commanders + main
    assert len(cards) == 100, (path, len(cards))
    return commanders, cards


def player(name, filename, ai):
    commanders, cards = parse_dck(DECK_DIR / filename)
    return {
        'name': name,
        'commanderNames': commanders,
        'deck': [{'name': c} for c in cards],
        'ai': ai,
    }


def rpc(proc, obj):
    line = json.dumps(obj, separators=(',', ':'))
    proc.stdin.write(line + '\n')
    proc.stdin.flush()
    response = proc.stdout.readline()
    if not response:
        raise RuntimeError('interactive harness closed stdout')
    parsed = json.loads(response)
    if not parsed.get('ok'):
        raise RuntimeError(parsed.get('error'))
    return parsed.get('result', '')


def main():
    if len(sys.argv) != 3:
        print('usage: manabrew_smoke.py HARNESS_JAR FORGE_GUI_DIR', file=sys.stderr)
        return 2
    jar, forge_gui = sys.argv[1], sys.argv[2]
    stderr_path = RESULT_DIR / 'manabrew-harness-stderr.log'
    stderr_f = stderr_path.open('w')
    proc = subprocess.Popen(
        ['java', '-Xmx4g', '-jar', jar, '--interactive-server', '--forge-home', forge_gui],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr_f,
        text=True, bufsize=1,
    )
    try:
        payload = {
            'gameId': 'kinnan-smoke-1',
            'variant': 'Commander',
            'startingLife': 40,
            'seed': 424242,
            'players': [
                player('Kinnan External', 'Kinnan_TestB.dck', False),
                player('RogSi AI', 'RogSi_2026.dck', True),
                player('Blue Farm AI', 'Blue_Farm_2026.dck', True),
                player('RogThras AI', 'RogThras_2026.dck', True),
            ],
        }
        start_raw = rpc(proc, {'command': 'startGame', 'payload': json.dumps(payload, separators=(',', ':'))})
        start = json.loads(start_raw)
        session = start['sessionId']
        (RESULT_DIR / 'manabrew-start.json').write_text(json.dumps(start, indent=2))

        prompt_raw = ''
        for _ in range(300):
            prompt_raw = rpc(proc, {'command': 'getPrompt', 'sessionId': session, 'playerIndex': 0})
            if prompt_raw:
                break
            time.sleep(0.1)
        if not prompt_raw:
            raise RuntimeError('no Kinnan prompt appeared within 30 seconds')

        snap_raw = rpc(proc, {'command': 'getSnapshot', 'sessionId': session, 'viewer': 0})
        (RESULT_DIR / 'manabrew-first-prompt.json').write_text(
            json.dumps(json.loads(prompt_raw), indent=2) if prompt_raw.strip().startswith('{') else prompt_raw
        )
        (RESULT_DIR / 'manabrew-first-snapshot.json').write_text(
            json.dumps(json.loads(snap_raw), indent=2) if snap_raw.strip().startswith('{') else snap_raw
        )
        summary = {
            'session': session,
            'prompt': json.loads(prompt_raw) if prompt_raw.strip().startswith('{') else prompt_raw,
            'snapshot': json.loads(snap_raw) if snap_raw.strip().startswith('{') else snap_raw,
        }
        (RESULT_DIR / 'manabrew-smoke-summary.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps({'ok': True, 'session': session, 'promptType': summary['prompt'].get('type') if isinstance(summary['prompt'], dict) else None}))
        try:
            rpc(proc, {'command': 'endGame', 'sessionId': session})
        except Exception:
            pass
        try:
            rpc(proc, {'command': 'quit'})
        except Exception:
            pass
        return 0
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        stderr_f.close()

if __name__ == '__main__':
    raise SystemExit(main())
