from openai import max_retries
from context import Context
from State import ReWOO
from utils.sop_runtime import _dedup_by_var

def run_replanner(state:ReWOO,ctx:Context):
    count = int(state.get('replan_count') or 0) + 1
    max_retries = state.get('max_iteration_limit') or 3
    trace = state.get('trace')
    if count > max_retries:
        trace.add_text('Exceeding the limitation of replan. End processing.')
        return {'eval_status':'FAILED','trace':trace}
    
    required = state.get('required_steps') or []
    agenda = state.get('plan_agenda') or []
    new_agenda = _dedup_by_var(required + agenda)

    trace.add_text(f'Replan task. Insert {len(required)} steps.')

    return {
        "plan_agenda": new_agenda,
         "required_steps": [],  # reset
         "replan_count": count, 
         "eval_status": "",     #reset
         "trace": trace
         }