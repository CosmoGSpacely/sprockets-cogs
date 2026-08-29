"""The capture pipeline, declared rather than inlined.

Stage 142 deliverable A1. `process_input` used to run thirteen post-classify
transformations as a hand-ordered wall of statements, and Stage 139 finding 34
established that nobody could say what the chain was without reading two
hundred lines. Here the chain is data: an ordered tuple of named steps that a
runner executes.

Three properties the inline version could not offer:

- **The order is inspectable.** `PIPELINE` is a list you can print. The drift
  guard reads it instead of parsing source.
- **Each step declares its scope.** A step is either `CAPTURE` - it decides
  something about the whole input and runs once - or `NODES` - it transforms a
  node list and is meaningful on any subset. That distinction is what the
  retry path needs and never had.
- **Each step declares purity.** Pure steps are functions of their inputs and
  the harness can run them; effectful ones write review packets or trace
  files. `capture_harness` used to hard-code its own copy of this split.

**This module changes no behaviour.** It is the same functions in the same
order with the same arguments. The score holding is the test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

Scope = Literal["capture", "nodes"]


@dataclass
class CaptureState:
    """Everything a pipeline step may read or replace.

    A single mutable state object rather than threaded arguments, because the
    thirteen steps take six different signatures between them and a uniform
    one is what makes the chain declarable at all.
    """

    content: str
    raw_nodes: list[dict]
    classified: list[dict]
    source_date: str
    session_id: str
    memory_parent: str | None = None

    terminated: bool = False
    """Set by a step that ends the capture early - today only the structural
    guard, which routes the whole input to review. The runner stops on it."""

    steps_run: list[str] = field(default_factory=list)
    """Which steps actually executed. Reported by the harness so a scored run
    can say what it applied instead of being trusted to have applied it."""


@dataclass(frozen=True)
class PipelineStep:
    name: str
    scope: Scope
    pure: bool
    run: Callable[[CaptureState], None]

    retry_note: str = ""
    """Why a `NODES` step does or does not re-run on retried nodes. Recorded
    per step because Stage 142 deliverable A2 found the retry path re-running
    three of thirteen with the omission documented nowhere."""


def run_pipeline(
    state: CaptureState,
    steps,
    *,
    only_scope: Scope | None = None,
) -> CaptureState:
    """Execute steps in order, stopping if one terminates the capture.

    `only_scope` selects a subset - the retry path passes "nodes" so that
    whole-capture decisions are not re-made on a handful of reclassified
    items.
    """

    for step in steps:
        if only_scope is not None and step.scope != only_scope:
            continue
        step.run(state)
        state.steps_run.append(step.name)
        if state.terminated:
            break
    return state


def retry_steps(steps):
    """The steps that re-run on reclassified nodes.

    Deliberately **not** every `NODES` step: see `RETRY_OMISSIONS`. This
    returns exactly what the inline retry path ran, so declaring the pipeline
    changes nothing. Widening it is a behaviour change and belongs to its own
    measured slice.
    """

    return tuple(step for step in steps if step.name in RETRY_INCLUDED)


#: What the inline retry path re-ran. Three of thirteen.
RETRY_INCLUDED = (
    "apply_runtime_date_context",
    "apply_bounded_recurrence_context",
    "apply_cogs_item_format",
)

#: Deliverable A2 required establishing whether the omission is deliberate.
#: It is not recorded anywhere, so it was reconstructed by reading the steps.
#: Three omissions are correct; seven are defects that this declaration makes
#: visible and a later slice must fix, because fixing them changes behaviour.
RETRY_OMISSIONS = {
    "route_structural_guard_to_review": (
        "CORRECT. A whole-capture decision that already ran and would have "
        "returned early. Re-deciding it on a retried subset is meaningless."
    ),
    "log_memory_parent_trace": (
        "CORRECT. Tracing for the capture, emitted once. Re-running would "
        "write a second trace for the same input."
    ),
    "write_memory_parent_trace": (
        "CORRECT. Same reason; it writes a file."
    ),
    "route_ordinary_entity_authority_to_review": (
        "DEFECT. Per-node review routing. A node that came back through retry "
        "is never checked for ordinary-entity authority."
    ),
    "route_recurrence_to_review": (
        "DEFECT. Per-node. A retried recurrence node skips the guard entirely."
    ),
    "apply_explicit_hierarchy_hints": (
        "DEFECT. A retried node never receives explicit hierarchy hints."
    ),
    "ensure_hierarchy_tasks": (
        "DEFECT. A retried node never gains its hierarchy task."
    ),
    "ensure_memory_hierarchy_tasks": (
        "DEFECT. Same, for the memory-derived parent."
    ),
    "apply_memory_parent_title": (
        "DEFECT. A retried node keeps no memory parent title."
    ),
    "ensure_cogs_companions": (
        "DEFECT. A retried task never gets its companion Cog, so it is "
        "invisible on the day it belongs to. Probably the most user-visible "
        "of the seven."
    ),
}
