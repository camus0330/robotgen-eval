"""Offline synchronous agent lifecycle; no I/O, providers or scoring."""

from dataclasses import dataclass
import time
from typing import Callable, Protocol, Sequence


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict

    def __post_init__(self):
        if not isinstance(self.arguments, dict):
            raise TypeError("arguments must be a dict")


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    ok: bool
    content: object


@dataclass(frozen=True)
class ModelReply:
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    final: bool = False


@dataclass(frozen=True)
class RunEvent:
    kind: str
    data: object = None


@dataclass(frozen=True)
class RunResult:
    status: str
    termination_reason: str
    events: tuple[RunEvent, ...]
    model_turns: int


class ModelError(Exception):
    """A model call failed; this round does not retry it."""


class Model(Protocol):
    def respond(self, history: tuple[RunEvent, ...]) -> ModelReply: ...


class MockModel:
    """Return scripted replies in order and retain received histories."""

    def __init__(self, replies: Sequence[ModelReply]):
        self.replies = tuple(replies)
        self.histories: list[tuple[RunEvent, ...]] = []

    def respond(self, history):
        index = len(self.histories)
        self.histories.append(tuple(history))
        if index >= len(self.replies):
            raise ModelError("mock replies exhausted")
        return self.replies[index]


class MockToolHandler:
    """Synthetic echo/failure behaviours, never real tool execution."""

    def __call__(self, call: ToolCall) -> ToolResult:
        if call.name == "echo":
            return ToolResult(call.call_id, True, dict(call.arguments))
        if call.name == "forced_failure":
            return ToolResult(call.call_id, False, "forced_failure")
        return ToolResult(call.call_id, False, "unknown_tool")


def _valid_reply(reply):
    return (
        isinstance(reply, ModelReply)
        and isinstance(reply.content, str)
        and type(reply.final) is bool
        and isinstance(reply.tool_calls, (tuple, list))
        and (not reply.tool_calls if reply.final else bool(reply.tool_calls))
        and all(isinstance(call, ToolCall) and isinstance(call.arguments, dict)
                for call in reply.tool_calls)
    )


def run_agent(
    model: Model,
    tool_handler: Callable[[ToolCall], ToolResult],
    max_model_turns: int,
    wall_time_s: float,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    """One respond() invocation counts as one turn, including ModelError.

    History is the event sequence through the current MODEL_REQUEST. Tools run
    sequentially, including those from the last permitted model turn. Limits
    are nonnegative; zero permits no work. Timeout takes precedence at checked
    boundaries. Synchronous calls cannot be preempted: overruns are detected
    when they return, before any further work or successful termination.
    """
    if type(max_model_turns) is not int or max_model_turns < 0:
        raise ValueError("max_model_turns must be a nonnegative integer")
    if type(wall_time_s) not in (int, float) or not 0 <= wall_time_s < float("inf"):
        raise ValueError("wall_time_s must be a finite nonnegative number")

    events = []
    model_turns = 0
    started = clock()

    def expired():
        return clock() - started >= wall_time_s

    def finish(status, reason):
        events.append(RunEvent("TERMINATION", reason))
        return RunResult(status, reason, tuple(events), model_turns)

    while True:
        if expired():
            return finish("TIMEOUT", "wall_time_exceeded")
        if model_turns >= max_model_turns:
            return finish("GENERATION_FAILED", "model_turn_limit")

        model_turns += 1
        events.append(RunEvent("MODEL_REQUEST", model_turns))
        try:
            reply = model.respond(tuple(events))
        except ModelError:
            if expired():
                return finish("TIMEOUT", "wall_time_exceeded")
            return finish("GENERATION_FAILED", "model_error")
        events.append(RunEvent("MODEL_RESPONSE", reply))
        if expired():
            return finish("TIMEOUT", "wall_time_exceeded")
        if not _valid_reply(reply):
            return finish("GENERATION_FAILED", "invalid_model_reply")
        if reply.final:
            return finish("COMPLETED", "final")

        for call in reply.tool_calls:
            if expired():
                return finish("TIMEOUT", "wall_time_exceeded")
            events.append(RunEvent("TOOL_CALL", call))
            try:
                result = tool_handler(call)
            except Exception:
                # Fixed diagnostic: no exception payload or traceback in history.
                result = ToolResult(call.call_id, False, "tool_exception")
            if (not isinstance(result, ToolResult) or type(result.ok) is not bool
                    or result.call_id != call.call_id):
                result = ToolResult(call.call_id, False, "invalid_tool_result")
            events.append(RunEvent("TOOL_RESULT", result))
            if expired():
                return finish("TIMEOUT", "wall_time_exceeded")
