from typing import List, Dict, Optional,Callable


class TraceCollector:
    """
    Generic trace collector.

    - No business semantics
    - No node classification
    - Output format strictly follows frontend contract
    """

    def __init__(self, event_type: str = "planning"):
        # 前端规定的 type，比如 "planning"
        self._event_type = event_type
        self._steps: List[Dict] = []
        self._counter: int = 0
        self._sse:Optional[Callable[[Dict],None]] = None

    def set_sse(self,fn:Callable[[Dict],None]):
        self._sse = fn

    # -------- 核心写入 API --------
    def add(
        self,
        title: str,
        subtitle: Optional[str] = None
    ) -> Dict:
        """
        Add one trace step.
        """
        self._counter += 1
        item = {
            "step": self._counter,
            "title": title,
            "subtitle": subtitle or ""
        }
        self._steps.append(item)
        if self._sse:
            self._sse({
                'type' : slef._event_type,
                'content' : [item]
            })
        return item

    # -------- 语法糖（你随便用） --------
    def add_text(self, text: str) -> Dict:
        return self.add(title=text)

    def add_with_detail(self, title: str, detail: str) -> Dict:
        return self.add(title=title, subtitle=detail)

    # -------- 输出给前端 --------
    def emit_event(self) -> Dict:
        """
        Emit full trace event.
        """
        return {
            "type": self._event_type,   # ← 固定 planning
            "content": list(self._steps)
        }

    def emit_last_event(self) -> Dict:
        """
        Emit only the latest step (best for streaming).
        """
        if not self._steps:
            return {
                "type": self._event_type,
                "content": []
            }

        return {
            "type": self._event_type,
            "content": [self._steps[-1]]
        }

    # -------- 其他 --------
    def dump(self) -> List[Dict]:
        """
        Raw trace list (internal use).
        """
        return list(self._steps)