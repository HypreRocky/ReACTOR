import json

from openai.types.responses.response_code_interpreter_tool_call_param import OutputLogs
from Prd_Agent.Langgraph_Planner_Project.call_plan import payload
from context import Context
from State import ReWOO,PlanStep
from utils.sop_runtime import _get_by_path,_pick_batch
from typing import Any,Dict
from utils.CoTtracer import TraceCollector

def resolve_ref(expr: Any, results: Dict[str, Any]):
    if not isinstance(expr, str):
        return expr
    if not expr.startswith("#"):
        return expr
    if "." in expr:
        ref, sub = expr.split(".", 1)
        base = results.get(ref)
        return _get_by_path(base, "$." + sub)
    return results.get(expr)

def select_agent_by_intent(tool_registry: dict, intent: str) -> str | None:
    for name, info in tool_registry.items():
        if name == "RouterNode":
            continue
        for p in info.get("intent_space", []):
            if intent.startswith(p):
                return name
    return None

def run_worker(state:ReWOO, ctx:Context) -> dict:
    agenda = list(state.get('plan_agenda') or [])
    if not agenda:
        return {}
    
    batch = _pick_batch(agenda)

    results = state.get('results',{})
    meta = state.get('result_meta',{})
    executed = state.get('executed',[])
    trace = state.get('trace',TraceCollector())
    working_input = state['working_input']

    # if ask user, then stop this loop
    if batch[0].get('type') == 'ask_user':
        step = batch[0]
        pending_q = {'key':step.get('key',''),'question':step.get('question','')}
        trace.add_text(f'Missing information:{pending_q["question"]}')
        return {
            'pending_question':pending_q,
            'eval_status': 'NEED_USER',
            'trace' : trace
        }
    
    def run_one(step:PlanStep):
        var = step['var']
        if var in executed:
            return (step,'ALREADY_DONE')
        
        stype = step.get('type')

        if stype == 'append_history':
            ref = step.get('payload_ref','')
            assistant_payload = results.get(ref) if isinstance(ref,str) and ref.startswith('#') else ref
            user_text = working_input.get('query','')

            def _to_text(x):
                if x is None:
                    return ''
                if isinstance(x,str):
                    return x
                try:
                    return json.dumps(x,ensure_ascii=False)[:2000]
                except Exception:
                    return str(x)[:2000]
            
            history = working_input.get('history',[])
            if user_text:
                history.append({
                    'role':'user',
                    'content':user_text
                })
            assistant_text = _to_text(assistant_payload)
            if assistant_text:
                history.append({
                    'role':'assistant',
                    'content':assistant_text
                })
            working_input['history'] = history
            return (step,'OK')
        
        if stype == 'call_agent':
            agent = step.get('agent','')
            tool = ctx.tool_registry.get(agent)
            if not tool:
                raise RuntimeError(f'agent not registered:{agent}')

            exec_fn = tool['execute']
            input = step.get('input','$WORKING_INPUT')
            builder = tool.get('payload_builder')
            if input == '$WORKING_INPUT':
                payload = builder(working_input,state.get('slots') or {})
            elif isinstance(input,str) and input.startswith('#'):
                payload = resolve_ref(input,results)
            elif isinstance(input,dict):
                payload = builder({**working_input,**input},state.get('slots') or {})
            else:
                payload = builder(working_input,state.get('slots') or {})
            
            out = exec_fn(payload)
            return (step,out)
        
        if stype == 'dispatch_by_intent':
            intent = working_input.get('intent','')
            agent = select_agent_by_intent(ctx.tool_registry,intent)

            if not agent:
                return (step,{'status':'no_agent','intent':intent})
            
            tool = ctx.tool_registry[agent]
            exec_fn = tool['execute']
            builder = tool.get('payload_builder')

            payload = builder(working_input,state.get('slots') or {})
            out = exec_fn(payload)

            step2 = dict(step)
            step2['agent'] = agent
            return (step2,out)
        
        raise RuntimeError(f'UNKNOWN STEP. STEP TYPE = {stype}')
    
    outputs = []
    try:
        for s in batch:
            outputs.append(run_one(s))
    except Exception as e:
        trace.add_text(f'worker failed:{e}')
        return {'eval_status':'FAILED','trace':trace}
    
    for step, out in outputs:
        var = step[var]
        results[var] = out
        executed.add(var)
        meta[var] = {
            'type' : step.get('type',''),
            'mode' : step.get('mode','serial'),
            'group' : step.get('group',''),
            'agent': step.get('agent','')
        }
        trace.append(f'Finish {step.get('desc','')} -> {var}')

    new_agenda = agenda[len(batch):]
    return {
        'plan_agenda' : new_agenda,
        'results' : results,
        'result_meta' : meta,
        'executed' : list(executed),
        'working_input' : working_input,
        'trace':trace
    }

    





                

            

