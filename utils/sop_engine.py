from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from State import ExecutionState, ReACTOR
from utils.sop_registry import _normalize_text


def _normalize_slot_name(name: str) -> str:
    return _normalize_text(name)


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_list(expr: str) -> List[str]:
    if not expr:
        return []
    expr = expr.strip()
    if expr.startswith("["):
        try:
            data = json.loads(expr)
            if isinstance(data, list):
                return [_normalize_text(item) for item in data if _normalize_text(item)]
        except Exception:
            pass
    # Fallback: split by comma
    parts = [p.strip() for p in expr.split(",") if p.strip()]
    return [_normalize_text(p) for p in parts if _normalize_text(p)]


def _extract_list_arg(expr: str) -> List[str]:
    if not expr:
        return []
    bracket = re.search(r"\[(.*)\]", expr)
    if bracket:
        return _parse_list("[" + bracket.group(1) + "]")
    paren = re.search(r"\((.*)\)", expr)
    if paren:
        return _parse_list(paren.group(1))
    return []


def _slot_filled(slots: Dict[str, Any], name: str) -> bool:
    key = _normalize_slot_name(name)
    val = slots.get(key)
    if val is None:
        return False
    if isinstance(val, str):
        return val.strip() != "" and val.strip().lower() not in ("unknown", "none")
    return True


def _eval_condition(expr: str, *, query: str, slots: Dict[str, Any]) -> bool:
    if not expr:
        return False
    expr = expr.strip()
    if expr.lower() in ("else", "default", "true"):
        return True
    if expr.startswith("all_filled"):
        items = _extract_list_arg(expr)
        return all(_slot_filled(slots, name) for name in items)
    if expr.startswith("any_filled"):
        items = _extract_list_arg(expr)
        return any(_slot_filled(slots, name) for name in items)
    if expr.startswith("slot_filled"):
        items = _extract_list_arg(expr)
        if items:
            return _slot_filled(slots, items[0])
        return False
    if expr.startswith("nlp_contains"):
        items = _extract_list_arg(expr)
        for kw in items:
            if kw and kw in query:
                return True
        return False
    return False


