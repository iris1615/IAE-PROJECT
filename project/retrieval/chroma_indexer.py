import json
import hashlib
from pathlib import Path
from typing import List
from project.common.types import EvidenceDocument  

def compute_case_layout_hash(case_dir: Path, case_id: str) -> str:
    """
    Computes a deterministic hash of the entire case directory layout.
    If any file inside 'evidences' or the truth JSON changes, the hash changes.
    """
    hasher = hashlib.md5()
    
    # Hash the truth file if it exists
    truth_file = case_dir / f"truth_{case_id}.json"
    if truth_file.exists():
        hasher.update(truth_file.read_bytes())
        
    # Hash all evidence files inside the folder alphabetically
    evidence_dir = case_dir / "evidences"
    if evidence_dir.exists() and evidence_dir.is_dir():
        for file_path in sorted(evidence_dir.glob("*.json")):
            hasher.update(file_path.name.encode('utf-8'))
            hasher.update(file_path.read_bytes())
            
    return hasher.hexdigest()

def ensure_chroma_index(repo_root: Path, case_id: str, documents: List[EvidenceDocument] = None, force: bool = False) -> bool:
    """
    Ensures the Chroma collection for a case is built and up-to-date.
    If documents are not provided, it automatically crawls the new directory layout.
    """
    import chromadb # Imported inline to match typical runtime setups
    
    case_dir = repo_root / "cases" / case_id
    manifest_path = case_dir / f"{case_id}_chroma_manifest.json"
    chroma_persist_dir = repo_root / "project" / "data" / "chroma"
    
    if not case_dir.exists():
        raise FileNotFoundError(f"Case directory not found at: {case_dir}")
        
    # Calculate current layout state fingerprint
    current_hash = compute_case_layout_hash(case_dir, case_id)
    
    # Check if we can skip indexing
    if not force and manifest_path.exists():
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            if manifest.get("layout_hash") == current_hash:
                # Structure matches, database is already perfectly indexed!
                return False
        except Exception:
            pass # If manifest is corrupted, force a rebuild

    # If documents weren't passed directly, let's harvest them using the new layout
    if not documents:
        documents = []
        
        # Parse evidences
        evidence_dir = case_dir / "evidences"
        if evidence_dir.exists():
            for file_path in evidence_dir.glob("*.json"):
                with open(file_path, "r", encoding="utf-8") as f:
                    ev = json.load(f)
                can_contra = ev.get("can_contradict", [])
                can_contra_str = ",".join(can_contra) if isinstance(can_contra, list) else str(can_contra)
                
                documents.append(
                    EvidenceDocument(
                        id=str(ev.get("id", file_path.stem)),
                        content=f"Name: {ev.get('name')}. Description: {ev.get('description', '')}",
                        kind="evidence",
                        metadata={"name": str(ev.get("name")), "can_contradict": can_contra_str}
                    )
                )
                
        # Parse truth facts
        truth_file = case_dir / f"truth_{case_id}.json"
        if truth_file.exists():
            with open(truth_file, "r", encoding="utf-8") as f:
                truth_data = json.load(f)
            facts = truth_data.get("facts") or truth_data.get("truth", {}).get("facts", [])
            for idx, fact in enumerate(facts):
                if isinstance(fact, dict) and (fact.get("truth") or fact.get("text")):
                    documents.append(
                        EvidenceDocument(
                            id=str(fact.get("id", f"fact_{idx}")),
                            content=fact.get("truth") or fact.get("text"),
                            kind="truth",
                            metadata={
                                "kind": "truth",
                                "fact_index": str(idx)
                            }
                        )
                    )

    if not documents:
        print(f"[WARNING] No documents found to index for case {case_id}.")
        return False

    print(f"Reindexing Chroma collection: court_docs_{case_id}...")
    
    # Initialize Chroma client and gather collection
    client = chromadb.PersistentClient(path=str(chroma_persist_dir))
    collection_name = f"court_docs_{case_id}"
    
    # If forced, clear existing collection to start clean
    if force:
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass
            
    collection = client.get_or_create_collection(name=collection_name)
    
    # Prepare payloads for Chroma upsert
    ids = [doc.id for doc in documents]
    docs = [doc.content for doc in documents]
    metadatas = [doc.metadata for doc in documents]
    
    # Let Chroma's default embedding function handle embedding generation implicitly
    collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    
    # Save the tracking manifest file so we don't repeat this on next boot
    with open(manifest_path, "w") as f:
        json.dump({"layout_hash": current_hash}, f)
        
    return True

def build_chroma_retriever(case_id: str):
    import chromadb
    chroma_persist_dir = Path("project/data/chroma")
    client = chromadb.PersistentClient(path=str(chroma_persist_dir))
    collection_name = f"court_docs_{case_id}"
    collection = client.get_collection(name=collection_name)
    
    class _Retriever:
        def similarity_search(self, query: str, k: int = 3):
            result = collection.query(query_texts=[query], n_results=k)
            ids = result.get("ids", [[]])[0]
            docs = result.get("documents", [[]])[0]
            metas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            
            from project.common.types import RetrievedChunk
            chunks = []
            for i, doc_id in enumerate(ids):
                distance = distances[i] if i < len(distances) else 0.0
                score = 1.0 / (1.0 + float(distance))
                chunks.append(
                    RetrievedChunk(
                        id=doc_id,
                        content=docs[i],
                        score=score,
                        metadata=metas[i] if i < len(metas) else {}
                    )
                )
            return chunks
            
    return _Retriever()