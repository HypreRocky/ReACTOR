
from inspect import istraceback
import stat
from Prd_Agent.Langgraph_Planner_Project.State import ReWOO
from context import Context
from utils.sop_runtime import extract_patch_by_sop,build_required_steps_from_sop
'''
Support Ability List:
    - get SOP and detect the steps. Assert the remain steps into replanner.

function:
    - extract_patch : extract update slots from results/agent response.    <e.g: 投资期限、偏好>
    - SOP cursor : check whether current SOP step match the 'DONE' condition.(In run_evaluator)
    - generate required_step : be asserted into replan.(In run_evaluator)
'''

def run_evaluator(state:ReWOO,ctx:Context) -> dict:
    if state.get('eval_status') in ('FAILED' or 'NEED_USER'):
        return {}
    
    intent = state.get('working_input',{}).get('intent','') or state.get('router_result','')
    sop = ctx.sop_list.get(intent)

    if sop:
        patch = extract_patch_by_sop(state,sop)
        slots = state.get('slots',{})
        slots.update(patch.get('slots_update') or {})
        state['slots'] = slots
        state['last_patch'] = patch

        required = build_required_steps_from_sop(state,sop)
        if required:
            trace = state['trace']
            trace.add_text(f'SOP need more preconditions. Insert {len(required)} steps.')
            return {'required_steps':required,'eval_status':'NEED_REPLAN','trace':trace}
    if not (state.get("plan_agenda") or []):
        pq = list(state.get("pending_queries") or [])
        if pq:
            next_q = pq.pop(0)

            working_input = dict(state.get("working_input") or {})
            working_input["query"] = next_q

            working_input["prev_intent"] = working_input.get("intent", "")
            working_input["intent"] = ""

            trace = list(state.get("trace", []))
            trace.append(f"切换子问题：{next_q} -> 回到 Router 重新导航")

            return {
                "pending_queries": pq,
                "active_query": next_q,
                "working_input": working_input,
                "plan_agenda": [],     
                "executed": [],         
                "eval_status": "NEXT_QUERY",
                "trace": trace
            }
            
    return {'eval_status':'DONE'}

        
