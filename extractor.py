import asyncio
import os
import json
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional
import requests

PROCESSED_DIR = 'processed'
EXTRACTED_DIR = 'extracted'

class ExtractedNode(BaseModel):
    title: str = Field(..., description="The title of the node")
    node_type: str = Field(..., description="Type: goal, project, task, milestone, event, daily, reflection")
    aliases: List[str] = Field(default_factory=list)
    additional_tags: List[str] = Field(default_factory=list)
    status: str = Field(default="todo", description="todo, inprogress, done")
    priority: str = Field(default="medium", description="high, medium, low")
    due: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    content: str = Field(default="", description="The main body content")
    parent: Optional[str] = Field(default=None, description="Title of parent node if applicable")

class ExtractionResult(BaseModel):
    nodes: List[ExtractedNode]

EXTRACTION_PROMPT = """
You are an expert extraction agent for a personal knowledge management system.

Your task is to parse the raw input text and extract structured nodes following the locked schemas.

Possible node types: goal (long-term objective), project (collection of tasks), task (actionable item), milestone (key achievement), event (scheduled happening), daily (daily note), reflection (thoughts and reviews).

For each extracted node, fill in the fields accurately based on the input.

If the input implies hierarchy, set 'parent' to the title of the parent node.

Output ONLY a valid JSON: {"nodes": [list of node dicts]}

Do not add extra text.

Raw input:
{raw_text}
"""

def create_extraction_prompt(raw_text: str) -> str:
    return EXTRACTION_PROMPT.format(raw_text=raw_text)

def call_llm(prompt: str, model: str = "llama3") -> str:
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.5}
    }
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        raise ValueError(f"LLM call failed: {e}")

async def watch_processed():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(EXTRACTED_DIR, exist_ok=True)
    seen = set(os.listdir(PROCESSED_DIR))
    while True:
        await asyncio.sleep(1)
        current = set(os.listdir(PROCESSED_DIR))
        new = current - seen
        for filename in new:
            if not filename.endswith('.json'):
                continue
            path = os.path.join(PROCESSED_DIR, filename)
            try:
                with open(path, 'r') as f:
                    input_data = json.load(f)
                raw_text = input_data['raw_text']
                prompt = create_extraction_prompt(raw_text)
                llm_response = call_llm(prompt)
                data = json.loads(llm_response)
                extraction = ExtractionResult(**data)
                extracted_filename = f"{os.path.splitext(filename)[0]}_extracted.json"
                extracted_path = os.path.join(EXTRACTED_DIR, extracted_filename)
                with open(extracted_path, 'w') as f:
                    json.dump(extraction.dict(), f, indent=4)
                print(f"Extracted {filename} to {extracted_path}")
            except Exception as e:
                print(f"Error extracting {filename}: {e}")
        seen = current

if __name__ == '__main__':
    asyncio.run(watch_processed())
# === STUB ADDED TO FIX IMPORT ERROR FROM agentic_loop.py ===
def extract_nodes(raw_data):
    """Stub: Turn raw input JSON into nodes for the pipeline."""
    print(f"✅ STUB: extract_nodes called with raw_data keys: {list(raw_data.keys()) if isinstance(raw_data, dict) else 'None'}")
    # Return a minimal list of nodes so the pipeline can continue
    return [{
        "node_type": "task",
        "title": raw_data.get("raw_text", "Untitled Task"),
        "uuid": "stub-uuid-1234",
        "status": "active"
    }]
# === END OF STUB ===
