"""JSON extraction helpers for LLM responses."""

import re


def extract_first_json_block(text: str) -> str:
    text = text.strip()

    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    code_blocks = re.findall(code_block_pattern, text)
    if code_blocks:
        text = code_blocks[0].strip()
    else:
        brace_idx = text.find("{")
        if brace_idx > 0:
            text = text[brace_idx:]

    brace_count = 0
    first_json: list[str] = []
    in_string = False
    escape_next = False

    for char in text:
        if escape_next:
            first_json.append(char)
            escape_next = False
            continue

        if char == "\\" and in_string:
            escape_next = True
            first_json.append(char)
            continue

        if char == '"' and not escape_next:
            in_string = not in_string

        first_json.append(char)

        if not in_string:
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    return "".join(first_json).strip()

    return "".join(first_json).strip()
