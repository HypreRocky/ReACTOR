# src/rewoo/planner_node.py
'''
Support Ability List:
    - call agent serially or parallelly.
    - assert clarify to add more data from user.


steps type:
{
  "id": "E1",
  "desc": "...",
  "type": "call_agent" | "ask_user" | "router" | "append_history",
  "tool": "credit_report_agent" | "DispatchByIntent" | ...,
  "input": "$WORKING_INPUT" | "#E1.xxx" | {...},
  "depends_on": ["E0", ...],
  "mode": "serial" | "parallel",
  "group": "G1"   # parallel group id (optional)
}
'''

from operator import imod
import re
import stat

from langchain_core.tools import tool
from Prd_Agent.Langgraph_Planner_Project.bank_planner_replan import raw_input
from utils.call_llm import call_llm
from State import ReWOO
from context import Context
import json
from utils.parse_plan import parse_plan_str,steps_to_agenda

def run_planner(state:ReWOO,ctx:Context)-> dict:
    tast = state.get('task') or state['working_input'].get('query','')
    prompt = ctx.planner_prompt.format(task=task,raw_input=state['raw_input'])
    plan_str = ctx.llm_invoke(prompt)

    raw_steps,reasoning = parse_plan_str(plan_str)
    agenda = steps_to_agenda(raw_steps)

    pending_queries = []
    for _,_,tag,tool_input in raw_steps:
        if tag == 'SplitQuery':
            try:
                pending_queries.extend(json.loads(tool_input))
            except Exception:
                pending_queries.extend([x.strip() for x in tool_input.split(',') if x.strip()])
    
    if not pending_queries:
        pending_queries = [state['working_input'].get('query','')]
    
    return {
        "plan_string": plan_str,
        "reasoning_overview": reasoning,
        "plan_agenda": agenda,
        "executed": [],
        "results": {},
        "result_meta": {},
        "slots": {},
        "required_steps": [],
        "pending_question": {},
        "pending_queries": pending_queries,
        "active_query": None,
        "trace": [f"思考过程：{reasoning.strip()}"],
        "eval_status": "",
        "replan_count": 0,
        "max_iteration_limit": state.get("max_iteration_limit", 5),
    }