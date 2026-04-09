#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/cosmo/icm-production')

from extractor import extract_nodes

raw_data = {
    'raw_text': '''I have had appointments on March 15 at 9:30am and April 5 at 2pm.
I have upcoming dentist appointments on August 25 at 7am and December 15 at 8:30pm.
Please schedule these appointments properly.'''
}

print("Testing extractor...")
nodes = extract_nodes(raw_data)
print(f'\nExtracted {len(nodes)} nodes:')
for i, node in enumerate(nodes, 1):
    print(f"\nNode {i}:")
    print(f"  Title: {node.get('title')}")
    print(f"  Due: {node.get('due')}")
    print(f"  Status: {node.get('status')}")
    print(f"  Time: {node.get('time')}")
