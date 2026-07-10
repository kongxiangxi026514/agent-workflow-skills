"""Validate UTF-8 JSON/JSONC without rewriting its source bytes."""
import json, sys
from pathlib import Path
def normalize_jsonc(text):
    """Remove comments and trailing commas with a string-aware scanner."""
    result, index = [], 0
    while index < len(text):
        char = text[index]
        if char == '"':
            result.append(char)
            index += 1
            while index < len(text):
                char = text[index]
                result.append(char)
                if char == "\\" and index + 1 < len(text):
                    index += 1
                    result.append(text[index])
                elif char == '"':
                    break
                index += 1
        elif text.startswith("//", index):
            index = text.find("\n", index + 2)
            if index < 0:
                break
            result.append("\n")
        elif text.startswith("/*", index):
            index = text.find("*/", index + 2)
            if index < 0:
                raise ValueError("unterminated block comment")
            index += 1
        elif char == ",":
            probe = index + 1
            while probe < len(text):
                if text[probe].isspace():
                    probe += 1
                elif text.startswith("//", probe):
                    probe = text.find("\n", probe + 2)
                    if probe < 0:
                        break
                elif text.startswith("/*", probe):
                    probe = text.find("*/", probe + 2)
                    if probe < 0:
                        raise ValueError("unterminated block comment")
                    probe += 2
                else:
                    break
            if probe >= len(text) or text[probe] not in "]}":
                result.append(char)
        else:
            result.append(char)
        index += 1
    return "".join(result)
def main():
    try:
        if len(sys.argv) != 2: raise ValueError("usage: validate_jsonc.py PATH")
        json.loads(normalize_jsonc(Path(sys.argv[1]).read_bytes().decode("utf-8-sig")))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Invalid UTF-8 JSON/JSONC: {error}", file=sys.stderr)
        return 1
    return 0
if __name__ == "__main__": raise SystemExit(main())
