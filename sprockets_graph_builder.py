import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union

ARTIFACTS_DIR = Path('Artifacts/Sprockets')
EXTRACTED_DIR = Path('extracted')

class NodeBuilder:
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.load_existing_nodes()

    def load_existing_nodes(self):
        """Load existing MD files into memory for updates."""
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        for file in ARTIFACTS_DIR.glob('*.md'):
            with file.open('r', encoding='utf-8') as f:
                content = f.read()
            if content.startswith('---'):
                parts = content.split('---', 2)
                yaml_str = parts[1].strip()
                body = parts[2].strip() if len(parts) > 2 else ''
                node = self.parse_yaml(yaml_str)
                node['body'] = body
                self.nodes[node['uuid']] = node

    def parse_yaml(self, yaml_str: str) -> Dict[str, Any]:
        """Simple YAML parser for basic frontmatter fields."""
        node: Dict[str, Any] = {}
        for line in yaml_str.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                node[key.strip()] = value.strip().strip('"')
        return node

    def build_node(self, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """Build or update node with UUID, links, and body content."""
        node_uuid = extracted.get('uuid') or str(uuid.uuid4())[:8]
        tags = extracted.get('tags') or []
        node = self.nodes.get(node_uuid, {
            'uuid': node_uuid,
            'title': extracted.get('title', 'Untitled'),
            'aliases': extracted.get('aliases', []),
            'tags': tags,
            'created': extracted.get('created', datetime.utcnow().isoformat()),
            'updated': datetime.utcnow().isoformat(),
            'status': extracted.get('status', 'active'),
            'priority': extracted.get('priority'),
            'due': extracted.get('due'),
            'node_type': extracted.get('node_type', 'task'),
            'body': extracted.get('body', extracted.get('content', '')),
        })

        parent = extracted.get('parent')
        if parent and parent in self.nodes:
            parent_node = self.nodes[parent]
            link = f'- [[{node_uuid}]] ({node["title"]})'
            if link not in parent_node['body']:
                parent_node['body'] += f'\n{link}'
                self.nodes[parent] = parent_node
        return node

    def write_node_to_md(self, node: Dict[str, Any]):
        """Write a node to Markdown with YAML frontmatter."""
        priority_line = json.dumps(node.get('priority'))
        due_line = json.dumps(node.get('due'))
        time_line = ''
        if node.get('time'):
            time_line = f'time: {json.dumps(node["time"])}\n'
        parent_line = ''
        if node.get('parent'):
            parent_line = f'parent: {json.dumps(node["parent"])}\n'
        node_type_line = f'node_type: {json.dumps(node.get("node_type", "task"))}\n'

        yaml_front = (
            '---\n'
            f'uuid: {json.dumps(node["uuid"])}\n'
            f'title: {json.dumps(node["title"])}\n'
            f'aliases: {json.dumps(node.get("aliases", []))}\n'
            f'tags: {json.dumps(node.get("tags", []))}\n'
            f'created: {json.dumps(node["created"])}\n'
            f'updated: {json.dumps(node["updated"])}\n'
            f'status: {json.dumps(node["status"])}\n'
            f'priority: {priority_line}\n'
            f'due: {due_line}\n'
            f'{time_line}'
            f'{node_type_line}'
            f'{parent_line}'
            '---\n\n'
        )

        content = yaml_front + node.get('body', '')
        path = ARTIFACTS_DIR / f'{node["uuid"]}.md'
        with path.open('w', encoding='utf-8') as f:
            f.write(content)

    def process_extracted(self, extracted_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> List[str]:
        """Process extracted node payloads and write Sprockets markdown."""
        if isinstance(extracted_data, list):
            nodes = extracted_data
        elif isinstance(extracted_data, dict):
            if 'nodes' in extracted_data and isinstance(extracted_data['nodes'], list):
                nodes = extracted_data['nodes']
            else:
                nodes = []
                for value in extracted_data.values():
                    if isinstance(value, list):
                        nodes.extend(value)
        else:
            raise ValueError('Unsupported extracted_data format')

        written_uuids: List[str] = []
        for ext_node in nodes:
            node = self.build_node(ext_node)
            self.nodes[node['uuid']] = node
            self.write_node_to_md(node)
            written_uuids.append(node['uuid'])
            if ext_node.get('parent'):
                parent_node = self.nodes.get(ext_node['parent'])
                if parent_node:
                    self.write_node_to_md(parent_node)
        return written_uuids


def build_sprockets_graph(nodes: Union[List[Dict[str, Any]], Dict[str, Any]]) -> List[str]:
    builder = NodeBuilder()
    return builder.process_extracted(nodes)


def main():
    builder = NodeBuilder()
    seen = set(os.listdir(EXTRACTED_DIR))
    while True:
        current = set(os.listdir(EXTRACTED_DIR))
        new = current - seen
        for filename in sorted(new):
            if filename.endswith('.json'):
                path = EXTRACTED_DIR / filename
                with path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                builder.process_extracted(data)
        seen = current
        import time
        time.sleep(1)


if __name__ == '__main__':
    main()