def _choose_transition(transitions: List[Dict[str, Any]], *, query: str, slots: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fallback = None
    for tr in transitions:
        if not isinstance(tr, dict):
            continue
        cond = str(tr.get("when", ""))
        if cond.strip().lower() in ("else", "default"):
            fallback = tr
            continue
        if _eval_condition(cond, query=query, slots=slots):
            return tr
    if fallback is not None:
        return fallback
    return None


def _extract_slots(slot_defs: List[Dict[str, Any]], texts: List[str], existing: Dict[str, Any]) -> Dict[str, Any]:
    filled: Dict[str, Any] = {}

    for slot in slot_defs:
        name = _normalize_slot_name(slot.get("name", ""))
        if not name or _slot_filled(existing, name):
            continue
        stype = _normalize_text(slot.get("type", ""))
        enums = slot.get("enum") or []
        value = None

        if enums:
            for text in texts:
                for opt in enums:
                    opt_norm = _normalize_text(opt)
                    if opt_norm and opt_norm in text:
                        value = opt_norm
                        break
                if value:
                    break

        if value is None and stype in ("number", "amount", "int", "float", "money"):
            for text in texts:
                match = re.search(r"(\d+(?:\.\d+)?)\s*(万|元|年|月)?", text)
                if match:
                    value = match.group(0)
                    break

        if value is not None:
            filled[name] = value

    return filled


def _build_plan_step(
    steps: List[Tuple[str, str, str, Any]],
    plan_lines: List[str],
    idx: int,
    desc: str,
    tag: str,
    payload: Any,
) -> Tuple[str, int]:
    var = f"#E{idx}"
    if isinstance(payload, (dict, list)):
        payload_text = json.dumps(payload, ensure_ascii=False)
    else:
        payload_text = str(payload)
    steps.append((desc, var, tag, payload_text))
    plan_lines.append(f"Plan:{desc} | {var} = {tag}[{payload_text}]")
    return var, idx + 1


def build_plan_from_sop(sop: Dict[str, Any], state: ReACTOR) -> Dict[str, Any]:
    query = state.get("working_input", {}).get("query", "")
    history = state.get("working_input", {}).get("history") or []
    texts = [query]
    for item in reversed(history[-4:]):
        if isinstance(item, dict) and item.get("role") == "user":
            text = item.get("content")
            if isinstance(text, str) and text:
                texts.append(text)

    raw_slots = state.get("slots") or {}
    slots = {_normalize_slot_name(k): v for k, v in raw_slots.items() if _normalize_slot_name(k)}
    slot_defs = sop.get("slots") or []
    required_slots = {
        _normalize_slot_name(s.get("name", ""))
        for s in slot_defs
        if isinstance(s, dict) and s.get("required") is True
    }
    extracted = _extract_slots(slot_defs, texts, slots)
    slots.update(extracted)

    state_map = sop.get("state_map") or {st.get("id"): st for st in sop.get("states", [])}
    sop_runtime = state.get("sop_runtime") or {}
    cursor = sop_runtime.get("cursor")
    if sop_runtime.get("active_sop_id") == sop.get("id") and cursor in state_map:
        current_id = cursor
    else:
        current_id = sop.get("start_state") or None

    steps: List[Tuple[str, str, str, Any]] = []
    plan_lines: List[str] = []
    idx = 1
    last_var = ""
    reached_prompt = False
    new_cursor = None

    guard = 0
    while current_id and guard < 40:
        guard += 1
        node = state_map.get(current_id)
        if not isinstance(node, dict):
            break
        node_type = _normalize_text(node.get("type", "")).lower()

        if node_type == "start":
            current_id = node.get("next")
            if not current_id:
                transitions = _ensure_list(node.get("transitions"))
                tr = _choose_transition(transitions, query=query, slots=slots)
                current_id = tr.get("to") if tr else None
            continue

        if node_type == "decision":
            transitions = _ensure_list(node.get("transitions"))
            tr = _choose_transition(transitions, query=query, slots=slots)
            current_id = tr.get("to") if tr else None
            continue

        if node_type == "prompt":
            utterances = _ensure_list(node.get("utterances"))
            question = _normalize_text(utterances[0]) if utterances else ""
            needed_slots = [_normalize_text(s) for s in _ensure_list(node.get("needed_slots")) if _normalize_text(s)]
            missing = [s for s in needed_slots if not _slot_filled(slots, s)]
            missing_required = [s for s in missing if s in required_slots] if required_slots else missing
            if missing_required:
                if not question:
                    question = "请补充：" + "、".join(missing)
                payload = {"key": ",".join(missing), "question": question}
                last_var, idx = _build_plan_step(steps, plan_lines, idx, node.get("id", "询问信息"), "AskUser", payload)
                _, idx = _build_plan_step(
                    steps,
                    plan_lines,
                    idx,
                    "将最终结果直接输出给用户",
                    "FinalOutput",
                    last_var,
                )
                reached_prompt = True
                new_cursor = node.get("id")
                break

            # If all slots are already filled, pass through to next transition.
            transitions = _ensure_list(node.get("transitions"))
            tr = _choose_transition(transitions, query=query, slots=slots)
            current_id = tr.get("to") if tr else node.get("next")
            continue

        if node_type == "action":
            mode = _normalize_text(node.get("mode", "serial")).lower() or "serial"
            calls = _ensure_list(node.get("calls"))
            if mode == "parallel" and len(calls) > 1:
                payload = []
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    payload.append(call)
                if payload:
                    last_var, idx = _build_plan_step(
                        steps,
                        plan_lines,
                        idx,
                        node.get("id", "并行执行"),
                        "ParallelCallAgent",
                        payload,
                    )
            else:
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    last_var, idx = _build_plan_step(
                        steps,
                        plan_lines,
                        idx,
                        f"{node.get('id','执行')}-{call.get('agent','agent')}",
                        "SerialCallAgent",
                        call,
                    )
                    if call.get("append_history"):
                        _, idx = _build_plan_step(
                            steps,
                            plan_lines,
                            idx,
                            f"{node.get('id','写入历史')}-AppendHistory",
                            "AppendHistory",
                            last_var,
                        )
            transitions = _ensure_list(node.get("transitions"))
            tr = _choose_transition(transitions, query=query, slots=slots)
            current_id = tr.get("to") if tr else node.get("next")
            continue

        if node_type == "jump":
            target_intent = _normalize_text(node.get("target_intent", ""))
            target_state = _normalize_text(node.get("target_state", ""))
            payload = {
                "jump_intent": target_intent,
                "jump_state": target_state,
            }
            last_var, idx = _build_plan_step(
                steps,
                plan_lines,
                idx,
                node.get("id", "跳转"),
                "FinalOutput",
                payload,
            )
            reached_prompt = True
            break

        if node_type == "end":
            break

        # Unknown node type: stop.
        break

    if steps and not reached_prompt:
        if last_var:
            _, idx = _build_plan_step(
                steps,
                plan_lines,
                idx,
                "将最终结果直接输出给用户",
                "FinalOutput",
                last_var,
            )
        else:
            _, idx = _build_plan_step(
                steps,
                plan_lines,
                idx,
                "将最终结果直接输出给用户",
                "FinalOutput",
                "",
            )
    elif not steps:
        _, idx = _build_plan_step(
            steps,
            plan_lines,
            idx,
            "将最终结果直接输出给用户",
            "FinalOutput",
            "SOP未生成可执行步骤",
        )

    plan_string = "\n".join(plan_lines)

    pending_queries = [query] if query else []

    sop_runtime_out = {}
    if reached_prompt:
        sop_runtime_out = {
            "active_sop_id": sop.get("id", ""),
            "cursor": new_cursor or sop.get("start_state"),
        }

    return {
        "plan_string": plan_string,
        "reasoning_overview": "",
        "execution": ExecutionState(steps=steps, results={}, idx=0),
        "pending_queries": pending_queries,
        "active_query": None,
        "slots": slots,
        "sop_runtime": sop_runtime_out,
    }
