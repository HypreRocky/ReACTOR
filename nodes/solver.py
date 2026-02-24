from __future__ import annotations

import json
from dataclasses import is_dataclass
from typing import Any, Dict, List

from State import ReACTOR
from prompt.bank_rewoo_prompt_v2 import bank_rewoo_solver_prompt
from runtime import AgentRuntime
from utils.append_history import aggregate_agent_output, extract_plain_text
from utils.call_llm import execute_react_agent

try:
    from src.output_config import OUTPUT_LAYOUT, OUTPUT_SEPARATOR
except Exception:
    OUTPUT_LAYOUT = [{"type": "summary"}]
    OUTPUT_SEPARATOR = "\n\n"


def _ensure_layout(layout: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    if not layout:
        return [{"type": "summary"}]
    return layout


def _build_summary(state: ReACTOR, runtime: AgentRuntime) -> str:
    reasoning_overview = state.get("reasoning_overview", "")
    plan_str = state.get("plan_string", "")
    execution = runtime.ensure_execution(state)
    evidence = json.dumps(runtime.results_to_plain(execution.results), ensure_ascii=False, indent=2)

    solve_prompt = bank_rewoo_solver_prompt.format(
        reasoning_overview=reasoning_overview,
        plan_str=plan_str,
        evidence=evidence,
    )

    return execute_react_agent(prompt=solve_prompt)


def _extract_result_meta(execution, step_id: str) -> Dict[str, Any]:
    meta = execution.result_meta or {}
    val = meta.get(step_id) or {}
    if isinstance(val, dict):
        return val
    return {}


def _collect_agent_outputs(state: ReACTOR, runtime: AgentRuntime) -> List[Dict[str, Any]]:
    execution = runtime.ensure_execution(state)
    outputs: List[Dict[str, Any]] = []

    for step_id, res in (execution.results or {}).items():
        if is_dataclass(res):
            tag = res.tag
            status = res.status
            payload = res.output
        elif isinstance(res, dict):
            tag = res.get("tag")
            status = res.get("status")
            payload = res.get("output")
        else:
            continue

        if tag == "SerialCallAgent":
            meta = _extract_result_meta(execution, step_id)
            outputs.append(
                {
                    "agent": meta.get("agent", ""),
                    "query": meta.get("query", ""),
                    "status": meta.get("status", status),
                    "output": payload,
                    "step_id": step_id,
                }
            )
            continue

        if tag == "ParallelCallAgent":
            meta = _extract_result_meta(execution, step_id)
            meta_items = meta.get("items") if isinstance(meta.get("items"), list) else []
            if isinstance(payload, list):
                for idx, item in enumerate(payload):
                    if isinstance(item, dict):
                        agent = item.get("agent", "")
                        query = item.get("query", "")
                        status = item.get("status")
                        out = item.get("output", item)
                    else:
                        agent = ""
                        query = ""
                        status = None
                        out = item

                    if idx < len(meta_items):
                        meta_item = meta_items[idx] or {}
                        agent = agent or meta_item.get("agent", "")
                        query = query or meta_item.get("query", "")
                        status = status or meta_item.get("status")

                    outputs.append(
                        {
                            "agent": agent,
                            "query": query,
                            "status": status,
                            "output": out,
                            "step_id": step_id,
                        }
                    )
            continue

    return outputs


def _render_payload_text(payload: Any) -> str:
    if isinstance(payload, dict) and "_stream_raw_events" in payload:
        raw_events = payload.get("_stream_raw_events") or []
        text = aggregate_agent_output(raw_events)
        if text:
            return text
        return ""

    text = extract_plain_text(payload)
    if text:
        return text

    if payload is None:
        return ""

    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return str(payload)


def _render_payload_stream(payload: Any) -> List[Any]:
    if isinstance(payload, dict) and "_stream_raw_events" in payload:
        raw_events = payload.get("_stream_raw_events") or []
        return list(raw_events)
    if payload is None:
        return []
    return [payload]


def compose_output(state: ReACTOR, runtime: AgentRuntime, *, streaming: bool = False):
    if state.get("eval_status") not in ("DONE", "FAILED"):
        return [] if streaming else ""

    layout = _ensure_layout(OUTPUT_LAYOUT)
    agent_outputs = _collect_agent_outputs(state, runtime)
    summary_cache: str | None = None

    pieces: List[Any] = []

    def add_separator_if_needed():
        if pieces and OUTPUT_SEPARATOR:
            pieces.append(OUTPUT_SEPARATOR)

    for section in layout:
        if not isinstance(section, dict):
            continue
        sec_type = section.get("type")
        title = section.get("title")
        section_chunks: List[Any] = []

        if sec_type == "agent":
            agent_name = section.get("agent", "")
            selected = (
                [o for o in agent_outputs if o.get("agent") == agent_name]
                if agent_name
                else list(agent_outputs)
            )
            for item in selected:
                payload = item.get("output")
                if streaming:
                    section_chunks.extend(_render_payload_stream(payload))
                else:
                    text = _render_payload_text(payload)
                    if text:
                        section_chunks.append(text)

        elif sec_type == "summary":
            if summary_cache is None:
                summary_cache = _build_summary(state, runtime)
            if summary_cache:
                section_chunks.append(summary_cache)

        elif sec_type == "text":
            value = section.get("value", "")
            if value:
                section_chunks.append(value)

        elif sec_type == "final":
            value = state.get("result", "")
            if value:
                section_chunks.append(value)

        if not section_chunks:
            continue

        if title:
            section_chunks.insert(0, f"{title}\n")

        add_separator_if_needed()
        pieces.extend(section_chunks)

    if streaming:
        return pieces

    return "".join(str(p) for p in pieces if p is not None)


def summary_plan_and_results(state: ReACTOR, runtime: AgentRuntime) -> str:
    return compose_output(state, runtime, streaming=False)
