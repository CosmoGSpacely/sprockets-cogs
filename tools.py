"""Tool definitions for the agentic loop. Stub — Stage 4 implements this."""
from datetime import datetime


def get_current_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_current_datetime() -> str:
    return datetime.now().isoformat()
