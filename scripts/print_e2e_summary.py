import json

with open('/app/scripts/session_library_e2e_results.json') as f:
    data = json.load(f)

fast = [r for r in data if r['mode'] == 'fast']
deep = [r for r in data if r['mode'] == 'deep']

# matched=True means outcome matched expectation (correct behavior)
fm = len([r for r in fast if r['matched'] == True])
fnm = len([r for r in fast if r['matched'] == False])
dm = len([r for r in deep if r['matched'] == True])
dnm = len([r for r in deep if r['matched'] == False])

print(f'=== E2E Summary ===')
print(f'Fast: total={len(fast)}, matched={fm}, unmatched={fnm}')
print(f'Deep: total={len(deep)}, matched={dm}, unmatched={dnm}')
print(f'ALL:  total={len(data)}, matched={fm+dm}, unmatched={fnm+dnm}')
print()

# Matrix: expect x outcome
print('=== Matrix (expect -> outcome) ===')
for mode in ['fast', 'deep']:
    rows = [r for r in data if r['mode'] == mode]
    for exp in ['answer', 'refuse']:
        for out in ['answer', 'refuse']:
            n = len([r for r in rows if r['expect'] == exp and r['outcome'] == out])
            m = len([r for r in rows if r['expect'] == exp and r['outcome'] == out and r['matched'] == True])
            print(f'  {mode} | expect={exp}, outcome={out}: {n} (matched={m})')
print()

# Per-session breakdown
print('=== Per-session ===')
for sess in sorted(set(r['session'] for r in data)):
    rows = [r for r in data if r['session'] == sess]
    m = len([r for r in rows if r['matched'] == True])
    print(f'  {sess}: {len(rows)} turns, matched={m}/{len(rows)}')
print()

# Failed turns (unmatched)
print('=== Unmatched turns (failures) ===')
for r in data:
    if r['matched'] == False:
        print(f'  T{r["turn"]:02d} | {r["session"]} | {r["mode"]} | expect={r["expect"]} outcome={r["outcome"]} | libs={str(r["libs"])[:40]} | cite={r["citations"]}')
        ans = str(r.get("answer", ""))[:120]
        print(f'    Q: {r["question"][:80]}')
        print(f'    A: {ans}')
        print()
