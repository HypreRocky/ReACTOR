import re
import json
from typing import List
from State import PlanStep

def parse_plan_str(plan_str :str):
    pattern = r'^Plan\s*[:：]\s*(.+?)\s*[\|｜]\s*(\#E\d+)\s*[=＝]\s*([A-Za-z_]\w*)\s*\[(.*)\]\s*$'
    matches = re.findall(pattern, plan_str, flags=re.M)
    
    steps = []
    for desc,var,tool_tag,tool_input in matches:
        steps.append((desc.strip(),var.strip(),tool_tag.strip(),tool_input))
    
    reasoning_match = re.search(r'思考过程：(.+?)(?=Plan:)',plan_str,flags=re.S)
    reasoning_overview = reasoning_match.group(1).strip() if reasoning_match else ''
    
    return steps,reasoning_overview

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

        if tool_tag == 'DispatchByIntent':
            agenda.append({
                'var':var,
                'id':var,
                'desc':desc,
                'type':'dispatch_by_intent',
                'mode':'serial',
                'input':tool_input
            })
            continue

        if tool_tag == 'CallAgent':
            try:
                cfg = json.loads(tool_input)
            except Exception:
                cfg = {'key':'','question':str(tool_input)}
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

        # if planner give an unknown tag, set to dispatch_by_intent as default
        agenda.append({
            'var':var,
            'id':var,
            'desc':f'{desc}(fallback:{tool_tag})',
            'type':'dispatch_by_intent',
            'mode':'serial'
        })
    
    # if agenda do not have any executable calling, add an dispatch_by_intent automatically
    has_exec = any(s['type'] in ('dispatch_by_intent','call_agent') for s in agenda)
    if not has_exec:
        agenda.append({
            'var':'#E_AUTO',
            'id':'#E_AUTO',
            'desc':'自动补充，按意图执行',
            'type':'dispatch_by_intent',
            'mode':'serial'
        })
    
    return agenda