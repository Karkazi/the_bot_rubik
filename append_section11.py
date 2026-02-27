# -*- coding: utf-8 -*-
import os
base = os.path.dirname(os.path.abspath(__file__))
plan_path = os.path.join(base, 'PLAN_UNIFIED_MAX_BOT.md')
append_path = os.path.join(base, 'plan_append_section11.txt')
with open(append_path, 'r', encoding='utf-8') as f:
    appendix = f.read()
with open(plan_path, 'a', encoding='utf-8', newline='\n') as f:
    f.write(appendix)
print('OK')
