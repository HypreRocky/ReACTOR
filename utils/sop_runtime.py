from statistics import quantiles
from sys import flags
from tokenize import group
from typing import List

from pydantic.type_adapter import R
from Prd_Agent.Langgraph_Planner_Project.State import PlanStep
import re
import json
from State import ReWOO, StepType

def _get_by_path(obj,path:str):
    
    if obj is None:
        return None
    
    if not path or path == '$' :
        return obj
    
    p = path
    if p.startswith('$.'):
        p = p[2:]
    cur = obj

    for key in p.split('.'):
        if isinstance(cur,dict):
            cur = cur.get(key)
        else:
            return None
    return cur

def _dedup_by_var(steps:List[PlanStep]) -> List[PlanStep]:
    have_done = set()
    out = []

    for s in steps:
        v = s.get('var')
        if not v:
            continue
        if v in have_done:
            continue
        have_done.add(v)
        out.append(s)

    return out

def _pick_batch(agenda:List[PlanStep]) -> List[PlanStep]:
    '''
    if head is parallel, then get same group of continous steps run together
    otherwise get one head only
    '''
    if not agenda:
        return []
    head = agenda[0]
    if head.get('mode') == 'parallel':
        group = head.get('group','')
        batch = []
        for s in agenda:
            if s.get('mode') == 'parallel' and s.get('group','') == group:
                batch.append(s)
            else:
                break
        return batch
    return [head]

def extract_patch_by_sop(state:ReWOO,sop:dict) -> dict:
    patch = {'slots_update':{},'facts_append':[]}
    slots_cfg = (sop or {}).get('slots') or {}
    extractors = slots_cfg.get('extractors') or {}

    results = state.get('results') or {}
    meta = state.get('result_meta') or {}
    exsiting = state.get('slots') or {}

    for slot_name,rules in extractors.items():
        if exsiting.get(slot_name) not in (None,[],'',{}):
            continue

        rules_sorted = sorted(rules,key = lambda r: int(r.get('priority',0)))
        for rule in rules_sorted:
            src_agent = rule.get('from')
            path = rule.get('path','$')

            for var,out in results.items():
                m = meta.get(var) or {}
                if m.get('agent') != src_agent:
                    continue
                val = _get_by_path(out,path)
                if val not in (None,{},[],''):
                    patch['slots_update'][slot_name] = val
                    break
            if slot_name in patch['slots_update']:
                break
    
    return patch

def build_required_steps_from_sop(state:ReWOO,sop:dict) -> List[PlanStep]:
    if not sop:
        return []
    
    required: List[StepType] = []
    slots = state.get('slots') or {}

    # agent has done(according to result_meta)
    done_agents = set()
    for var,m in (state.get('result_meta') or {}).items():
        agent = (m or {}).get('agent')
        if agent:
            done_agents.append(agent)

    # 1) insert call_agent in preconditions 
    for pc in sop.get('preconditions',[]) or []:
        pc_id = pc.get('id') or pc.get('agent')
        agent = pc.get('agent')
        if not agent:
            continue
        if agent in done_agents:
            continue

        v = f'#PC_{pc_id}'
        required.append({
            'var':v,
            'id':v,
            'desc':f'SOP前置需求：{pc_id}',
            'type':'call_agent',
            'mode':'serial',
            'agent':agent,
            'input':{'query':pc.get('query','')}
        })
    
    # 2) required slots. insert ask_user.  - var: #ASK_{slot}
    slots_cfg = sop.get('slots') or {}
    req_slots = slots_cfg.get('required') or []
    questions = slots_cfg.get('questions') or {}

    for key in req_slots:
        if slots.get('key') in (None,[],{},''):
            v = f'#ASK_{key}'
            required.append({
                'var':v,
                'id':v,
                'desc':f'补齐信息:{key}',
                'type':'ask_user',
                'mode':'serial',
                'key':key,
                'question':questions.get(key,f'请补充{key}')
            })
    
    return required
