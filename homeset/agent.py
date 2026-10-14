"""Model wiring (Strands + LiteLLM), the same setup as the Morning Briefing agent.

NOT YET RUN.  This module was written on 2026-10-13 without a live model call.  The
deterministic parts (labels, wger client, time calculator, output checks, harness) have
unit tests; this file is the first thing to run and fix tomorrow.

Strands and LiteLLM are imported inside build_agent so the rest of the package (and the
tests) work without them installed.
"""

from __future__ import annotations

import os

from .harness import Outcome, RequestState, handle_request, make_tools
from .prompt import SYSTEM_PROMPT

DEFAULT_MODEL_ID = "anthropic/claude-sonnet-5-5"  # set MODEL_ID in .env to override


def build_agent(state: RequestState, search_fn=None):
    """A Strands Agent whose two tools are bound to this request's state."""
    from dotenv import load_dotenv
    from strands import Agent, tool
    from strands.models.litellm import LiteLLMModel

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or "your-key-here" in api_key:
        raise SystemExit("ANTHROPIC_API_KEY is missing or still a placeholder in .env")

    search_impl, time_impl = make_tools(state) if search_fn is None else make_tools(state, search_fn)

    @tool
    def search_exercises(focus: str, equipment: list[str]) -> str:
        """Look up exercises in the wger exercise database (read-only).

        Args:
            focus: One FOCUS LABEL from the system prompt, for example "legs".
            equipment: EQUIPMENT LABELS from the system prompt, for example ["mat", "dumbbells"].

        Returns:
            JSON with "groups" (exercises grouped by muscle, each with name, equipment,
            muscles, and category) or an "error" the model must report.
        """
        return search_impl(focus, equipment)

    @tool
    def calculate_plan_time(exercises: list[dict]) -> str:
        """Add up the total minutes for a plan.  Use this instead of doing time math.

        Args:
            exercises: One item per exercise, each with "sets", "reps", and "rest_seconds".

        Returns:
            JSON with "total_minutes", or an "error".
        """
        return time_impl(exercises)

    model = LiteLLMModel(
        client_args={"api_key": api_key},
        model_id=os.getenv("MODEL_ID", DEFAULT_MODEL_ID),
        params={"max_tokens": 2048},
    )
    return Agent(
        model=model,
        tools=[search_exercises, calculate_plan_time],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None,
    )


def run_once(user_message: str, search_fn=None) -> Outcome:
    state = RequestState(user_message=user_message)
    agent = build_agent(state, search_fn)
    return handle_request(user_message, lambda text: str(agent(text)), state)


def run_conversation(turns: list[str], search_fn=None, agent_factory=build_agent) -> list[Outcome]:
    """One conversation with several user messages and one model history (multi-turn evals).

    The model keeps the whole conversation; the harness treats each message as its own
    request, so the 10-call cap and the output checks restart every turn.  `agent_factory`
    exists so tests can pass a scripted agent that needs no key.
    """
    state = RequestState(user_message=turns[0])
    agent = agent_factory(state, search_fn)
    outcomes = []
    for turn in turns:
        state.reset_for(turn)
        outcomes.append(handle_request(turn, lambda text: str(agent(text)), state))
    return outcomes
