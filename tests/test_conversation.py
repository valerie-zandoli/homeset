"""Multi-turn runs without a model:  a scripted agent stands in for the real one."""

from homeset.agent import run_conversation
from homeset.checks import HANDOFF_SENTENCE
from homeset.harness import RequestState, extract_minutes


class ScriptedAgent:
    """Returns the next scripted reply and remembers every message it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def __call__(self, text):
        self.seen.append(text)
        return self.replies.pop(0)


def factory_for(agent):
    return lambda state, search_fn: agent


def test_each_turn_gets_its_own_outcome_from_one_agent():
    # No trigger word in either message, so code does not fire and the model decides each turn.
    agent = ScriptedAgent(["Is your lower back sore, or is it something else?", HANDOFF_SENTENCE])
    turns = ["My lower back feels a little off.  Legs please.", "It feels sharp when I bend.  Legs please."]
    outcomes = run_conversation(turns, agent_factory=factory_for(agent))
    assert [o.kind for o in outcomes] == ["question", "handoff"]
    assert agent.seen == turns  # the same agent saw both messages, in order


def test_state_restarts_each_turn_but_minutes_carry_over():
    state = RequestState("I have 20 minutes and a mat.  Legs.")
    state.tool_calls = 7
    state.known_exercises = {"Squat": [7]}
    state.budget_exceeded = True
    state.reset_for("Swap the first exercise.")
    assert state.tool_calls == 0 and state.known_exercises == {} and state.budget_exceeded is False
    assert state.requested_minutes == 20  # none stated in the follow-up, so keep the earlier time
    state.reset_for("Make it 30 minutes instead.")
    assert state.requested_minutes == extract_minutes("30 minutes") == 30
