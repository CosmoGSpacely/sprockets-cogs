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

Multi-day settings: if a setting spans multiple days ("all week", "Mon-Fri"),
extract one item per day using the workdays list in the message. Embed the date
in the raw field: e.g. {"raw": "WFH 2026-04-20", "type_hint": "setting"}.

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
    {
        "role": "user",
        "content": (
            "This week's workdays: Mon 2026-04-21  Tue 2026-04-22  Wed 2026-04-23  Thu 2026-04-24  Fri 2026-04-25\n\n"
            "Extract all items from this text:\n\nWorking from home all week. Team standup Tuesday at 9am."
        )
    },
    {
        "role": "assistant",
        "content": '{"items": [{"raw": "WFH 2026-04-21", "type_hint": "setting"}, {"raw": "WFH 2026-04-22", "type_hint": "setting"}, {"raw": "WFH 2026-04-23", "type_hint": "setting"}, {"raw": "WFH 2026-04-24", "type_hint": "setting"}, {"raw": "WFH 2026-04-25", "type_hint": "setting"}, {"raw": "team standup Tuesday at 9am", "type_hint": "appointment"}]}'
    },
    {
        "role": "user",
        "content": "Extract all items from this text:\n\nIdea: use Dataview to build a task dashboard that filters Sprockets tasks by status and area. Could replace the manual weekly review."
    },
    {
        "role": "assistant",
        "content": '{"items": [{"raw": "use Dataview to build a task dashboard that filters Sprockets tasks by status and area — could replace the manual weekly review", "type_hint": "note"}]}'
    },
    {
        "role": "user",
        "content": "Extract all items from this text:\n\nMet Alice Nguyen from Pinnacle Labs today. Her email is alice@pinnacle.io. She wants a proposal by next Friday."
    },
    {
        "role": "assistant",
        "content": '{"items": ['
                    '{"raw": "met Alice Nguyen from Pinnacle Labs today", "type_hint": "appointment"}, '
                    '{"raw": "Alice Nguyen, email alice@pinnacle.io", "type_hint": "contact"}, '
                    '{"raw": "Pinnacle Labs", "type_hint": "entity"}, '
                    '{"raw": "send proposal to Alice Nguyen (Pinnacle Labs) by next Friday", "type_hint": "task"}]}'
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

Tasks:
  Named person or ongoing effort → TWO nodes: sprockets/task + cogs/daily (mixed case).
  Simple errand, no named person  → cogs/daily only (mixed case).
  For both: use the mentioned day if given, otherwise today's date.

Multi-day settings: a setting that spans multiple days ("all week", "Mon–Fri") yields one
cogs/daily per workday. "WFH all week" → five WFH nodes, one per workday Mon–Fri of the
current week.

Date resolution: use today's date from the user message.
"next Monday" when today is Tuesday means 6 days away, not yesterday.
Use confidence "low" when date or type is ambiguous.

Output at least one node per input item. Never silently drop an item.

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
                    "item_text":  {"type": "string", "minLength": 1},
                    "title":      {"type": "string", "minLength": 1},
                    "date":       {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                    "status":     {"type": "string", "enum": ["active"]},
                    "confidence": {"type": "string", "enum": ["high", "low"]}
                },
                "required": ["node_type", "confidence", "title", "item_text", "date"]
            }
        }
    },
    "required": ["nodes"]
}

CLASSIFY_EXAMPLES = [
    # ── Example 1: appointment + errand + contact ──────────────────────────────
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
            '{"node_type": "cogs/daily", "title": "DENTIST 8am", "item_text": "DENTIST 8am", "date": "2026-04-27", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "Pick up prescription at CVS", "item_text": "Pick up prescription at CVS", "date": "2026-04-27", "confidence": "high"}, '
            '{"node_type": "sprockets/contact", "title": "Frank", "item_text": "Frank, phone 410-555-1212", "date": "2026-04-21", "confidence": "high"}'
            ']}'
        )
    },
    # ── Example 4: multi-day setting → one cogs/daily per workday ─────────────────
    {
        "role": "user",
        "content": (
            "Today: 2026-04-22 (Wednesday)\n\n"
            "Extracted:\n"
            '[{"raw": "working from home all week", "type_hint": "setting"}]\n\n'
            "Classify each item."
        )
    },
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-20", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-21", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-22", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-23", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "WFH", "item_text": "WFH", "date": "2026-04-24", "confidence": "high"}'
            ']}'
        )
    },
    # ── Example 5: simple errand → cogs/daily ONLY (no sprockets/task) ──────────────
    {
        "role": "user",
        "content": (
            "Today: 2026-04-22 (Wednesday)\n\n"
            "Extracted:\n"
            '[{"raw": "buy milk", "type_hint": "task"}]\n\n'
            "Classify each item."
        )
    },
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            '{"node_type": "cogs/daily", "title": "Buy milk", "item_text": "Buy milk", "date": "2026-04-22", "confidence": "high"}'
            ']}'
        )
    },
    # ── Example 6: idea/reference → sprockets/note only ───────────────────────
    {
        "role": "user",
        "content": (
            "Today: 2026-04-22 (Wednesday)\n\n"
            "Extracted:\n"
            '[{"raw": "use Dataview to build a task dashboard that filters Sprockets tasks by status and area — could replace the manual weekly review", "type_hint": "note"}]\n\n'
            "Classify each item."
        )
    },
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            '{"node_type": "sprockets/note", "title": "Dataview task dashboard", "item_text": "use Dataview to build a task dashboard that filters Sprockets tasks by status and area", "date": "2026-04-22", "confidence": "high"}'
            ']}'
        )
    },
    # ── Example 7: named-contact proposal → dual node + contact + entity ────────────
    {
        "role": "user",
        "content": (
            "Today: 2026-04-23 (Thursday)\n\n"
            "Extracted:\n"
            '[{"raw": "met Alice Nguyen from Pinnacle Labs today", "type_hint": "appointment"}, '
            '{"raw": "Alice Nguyen, email alice@pinnacle.io", "type_hint": "contact"}, '
            '{"raw": "Pinnacle Labs", "type_hint": "entity"}, '
            '{"raw": "send proposal to Alice Nguyen (Pinnacle Labs) by next Friday", "type_hint": "task"}]\n\n'
            "Classify each item."
        )
    },
    {
        "role": "assistant",
        "content": (
            '{"nodes": ['
            '{"node_type": "cogs/daily", "title": "Met Alice Nguyen (Pinnacle Labs)", "item_text": "Met Alice Nguyen (Pinnacle Labs)", "date": "2026-04-23", "confidence": "high"}, '
            '{"node_type": "sprockets/contact", "title": "Alice Nguyen", "item_text": "Alice Nguyen, email alice@pinnacle.io", "date": "2026-04-23", "confidence": "high"}, '
            '{"node_type": "sprockets/entity", "title": "Pinnacle Labs", "item_text": "Pinnacle Labs", "date": "2026-04-23", "confidence": "high"}, '
            '{"node_type": "sprockets/task", "title": "Send proposal to Alice Nguyen (Pinnacle Labs)", "item_text": "Send proposal to Alice Nguyen (Pinnacle Labs)", "date": "2026-04-25", "status": "active", "confidence": "high"}, '
            '{"node_type": "cogs/daily", "title": "Proposal for Alice (Pinnacle Labs)", "item_text": "Proposal for Alice (Pinnacle Labs)", "date": "2026-04-25", "confidence": "high"}'
            ']}'
        )
    },
]
