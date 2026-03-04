from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List

from State import ExecutionState, ReplanState
from conf.config import agent_config
from conf.sop_config import sop_config
from utils.agent_register import build_agent_registry
from utils.sop_registry import build_sop_registry, build_sop_catalog, match_sop


class AgentRuntime:
    def __init__(self, config: Dict[str, Any] | None = None):
        cfg = config if config is not None else agent_config
        self.agent_registry = build_agent_registry(cfg)
        self.agent_catalog = self._build_agent_catalog()
        self.sop_registry = build_sop_registry(sop_config)
        self.sop_catalog = build_sop_catalog(self.sop_registry)
        # Optional external evaluator hook (e.g., reward model); may be set by caller.
        self.evaluator_hook = None

    def _build_agent_catalog(self) -> str:
        lines: List[str] = []
        for agent_name, info in self.agent_registry.items():
            desc = (info.get("description") or "").strip()
            desc_text = desc if desc else "无"
            lines.append(f"- {agent_name}: {desc_text}")
        return "\n".join(lines)

    def match_sop(self, query: str):
        return match_sop(query, self.sop_registry)

    def _extract_deps(self, tool_input: str) -> List[str]:
        if not isinstance(tool_input, str):
            return []
        return re.findall(r"#E\d+", tool_input)

    def _infer_implicit_deps(self, steps: List[tuple], idx: int, tool_tag: str) -> List[str]:
        if idx <= 0:
            return []
        return []

    def _load_by_path(self, obj: Any, path: str):
        cur = obj
        for key in path.split("."):
            if cur is None:
                return None
            if isinstance(cur, dict):
                cur = cur.get(key)
            else:
                cur = getattr(cur, key, None)
        return cur

    def ensure_execution(self, state: Dict[str, Any]) -> ExecutionState:
        execution = state.get("execution")
        if isinstance(execution, ExecutionState):
            return execution
        if isinstance(execution, dict):
            return ExecutionState(
                idx=execution.get("idx", 0),
                steps=execution.get("steps", []),
                results=execution.get("results", {}),
                result_meta=execution.get("result_meta", {}),
            )
        return ExecutionState()

    def ensure_replan(self, state: Dict[str, Any]) -> ReplanState:
        replan = state.get("replan")
        if isinstance(replan, ReplanState):
            return replan
        if isinstance(replan, dict):
            return ReplanState(
                count=replan.get("count", 0),
                max_iteration_limit=replan.get("max_iteration_limit", 0),
                last_failure=replan.get("last_failure", ""),
                last_plan=replan.get("last_plan", ""),
                last_results=replan.get("last_results", {}),
            )
        return ReplanState()

    def results_to_plain(self, results: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in (results or {}).items():
            if is_dataclass(v):
                out[k] = asdict(v)
            else:
                out[k] = v
        return out

    def _load_step_output(self, value: Any):
        if is_dataclass(value) and hasattr(value, "output"):
            return value.output
        if isinstance(value, dict) and "output" in value:
            return value.get("output")
        return value

    def resolve_tool_input(self, tool_input: str, state: Dict[str, Any]):
        if tool_input == "$WORKING_INPUT":
            return state["working_input"]

        if tool_input.startswith("#"):
            results = self.ensure_execution(state).results
            if "." in tool_input:
                ref, path = tool_input.split(".", 1)
                base = results.get(ref)
                base = self._load_step_output(base)
                return self._load_by_path(base, path)

            return self._load_step_output(results.get(tool_input))

        return tool_input

    def build_replan_hint(self, state: Dict[str, Any]) -> str:
        replan = self.ensure_replan(state)
        count = replan.count
        if not count:
            return "无"

        last_plan = replan.last_plan
        last_failure = replan.last_failure
        last_results = replan.last_results

        results_text = ""
        try:
            results_text = json.dumps(last_results, ensure_ascii=False)
        except Exception:
            results_text = str(last_results)

        if len(results_text) > 800:
            results_text = results_text[:800] + "..."

        return (
            f"这是第{count}次重新规划。\n"
            f"上次计划: {last_plan}\n"
            f"上次失败原因: {last_failure}\n"
            f"上次结果摘要: {results_text}\n"
            "要求: 必须避免重复上次计划，必要时调整拆解顺序或Action组合。"
        )
