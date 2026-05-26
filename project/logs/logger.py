import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def append_log(log_file: Path, payload: Dict[str, Any]) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
