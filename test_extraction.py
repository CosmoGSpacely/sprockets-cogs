#!/usr/bin/env python3
from extractor import extract_nodes

raw_data = {
    'raw_text': '''I had a dentist appointment on March 15 at 9:30am.
I have upcoming appointments on August 25 at 7am and December 15 at 8:30pm.'''
}

nodes = extract_nodes(raw_data)
print(f'Extracted {len(nodes)} nodes:')
for i, node in enumerate(nodes, 1):
    print(f"\nNode {i}:")
    print(f"  Title: {node['title']}")
    print(f"  Due: {node.get('due')}")
    print(f"  Status: {node.get('status')}")
    print(f"  Time: {node.get('time')}")
