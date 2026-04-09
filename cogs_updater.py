import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

COGS_DIR = Path('Artifacts/Cogs')
SPROCKETS_DIR = Path('Artifacts/Sprockets')
DATE_PATTERN = re.compile(r'due:\s*["\']?(\d{4}-\d{2}-\d{2})["\']?')


def ensure_dirs() -> None:
    COGS_DIR.mkdir(parents=True, exist_ok=True)
    SPROCKETS_DIR.mkdir(parents=True, exist_ok=True)


def generate_uuid() -> str:
    return str(uuid.uuid4())[:8]


def get_today_date() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def get_daily_note_path(date_str: str) -> Path:
    return COGS_DIR / f'{date_str}.md'


def write_markdown(path: Path, frontmatter: dict, body: str) -> None:
    content = ['---']
    for key, value in frontmatter.items():
        content.append(f'{key}: {json.dumps(value)}')
    content.append('---\n')
    content.append(body)
    path.write_text('\n'.join(content), encoding='utf-8')


def create_or_update_daily_note() -> Path:
    ensure_dirs()
    today = get_today_date()
    daily_path = get_daily_note_path(today)

    frontmatter = {
        'uuid': generate_uuid(),
        'title': f'Daily Note - {today}',
        'tags': ['cogs/daily'],
        'created': datetime.utcnow().isoformat(),
        'updated': datetime.utcnow().isoformat(),
        'status': 'active'
    }

    if not daily_path.exists():
        body = '# Daily Note for ' + today + '\n\n'
        body += '## Todos\n\n'
        body += '## Events\n\n'
        body += '## Reflections\n\n'
        write_markdown(daily_path, frontmatter, body)
        return daily_path

    content = daily_path.read_text(encoding='utf-8')
    updated_lines = []
    found = False
    for line in content.splitlines():
        if line.startswith('updated:'):
            updated_lines.append(f'updated: "{datetime.utcnow().isoformat()}"')
            found = True
        else:
            updated_lines.append(line)
    if not found:
        updated_lines.insert(1, f'updated: "{datetime.utcnow().isoformat()}"')
    updated_content = '\n'.join(updated_lines)
    daily_path.write_text(updated_content, encoding='utf-8')
    return daily_path


def append_unique_lines(path: Path, section: str, lines: list[str]) -> None:
    text = path.read_text(encoding='utf-8')
    section_header = f'## {section}'
    if section_header not in text:
        text += f'\n{section_header}\n' + '\n'.join(line for line in lines if line not in text) + '\n'
        path.write_text(text, encoding='utf-8')
        return

    before, sep, after = text.partition(section_header)
    body, sep2, rest = after.partition('\n## ')
    new_lines = [line for line in lines if line not in text]
    if not new_lines:
        return

    text = before + section_header + body + '\n' + '\n'.join(new_lines)
    if sep2:
        text += '\n## ' + rest
    path.write_text(text, encoding='utf-8')


def carry_over_todos() -> None:
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = get_today_date()
    yesterday_path = get_daily_note_path(yesterday)
    today_path = get_daily_note_path(today)

    if not yesterday_path.exists() or not today_path.exists():
        return

    yesterday_content = yesterday_path.read_text(encoding='utf-8')
    unfinished = [line for line in yesterday_content.splitlines() if line.startswith('- [ ]')]
    if not unfinished:
        return

    append_unique_lines(today_path, 'Carried Over Todos', unfinished)


def extract_frontmatter_uuid(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding='utf-8')
    for line in text.splitlines():
        if line.startswith('uuid:'):
            return line.split(':', 1)[1].strip().strip('"')
    return None


def maintain_cross_references() -> None:
    today = get_today_date()
    today_path = get_daily_note_path(today)
    if not today_path.exists():
        return

    today_uuid = extract_frontmatter_uuid(today_path) or today
    links_to_add: list[str] = []
    backlinks: dict[Path, str] = {}

    for sprocket_file in SPROCKETS_DIR.glob('*.md'):
        content = sprocket_file.read_text(encoding='utf-8')
        due_match = DATE_PATTERN.search(content)
        if due_match and due_match.group(1) == today:
            node_uuid = sprocket_file.stem
            line = f'- [[{node_uuid}]] (Due today)'
            if line not in content:
                links_to_add.append(line)
                backlinks[sprocket_file] = f'Linked to daily: [[{today_uuid}]]'

    if links_to_add:
        append_unique_lines(today_path, 'Due Today', links_to_add)
    for sprocket_file, backlink in backlinks.items():
        content = sprocket_file.read_text(encoding='utf-8')
        if backlink not in content:
            sprocket_file.write_text(content + '\n' + backlink + '\n', encoding='utf-8')


def update_cogs(nodes=None):
    if nodes is None:
        nodes = []
    ensure_dirs()
    
    # Create today's daily note
    today = get_today_date()
    create_or_update_daily_note()
    carry_over_todos()
    
    # For each task node with a due date, create/update that day's daily note and link the task
    for node in nodes:
        node_type = node.get('node_type', 'task')
        due_date = node.get('due')
        
        # Only process task nodes with due dates
        if node_type == 'task' and due_date:
            # Create/update the daily note for that date
            due_path = get_daily_note_path(due_date)
            
            if not due_path.exists():
                frontmatter = {
                    'uuid': generate_uuid(),
                    'title': f'Daily Note - {due_date}',
                    'tags': ['cogs/daily'],
                    'created': datetime.utcnow().isoformat(),
                    'updated': datetime.utcnow().isoformat(),
                    'status': 'active'
                }
                body = f'# Daily Note for {due_date}\n\n'
                body += '## Todos\n\n'
                body += '## Events\n\n'
                body += '## Reflections\n\n'
                write_markdown(due_path, frontmatter, body)
            
            # Build the task link with time if available
            time_str = f' at {node.get("time")}' if node.get('time') else ''
            task_title = f'{node["title"]}{time_str}'
            
            # Use checked box if task is "done", unchecked otherwise
            checkbox = 'x' if node.get('status') == 'done' else ' '
            task_link = f'- [{checkbox}] [[{node["uuid"]}|{task_title}]]'
            append_unique_lines(due_path, 'Todos', [task_link])
            
            # Add backlink from the Sprocket to the daily note
            sprocket_path = SPROCKETS_DIR / f'{node["uuid"]}.md'
            if sprocket_path.exists():
                content = sprocket_path.read_text(encoding='utf-8')
                backlink = f'\n[[{due_date}|Due on {due_date}]]'
                if backlink not in content:
                    sprocket_path.write_text(content + backlink + '\n', encoding='utf-8')
    
    # Handle today's tasks
    maintain_cross_references()


if __name__ == '__main__':
    update_cogs()
