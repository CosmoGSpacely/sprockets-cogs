import asyncio
import os
import re
import json
import uuid
import urllib.request
from datetime import datetime
from typing import List, Optional, Dict

PROCESSED_DIR = 'processed'
EXTRACTED_DIR = 'extracted'
DATE_PATTERN = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')

EXTRACTION_PROMPT = """
You are an expert extraction agent for a personal knowledge management system.

Your task is to parse the raw input text and extract structured task nodes.

CRITICAL: For ANY dates mentioned (like "March 15th", "April 5th", etc.):
1. Convert to YYYY-MM-DD format (assume current year is 2026 for dates without year)
2. Create a SEPARATE TASK NODE for each date mentioned
3. Set the "due" field to that date in YYYY-MM-DD format

Examples:
- "March 15th at 10am" → due: "2026-03-15"
- "April 5th" → due: "2026-04-05"
- "Monday" → calculate the actual date and use YYYY-MM-DD

For each task:
- title: concise action (e.g., "Go to dentist")
- due: YYYY-MM-DD or null
- description: details from input
- node_type: "task"

Output ONLY valid JSON: {"nodes": [{"title": "...", "due": "YYYY-MM-DD", "description": "...", "node_type": "task"}, ...]}

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
        request_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=request_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode('utf-8')
            result = json.loads(body)
        if "response" not in result:
            raise ValueError(f"LLM response missing 'response' field: {result}")
        return result["response"]
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
        for filename in sorted(new):
            if not filename.endswith('.json'):
                continue
            path = os.path.join(PROCESSED_DIR, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    input_data = json.load(f)
                raw_text = input_data.get('raw_text', '')
                prompt = create_extraction_prompt(raw_text)
                llm_response = call_llm(prompt)
                data = json.loads(llm_response)
                extracted_filename = f"{os.path.splitext(filename)[0]}_extracted.json"
                extracted_path = os.path.join(EXTRACTED_DIR, extracted_filename)
                with open(extracted_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                print(f"Extracted {filename} to {extracted_path}")
            except Exception as e:
                print(f"Error extracting {filename}: {e}")
        seen = current

if __name__ == '__main__':
    asyncio.run(watch_processed())


def extract_nodes(raw_data):
    """Extract structured nodes from raw input using LLM."""
    if not isinstance(raw_data, dict):
        return []

    text = raw_data.get('raw_text', '') or raw_data.get('text', '')
    if not isinstance(text, str) or not text.strip():
        return []

    try:
        prompt = create_extraction_prompt(text)
        llm_response = call_llm(prompt)
        data = json.loads(llm_response)
        if not isinstance(data, dict) or 'nodes' not in data:
            raise ValueError("Invalid LLM response format")
        nodes = data['nodes']
        if not isinstance(nodes, list):
            raise ValueError("Nodes must be a list")

        # Add uuid, created, updated to each node
        for node in nodes:
            if 'uuid' not in node:
                node['uuid'] = str(uuid.uuid4())[:8]
            if 'created' not in node:
                node['created'] = datetime.utcnow().isoformat()
            if 'updated' not in node:
                node['updated'] = datetime.utcnow().isoformat()
            # Ensure tags are lists
            if 'tags' not in node:
                node['tags'] = []
            elif not isinstance(node['tags'], list):
                node['tags'] = [node['tags']]
            # Add sprockets/ or cogs/ prefix based on node_type
            node_type = node.get('node_type', 'task')
            if node_type in ['goal', 'project', 'task', 'milestone']:
                node['tags'] = ['sprockets/' + t if not t.startswith('sprockets/') else t for t in node['tags']]
            elif node_type in ['event', 'daily', 'reflection']:
                node['tags'] = ['cogs/' + t if not t.startswith('cogs/') else t for t in node['tags']]

        return nodes
    except Exception as e:
        print(f"LLM extraction failed: {e}, falling back to simple extraction")
        # Fallback: parse text dates and create multiple task nodes
        import re
        from datetime import datetime as dt, timedelta
        
        today_dt = dt(2026, 4, 9)  # Current date
        
        # Extract dates: both numeric (4/8/26, 4/8/2026) and named (August 25, August 25th)
        numeric_pattern = r'(\d{1,2})/(\d{1,2})/(\d{2,4})'  # MM/DD/YY or MM/DD/YYYY
        named_pattern = r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?'
        time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)'  # Time pattern: 7am, 7:30pm, etc.
        
        # Find all dates with their positions
        numeric_matches = [(m.group(1), m.group(2), m.group(3), m.start()) for m in re.finditer(numeric_pattern, text)]
        named_matches = [(m.group(1), m.group(2), m.start()) for m in re.finditer(named_pattern, text, re.IGNORECASE)]
        time_matches = [(m.group(1), m.group(2) or '', m.group(3), m.start()) for m in re.finditer(time_pattern, text)]
        
        print(f"[DEBUG] Named matches: {named_matches}")
        print(f"[DEBUG] Time matches: {time_matches}")
        
        def find_nearest_time(date_pos):
            """Find the time closest to the given date position."""
            if not time_matches:
                return None
            # Find the time that comes closest after the date
            times_after = [t for t in time_matches if t[3] > date_pos]
            if times_after:
                hour, minute, ampm, _ = times_after[0]  # Take the first time after the date
                minute = minute if minute else '00'
                return f"{hour}:{minute} {ampm}"
            # If no time after, look for time before
            times_before = [t for t in time_matches if t[3] <= date_pos]
            if times_before:
                hour, minute, ampm, _ = times_before[-1]  # Take the last time before the date
                minute = minute if minute else '00'
                return f"{hour}:{minute} {ampm}"
            return None
        
        nodes = []
        months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        
        # Extract the main action from the text
        title = text.splitlines()[0][:100].split('on')[0].strip() or 'Task'
        if 'appointment' in title.lower():
            if 'dentist' in text.lower():
                title = 'Go to dentist'
            elif 'doctor' in text.lower():
                title = 'Doctor appointment'
            else:
                title = 'Appointment'
        elif 'need to' in title.lower():
            title = title.split('need to')[1].strip() if 'need to' in title.lower() else title
        
        # Process numeric dates (MM/DD/YY or MM/DD/YYYY)
        for month_str, day_str, year_str, date_pos in numeric_matches:
            month_num = int(month_str)
            day_num = int(day_str)
            year_num = int(year_str)
            # Handle 2-digit years
            if year_num < 100:
                year_num = 2000 + year_num if year_num < 50 else 1900 + year_num
            
            due_date_obj = dt(year_num, month_num, day_num)
            due_date = f"{year_num:04d}-{month_num:02d}-{day_num:02d}"
            # Mark past appointments as "done"
            status = 'done' if due_date_obj < today_dt else 'active'
            appointment_time = find_nearest_time(date_pos)
            node = {
                'uuid': str(uuid.uuid4())[:8],
                'title': title,
                'node_type': 'task',
                'aliases': [],
                'tags': ['sprockets/task'],
                'status': status,
                'priority': 'medium',
                'due': due_date,
                'time': appointment_time,
                'content': text,
                'parent': None,
                'created': datetime.utcnow().isoformat(),
                'updated': datetime.utcnow().isoformat(),
            }
            nodes.append(node)
        
        # Process named month dates (August 25, etc.)
        for month_str, day_str, date_pos in named_matches:
            month_num = months[month_str.lower()]
            day_num = int(day_str)
            due_date_obj = dt(2026, month_num, day_num)
            # Mark past appointments as "done"
            status = 'done' if due_date_obj < today_dt else 'active'
            due_date = f"2026-{month_num:02d}-{day_num:02d}"
            appointment_time = find_nearest_time(date_pos)
            print(f"[DEBUG] {month_str} {day_str} (pos {date_pos}) -> time: {appointment_time}")
            node = {
                'uuid': str(uuid.uuid4())[:8],
                'title': title,
                'node_type': 'task',
                'aliases': [],
                'tags': ['sprockets/task'],
                'status': status,
                'priority': 'medium',
                'due': due_date,
                'time': appointment_time,
                'content': text,
                'parent': None,
                'created': datetime.utcnow().isoformat(),
                'updated': datetime.utcnow().isoformat(),
            }
            nodes.append(node)
        
        # If no future dates found, create a single task with no due date
        if not nodes:
            node = {
                'uuid': str(uuid.uuid4())[:8],
                'title': title,
                'node_type': 'task',
                'aliases': [],
                'tags': ['sprockets/task'],
                'status': 'active',
                'priority': 'medium',
                'due': None,
                'time': None,
                'content': text,
                'parent': None,
                'created': datetime.utcnow().isoformat(),
                'updated': datetime.utcnow().isoformat(),
            }
            nodes.append(node)
        
        return nodes
