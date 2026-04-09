import asyncio
import os
import json
from datetime import datetime

INPUT_DIR = 'Artifacts/Input/raw'
PROCESSED_DIR = 'Artifacts/Input/processed'
ARCHIVED_DIR = 'Artifacts/Input/archived'

async def watch_input():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(ARCHIVED_DIR, exist_ok=True)
    seen = set()
    # Process any existing files on startup
    current = set(os.listdir(INPUT_DIR))
    for filename in sorted(current):
        path = os.path.join(INPUT_DIR, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            metadata = {
                'received_at': datetime.utcnow().isoformat(),
                'filename': filename,
                'source': 'filesystem'
            }
            json_data = {
                'raw_text': raw_text,
                'metadata': metadata
            }
            json_filename = f"{os.path.splitext(filename)[0]}.json"
            json_path = os.path.join(PROCESSED_DIR, json_filename)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=4)
            archived_path = os.path.join(ARCHIVED_DIR, filename)
            os.replace(path, archived_path)
            print(f"Processed {filename} -> {json_path} and archived original to {archived_path}")
        except Exception as e:
            print(f"Error processing {filename}: {e}")
    while True:
        await asyncio.sleep(1)
        current = set(os.listdir(INPUT_DIR))
        new = current - seen
        for filename in new:
            path = os.path.join(INPUT_DIR, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    raw_text = f.read()
                metadata = {
                    'received_at': datetime.utcnow().isoformat(),
                    'filename': filename,
                    'source': 'filesystem'
                }
                json_data = {
                    'raw_text': raw_text,
                    'metadata': metadata
                }
                json_filename = f"{os.path.splitext(filename)[0]}.json"
                json_path = os.path.join(PROCESSED_DIR, json_filename)
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=4)
                archived_path = os.path.join(ARCHIVED_DIR, filename)
                os.replace(path, archived_path)
                print(f"Processed {filename} -> {json_path} and archived original to {archived_path}")
            except Exception as e:
                print(f"Error processing {filename}: {e}")
        seen = current

if __name__ == '__main__':
    asyncio.run(watch_input())