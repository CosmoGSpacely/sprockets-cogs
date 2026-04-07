import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

ARTIFACTS_DIR = 'Artifacts/Sprockets/'
EXTRACTED_DIR = 'extracted'  # Assuming from stage 10

class NodeBuilder:
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.load_existing_nodes()

    def load_existing_nodes(self):
        """Load existing MD files into memory for updates."""
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)
        for file in Path(ARTIFACTS_DIR).glob('*.md'):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
            # Parse YAML (simple split for demo)
            if content.startswith('---'):
                parts = content.split('---', 2)
                yaml_str = parts[1].strip()
                body = parts[2].strip() if len(parts) > 2 else ''
                node = self.parse_yaml(yaml_str)
                node['body'] = body
                self.nodes[node['uuid']] = node

    def parse_yaml(self, yaml_str: str) -> Dict[str, Any]:
        """Simple YAML parser (use ruamel.yaml in production)."""
        node = {}
        for line in yaml_str.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                node[key.strip()] = value.strip()
        return node

    def build_node(self, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """Build or update node with UUID, links, etc."""
        node_uuid = extracted.get('uuid', str(uuid.uuid4())[:8])
        parent = extracted.get('parent')
        node = self.nodes.get(node_uuid, {
            'uuid': node_uuid,
            'title': extracted['title'],
            'aliases': extracted.get('aliases', []),
            'tags': extracted.get('tags', []),
            'created': extracted.get('created', datetime.utcnow().isoformat()),
            'updated': datetime.utcnow().isoformat(),
            'status': extracted.get('status', 'active'),
            'priority': extracted.get('priority'),
            'due': extracted.get('due'),
            'body': extracted.get('body', extracted.get('content', '')),
            'children': []
        })
        # Add wiki-link to parent if exists
        if parent and parent in self.nodes:
            parent_node = self.nodes[parent]
            if f'[[{node_uuid}]]' not in parent_node['body']:
                parent_node['body'] += f'\n- [[{node_uuid}]] ({node["title"]})'
                self.nodes[parent] = parent_node
        return node

    def write_node_to_md(self, node: Dict[str, Any]):
        """Write node to Markdown with YAML frontmatter."""
        yaml_front = (f'---\n'
                      f'title: {node["title"]}\n'
                      f'aliases: {json.dumps(node["aliases"])}\n'
                      f'tags: {json.dumps(node["tags"])}\n'
                      f'created: {node["created"]}\n'
                      f'updated: {node["updated"]}\n'
                      f'status: {node["status"]}\n'
                      f'priority: {node.get("priority")}\n'
                      f'due: {node.get("due")}\n'
                      f'---\n')
        content = yaml_front + node['body']
        path = Path(ARTIFACTS_DIR) / f'{node["uuid"]}.md'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def process_extracted(self, extracted_data: Dict[str, List[Dict[str, Any]]]):
        """Process all extracted nodes and build graph."""
        for node_type, nodes in extracted_data.items():
            for ext_node in nodes:
                node = self.build_node(ext_node)
                self.nodes[node['uuid']] = node
                self.write_node_to_md(node)
                # Update parents if needed
                if 'parent' in ext_node:
                    parent_node = self.nodes.get(ext_node['parent'])
                    if parent_node:
                        self.write_node_to_md(parent_node)

def main():
    builder = NodeBuilder()
    # Watch extracted dir (similar to previous stages)
    seen = set(os.listdir(EXTRACTED_DIR))
    while True:
        current = set(os.listdir(EXTRACTED_DIR))
        new = current - seen
        for filename in new:
            if filename.endswith('.json'):
                path = os.path.join(EXTRACTED_DIR, filename)
                with open(path, 'r') as f:
                    data = json.load(f)
                builder.process_extracted(data)  # Assuming data is dict of lists
        seen = current
        # Sleep or use asyncio in production
        import time
        time.sleep(1)

if __name__ == '__main__':
    main()
# === STUBS REQUIRED BY agentic_loop.py (Stage 13) ===
# Added with backup protection per your rule

def build_sprockets_graph(nodes):
    """Stub: Build Sprockets graph from extracted nodes."""
    print(f"✅ STUB: build_sprockets_graph called with {len(nodes) if nodes else 0} nodes")
    return True

def load_node(uuid: str):
    """Stub: Load a node by UUID."""
    print(f"✅ STUB: load_node called for UUID {uuid}")
    return None

def write_node(node):
    """Stub: Write a node to Markdown."""
    print("✅ STUB: write_node called")
    return True

class ObsidianNode:
    """Stub: ObsidianNode class."""
    def __init__(self, **kwargs):
        pass
    @classmethod
    def from_dict(cls, data):
        return cls(**data)
# === END OF STUBS ===
