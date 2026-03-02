'''
Agent call add_text('xxxx') to write text into Collect.
In Service.py, agent use 
    for sse_chunk in trace.stream_from_upstream(upstream):
        yield sse_chunk
to send SSE text.
'''
TraceBridge_type = 'CoTTrace'

from typing import List, Dict, Optional, Callable


class TraceCollector:
    """
    Frontend trace collector.
    Output format strictly follows frontend contract.
    """

    def __init__(self, event_type: str = "planning"):
        self._event_type = event_type
        self._steps: List[Dict] = []
        self._counter: int = 0
        self._sse: Optional[Callable[[Dict], None]] = None

    def set_sse(self, fn: Callable[[Dict], None]):
        self._sse = fn

    # -------- core --------
    def add(self, title: str, subtitle: Optional[str] = None) -> Dict:
        self._counter += 1
        item = {
            "step": self._counter,
            "title": title,
            "subtitle": subtitle or ""
        }
        self._steps.append(item)

        if self._sse:
            self._sse(self.emit_last_event())

        return item

    def add_text(self, text: str) -> Dict:
        return self.add(title=text)

    def add_with_detail(self, title: str, detail: str) -> Dict:
        return self.add(title=title, subtitle=detail)

    # -------- frontend --------
    def emit_last_event(self) -> Dict:
        data = {
            "type": self._event_type,
            "content": [self._steps[-1]] if self._steps else []
        }
        return {
            'event' : 'stream',
            'data' : data
        }

    def emit_event(self) -> Dict:
        data ={
            "type": self._event_type,
            "content": list(self._steps)
        }
        return {
            'event' : 'stream',
            'data' : data
        }

    def dump(self) -> List[Dict]:
        return list(self._steps)

# Agent user
class AgentTraceEmitter:
    """
    Agent-side trace emitter.
    Uses utils internal protocol.
    """
    _TraceBridge_type = TraceBridge_type
    def __init__(self, emit_fn: Callable[[Dict], None]):
        self._emit = emit_fn

    def add_text(self, text: str):
        self._emit({
            "type": self._TraceBridge_type,
            "data": {
                "title": text,
                "subtitle": ""
            }
        })

    def add_with_detail(self, title: str, detail: str):
        self._emit({
            "type": self._TraceBridge_type,
            "data": {
                "title": title,
                "subtitle": detail
            }
        })


class TraceBridge:
    """
    Bridge utils protocol -> frontend trace collector
    """
    _TraceBridge_Type = TraceBridge_type
    def __init__(self, trace: TraceCollector):
        self.trace = trace

    def on_event(self, event: Dict):
        etype = event.get("type")

        if etype == self._TraceBridge_Type:
            data = event.get("data", {})

            if isinstance(data, str):
                self.trace.add_text(data)
            elif isinstance(data, dict):
                self.trace.add(
                    title=data.get("title", ""),
                    subtitle=data.get("subtitle", "")
                )