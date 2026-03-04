from __future__ import annotations

import json
from typing import Dict

from State import ExecutionState, ReACTOR
from prompt.planner_prompt import bank_rewoo_planner_prompt
from runtime import AgentRuntime
from utils.call_llm import execute_react_agent
from utils.parse_plan import parse_plan_str
from utils.sop_engine import build_plan_from_sop


def run_planner(state: ReACTOR, runtime: AgentRuntime) -> Dict:
    task = state["task"]
    sop_runtime = state.get("sop_runtime") or {}
    active_sop_id = sop_runtime.get("active_sop_id")
    sop_match = None
    if active_sop_id and active_sop_id in runtime.sop_registry:
        sop_match = runtime.sop_registry.get(active_sop_id)
    if sop_match is None:
        sop_match = runtime.match_sop(task)
    if sop_match is None:
        history = state.get("working_input", {}).get("history") or []
        for item in reversed(history):
            if isinstance(item, dict) and item.get("role") == "user":
                cand = runtime.match_sop(item.get("content", ""))
                if cand is not None:
                    sop_match = cand
                    break
    if sop_match:
        return build_plan_from_sop(sop_match, state)

    replan_hint = runtime.build_replan_hint(state)
    agent_catalog = runtime.agent_catalog
    sop_catalog = runtime.sop_catalog
    prompt = bank_rewoo_planner_prompt.format(
        task=task,
        replan_hint=replan_hint,
        agent_catalog=agent_catalog,
        sop_catalog=sop_catalog,
    )

    plan_str = execute_react_agent(prompt=prompt)
    steps, reasoning_overview = parse_plan_str(plan_str)

    pending_queries = []
    for plan_text, step_var, tool_tag, tool_input in steps:
        if tool_tag == "SplitQuery":
            if isinstance(tool_input, str):
                try:
                    queries = json.loads(tool_input)
                except Exception:
                    queries = [q.strip() for q in tool_input.split(",")]
            else:
                queries = list(tool_input)
            pending_queries.extend(queries)

    if not pending_queries:
        pending_queries = [state["working_input"]["query"]]

    return {
        "plan_string": plan_str,
        "reasoning_overview": reasoning_overview,
        "execution": ExecutionState(
            steps=steps,
            results={},
            idx=0,
        ),
        "pending_queries": pending_queries,
        "active_query": None,
    }
