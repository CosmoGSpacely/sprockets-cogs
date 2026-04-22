"""Prompts, JSON schemas, and few-shot message histories for the two-call chain."""

# ── Call 1: Extract ────────────────────────────────────────────────────────────

EXTRACT_SYSTEM = """\
You are an extraction engine. Given text, identify all discrete items and output them as JSON.

type_hint values:
  appointment — has a specific time (8am, 5:30p, noon)
  setting     — context keyword, no time (WFH, ONSITE, HOLIDAY)
  task        — actionable, no time anchor
  contact     — a person
  entity      — org, place, or thing
  note        — reference or idea, no action

Output format: {"items": [{"raw": "...", "type_hint": "..."}]}
"""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw":       {"type": "string"},
                    "type_hint": {"type": "string",
                                  "enum": ["appointment", "task", "setting",
                                           "contact", "entity", "note"]}
                },
                "required": ["raw", "type_hint"]
            }
        }
    },
    "required": ["items"]
}

EXTRACT_EXAMPLES = [
    {
        "role": "user",
        "content": "Extract all items from this text:\n\nI have a dentist appointment Monday at 8am and need to pick up my prescription at CVS afterward."
    },
    {
        "role": "assistant",
        "content": '{"items": [{"raw": "dentist appointment Monday at 8am", "type_hint": "appointment"}, {"raw": "pick up prescription at CVS", "type_hint": "task"}]}'
    },
    {
        "role": "user",
        "content": "Extract all items from this text:\n\nCall Frank re: the Acme contract. He's at 410-555-1212."
    },
    {
        "role": "assistant",
        "content": '{"items": [{"raw": "call Frank re: the Acme contract", "type_hint": "task"}, {"raw": "Frank, phone 410-555-1212", "type_hint": "contact"}, {"raw": "Acme", "type_hint": "entity"}]}'
    },
    {
        "role": "user",
        "content": "Extract all items from this text:\n\nWorking from home Thursday. Yoga at 5:30."
    },
    {
        "role": "assistant",
        "content": '{"items": [{"raw": "working from home Thursday", "type_hint": "setting"}, {"raw": "yoga at 5:30pm", "type_hint": "appointment"}]}'
    },
]

# ── Call 2: Classify ───────────────────────────────────────────────────────────

CLASSIFY_SYSTEM = """\
You are a classification engine. Given extracted items, assign each a node_type and fields.

node_type rules:
  cogs/daily        has a specific time, OR is WFH/ONSITE/HOLIDAY, OR is a one-off day action
  sprockets/task    persistent actionable item, no time anchor
  sprockets/contact a person
  sprockets/entity  org, place, or thing
  sprockets/note    reference or idea, no action

item_text formatting for cogs/daily:
  appointment → ALLCAPS name + time   e.g. "DENTIST 8am"  "YOGA 5:30p"
  setting     → ALLCAPS only          e.g. "WFH"  "ONSITE ACME"
  todo        → mixed case            e.g. "Pick up prescription at CVS"

Date resolution: use today's date from the user message.
"next Monday" when today is Tuesday means 6 days away, not yesterday.
Use confidence "low" when date or type is ambiguous.

Output format: {"nodes": [...]}
"""

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_type":  {"type": "string",
                                   "enum": ["cogs/daily", "sprockets/task",
                                            "sprockets/contact", "sprockets/entity",
                                            "sprockets/note"]},
                    "item_text":  {"type": "string"},
                    "title":      {"type": "string"},
                    "date":       {"type": "string"},
                    "status":     {"type": "string", "enum": ["active"]},
                    "confidence": {"type": "string", "enum": ["high", "low"]}
                },
                "required": ["node_type", "confidence"]
            }
        }
    },
    "required": ["nodes"]
}

CLASSIFY_EXAMPLES = [
    {
        "role": "user",
        "content": (
            "Today: 2026-04-21 (Tuesday)\n\n"
            "Extracted:\n"
            '[{"raw": "dentist appointment Monday at 8am", "type_hint": "appointment"}, '
            '{"raw": "pick up prescription at CVS", "type_hint": "task"}, '
            '{"raw": "Frank, phone 410-555-1212", "type_hint": "contact"}]\n\n'
            "Classify each item."
        )
    },
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            '{"node_type": "cogs/daily", "item_text": "DENTIST 8am", "date": "2026-04-27", "confidence": "high"}, '
            '{"node_type": "sprockets/task", "title": "Pick up prescription at CVS", "status": "active", "confidence": "high"}, '
            '{"node_type": "sprockets/contact", "title": "Frank", "confidence": "high"}'
            ']}'
        )
    },
    {
        "role": "user",
        "content": (
            "Today: 2026-04-21 (Tuesday)\n\n"
            "Extracted:\n"
            '[{"raw": "working from home Thursday", "type_hint": "setting"}, '
            '{"raw": "yoga at 5:30pm", "type_hint": "appointment"}]\n\n'
            "Classify each item."
        )
    },
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            '{"node_type": "cogs/daily", "item_text": "WFH", "date": "2026-04-23", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "item_text": "YOGA 5:30p", "date": "2026-04-21", "confidence": "high"}'
            ']}'
        )
    },
]
