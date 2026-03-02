import re
import json
from typing import List
from State import PlanStep

def _normalize_tool_input(raw: str) -> str:
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        inner = s[1:-1].strip()
        # Strip quotes for JSON-like payloads or simple scalars
        if inner:
            if inner[0] in "[{":
                s = inner
            elif s[0] not in inner:
                s = inner
    return s


def parse_plan_str(plan_str: str):
    # Support ASCII/full-width punctuation and flexible spacing, parse per-line to avoid
    # prematurely stopping on ']' inside JSON list payloads.
    pattern = r'^Plan[:：]\s*(.*?)\s*[|\uFF5C]\s*(#E\d+)\s*[=＝]\s*([A-Za-z_]\w*)\s*\[(.*)\]\s*$'
    steps = []
    for line in plan_str.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(pattern, line)
        if not match:
            continue
        desc, var, tool_tag, tool_input = match.groups()
        steps.append(
            (
                desc.strip(),
                var.strip(),
                tool_tag.strip(),
                _normalize_tool_input(tool_input),
            )
        )

    reasoning_match = re.search(r'思考过程[:：](.+?)(?=Plan[:：])', plan_str, flags=re.S)
    reasoning_overview = reasoning_match.group(1).strip() if reasoning_match else ""

    return steps, reasoning_overview

def steps_to_agenda(raw_steps: List[tuple],working_input: dict) -> List[PlanStep]:
    '''
    convert tuple step to agenda steps(PlanStep dict)
    '''
    agenda: List[PlanStep] = []
    for desc,var,tool_tag,tool_input in raw_steps:
        if tool_tag == 'AppendHistory':
            agenda.append({
                'var':var,
                'id':var,
                'desc':desc,
                'type':'append_history',
                'mode':'serial',
                'payload_ref':tool_input
                })
            continue


        if tool_tag == 'SerialCallAgent':
            try:
                cfg = json.loads(tool_input)
            except Exception:
                cfg = {'agent': str(tool_input), 'input': '$WORKING_INPUT'}
            agenda.append({
                'var':var,
                'id':var,
                'desc':desc,
                'type':'call_agent',
                'mode':'serial',
                'agent':cfg.get('agent') if isinstance(cfg,dict) else '',
                'input':cfg
                })
            continue
        if tool_tag == 'ParallelCallAgent':
            try:
                cfg = json.loads(tool_input)
            except Exception:
                cfg = []
            agenda.append({
                'var':var,
                'id':var,
                'desc':desc,
                'type':'call_agent',
                'mode':'parallel',
                'agent':'',
                'input':cfg
                })
            continue

        if tool_tag == 'AskUser':
            try:
                cfg = json.loads(tool_input)
            except Exception:
                cfg = {'key':'','question':str(tool_input)}
            agenda.append({
                'var':var,
                'id':var,
                'desc':desc,
                'type':'ask_user',
                'mode':'serial',
                'key':cfg.get('key',''),
                'question':cfg.get('question','')
            })
            continue

        # if planner gives an unknown tag, keep a placeholder step for debugging
        agenda.append({
            'var':var,
            'id':var,
            'desc':f'{desc}(unknown:{tool_tag})',
            'type':'unknown',
            'mode':'serial'
        })

    # if agenda does not have any executable calling, do not auto-insert steps
    has_exec = any(s['type'] == 'call_agent' for s in agenda)
    if not has_exec:
        return agenda
    
    return agenda
