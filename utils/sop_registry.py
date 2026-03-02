from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import yaml


_QUOTE_CHARS = '"\'“”‘’`'


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    s = value.strip()
    while s and s[0] in _QUOTE_CHARS:
        s = s[1:]
    while s and s[-1] in _QUOTE_CHARS:
        s = s[:-1]
    return s.strip()


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if isinstance(data, dict):
        return data
    return {}


def _normalize_slot_defs(raw_slots: Any) -> List[Dict[str, Any]]:
    slots = []
    for slot in _ensure_list(raw_slots):
        if not isinstance(slot, dict):
            continue
        name = _normalize_text(slot.get("name", ""))
        enums = [_normalize_text(item) for item in _ensure_list(slot.get("enum")) if _normalize_text(item)]
        slot_norm = dict(slot)
        slot_norm["name"] = name
        if enums:
            slot_norm["enum"] = enums
        slots.append(slot_norm)
    return slots


def _normalize_needed_slots(state: Dict[str, Any]) -> Dict[str, Any]:
    needed = state.get("needed_slots")
    if needed is None:
        return state
    needed_list = [_normalize_text(item) for item in _ensure_list(needed) if _normalize_text(item)]
    state["needed_slots"] = needed_list
    return state


def _normalize_state_defs(raw_states: Any) -> List[Dict[str, Any]]:
    states = []
    for st in _ensure_list(raw_states):
        if not isinstance(st, dict):
            continue
        st_norm = dict(st)
        if "transitions" not in st_norm and "transtions" in st_norm:
            st_norm["transitions"] = st_norm.get("transtions")
        st_norm = _normalize_needed_slots(st_norm)
        states.append(st_norm)
    return states


def _resolve_path(path: str, base_dir: Optional[str]) -> str:
    if os.path.isabs(path):
        return path
    root = base_dir or os.getcwd()
    return os.path.abspath(os.path.join(root, path))


def _default_sop_id(path: str, intent: str) -> str:
    if intent:
        return intent
    return os.path.splitext(os.path.basename(path))[0]


def _collect_keywords(sop: Dict[str, Any]) -> List[str]:
    keywords: List[str] = []
    for field in ("intent", "description"):
        text = _normalize_text(sop.get(field, ""))
        if text:
            keywords.append(text)
            keywords.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text))
    for slot in sop.get("slots", []) or []:
        enums = slot.get("enum") or []
        for item in enums:
            item_norm = _normalize_text(item)
            if item_norm:
                keywords.append(item_norm)
    # Deduplicate while keeping order
    seen = set()
    deduped = []
    for kw in keywords:
        if kw in seen:
            continue
        seen.add(kw)
        deduped.append(kw)
    return deduped


def build_sop_registry(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {}
    if not config:
        return registry

    base_dir = config.get("base_dir") if isinstance(config, dict) else None
    sop_items = config.get("sops") if isinstance(config, dict) else []

    for item in _ensure_list(sop_items):
        if isinstance(item, str):
            entry = {"path": item}
        elif isinstance(item, dict):
            entry = dict(item)
        else:
            continue

        path = entry.get("path")
        if not path:
            continue

        abs_path = _resolve_path(path, base_dir)
        if not os.path.exists(abs_path):
            continue

        raw = _load_yaml(abs_path)
        if not raw:
            continue

        intent = _normalize_text(entry.get("intent") or raw.get("intent", ""))
        sop_id = _normalize_text(entry.get("id") or raw.get("id") or _default_sop_id(abs_path, intent))
        description = _normalize_text(entry.get("description") or raw.get("description", ""))
        triggers = entry.get("triggers") or raw.get("triggers") or raw.get("keywords") or raw.get("match")
        triggers_list = [_normalize_text(item) for item in _ensure_list(triggers) if _normalize_text(item)]

        slots = _normalize_slot_defs(raw.get("slots"))
        states = _normalize_state_defs(raw.get("states"))

        state_map = {st.get("id"): st for st in states if st.get("id")}
        start_state = None
        for st in states:
            if _normalize_text(st.get("type")).lower() == "start":
                start_state = st.get("id")
                break
        if not start_state and states:
            start_state = states[0].get("id")

        sop_def = {
            "id": sop_id,
            "intent": intent,
            "description": description,
            "triggers": triggers_list,
            "slots": slots,
            "states": states,
            "state_map": state_map,
            "start_state": start_state,
            "path": abs_path,
        }

        if not sop_def["triggers"]:
            sop_def["triggers"] = _collect_keywords(sop_def)

        registry[sop_id] = sop_def

    return registry


def match_sop(query: str, registry: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not query or not registry:
        return None
    query_text = str(query)
    best = None
    best_score = 0
    for sop in registry.values():
        triggers = sop.get("triggers") or []
        score = 0
        for trig in triggers:
            trig_norm = _normalize_text(trig)
            if not trig_norm:
                continue
            if trig_norm in query_text:
                score += max(1, len(trig_norm))
        if score > best_score:
            best = sop
            best_score = score
    return best


def build_sop_catalog(registry: Dict[str, Dict[str, Any]]) -> str:
    if not registry:
        return "无"
    lines = []
    for sop_id, sop in registry.items():
        desc = _normalize_text(sop.get("description") or sop.get("intent") or "")
        triggers = sop.get("triggers") or []
        trigger_text = ""
        if triggers:
            sample = ",".join(triggers[:6])
            trigger_text = f" | 触发词: {sample}"
        lines.append(f"- {sop_id}: {desc or '无'}{trigger_text}")
    return "\n".join(lines)
