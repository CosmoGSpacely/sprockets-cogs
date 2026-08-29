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
    """The capture's memory-derived parent title.

    Computed once by `log_memory_parent_trace`, which is `capture`-scoped and
    so does not re-run on retry. The retry state inherits the value rather
    than recomputing it: retried nodes belong to the same capture, and a
    second RUDI retrieval could return something different for no reason.
    """

    memory_trace: object | None = None
    """Trace record passed from the logging step to the writing step."""

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
    """The steps that re-run on reclassified nodes: every `nodes`-scoped one.

    Slice 2b. The inline retry path re-ran three of thirteen, and slice 2
    reconstructed why - three omissions correct, seven defects. The fix is not
    a new list but the scope distinction the declaration already carries: a
    `nodes` step transforms a node list and is meaningful on any subset, so it
    belongs in retry; a `capture` step decides something about the whole input
    and must not be re-decided on a handful of reclassified items.

    The three correct omissions fall out automatically - all three are
    `capture`-scoped. That they do is the evidence that the scope field is
    carrying a real distinction rather than restating a hand-written list.
    """

    return tuple(step for step in steps if step.scope == "nodes")


#: Steps deliberately absent from retry, and why. After slice 2b these are
#: exactly the `capture`-scoped steps; there is no longer a hand-maintained
#: inclusion list to drift from the declaration.
RETRY_OMISSIONS = {
    "route_structural_guard_to_review": (
        "CORRECT. A whole-capture decision that already ran and would have "
        "returned early. Re-deciding it on a retried subset is meaningless."
    ),
    "log_memory_parent_trace": (
        "CORRECT. Tracing for the capture, emitted once. Re-running would "
        "write a second trace for the same input. The `memory_parent` it "
        "computes is carried into the retry state instead of recomputed."
    ),
    "write_memory_parent_trace": (
        "CORRECT. Same reason; it writes a file."
    ),
}

#: The seven defects slice 2b fixed, kept so the history is not lost when the
#: omission list shrinks to three. Each was a per-node step that a retried
#: node silently never received.
RETRY_DEFECTS_FIXED = {
    "route_ordinary_entity_authority_to_review":
        "a retried node was never checked for ordinary-entity authority",
    "route_recurrence_to_review":
        "a retried recurrence node skipped the guard entirely",
    "apply_explicit_hierarchy_hints":
        "a retried node never received explicit hierarchy hints",
    "ensure_hierarchy_tasks":
        "a retried node never gained its hierarchy task",
    "ensure_memory_hierarchy_tasks":
        "same, for the memory-derived parent",
    "apply_memory_parent_title":
        "a retried node kept no memory parent title",
    "ensure_cogs_companions":
        "a retried task never got its companion Cog, so it never appeared on "
        "the day it belonged to - the most user-visible of the seven",
}
