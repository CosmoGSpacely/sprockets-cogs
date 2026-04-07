import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import uuid

# Assuming imports from previous stages
# from extractor import CogNode, Todo, Daily  # Adjust based on actual modules
from sprockets_graph_builder import build_cog_markdown  # From Stage 11

COGS_DIR = 'Artifacts/Cogs/'
SPROCKETS_DIR = 'Artifacts/Sprockets/'

 def generate_uuid() -> str:
    return str(uuid.uuid4())[:8]

def get_today_date() -> str:
    return datetime.now().strftime('%Y-%m-%d')

def get_daily_note_path(date_str: str) -> Path:
    return Path(COGS_DIR) / f'{date_str}.md'

def create_or_update_daily_note():
    today = get_today_date()
    daily_path = get_daily_note_path(today)
    
    if not daily_path.exists():
        # Create new daily note
        daily_uuid = generate_uuid()
        daily_data = {
            'uuid': daily_uuid,
            'title': f'Daily Note - {today}',
            'tags': ['cogs/daily'],
            'created': datetime.utcnow().isoformat(),
            'updated': datetime.utcnow().isoformat(),
            'status': 'active',
            'body': f'# Daily Note for {today}\n\n## Todos\n\n## Events\n\n## Reflections\n'
        }
        build_cog_markdown(daily_data, COGS_DIR)
    else:
        # Update existing (e.g., update timestamp)
        with open(daily_path, 'r') as f:
            content = f.read()
        # Simple update: append updated timestamp or something
        updated_content = content.replace('updated: ', f'updated: {datetime.utcnow().isoformat()}')
        with open(daily_path, 'w') as f:
            f.write(updated_content)

def carry_over_todos():
    today = get_today_date()
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_path = get_daily_note_path(yesterday)
    today_path = get_daily_note_path(today)
    
    if not yesterday_path.exists() or not today_path.exists():
        return
    
    # Parse yesterday's todos (assuming todos are listed in body with status)
    with open(yesterday_path, 'r') as f:
        yesterday_content = f.read()
    
    # Heuristic: find unfinished todos (e.g., lines starting with - [ ] )
    unfinished = [line for line in yesterday_content.split('\n') if line.startswith('- [ ]')]
    
    if unfinished:
        carry_over = '\n'.join(unfinished) + '\n'
        with open(today_path, 'a') as f:
            f.write('\n## Carried Over Todos\n' + carry_over)

def maintain_cross_references():
    # Scan sprockets and link to today's daily if relevant (e.g., due today)
    today = get_today_date()
    today_path = get_daily_note_path(today)
    today_uuid = ''  # Extract from file or generate
    with open(today_path, 'r') as f:
        for line in f:
            if 'uuid:' in line:
                today_uuid = line.split(':')[1].strip().strip('"')
                break
    
    for sprocket_file in Path(SPROCKETS_DIR).glob('*.md'):
        with open(sprocket_file, 'r') as f:
            content = f.read()
        if f'due: "{today}"' in content:
            # Add link to daily
            uuid = sprocket_file.stem
            append = f'\n- [[{uuid}]] (Due today)\n'
            with open(today_path, 'a') as f:
                f.write(append)
            # Add backlink to sprocket
            with open(sprocket_file, 'a') as f:
                f.write(f'\nLinked to daily: [[{today_uuid}]]\n')

def cogs_update_loop():
    create_or_update_daily_note()
    carry_over_todos()
    maintain_cross_references()

if __name__ == '__main__':
    cogs_update_loop()