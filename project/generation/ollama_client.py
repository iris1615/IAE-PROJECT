import json
import subprocess
from typing import Any, Optional


def ollama_generate_json(prompt: str, model: str = "gemma4", temperature: float = 0.4, timeout: int = 60) -> Optional[Any]:
    """Call Ollama CLI to generate output and try to extract JSON from stdout.

    Returns parsed JSON (object or array) or None on failure.
    """
    # Try multiple ollama CLI invocation patterns to be compatible across versions
    candidates = [
        ["ollama", "run", model, "--prompt", prompt, "--temperature", str(temperature)],
        ["ollama", "chat", model, "--prompt", prompt, "--temperature", str(temperature)],
        ["ollama", "generate", model, "--prompt", prompt, "--temperature", str(temperature)],
    ]

    out = ""
    proc = None
    last_err = None
    for cmd in candidates:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
            out = proc.stdout.strip() or proc.stderr.strip()
            break
        except subprocess.CalledProcessError as e:
            last_err = e
            # try next
        except FileNotFoundError as e:
            last_err = e
            break
        except Exception as e:
            last_err = e
            break
    if not out:
        if isinstance(last_err, FileNotFoundError):
            print("ollama binary not found in PATH; please install ollama or add to PATH")
        elif last_err is not None:
            print("ollama invocation failed:", str(last_err))
        return None
    # Try to extract the first JSON object/array in the output and parse it
    try:
        start_idx = min([i for i in (out.find("["), out.find("{")) if i != -1], default=-1)
        if start_idx == -1:
            return None
        # find matching end: prefer array
        if out[start_idx] == "[":
            end_idx = out.rfind("]")
        else:
            end_idx = out.rfind("}")
        if end_idx == -1:
            return None
        json_text = out[start_idx:end_idx + 1]
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        print("Failed to parse JSON from model output:", e)
        return None
    except Exception as e:
        print("Unexpected error parsing ollama output:", e)
        return None
