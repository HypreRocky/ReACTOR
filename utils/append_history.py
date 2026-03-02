def extract_plain_text(obj) -> str:
    if obj is None:
        return ""

    if isinstance(obj, (int, float)):
        return str(obj)

    if isinstance(obj, str):
        return obj

    if isinstance(obj, dict):
        # 常见 graph_trace / llm 输出
        if "content" in obj:
            return extract_plain_text(obj["content"])
        if "text" in obj:
            return extract_plain_text(obj["text"])
        if "data" in obj:
            return extract_plain_text(obj["data"])
        if "message" in obj:
            return extract_plain_text(obj["message"])
        if "answer" in obj:
            return extract_plain_text(obj["answer"])
        if "output" in obj:
            return extract_plain_text(obj["output"])
        if "result" in obj:
            return extract_plain_text(obj["result"])
        return ""

    if isinstance(obj, list):
        return "\n".join(
            extract_plain_text(x)
            for x in obj
            if isinstance(x, (str, int, float, dict))
        )

    return ""


def aggregate_agent_output(raw_events: list) -> str:
    if not raw_events:
        return ""

    parts: list[str] = []
    for ev in raw_events:
        if ev is None:
            continue

        if isinstance(ev, dict):
            if "data" in ev:
                parts.append(extract_plain_text(ev["data"]))
                continue
            if "content" in ev:
                parts.append(extract_plain_text(ev["content"]))
                continue
            if "text" in ev:
                parts.append(extract_plain_text(ev["text"]))
                continue
            if "delta" in ev:
                parts.append(extract_plain_text(ev["delta"]))
                continue
            if "choices" in ev and isinstance(ev["choices"], list):
                for choice in ev["choices"]:
                    if not isinstance(choice, dict):
                        continue
                    if "delta" in choice:
                        parts.append(extract_plain_text(choice["delta"]))
                    elif "message" in choice:
                        parts.append(extract_plain_text(choice["message"]))
                    elif "text" in choice:
                        parts.append(extract_plain_text(choice["text"]))
                continue

        parts.append(extract_plain_text(ev))

    text = "".join([p for p in parts if p])
    return text.strip()