import json
from pathlib import Path
from typing import Dict, List

from project.common.types import EvidenceDocument


def _load_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_case_bundle(repo_root: Path, case_id: str) -> Dict:
    case_dir = repo_root / "cases" / case_id
    case_data = _load_json(case_dir / f"{case_id}.json")

    evidence_ref = case_data.get("_evidence_ref", "./evidence.json")
    evidence_path = (case_dir / evidence_ref).resolve()
    if evidence_path.is_dir():
        evidence_data = []
        for evidence_file in sorted(evidence_path.glob("*.json")):
            evidence_data.append(_load_json(evidence_file))
    else:
        evidence_data = _load_json(evidence_path if evidence_path.exists() else case_dir / "evidence.json")

    truth_data = _load_json(case_dir / f"truth_{case_id}.json")

    # Load testimonies from folder (one file per witness), keyed by testimony id.
    # Falls back to the legacy single-file testimonies.json if the folder doesn't exist.
    testimonies_data: Dict[str, Dict] = {}
    testimonies_dir = case_dir / "testimonies"
    if testimonies_dir.exists() and testimonies_dir.is_dir():
        for testimony_file in sorted(testimonies_dir.glob("*.json")):
            testimony = _load_json(testimony_file)
            testimony_id = testimony.get("id")
            if testimony_id:
                testimonies_data[testimony_id] = testimony
    else:
        # Legacy fallback: single testimonies.json keyed by its own id
        legacy_path = case_dir / "testimonies.json"
        if legacy_path.exists():
            legacy = _load_json(legacy_path)
            testimony_id = legacy.get("id")
            if testimony_id:
                testimonies_data[testimony_id] = legacy

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
        "evidence": evidence_data,
        # testimonies is now a dict keyed by testimony id, e.g.:
        # { "testimony_cashier_1": {...}, "testimony_person_in_line_1": {...} }
        "testimonies": testimonies_data,
        "truth": truth_data,
        "witnesses": witnesses_data,
        "judge": judge_data,
        "prosecutor": prosecutor_data,
    }


def build_documents(bundle: Dict) -> List[EvidenceDocument]:
    docs: List[EvidenceDocument] = []

    evidence_data = bundle["evidence"]
    if isinstance(evidence_data, list):
        evidence_items = evidence_data
    else:
        evidence_items = [evidence_data]

    for evidence in evidence_items:
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

    
    testimonies = bundle["testimonies"]
    for testimony in testimonies.values():
        for stmt in testimony.get("statements", []):
            docs.append(
                EvidenceDocument(
                    id=stmt["id"],
                    kind="testimony",
                    content=stmt["text"],
                    metadata={
                        "testimony_id": testimony.get("id"),
                        "witness_id": testimony.get("witness_id"),
                        "emotion": stmt.get("emotion", "calm"),
                        "contradicted_by": stmt.get("contradicted_by"),
                        "truthfulness": stmt.get("truthfulness"),
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