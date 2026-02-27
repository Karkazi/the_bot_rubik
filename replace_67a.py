# -*- coding: utf-8 -*-
import os
base = os.path.dirname(os.path.abspath(__file__))
plan_path = os.path.join(base, 'PLAN_UNIFIED_MAX_BOT.md')
repl_path = os.path.join(base, 'plan_67a_replacement.txt')

with open(plan_path, 'rb') as f:
    data = f.read()
with open(repl_path, 'r', encoding='utf-8') as f:
    new_section = f.read()

start = data.find(b'### 6.7a')
end = data.find(b'### 6.8')
if start < 0 or end < 0:
    raise SystemExit('Markers not found')
out = data[:start] + new_section.encode('utf-8') + data[end:]
with open(plan_path, 'wb') as f:
    f.write(out)
print('OK')
