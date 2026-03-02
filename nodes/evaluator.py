from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from State import ReACTOR
from runtime import AgentRuntime


_QUALITY_KEYS = ("quality", "quality_score", "eval_quality")
_CONFIDENCE_KEYS = ("confidence", "confidence_score", "eval_confidence", "conf")
_FAIL_HINT_KEYS = ("failure_hint", "reason", "error", "message", "hint")


def _iter_values(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        return obj.values()
    if isinstance(obj, list):
        return obj
    return []


def _extract_metric(obj: Any, keys: Tuple[str, ...], depth: int = 0, max_depth: int = 3) -> Optional[float]:
    if depth > max_depth:
        return None
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        for value in _iter_values(obj):
            found = _extract_metric(value, keys, depth + 1, max_depth)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _extract_metric(value, keys, depth + 1, max_depth)
            if found is not None:
                return found
    return None


def _extract_failure_hint(output: Any) -> str:
    if isinstance(output, dict):
        for key in _FAIL_HINT_KEYS:
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in _iter_values(output):
            hint = _extract_failure_hint(value)
            if hint:
                return hint
    return ""


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
        elif isinstance(output, dict) and output.get("status") == "fail":
            failure_hint = (
                output.get("reason")
                or output.get("error")
                or output.get("message")
                or "agent returned fail"
            )
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
                    or _extract_failure_hint(output)
                    or "external evaluator rejected result"
                )
                _mark_replan(str(hint))
            else:
                cfg = state.get("evaluator_config") or {}
                if cfg.get("enable_quality_gate", True):
                    min_conf = float(cfg.get("min_confidence", 0.55))
                    min_quality = float(cfg.get("min_quality", 0.5))
                    confidence = _extract_metric(output, _CONFIDENCE_KEYS)
                    quality = _extract_metric(output, _QUALITY_KEYS)
                    if confidence is not None and confidence < min_conf:
                        _mark_replan(f"low confidence {confidence:.3f} < {min_conf:.3f}")
                    elif quality is not None and quality < min_quality:
                        _mark_replan(f"low quality {quality:.3f} < {min_quality:.3f}")
                    else:
                        state["eval_status"] = "DONE"
                        state["evaluator_hint"] = ""
                        state["trace"].add_text("已经成功处理任务，正在为您整合答案")
                else:
                    state["eval_status"] = "DONE"
                    state["evaluator_hint"] = ""
                    state["trace"].add_text("已经成功处理任务，正在为您整合答案")
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
