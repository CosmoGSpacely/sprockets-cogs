#!/usr/bin/env python3
import asyncio
import json
from pathlib import Path
from datetime import datetime
import time

# === ALL STUBS INCLUDED (no import errors) ===
def extract_nodes(raw_data):
    print(f"✅ STUB extract_nodes called with keys: {list(raw_data.keys()) if isinstance(raw_data, dict) else 'None'}")
    return [{"node_type": "task", "title": raw_data.get("raw_text", "Untitled Task"), "uuid": "stub-uuid-1234", "status": "active"}]

def build_sprockets_graph(nodes):
    print(f"✅ STUB build_sprockets_graph called with {len(nodes) if nodes else 0} nodes")
    return True

def update_cogs():
    print("✅ STUB update_cogs called — wrote daily note")
    return True

def load_node(uuid: str):
    print(f"✅ STUB load_node called for {uuid}")
    return None

def write_node(node):
    print("✅ STUB write_node called")
    return True

class ObsidianNode:
    def __init__(self, **kwargs):
        pass
    @classmethod
    def from_dict(cls, data):
        return cls(**data)
# === END OF STUBS ===

async def agentic_loop():
    print("=== AGENTIC LOOP STARTED ===")
    print("✅ Top-level heartbeat — loop is alive and running")
    
    input_dir = Path("Artifacts/Input")
    input_dir.mkdir(parents=True, exist_ok=True)
    
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❤️ Heartbeat — scanning for input...")
            
            for input_file in list(input_dir.glob("*.json")):
                print(f"📥 Processing input file: {input_file.name}")
                try:
                    with open(input_file, "r") as f:
                        raw_data = json.load(f)
                    
                    nodes = extract_nodes(raw_data)
                    build_sprockets_graph(nodes)
                    update_cogs()
                    
                    processed_dir = input_dir / "processed"
                    processed_dir.mkdir(exist_ok=True)
                    input_file.rename(processed_dir / input_file.name)
                    
                    print(f"✅ Successfully processed {input_file.name}")
                except Exception as e:
                    print(f"❌ Error processing {input_file.name}: {e}")
            
            await asyncio.sleep(5)
            
        except Exception as e:
            print(f"❌ Unexpected error in loop: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(agentic_loop())
    except KeyboardInterrupt:
        print("\n👋 Agentic loop stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
