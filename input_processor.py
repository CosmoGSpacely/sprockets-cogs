import asyncio
import os
import json
from datetime import datetime

INPUT_DIR = 'input'
PROCESSED_DIR = 'processed'

async def watch_input():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    seen = set(os.listdir(INPUT_DIR))
    while True:
        await asyncio.sleep(1)
        current = set(os.listdir(INPUT_DIR))
        new = current - seen
        for filename in new:
            path = os.path.join(INPUT_DIR, filename)
            try:
                with open(path, 'r') as f:
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
                with open(json_path, 'w') as f:
                    json.dump(json_data, f, indent=4)
                os.rename(path, os.path.join(PROCESSED_DIR, filename))
                print(f"Processed {filename} to {json_path}")
            except Exception as e:
                print(f"Error processing {filename}: {e}")
        seen = current

if __name__ == '__main__':
    asyncio.run(watch_input())