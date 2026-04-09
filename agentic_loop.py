#!/usr/bin/env python3
import asyncio
import json
from pathlib import Path
from datetime import datetime

from extractor import extract_nodes
from sprockets_graph_builder import build_sprockets_graph
from cogs_updater import update_cogs

INPUT_DIR = Path("Artifacts/Input/processed")
ARCHIVE_DIR = Path("Artifacts/Input/archived")

async def agentic_loop():
    print("=== AGENTIC LOOP STARTED ===")
    print("✅ Top-level heartbeat — loop is alive and running")

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❤️ Heartbeat — scanning for input...")

            for input_file in sorted(INPUT_DIR.glob("*.json")):
                print(f"📥 Processing input file: {input_file.name}")
                try:
                    with input_file.open("r", encoding="utf-8") as f:
                        raw_data = json.load(f)

                    nodes = extract_nodes(raw_data)
                    if not nodes:
                        raise ValueError("No extracted nodes returned")

                    written = build_sprockets_graph(nodes)
                    update_cogs(nodes)

                    archive_path = ARCHIVE_DIR / input_file.name
                    input_file.rename(archive_path)
                    print(f"✅ Successfully processed {input_file.name} -> {archive_path}")
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
