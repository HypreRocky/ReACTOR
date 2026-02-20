from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict

from State import StepResult, ReACTOR
from runtime import AgentRuntime
from utils.ReACTORTracer import TraceCollector
from utils.append_history import aggregate_agent_output, extract_plain_text
from utils.sse_solver import consume_agent_http_stream, is_graph_trace_event


def _ensure_trace(state: ReACTOR) -> TraceCollector:
    trace = state.get("trace")
    if isinstance(trace, TraceCollector):
        return trace
    return TraceCollector(event_type="planning")


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
    active_query = state.get("active_query", working_input.get("query", ""))

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
        return {
            "working_input": working_input,
            "trace": trace,
            "execution": execution,
            "pending_queries": state.get("pending_queries", []),
            "active_query": active_query,
        }

    if tool_tag == "ParallelCallAgent":
        is_streaming = working_input.get("is_streaming", False)
        routes = list(state.get("routes") or [])
        if not routes and state.get("route"):
            routes = [state["route"]]

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
            return {
                "working_input": working_input,
                "trace": trace,
                "execution": execution,
                "pending_queries": state.get("pending_queries", []),
                "active_query": None,
            }

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

            if is_streaming:
                raw_chunks = []
                consume_agent_http_stream(
                    func(payload),
                    trace,
                    on_raw=raw_chunks.append,
                )
                output = {"_stream_raw_events": raw_chunks}
                return {
                    "query": query,
                    "agent": agent_name,
                    "status": "ok",
                    "error": "",
                    "output": output,
                }

            raw_res = func(payload)
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
            return {
                "query": query,
                "agent": agent_name,
                "status": status,
                "error": error,
                "output": data,
            }

        if is_streaming:
            trace.add_text("并行调用在流式模式下降级为顺序执行")
            outputs = [_execute_one(r) for r in routes]
        else:
            max_workers = min(4, len(routes)) if routes else 1
            outputs_map = {}
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(_execute_one, r): i for i, r in enumerate(routes)}
                for fut in as_completed(futures):
                    outputs_map[futures[fut]] = fut.result()
            outputs = [outputs_map[i] for i in sorted(outputs_map)]

        results[step_var] = StepResult(
            id=step_var,
            tag=tool_tag,
            desc=plan_text,
            status="ok",
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
        return {
            "working_input": working_input,
            "trace": trace,
            "execution": execution,
            "pending_queries": [],
            "active_query": None,
        }

    if tool_tag == "AppendHistory":
        assistant_payload = runtime.resolve_tool_input(tool_input, state)
        user_text = active_query or working_input.get("query", "")

        is_streaming = working_input.get("is_streaming", False)
        if (
            is_streaming
            and isinstance(assistant_payload, dict)
            and "_stream_raw_events" in assistant_payload
        ):
            raw_events = assistant_payload["_stream_raw_events"]
            non_trace_events = [
                ev for ev in raw_events
                if not is_graph_trace_event(ev)
            ]
            assistant_text = aggregate_agent_output(non_trace_events)
            assistant_text = extract_plain_text(assistant_text)[:2000]
        else:
            assistant_text = extract_plain_text(assistant_payload)[:2000]

        history = list(working_input.get("history", []))
        if user_text:
            history.append({"role": "user", "content": user_text})
        if assistant_text:
            history.append({"role": "assistant", "content": assistant_text})

        working_input["history"] = history
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
        route = state.get("route") or {}
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
                error="no agent for intent",
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
            return {
                "working_input": working_input,
                "trace": trace,
                "execution": execution,
            }

        func = runtime.agent_registry.get(agent_name, {}).get("execute") if agent_name else None
        if func is None:
            trace.add_text("正在处理您请求时遇到问题。相关agent未注册，已经为您反馈。")
            state["eval_status"] = "FAILED"
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
            return {"trace": trace, "execution": execution}

        is_streaming = working_input.get("is_streaming", False)
        if is_streaming:
            trace.add_text("已进入流式")
            raw_chunks = []
            stream_cb = state.get("stream_cb")

            def _on_raw(raw):
                raw_chunks.append(raw)
                if callable(stream_cb):
                    stream_cb(raw)

            consume_agent_http_stream(
                func(payload),
                trace,
                on_raw=_on_raw,
            )

            trace.add_text("正在为您处理相关信息。")
            output = {"_stream_raw_events": raw_chunks}
            results[step_var] = StepResult(
                id=step_var,
                tag=tool_tag,
                desc=plan_text,
                status="ok",
                output=output,
            )
            execution.result_meta[step_var] = {
                "tag": tool_tag,
                "agent": agent_name,
                "query": route.get("query"),
                "status": "ok",
            }
        else:
            raw_res = func(payload)
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

    state["working_input"] = working_input
    state["trace"] = trace
    state["execution"] = execution
    return {
        "working_input": working_input,
        "trace": trace,
        "execution": execution,
        "pending_queries": state.get("pending_queries", []),
        "active_query": active_query,
    }
