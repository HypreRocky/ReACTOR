from __future__ import annotations

from dataclasses import is_dataclass
from typing import Dict

from State import ReACTOR
from runtime import AgentRuntime


def run_evaluator(state: ReACTOR, runtime: AgentRuntime) -> Dict:
    if state.get("sop_runtime", {}).get("active"):
        return state

    execution = runtime.ensure_execution(state)
    results = execution.results
    replan = runtime.ensure_replan(state)

    if results:
        last_key = list(results.keys())[-1]
        last_res = results.get(last_key)

        if is_dataclass(last_res):
            status = last_res.status
            output = last_res.output
            error = last_res.error
        elif isinstance(last_res, dict):
            status = last_res.get("status")
            output = last_res.get("output")
            error = last_res.get("error")
        else:
            status = None
            output = None
            error = None

        if status == "fail":
            state["eval_status"] = "NEED_REPLAN"
            if not replan.last_failure:
                replan.last_failure = error or "agent returned fail"
            state["trace"].add_text("智能体返回错误，正在为您重新处理任务")
        elif isinstance(output, dict) and output.get("status") == "fail":
            state["eval_status"] = "NEED_REPLAN"
            if not replan.last_failure:
                replan.last_failure = (
                    output.get("reason")
                    or output.get("error")
                    or output.get("message")
                    or "agent returned fail"
                )
            state["trace"].add_text("智能体返回错误，正在为您重新处理任务")
        else:
            state["eval_status"] = "DONE"
            state["trace"].add_text("已经成功处理任务，正在为您整合答案")
        if status is None and output is None and error is None:
            state["eval_status"] = "DONE"
            state["trace"].add_text("已经成功处理任务，正在为您整合答案")

    replan_count = replan.count
    max_limit = replan.max_iteration_limit
    if max_limit and replan_count > max_limit:
        state["eval_status"] = "FAILED"
        state["trace"].add_text(
            "任务请求尝试次数超限，处理失败。十分抱歉未能处理您的问题，如果需要请联系人工客服处理。"
        )

    state["replan"] = replan
    return state
