from __future__ import annotations

import time
from typing import Any, Dict

from langgraph.graph import StateGraph, START, END

from State import ReACTOR
from node.planner import run_planner
from node.router import run_router
from node.worker import run_worker
from node.evaluator import run_evaluator
from node.replanner import run_replanner
from node.solver import summary_plan_and_results, compose_output
from runtime import AgentRuntime
from utils.ReACTORTracer import TraceCollector
from utils.logger import ReACTORLogger


class AgentReACTORPlanner:
    def __init__(self):
        self.runtime = AgentRuntime()
        self.logger = ReACTORLogger()
        self.graph = self.build_graph()

    def run_planner(self, state: ReACTOR):
        return self._run_with_log("planner", run_planner, state)

    def run_router(self, state: ReACTOR):
        return self._run_with_log("router", run_router, state)

    def run_worker(self, state: ReACTOR):
        execution = self.runtime.ensure_execution(state)
        steps = execution.steps
        idx = execution.idx
        tag = steps[idx][2] if idx < len(steps) else ""
        node_name = "callagent" if tag in ("SerialCallAgent", "ParallelCallAgent") else "worker"
        return self._run_with_log(node_name, run_worker, state)

    def run_evaluator(self, state: ReACTOR):
        return self._run_with_log("evaluator", run_evaluator, state)

    def run_replanner(self, state: ReACTOR):
        return self._run_with_log("replanner", run_replanner, state)

    def summary_plan_and_results(self, state: ReACTOR):
        return summary_plan_and_results(state, self.runtime)

    def compose_output(self, state: ReACTOR, *, streaming: bool = False):
        return compose_output(state, self.runtime, streaming=streaming)

    def _summarize_execution(self, state: ReACTOR) -> Dict[str, Any]:
        execution = self.runtime.ensure_execution(state)
        steps = execution.steps
        idx = execution.idx
        step = None
        if idx < len(steps):
            desc, var, tag, inp = steps[idx]
            step = {
                "idx": idx,
                "desc": desc,
                "var": var,
                "tag": tag,
                "input": inp,
            }
        return {
            "idx": idx,
            "total_steps": len(steps),
            "step": step,
            "result_keys": list((execution.results or {}).keys()),
        }

    def _summarize_state(self, state: ReACTOR) -> Dict[str, Any]:
        return {
            "task": state.get("task"),
            "active_query": state.get("active_query"),
            "pending_queries": state.get("pending_queries"),
            "working_input": state.get("working_input"),
            "route": state.get("route"),
            "routes": state.get("routes"),
            "execution": self._summarize_execution(state),
        }

    def _extract_trace(self, trace_obj: Any) -> Any:
        if isinstance(trace_obj, TraceCollector):
            return trace_obj.dump()
        return trace_obj

    def _extract_trace_from(self, state: ReACTOR, patch: Any) -> Any:
        trace_obj = None
        if isinstance(patch, dict):
            trace_obj = patch.get("trace")
        if trace_obj is None:
            trace_obj = state.get("trace")
        return self._extract_trace(trace_obj)

    def _log_event(self, event: Dict[str, Any]) -> None:
        try:
            self.logger.log(event)
        except Exception:
            pass

    def _run_with_log(self, name: str, fn, state: ReACTOR):
        start = time.perf_counter()
        input_state = self._summarize_state(state)
        patch = fn(state, self.runtime)
        duration_ms = round((time.perf_counter() - start) * 1000, 3)

        event = {
            "node": name,
            "duration_ms": duration_ms,
            "input": input_state,
            "output": patch,
            "trace": self._extract_trace_from(state, patch),
        }
        if name == "planner" and isinstance(patch, dict):
            event["plan_string"] = patch.get("plan_string", "")
            event["reasoning_overview"] = patch.get("reasoning_overview", "")
        self._log_event(event)
        return patch

    def _route(self, state: ReACTOR):
        execution = self.runtime.ensure_execution(state)
        steps = execution.steps
        idx = execution.idx

        if idx >= len(steps):
            return "evaluator"

        next_tag = steps[idx][2]
        if next_tag in ("SerialCallAgent", "ParallelCallAgent"):
            return "router"
        return "worker"

    def _how_end(self, state: ReACTOR):
        if state.get("eval_status") in ("DONE", "FAILED"):
            return "END"
        return "replanner"

    def build_graph(self):
        graph = StateGraph(ReACTOR)
        graph.add_node("plan", self.run_planner)
        graph.add_node("router", self.run_router)
        graph.add_node("worker", self.run_worker)
        graph.add_node("evaluator", self.run_evaluator)
        graph.add_node("replanner", self.run_replanner)

        graph.add_edge(START, "plan")
        graph.add_edge("plan", "router")
        graph.add_edge("router", "worker")

        graph.add_conditional_edges(
            "worker",
            self._route,
            {"worker": "worker", "router": "router", "evaluator": "evaluator"},
        )

        graph.add_conditional_edges(
            "evaluator",
            self._how_end,
            {"replanner": "replanner", "END": END},
        )
        graph.add_edge("replanner", "plan")

        return graph.compile()
