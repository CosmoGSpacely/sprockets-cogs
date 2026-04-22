"""Pydantic node schemas. Stub — Stage 5 implements this."""
from pydantic import BaseModel


class NodeBase(BaseModel):
    node_type: str
    title: str


# Stage 5 expands each node type with full field sets
