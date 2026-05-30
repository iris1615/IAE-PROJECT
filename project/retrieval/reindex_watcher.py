from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Dict, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except Exception:  # pragma: no cover - informative fallback
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore

from project.retrieval.chroma_indexer import ensure_chroma_index
from project.retrieval.loader import load_case_bundle, build_documents


class DebouncedReindexHandler(FileSystemEventHandler):
    def __init__(self, repo_root: Path, delay: float = 1.0):
        self.repo_root = repo_root
        self.delay = delay
        self.timers: Dict[str, threading.Timer] = {}

    def on_any_event(self, event):
        path = Path(event.src_path)
        # If change in schemas or prompts, reindex all cases
        if self._is_schema(path) or self._is_prompt(path):
            self._schedule("__all__")
            return

        # If change in a case file, schedule that case
        case_id = self._find_case_id(path)
        if case_id:
            self._schedule(case_id)

    def _schedule(self, case_id: str):
        # cancel previous timer
        t = self.timers.get(case_id)
        if t and t.is_alive():
            t.cancel()
        timer = threading.Timer(self.delay, self._do_reindex, args=(case_id,))
        self.timers[case_id] = timer
        timer.start()

    def _do_reindex(self, case_id: str):
        try:
            if case_id == "__all__":
                for case_dir in sorted((self.repo_root / "cases").iterdir()):
                    if case_dir.is_dir():
                        case_id_name = case_dir.name
                        bundle = load_case_bundle(self.repo_root, case_id_name)
                        docs = build_documents(bundle)
                        ensure_chroma_index(self.repo_root, case_id_name, docs, force=True)
            else:
                bundle = load_case_bundle(self.repo_root, case_id)
                docs = build_documents(bundle)
                ensure_chroma_index(self.repo_root, case_id, docs, force=True)
        except Exception as e:
            print(f"[reindex-watcher] failed to reindex {case_id}: {e}")

    def _find_case_id(self, path: Path) -> Optional[str]:
        # look for a parent directory named like a case (case_XXX)
        for p in path.parents:
            if p.name.startswith("case_") and (p / (p.name + ".json")).exists():
                return p.name
        # also accept direct files under cases/<case_id>/*.json
        try:
            parts = path.parts
            if "cases" in parts:
                idx = parts.index("cases")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
        except Exception:
            pass
        return None

    def _is_schema(self, path: Path) -> bool:
        return "schemas" in path.parts and path.suffix == ".json"

    def _is_prompt(self, path: Path) -> bool:
        return "prompts" in path.parts or path.suffix in {".py", ".md", ".txt"}


def start_watcher(repo_root: Optional[Path] = None, delay: float = 1.0):
    repo_root = Path(repo_root or Path.cwd())
    if Observer is None:
        print("watchdog is not installed. Install with 'pip install watchdog' to use reindex watcher.")
        return

    handler = DebouncedReindexHandler(repo_root, delay=delay)
    observer = Observer()
    observer.schedule(handler, str(repo_root / "cases"), recursive=True)
    observer.schedule(handler, str(repo_root / "schemas"), recursive=True)
    observer.schedule(handler, str(repo_root / "project" / "prompts"), recursive=True)
    observer.start()
    print(f"Reindex watcher started for {repo_root}. Watching cases/, schemas/, project/prompts/")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    start_watcher()
