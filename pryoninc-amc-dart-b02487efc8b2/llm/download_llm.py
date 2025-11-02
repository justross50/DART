"""
NOTE Downloading a new LLM requires the internet. You won't be able to run these functions without being connected.
"""
from huggingface_hub import snapshot_download

def download_llm(repo_id: str, local_dir = None | str) -> None:
    snapshot_download(
        repo_id=repo_id,
        local_dir=local_dir,
    )
repo_id = "MBZUAI/LaMini-Flan-T5-783M"
local_dir = f"./llm/models/{repo_id.split('/')[-1]}"

download_llm(repo_id, local_dir)
