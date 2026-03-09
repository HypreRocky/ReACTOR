from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict

from fastapi import Body, FastAPI
from sse_starlette.sse import EventSourceResponse

from graph import AgentReACTORPlanner as GraphPlanner
from State import ExecutionState, ReplanState, ReACTOR
from utils.ReACTORTracer import TraceCollector
import uvicorn

app = FastAPI(title="ReACTOR Planner Service", version="1.0.0")


class AgentReACTORPlanner:
    """
    Full pipeline runner.
    Input: full working_input dict.
    Output: streaming final answer if working_input.is_streaming == True, else direct output.
    """

    def __init__(self) -> None:
        self.graph = GraphPlanner()
        self.evaluator_enabled = True

    def set_evaluator(self, enabled: bool = True):
        self.evaluator_enabled = bool(enabled)
        if hasattr(self.graph, "set_evaluator"):
            self.graph.set_evaluator(enabled)
        return self

    def _ensure_working_input(self, working_input: Dict[str, Any]) -> Dict[str, Any]:
        raw = dict(working_input or {})
        raw.setdefault("request_id", "")
        raw.setdefault("query", "")
        raw.setdefault("history", [])
        raw.setdefault("knowledge_result", "")
        raw.setdefault("customer_no", "")
        raw.setdefault("enable_aigc", True)
        raw.setdefault("is_streaming", False)
        raw.setdefault("hotfix_query", "")
        raw.setdefault("recursion_limit", 10)
        raw.setdefault("sop_runtime", {})
        raw.setdefault("slots", {})
        return raw

    def _init_state(self, raw: Dict[str, Any]) -> ReACTOR:
        sop_runtime = raw.get("sop_runtime") if isinstance(raw.get("sop_runtime"), dict) else {}
        slots = raw.get("slots") if isinstance(raw.get("slots"), dict) else {}
        return {
            "raw_input": raw,
            "working_input": dict(raw),
            "task": raw.get("query", ""),
            "plan_string": "",
            "reasoning_overview": "",
            "execution": ExecutionState(
                steps=[],
                results={},
                idx=0,
            ),
            "sop_runtime": sop_runtime,
            "slots": slots,
            "pending_question": None,
            "trace": TraceCollector(event_type="planning"),
            "pending_queries": [],
            "active_query": None,
            "route": None,
            "routes": None,
            "eval_status": "",
            "evaluator_hint": "",
            "replan": ReplanState(
                count=0,
                max_iteration_limit=int(raw.get("recursion_limit", 10)),
                last_failure="",
                last_plan="",
                last_results={},
            ),
            "result": "",
        }

    def _merge_state(self, state: ReACTOR, patch: Any) -> ReACTOR:
        if isinstance(patch, dict) and patch:
            state.update(patch)
        return state

    def _build_state_payload(self, state: ReACTOR) -> Dict[str, Any]:
        return {
            "sop_runtime": state.get("sop_runtime") or {},
            "slots": state.get("slots") or {},
            "pending_question": state.get("pending_question"),
        }

    def _encode_sse_data(self, data: Any) -> str:
        if isinstance(data, str):
            return data
        try:
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return str(data)

    async def _execute(self, state: ReACTOR) -> ReACTOR:
        recursion_limit = int(state.get("working_input", {}).get("recursion_limit", 10))
        compiled = self.graph.graph
        config = {"recursion_limit": recursion_limit * 50}

        if hasattr(compiled, "ainvoke"):
            final_state = await compiled.ainvoke(state, config=config)
        else:
            final_state = await asyncio.to_thread(compiled.invoke, state, config)

        if isinstance(final_state, dict):
            state = self._merge_state(state, final_state)
        return state

    async def _stream_handle(self, state: ReACTOR) -> AsyncGenerator[Dict[str, str], None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        trace = state.get("trace")
        if isinstance(trace, TraceCollector):
            def _emit(payload: Dict[str, Any]) -> None:
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, payload)
                except Exception:
                    pass

            trace.set_sse(_emit)

        execute_task = asyncio.create_task(self._execute(state))

        while True:
            if execute_task.done() and queue.empty():
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            if not isinstance(payload, dict):
                continue
            event_name = payload.get("event", "stream")
            event_data = self._encode_sse_data(payload.get("data", ""))
            yield {"event": event_name, "data": event_data}

        try:
            state = await execute_task
        except Exception as exc:
            yield {"event": "error", "data": self._encode_sse_data({"message": str(exc)})}
            yield {"event": "done", "data": self._encode_sse_data("")}
            return

        try:
            final_items = self.graph.compose_output(state, streaming=True)
        except Exception as exc:
            yield {"event": "error", "data": self._encode_sse_data({"message": str(exc)})}
            yield {"event": "done", "data": self._encode_sse_data("")}
            return
        for item in final_items:
            yield {"event": "final", "data": self._encode_sse_data(item)}

        yield {"event": "state", "data": self._encode_sse_data(self._build_state_payload(state))}
        yield {"event": "done", "data": self._encode_sse_data("")}

    async def handle(self, working_input: Dict[str, Any]):
        raw = self._ensure_working_input(working_input)
        state = self._init_state(raw)

        if raw.get("is_streaming", False):
            return EventSourceResponse(self._stream_handle(state))

        state = await self._execute(state)
        result = self.graph.compose_output(state, streaming=False)
        return {
            "result": result,
            "sop_runtime": state.get("sop_runtime") or {},
            "slots": state.get("slots") or {},
            "pending_question": state.get("pending_question"),
        }


planner = AgentReACTORPlanner()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/plan")
async def plan(working_input: Dict[str, Any] = Body(...)):
    return await planner.handle(working_input)


@app.post("/plan/stream")
async def plan_stream(working_input: Dict[str, Any] = Body(...)):
    payload = dict(working_input or {})
    payload["is_streaming"] = True
    return await planner.handle(payload)


if __name__ == '__main__':
    uvicorn.run('Service:app',host='127.0.0.1',port=8080)
