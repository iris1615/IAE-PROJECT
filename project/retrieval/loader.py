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
    evidence_data = _load_json(case_dir / "evidence.json")
    testimonies_data = _load_json(case_dir / "testimonies.json")
    truth_data = _load_json(case_dir / f"truth_{case_id}.json")

    characters_dir = repo_root / "characters"
    judge_data = _load_json(characters_dir / "judge.json")
    prosecutor_data = _load_json(characters_dir / "prosecutor.json")

    return {
        "case": case_data,
        "evidence": evidence_data,
        "testimonies": testimonies_data,
        "truth": truth_data,
        "judge": judge_data,
        "prosecutor": prosecutor_data,
    }


def build_documents(bundle: Dict) -> List[EvidenceDocument]:
    docs: List[EvidenceDocument] = []

    evidence = bundle["evidence"]
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

    testimony = bundle["testimonies"]
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
