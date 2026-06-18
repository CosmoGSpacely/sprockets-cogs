# RUDI

RUDI is the reasoning, orchestration, and memory/retrieval specialist.

The name fits the role: RUDI is the Referential Universal Digital Indexer.

## Responsibility

RUDI previews route decisions, builds handoff messages, rehearses
cross-specialist workflows, and provides retrieval/memory support for safe
post-classification decisions.

RUDI owns memory and retrieval as part of reasoning. It does not directly write
to the vault.

## Runtime Form

RUDI is currently command-driven and preview-first. It is not an always-on
dispatcher.

## Current Implementation

- `orchestrator_contract.py`
- `orchestrated_rehearsal.py`
- `agent_message_bus.py`
- `memory_specialist.py`
- `memory_index.py`
- `memory_guards.py`
- `production_retrieval.py`
- `retrieval_*`
- `memory_packets.py`
- `memory_trace_log.py`
- `memory_demo.py`
- `scripts/orchestrator-route`
- `scripts/orchestrated-rehearsal`
- `scripts/agent-message-bus`
- `scripts/memory-specialist`
- `scripts/memory-demo`
- `scripts/retrieval-preview`
- `scripts/retrieval-traces`
- `scripts/memory-packets`

## Boundaries

- Prompt-appended memory context remains off.
- The message bus is a contract and rehearsal surface, not live dispatch.
- Graph and packet retrieval remain preview or benchmark first.
