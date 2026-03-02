from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from State import StepResult, ReACTOR
from runtime import AgentRuntime
from utils.ReACTORTracer import TraceCollector
from utils.append_history import extract_plain_text
from utils.agent_response import validate_agent_response


def _ensure_trace(state: ReACTOR) -> TraceCollector:
    trace = state.get("trace")
    if isinstance(trace, TraceCollector):
        return trace
    return TraceCollector(event_type="planning")


def _parse_call_config(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return {"agent": raw}
        except Exception:
            return {"agent": raw}
    return {}


def _parse_call_list(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [_parse_call_config(item) for item in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        if isinstance(parsed, list):
            return [_parse_call_config(item) for item in parsed]
        if isinstance(parsed, dict):
            return [parsed]
    return []


def _build_payload(
    working_input: Dict[str, Any],
    cfg: Dict[str, Any],
    state: ReACTOR,
    runtime: AgentRuntime,
    query_fallback: str,
) -> Any:
    payload = dict(working_input)
    payload["slots"] = dict(state.get("slots") or {})
    query = cfg.get("query") or query_fallback
    if query:
        payload["query"] = query

    input_val = cfg.get("input", "$WORKING_INPUT")
    if isinstance(input_val, str):
        if input_val == "$WORKING_INPUT":
            return payload
        return runtime.resolve_tool_input(input_val, state)
    return input_val


def _extract_agent_reply(payload: Any) -> str:
    if isinstance(payload, dict):
        if "data" in payload:
            return extract_plain_text(payload.get("data"))
        if "content" in payload:
            return extract_plain_text(payload.get("content"))
        return ""
    return extract_plain_text(payload)


def _append_history_from_payload(
    working_input: Dict[str, Any],
    active_query: Optional[str],
    assistant_payload: Any,
) -> None:
    if assistant_payload is None:
        return
    user_text = active_query or working_input.get("query", "")

    assistant_text = _extract_agent_reply(assistant_payload)[:2000]

    history = list(working_input.get("history", []))
    if user_text:
        history.append({"role": "user", "content": user_text})
    if assistant_text:
        history.append({"role": "assistant", "content": assistant_text})

    working_input["history"] = history


def _prepare_routing(
    *,
    tool_tag: str,
    tool_input: Any,
    working_input: Dict[str, Any],
    state: ReACTOR,
    runtime: AgentRuntime,
    trace: TraceCollector,
    pending_queries: List[str],
    active_query: Optional[str],
) -> Dict[str, Any]:
    if tool_tag == "ParallelCallAgent":
        call_list = _parse_call_list(tool_input)
        routes = []
        for cfg in call_list:
            agent_name = cfg.get("agent", "")
            if not cfg.get("query"):
                if pending_queries:
                    cfg = dict(cfg)
                    cfg["query"] = pending_queries.pop(0)
                elif active_query:
                    cfg = dict(cfg)
                    cfg["query"] = active_query
                else:
                    cfg = dict(cfg)
                    cfg["query"] = working_input.get("query", "")

            payload = _build_payload(working_input, cfg, state, runtime, cfg.get("query", ""))
            routes.append(
                {
                    "agent": agent_name,
                    "payload": payload,
                    "query": cfg.get("query", ""),
                }
            )
            trace.add_text(
                f"已识别到您的问题{cfg.get('query','')},正在为您调度{agent_name}处理。"
            )

        return {
            "routes": routes,
            "pending_queries": [],
            "active_query": None,
            "working_input": working_input,
            "trace": trace,
            "route": None,
        }

    if tool_tag == "SerialCallAgent":
        if active_query is None:
            if pending_queries:
                active_query = pending_queries.pop(0)
            else:
                active_query = working_input.get("query", "")

        cfg = _parse_call_config(tool_input)
        if cfg.get("query"):
            active_query = cfg.get("query", active_query)
        else:
            cfg = dict(cfg)
            cfg["query"] = active_query

        working_input["query"] = active_query
        payload = _build_payload(working_input, cfg, state, runtime, active_query or "")
        agent_name = cfg.get("agent", "")

        trace.add_text(f"已识别到您的问题{active_query},正在为您调度{agent_name}处理。")

        return {
            "route": {
                "agent": agent_name,
                "payload": payload,
                "query": active_query,
            },
            "pending_queries": pending_queries,
            "active_query": active_query,
            "working_input": working_input,
            "trace": trace,
        }

    return {}


def run_worker(state: ReACTOR, runtime: AgentRuntime):
    execution = runtime.ensure_execution(state)
    steps = execution.steps
    idx = execution.idx
    if idx > len(steps):
        return None

    plan_text, step_var, tool_tag, tool_input = steps[idx]

    if idx == 0:
        print("===================== FULL PLAN ==========================")
        for i, (desc, var, tag, inp) in enumerate(steps, start=1):
            deps = runtime._extract_deps(inp)
            if not deps:
                deps = runtime._infer_implicit_deps(steps, i - 1, tag)
            print(f"Step{i} {desc}")
            print(f"   -> {var} = {tag}[{inp}]")
            print(f"      tag: {tag}")
            print(f"      input: {inp}")
            print(f"      depends_on: {deps if deps else 'none'}")
        print("==========================================================")

    results = dict(execution.results or {})
    working_input = dict(state["working_input"])
    trace = _ensure_trace(state)
    pending_queries = list(state.get("pending_queries", []))
    active_query = state.get("active_query", working_input.get("query", ""))
    route = state.get("route")
    routes = state.get("routes")
    routing_patch = {}
    if tool_tag in ("SerialCallAgent", "ParallelCallAgent"):
        routing_patch = _prepare_routing(
            tool_tag=tool_tag,
            tool_input=tool_input,
            working_input=working_input,
            state=state,
            runtime=runtime,
            trace=trace,
            pending_queries=pending_queries,
            active_query=active_query,
        )
        if routing_patch:
            working_input = routing_patch.get("working_input", working_input)
            trace = routing_patch.get("trace", trace)
            pending_queries = routing_patch.get("pending_queries", pending_queries)
            active_query = routing_patch.get("active_query", active_query)
            if "route" in routing_patch:
                route = routing_patch.get("route")
            if "routes" in routing_patch:
                routes = routing_patch.get("routes")
    routing_keys: Dict[str, Any] = {}
    for key in ("route", "routes"):
        if key in routing_patch:
            routing_keys[key] = routing_patch[key]

    force_replan_reason = ""

    def _mark_need_replan(reason: str) -> None:
        state["eval_status"] = "NEED_REPLAN"
        if reason:
            state["evaluator_hint"] = reason
        execution.idx = len(steps)

    def _patch(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        patch = {
            "working_input": working_input,
            "trace": trace,
            "execution": execution,
            "pending_queries": pending_queries,
            "active_query": active_query,
        }
        patch.update(routing_keys)
        if extra:
            patch.update(extra)
        return patch

    if tool_tag == "SplitQuery":
        results[step_var] = StepResult(
            id=step_var,
            tag=tool_tag,
            desc=plan_text,
            status="ok",
            output=tool_input,
        )
        execution.result_meta[step_var] = {
            "tag": tool_tag,
        }
        execution.results = results
        execution.idx = idx + 1
        state["execution"] = execution
        return _patch()

    if tool_tag == "AskUser":
        cfg = {}
        if isinstance(tool_input, dict):
            cfg = tool_input
        elif isinstance(tool_input, str):
            try:
                parsed = json.loads(tool_input)
                if isinstance(parsed, dict):
                    cfg = parsed
                else:
                    cfg = {"question": tool_input}
            except Exception:
                cfg = {"question": tool_input}
        else:
            cfg = {"question": str(tool_input)}

        question = cfg.get("question") or ""
        results[step_var] = StepResult(
            id=step_var,
            tag=tool_tag,
            desc=plan_text,
            status="ok",
            output=question,
        )
        execution.result_meta[step_var] = {
            "tag": tool_tag,
            "key": cfg.get("key", ""),
            "question": question,
        }
        state["pending_question"] = cfg
        trace.add_text("需要补充信息，已向用户发起提问")

        execution.results = results
        execution.idx = idx + 1
        state["execution"] = execution
        return _patch()

    if tool_tag == "ParallelCallAgent":
        routes = list(routes or [])
        if not routes and route:
            routes = [route]

        if not routes:
            results[step_var] = StepResult(
                id=step_var,
                tag=tool_tag,
                desc=plan_text,
                status="fail",
                error="route not prepared",
                output=None,
            )
            execution.result_meta[step_var] = {
                "tag": tool_tag,
                "items": [],
            }
            execution.results = results
            execution.idx = idx + 1
            state["execution"] = execution
            return _patch()

        def _execute_one(route: Dict[str, Any]) -> dict:
            query = route.get("query", "")
            agent_name = route.get("agent")
            payload = route.get("payload")
            if payload is None:
                payload = dict(working_input)
                if query:
                    payload["query"] = query

            func = runtime.agent_registry.get(agent_name, {}).get("execute") if agent_name else None
            if func is None:
                return {
                    "query": query,
                    "agent": agent_name,
                    "status": "fail",
                    "error": "agent not registered",
                    "output": None,
                }

            raw_res = func(payload)
            raw_status = getattr(raw_res, "status_code", None)
            if hasattr(raw_res, "json"):
                try:
                    data = raw_res.json()
                except Exception:
                    data = raw_res.text
            else:
                data = raw_res
            status = "ok"
            error = ""
            if isinstance(data, dict) and data.get("status") == "fail":
                status = "fail"
                error = data.get("reason") or data.get("error") or data.get("message") or ""
            ok, hint = validate_agent_response(data, raw_status_code=raw_status)
            if not ok:
                status = "fail"
                if not error:
                    error = hint
            return {
                "query": query,
                "agent": agent_name,
                "status": status,
                "error": error,
                "output": data,
            }

        max_workers = min(4, len(routes)) if routes else 1
        outputs_map = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_execute_one, r): i for i, r in enumerate(routes)}
            for fut in as_completed(futures):
                outputs_map[futures[fut]] = fut.result()
        outputs = [outputs_map[i] for i in sorted(outputs_map)]

        overall_error = ""
        for item in outputs:
            if isinstance(item, dict) and item.get("status") == "fail":
                overall_error = item.get("error") or "agent returned error"
                break
        overall_status = "fail" if overall_error else "ok"

        results[step_var] = StepResult(
            id=step_var,
            tag=tool_tag,
            desc=plan_text,
            status=overall_status,
            error=overall_error,
            output=outputs,
        )
        execution.result_meta[step_var] = {
            "tag": tool_tag,
            "items": [
                {
                    "agent": item.get("agent") if isinstance(item, dict) else None,
                    "query": item.get("query") if isinstance(item, dict) else None,
                    "status": item.get("status") if isinstance(item, dict) else None,
                }
                for item in outputs
            ],
        }

        execution.results = results
        execution.idx = idx + 1
        state["execution"] = execution
        state["working_input"] = working_input
        state["trace"] = trace
        state["pending_queries"] = []
        if overall_status == "fail":
            _mark_need_replan(overall_error)
        return _patch()

    if tool_tag == "AppendHistory":
        assistant_payload = runtime.resolve_tool_input(tool_input, state)
        _append_history_from_payload(
            working_input,
            active_query,
            assistant_payload,
        )
        results[step_var] = StepResult(
            id=step_var,
            tag=tool_tag,
            desc=plan_text,
            status="ok",
            output=assistant_payload,
        )
        execution.result_meta[step_var] = {
            "tag": tool_tag,
        }
        active_query = None

    elif tool_tag == "SerialCallAgent":
        route = route or {}
        agent_name = route.get("agent")
        payload = route.get("payload")
        if payload is None:
            payload = dict(working_input)

        if agent_name == "others":
            state["eval_status"] = "DONE"
            results[step_var] = StepResult(
                id=step_var,
                tag=tool_tag,
                desc=plan_text,
                status="skipped",
                error="no agent selected",
                output=None,
            )
            execution.result_meta[step_var] = {
                "tag": tool_tag,
                "agent": agent_name,
                "query": route.get("query"),
                "status": "skipped",
            }
            execution.results = results
            execution.idx = idx + 1
            return _patch()

        func = runtime.agent_registry.get(agent_name, {}).get("execute") if agent_name else None
        if func is None:
            trace.add_text("正在处理您请求时遇到问题。相关agent未注册，已经为您反馈。")
            state["eval_status"] = "NEED_REPLAN"
            results[step_var] = StepResult(
                id=step_var,
                tag=tool_tag,
                desc=plan_text,
                status="fail",
                error="agent not registered",
                output=None,
            )
            execution.result_meta[step_var] = {
                "tag": tool_tag,
                "agent": agent_name,
                "query": route.get("query"),
                "status": "fail",
            }
            execution.results = results
            execution.idx = idx + 1
            _mark_need_replan("agent not registered")
            return _patch()

        raw_res = func(payload)
        raw_status = getattr(raw_res, "status_code", None)
        trace.add_text("正在为您处理相关信息。")
        if hasattr(raw_res, "json"):
            try:
                data = raw_res.json()
            except Exception:
                data = raw_res.text
        else:
            data = raw_res
        status = "ok"
        error = ""
        if isinstance(data, dict) and data.get("status") == "fail":
            status = "fail"
            error = data.get("reason") or data.get("error") or data.get("message") or ""
        ok, hint = validate_agent_response(data, raw_status_code=raw_status)
        if not ok:
            status = "fail"
            if not error:
                error = hint
        results[step_var] = StepResult(
            id=step_var,
            tag=tool_tag,
            desc=plan_text,
            status=status,
            error=error,
            output=data,
        )
        execution.result_meta[step_var] = {
            "tag": tool_tag,
            "agent": agent_name,
            "query": route.get("query"),
            "status": status,
        }
        if status == "fail":
            force_replan_reason = error or "agent returned error"

    elif tool_tag == "FinalOutput":
        final_value = runtime.resolve_tool_input(tool_input, state)

        results[step_var] = StepResult(
            id=step_var,
            tag=tool_tag,
            desc=plan_text,
            status="ok",
            output=final_value,
        )
        execution.result_meta[step_var] = {
            "tag": tool_tag,
        }

        trace.add_text("已为您整合信息")
        state["result"] = final_value

    else:
        trace.add_text(f"未知 tool_tag = {tool_tag}")
        return {"trace": trace}

    execution.results = results
    execution.idx = idx + 1
    if force_replan_reason:
        _mark_need_replan(force_replan_reason)

    state["working_input"] = working_input
    state["trace"] = trace
    state["execution"] = execution
    return _patch()
