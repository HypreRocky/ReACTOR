from __future__ import annotations

from dataclasses import is_dataclass
import json
from typing import Any, Dict

from State import ReACTOR
from runtime import AgentRuntime
from prompt.evaluator_prompt import bank_rewoo_evaluator_prompt
from utils.call_llm import execute_react_agent


def _apply_external_hook(state: ReACTOR, runtime: AgentRuntime, output: Any) -> Dict[str, Any]:
    hook = state.get("evaluator_hook") or getattr(runtime, "evaluator_hook", None)
    if not callable(hook):
        return {}
    try:
        res = hook(state, output)
    except Exception as exc:
        state["trace"].add_text(f"评估模型异常，忽略该结果: {exc}")
        return {}
    if isinstance(res, dict):
        return res
    return {}


def _safe_json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def _parse_eval_result(text: str) -> Dict[str, str]:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            decision = str(data.get("decision", "")).strip().upper()
            hint = str(data.get("hint", "")).strip()
            return {"decision": decision, "hint": hint}
    except Exception:
        pass

    upper = text.strip().upper()
    if "PASS" in upper and "FAIL" not in upper:
        return {"decision": "PASS", "hint": ""}
    if "FAIL" in upper:
        return {"decision": "FAIL", "hint": text.strip()}
    return {"decision": "FAIL", "hint": "评估输出无法解析"}


def run_evaluator(state: ReACTOR, runtime: AgentRuntime) -> Dict:
    if state.get("sop_runtime", {}).get("active"):
        return state

    execution = runtime.ensure_execution(state)
    results = execution.results
    replan = runtime.ensure_replan(state)

    if state.get("eval_status") == "NEED_REPLAN":
        if not replan.last_failure:
            replan.last_failure = state.get("evaluator_hint") or "agent returned error"
        state["replan"] = replan
        return state

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

        def _mark_replan(reason: str) -> None:
            state["eval_status"] = "NEED_REPLAN"
            if reason and not replan.last_failure:
                replan.last_failure = reason
            state["evaluator_hint"] = reason
            state["trace"].add_text("结果质量不足，正在为您重新处理任务")

        if status == "fail":
            failure_hint = error or "agent returned fail"
            state["eval_status"] = "NEED_REPLAN"
            if not replan.last_failure:
                replan.last_failure = failure_hint
            state["evaluator_hint"] = failure_hint
            state["trace"].add_text("智能体返回错误，正在为您重新处理任务")
        else:
            hook_result = _apply_external_hook(state, runtime, output)
            if hook_result.get("should_replan") is True:
                hint = (
                    hook_result.get("hint")
                    or hook_result.get("reason")
                    or "external evaluator rejected result"
                )
                _mark_replan(str(hint))
            else:
                task = state.get("task") or state.get("working_input", {}).get("query", "")
                evidence = _safe_json_dumps(runtime.results_to_plain(results))
                answer = _safe_json_dumps(output)

                prompt = bank_rewoo_evaluator_prompt.format(
                    task=task,
                    answer=answer,
                    evidence=evidence,
                )
                eval_text = execute_react_agent(prompt=prompt)
                parsed = _parse_eval_result(eval_text)
                decision = parsed.get("decision", "").upper()
                if decision == "PASS":
                    state["eval_status"] = "DONE"
                    state["evaluator_hint"] = ""
                    state["trace"].add_text("评估通过，正在为您整合答案")
                else:
                    hint = parsed.get("hint") or "评估未通过"
                    _mark_replan(hint)
        if status is None and output is None and error is None:
            state["eval_status"] = "DONE"
            state["evaluator_hint"] = ""
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
