from __future__ import annotations

import json
from typing import Dict, List, Any

from State import ReACTOR
from runtime import AgentRuntime
from utils.ReACTORTracer import TraceCollector
from utils.router_api import router_api


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
    query = cfg.get("query") or query_fallback
    if query:
        payload["query"] = query

    input_val = cfg.get("input", "$WORKING_INPUT")
    if isinstance(input_val, str):
        if input_val == "$WORKING_INPUT":
            return payload
        return runtime.resolve_tool_input(input_val, state)
    return input_val


def _analyze_intent(query: str, working_input: Dict[str, Any]) -> str:
    payload = {
        "query": query,
        "history": working_input.get("history", []),
        "prev_intent": working_input.get("prev_intent", ""),
    }
    try:
        return router_api(payload)
    except Exception:
        return ""


def run_router(state: ReACTOR, runtime: AgentRuntime) -> Dict:
    working_input = dict(state["working_input"])
    execution = runtime.ensure_execution(state)

    steps = execution.steps
    idx = execution.idx
    next_tag = steps[idx][2] if idx < len(steps) else None

    trace = _ensure_trace(state)

    active_query = state.get("active_query")
    pending_queries: List[str] = list(state.get("pending_queries", []))

    if next_tag == "ParallelCallAgent":
        call_list = _parse_call_list(steps[idx][3] if idx < len(steps) else None)
        routes = []
        intents: List[str] = []
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
            intent = _analyze_intent(cfg.get("query", ""), working_input)
            routes.append(
                {
                    "agent": agent_name,
                    "payload": payload,
                    "query": cfg.get("query", ""),
                    "intent": intent,
                }
            )
            intents.append(intent)
            trace.add_text(
                f"已识别到您的问题{cfg.get('query','')},正在为您调度{agent_name}处理。"
            )

        pending_queries = []
        return {
            "working_input": working_input,
            "active_query": None,
            "router_result": intents,
            "routes": routes,
            "trace": trace,
            "execution": execution,
            "pending_queries": pending_queries,
        }

    if next_tag == "SerialCallAgent":
        if active_query is None:
            if pending_queries:
                active_query = pending_queries.pop(0)
            else:
                active_query = working_input.get("query", "")

        cfg = _parse_call_config(steps[idx][3] if idx < len(steps) else None)
        if cfg.get("query"):
            active_query = cfg.get("query", active_query)
        else:
            cfg = dict(cfg)
            cfg["query"] = active_query

        working_input["query"] = active_query
        payload = _build_payload(working_input, cfg, state, runtime, active_query)
        agent_name = cfg.get("agent", "")
        intent = _analyze_intent(active_query, working_input)
        working_input["intent"] = intent

        trace.add_text(f"已识别到您的问题{active_query},正在为您调度{agent_name}处理。")

        return {
            "working_input": working_input,
            "active_query": active_query,
            "router_result": intent,
            "route": {
                "agent": agent_name,
                "payload": payload,
                "query": active_query,
                "intent": intent,
            },
            "trace": trace,
            "execution": execution,
            "pending_queries": pending_queries,
        }

    return {
        "working_input": working_input,
        "active_query": active_query,
        "router_result": "",
        "trace": trace,
        "execution": execution,
        "pending_queries": pending_queries,
    }
