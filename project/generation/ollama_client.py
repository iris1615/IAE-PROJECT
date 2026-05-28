import json
import re
import subprocess
from typing import Any, Optional


def ollama_generate_json(prompt: str, model: str = "llama3:8b", temperature: float = 0.4, timeout: int = 60) -> Optional[Any]:
    """Call Ollama CLI to generate output and try to extract JSON from stdout.

    Returns parsed JSON (object or array) or None on failure.
    """
    def _extract_json(text: str) -> Optional[Any]:
        start_delim = "<<<JSON_START>>>"
        end_delim = "<<<JSON_END>>>"
        if start_delim in text and end_delim in text:
            start_idx = text.find(start_delim) + len(start_delim)
            end_idx = text.find(end_delim, start_idx)
            if end_idx == -1:
                return None
            candidate = text[start_idx:end_idx].strip()
        else:
            start_idx = min([i for i in (text.find("["), text.find("{")) if i != -1], default=-1)
            if start_idx == -1:
                return None
            end_idx = text.rfind("]") if text[start_idx] == "[" else text.rfind("}")
            if end_idx == -1:
                return None
            candidate = text[start_idx:end_idx + 1]

        def _normalize_json_text(s: str) -> str:
            out_chars = []
            in_string = False
            escaped = False
            length = len(s)
            for index, ch in enumerate(s):
                if in_string:
                    if escaped:
                        out_chars.append(ch)
                        escaped = False
                        continue
                    if ch == '\\':
                        out_chars.append(ch)
                        escaped = True
                        continue
                    if ch == '"':
                        lookahead = index + 1
                        while lookahead < length and s[lookahead] in (' ', '\t', '\r', '\n'):
                            lookahead += 1
                        if lookahead >= length or s[lookahead] in (',', '}', ']'):
                            out_chars.append(ch)
                            in_string = False
                        else:
                            out_chars.append('\\"')
                        continue
                    if ch == '\n':
                        out_chars.append('\\n')
                        continue
                    if ch == '\r':
                        out_chars.append('\\r')
                        continue
                    if ch == '\t':
                        out_chars.append('\\t')
                        continue
                    if ch == '\u2028':
                        out_chars.append('\\u2028')
                        continue
                    if ch == '\u2029':
                        out_chars.append('\\u2029')
                        continue
                    out_chars.append(ch)
                    continue

                if ch == '"':
                    in_string = True
                    out_chars.append(ch)
                    continue
                out_chars.append(ch)
            return ''.join(out_chars)

        def _parse_fragment(fragment: str) -> Optional[Any]:
            try:
                return json.loads(fragment, strict=False)
            except json.JSONDecodeError:
                sanitized = _normalize_json_text(fragment)
                try:
                    return json.loads(sanitized, strict=False)
                except json.JSONDecodeError:
                    return None

        parsed = _parse_fragment(candidate)
        if parsed is not None:
            return parsed

        def _balanced_object(fragment: str) -> Optional[str]:
            depth = 0
            in_string = False
            escaped = False
            for index, ch in enumerate(fragment):
                if in_string:
                    if escaped:
                        escaped = False
                        continue
                    if ch == '\\':
                        escaped = True
                        continue
                    if ch == '"':
                        in_string = False
                    continue

                if ch == '"':
                    in_string = True
                    continue
                if ch == '{':
                    depth += 1
                    continue
                if ch == '}':
                    depth -= 1
                    if depth == 0:
                        return fragment[: index + 1]
            return None

        objects = []
        search_start = 0
        while True:
            # look for either a `strategy` object (preferred) or legacy `tone` key
            object_start = None
            for key in ("{\"strategy\"", "{\"tone\""):
                idx = candidate.find(key, search_start)
                if idx != -1 and (object_start is None or idx < object_start):
                    object_start = idx
            if object_start is None:
                break
            fragment = _balanced_object(candidate[object_start:])
            if fragment is not None:
                obj = _parse_fragment(fragment)
                if isinstance(obj, dict):
                    objects.append(obj)
                    search_start = object_start + len(fragment)
                    continue
            search_start = object_start + 1

        if objects:
            return objects

        return None

    # 1) Python SDK
    try:
        import ollama as _ollama  # pyright: ignore[reportMissingImports]
        print(f"[debug] trying Ollama Python SDK chat for model={model}")
        resp = _ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        sdk_text = None
        if isinstance(resp, dict):
            sdk_text = resp.get("message", {}).get("content") if isinstance(resp.get("message"), dict) else None
            sdk_text = sdk_text or resp.get("response") or resp.get("text") or resp.get("content")
        else:
            message = getattr(resp, "message", None)
            sdk_text = getattr(message, "content", None) if message is not None else None
        if sdk_text:
            print("[debug] Ollama Python SDK returned output")
            parsed = _extract_json(str(sdk_text))
            if parsed is not None:
                return parsed
            print("[debug] Ollama Python SDK output was not valid JSON; falling back")
        else:
            print("[debug] Ollama Python SDK returned no usable text")
    except Exception as e:
        print("[debug] Ollama Python SDK call failed:", e)

    # 2) CLI fallback
    out = ""
    last_err = None
    try:
        cmd = ["ollama", "run", model, prompt]
        print(f"[debug] trying ollama command: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
        out = proc.stdout.strip() or proc.stderr.strip()
        if out:
            print("[debug] ollama command succeeded, captured output")
    except subprocess.CalledProcessError as e:
        last_err = e
        print(f"[debug] ollama command failed (non-zero exit). stdout={(e.stdout or '').strip()!r} stderr={(e.stderr or '').strip()!r}")
    except FileNotFoundError as e:
        last_err = e
        print("[debug] ollama CLI binary not found in PATH")
    except Exception as e:
        last_err = e
        print(f"[debug] unexpected error invoking ollama: {e}")

    # 3) Local HTTP API fallback
    if not out:
        try:
            ollama_url = "http://localhost:11434/api/generate"
            payload = {"model": model, "prompt": prompt, "stream": False}
            print(f"[debug] trying Ollama HTTP API at {ollama_url}")
            obj = None
            import urllib.request
            req = urllib.request.Request(
                ollama_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                obj = json.loads(response.read().decode("utf-8"))

            if obj:
                out = obj.get("response") or obj.get("text") or obj.get("output") or ""
                if not out and isinstance(obj.get("outputs"), list) and obj["outputs"]:
                    first = obj["outputs"][0]
                    if isinstance(first, dict):
                        out = first.get("content") or first.get("text") or ""
                if out:
                    print("[debug] Ollama HTTP API returned output")
        except Exception as e:
            print("[debug] Ollama HTTP API fallback failed:", e)

    if not out:
        if isinstance(last_err, FileNotFoundError):
            print("ollama CLI not found in PATH:", last_err)
            return None
        print("ollama invocation failed:", str(last_err))
        return None

    try:
        parsed = _extract_json(out)
        if parsed is not None:
            return parsed
        print("Failed to parse JSON from model output: no JSON block found")
        print("[debug] raw model output:\n", out)
        return None
    except Exception as e:
        print("Failed to parse JSON from model output:", e)
        try:
            print("[debug] raw model output:\n", out)
        except Exception:
            pass
        return None
