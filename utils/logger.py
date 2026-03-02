from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict


class ReACTORLogger:
    def __init__(self, log_dir: str | None = None, prefix: str = "reactor"):
        root = os.path.dirname(os.path.dirname(__file__))
        if log_dir is None:
            log_dir = os.path.join(root, "log")
        self._log_dir = log_dir
        self._prefix = prefix
        self._lock = threading.Lock()
        os.makedirs(self._log_dir, exist_ok=True)

    @property
    def path(self) -> str:
        return self._current_path()

    def _current_path(self) -> str:
        day = datetime.now().strftime("%Y%m%d")
        filename = f"{self._prefix}_{day}.log"
        return os.path.join(self._log_dir, filename)

    def log(self, event: Dict[str, Any]) -> None:
        if "ts" not in event:
            event["ts"] = datetime.utcnow().isoformat() + "Z"
        line = json.dumps(event, ensure_ascii=False, default=str)
        path = self._current_path()
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
