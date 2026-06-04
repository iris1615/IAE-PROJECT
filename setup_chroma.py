# setup_chroma.py
from pathlib import Path
from project.retrieval.chroma_indexer import ensure_chroma_index

def build_database():
    # repo_root points to the root directory where the "cases" folder lives
    repo_root = Path(__file__).parent.resolve()
    case_id = "case_001"
    
    print(f"Initializing build script for layout... Case: '{case_id}'")
    print(f"Target repository root: {repo_root}")
    print("Triggering the auto-crawler from chroma_indexer...")
    
    try:
        # By passing documents=None, we force the updated indexer to look into
        # the 'evidences' folder and 'truth_case_001.json' on its own!
        reindexed = ensure_chroma_index(
            repo_root=repo_root, 
            case_id=case_id, 
            documents=None, 
            force=True
        )
        
        if reindexed:
            print("\n🎉 Chroma database built successfully from the new directory layout!")
        else:
            print("\n✨ Chroma index was already up to date matching the current file hashes.")
            
    except FileNotFoundError as fnf:
        print(f"\n[ERROR] Path mismatch: {fnf}")
        print("Please verify your directory structure matches: cases/case_001/evidences/")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred during Chroma execution: {e}")

if __name__ == "__main__":
    build_database()