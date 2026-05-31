import json
from pathlib import Path
from typing import Dict, List, Optional

from project.common.types import EvidenceDocument


def _load_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_json_items(directory: Path) -> List[Dict]:
    if not directory.exists():
        return []
    items: List[Dict] = []
    for json_file in sorted(directory.glob("*.json")):
        items.append(_load_json(json_file))
    return items


def load_case_bundle(repo_root: Path, case_id: str) -> Dict:
    case_dir = repo_root / "cases" / case_id
    case_data = _load_json(case_dir / f"{case_id}.json")
    truth_data = _load_json(case_dir / f"truth_{case_id}.json")

    evidence_items = _load_json_items(case_dir / "evidences")
    if not evidence_items:
        legacy_evidence = case_dir / "evidence.json"
        if legacy_evidence.exists():
            evidence_items = [_load_json(legacy_evidence)]

    testimony_items = _load_json_items(case_dir / "testimonies")
    if not testimony_items:
        legacy_testimonies = case_dir / "testimonies.json"
        if legacy_testimonies.exists():
            loaded_testimonies = _load_json(legacy_testimonies)
            if isinstance(loaded_testimonies, dict) and isinstance(loaded_testimonies.get("testimonies"), list):
                testimony_items = list(loaded_testimonies.get("testimonies", []))
            elif isinstance(loaded_testimonies, dict):
                testimony_items = [loaded_testimonies]

    witnesses_data: Dict[str, Dict] = {}
    witnesses_dir = case_dir / "witnesses"
    if witnesses_dir.exists():
        for witness_file in sorted(witnesses_dir.glob("*.json")):
            witness_data = _load_json(witness_file)
            witness_id = witness_data.get("id")
            if witness_id:
                witnesses_data[witness_id] = witness_data

    characters_dir = repo_root / "characters"
    judge_data = _load_json(characters_dir / "judge.json")
    prosecutor_data = _load_json(characters_dir / "prosecutor.json")

    return {
        "case": case_data,
        "evidence_items": evidence_items,
        "testimony_items": testimony_items,
        "evidence": evidence_items[0] if evidence_items else {},
        "testimonies": testimony_items[0] if testimony_items else {},
        "truth": truth_data,
        "witnesses": witnesses_data,
        "judge": judge_data,
        "prosecutor": prosecutor_data,
    }


def get_evidence(bundle: Dict, evidence_id: Optional[str] = None) -> Dict:
    evidence_items = bundle.get("evidence_items", [])
    if evidence_id is None:
        return evidence_items[0] if evidence_items else bundle.get("evidence", {})
    for item in evidence_items:
        if item.get("id") == evidence_id:
            return item
    return {}


def get_testimony(bundle: Dict, testimony_id: Optional[str] = None, witness_id: Optional[str] = None) -> Dict:
    testimony_items = bundle.get("testimony_items", [])
    if testimony_id is None and witness_id is None:
        return testimony_items[0] if testimony_items else bundle.get("testimonies", {})
    for item in testimony_items:
        if testimony_id and item.get("id") == testimony_id:
            return item
        if witness_id and item.get("witness_id") == witness_id:
            return item
    return {}


def build_documents(bundle: Dict) -> List[EvidenceDocument]:
    docs: List[EvidenceDocument] = []

    for evidence in bundle.get("evidence_items", []):
        docs.append(
            EvidenceDocument(
                id=evidence["id"],
                kind="evidence",
                content=f"{evidence['name']}: {evidence['description']}",
                metadata={
                    "can_contradict": evidence.get("can_contradict", []),
                    "reveals": evidence.get("reveals", []),
                },
            )
        )

    for testimony in bundle.get("testimony_items", []):
        for stmt in testimony.get("statements", []):
            docs.append(
                EvidenceDocument(
                    id=stmt["id"],
                    kind="testimony",
                    content=stmt["text"],
                    metadata={
                        "emotion": stmt.get("emotion", "calm"),
                        "contradicted_by": stmt.get("contradicted_by"),
                        "truthfulness": stmt.get("truthfulness"),
                        "testimony_id": testimony.get("id"),
                    },
                )
            )

    for fact in bundle["truth"].get("facts", []):
        docs.append(
            EvidenceDocument(
                id=fact["id"],
                kind="truth",
                content=fact["truth"],
                metadata={},
            )
        )

    docs.append(
        EvidenceDocument(
            id=bundle["judge"]["id"],
            kind="character",
            content=f"Judge personality: {bundle['judge'].get('personality', {})}",
            metadata={"role": "judge"},
        )
    )
    docs.append(
        EvidenceDocument(
            id=bundle["prosecutor"]["id"],
            kind="character",
            content=f"Prosecutor personality: {bundle['prosecutor'].get('personality', {})}",
            metadata={"role": "prosecutor"},
        )
    )

    return docs
