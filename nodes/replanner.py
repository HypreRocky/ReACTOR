from __future__ import annotations

from typing import Dict

from State import ExecutionState, ReACTOR
from runtime import AgentRuntime


def run_replanner(state: ReACTOR, runtime: AgentRuntime) -> Dict:
    raw_input = state["raw_input"]

    if state.get("sop_runtime", {}).get("active"):
        return state

    history = raw_input.get("history", [])

    if history:
        state["working_input"]["history"] = history[-1:]
    else:
        state["working_input"]["history"] = []

    replan = runtime.ensure_replan(state)
    if not replan.max_iteration_limit:
        replan.max_iteration_limit = raw_input.get("recursion_limit", 10)
    replan.last_plan = state.get("plan_string", "")
    execution = runtime.ensure_execution(state)
    replan.last_results = runtime.results_to_plain(execution.results)
    if not replan.last_failure:
        replan.last_failure = "unknown"
    replan.count += 1
    state["replan"] = replan

    state.update(
        {
            "task": raw_input.get("query", ""),
            "plan_string": "",
            "reasoning_overview": "",
            "execution": ExecutionState(
                steps=[],
                results={},
                idx=0,
            ),
            "pending_queries": [],
            "active_query": None,
            "eval_status": "",
            "route": None,
            "routes": None,
        }
    )

    state["trace"].add_text("正在为您重新规划任务...")

    return state
