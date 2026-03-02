import json
from typing import Any, Callable

import requests

from utils.append_history import extract_plain_text


def is_graph_trace_event(ev: Any) -> bool:
    return isinstance(ev, dict) and ev.get("type") == "graph_trace"


def consume_agent_http_stream(
    resp: requests.Request,
    trace,
    *,
    on_raw: Callable[[dict], None] | None = None,
) -> str:
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue

            if line.startswith('data:'):
                line = line[len('data:'):].strip()

            try:
                raw = json.loads(line)
            except Exception:
                continue

            if on_raw:
                if not is_graph_trace_event(raw):
                    on_raw(raw)
                    continue

            if is_graph_trace_event(raw):
                content = raw.get('data', {}).get('content')
                text = extract_plain_text(content)
                if text:
                    trace.add_text(text)
    except Exception as e:
        trace.add_text(f'[STREAM ERROR] {repr(e)}')
