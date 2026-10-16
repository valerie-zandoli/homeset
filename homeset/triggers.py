"""Hard safety triggers, checked by code before the model is called.

PRD 3b says the hand-off fires on "pain, an injury, surgery, pregnancy, or a medical
condition".  That rule used to live only in the prompt (step 1), so the most important
rule in the design depended on the model's judgment.  Code now checks the user's words for
the clear cases and returns the exact hand-off sentence without calling the model.  Vague
wording ("my lower back feels a little off") gets one fixed clarifying question from code too
(find_vague, messages.VAGUE_QUESTION; Yadan's decision of 2026-10-15:  a question, not a
hand-off).  The prompt's step 1 stays as the second layer for wording that neither list knows.

Errs toward the hand-off:  a false hand-off costs the user a plan; a missed trigger can cost
them an injury.  A trigger word that the user negates ("no pain", "pain free", "I do not have
any injuries") does not fire.  The whole conversation is checked, so a clearance claim in a
later turn does not undo an earlier mention.

Add a word here only with a test in tests/test_triggers.py, including a control that must not
fire.  This module has no model or network code.
"""

from __future__ import annotations

import re

# One word that names pain, an injury, surgery, pregnancy, or a medical condition.
_WORDS = {
    # pain
    "pain", "pains", "painful", "hurt", "hurts", "hurting", "agony",
    # injury
    "injury", "injuries", "injured", "sprain", "sprains", "sprained", "strain", "strained",
    "fracture", "fractured", "dislocated", "concussion", "herniated", "sciatica", "tendonitis",
    "tendinitis", "whiplash", "torn",
    # surgery
    "surgery", "surgeries", "surgical", "postop", "operated",
    # pregnancy
    "pregnant", "pregnancy", "postpartum",
    # medical conditions
    "diagnosed", "diagnosis", "chronic", "arthritis", "diabetes", "diabetic", "asthma",
    "hypertension", "cancer", "epilepsy", "osteoporosis", "scoliosis", "fibromyalgia",
}

# Phrases that name the same things in more than one word.
_PHRASES = (
    "medical condition", "medical conditions", "pulled a muscle", "pulled muscle", "slipped disc",
    "heart condition", "heart disease", "blood pressure", "post surgery", "post op",
    "c section", "knee replacement", "hip replacement", "joint replacement", "broken bone",
    "broken bones", "broken leg", "broken arm", "broken ankle", "broken wrist", "broken rib",
    "broken collarbone", "rotator cuff",
)

_NEGATORS = {
    "no", "not", "without", "never", "zero", "nor", "free", "none", "dont", "don't", "doesnt",
    "doesn't", "havent", "haven't", "hasnt", "hasn't", "isnt", "isn't", "wasnt", "wasn't",
    "arent", "aren't",
}


def _tokens(text: str) -> list[str]:
    lowered = text.lower().replace("’", "'").replace("-", " ")
    return re.sub(r"[^a-z0-9' ]", " ", lowered).split()


def _negated(tokens: list[str], start: int, end: int) -> bool:
    """True when a negator sits in the 3 words before the match, or "free" follows it."""
    before = tokens[max(0, start - 3):start]
    after = tokens[end:end + 1]
    return any(t in _NEGATORS for t in before) or after == ["free"]


# Vague wording that might be a symptom:  not a clear trigger, so code asks one fixed question
# (messages.VAGUE_QUESTION) instead of handing off.  "sore" and "tired" are left out on
# purpose:  ordinary soreness still reaches the model, as before.
_VAGUE_WORDS = {
    "twinge", "twinges", "niggle", "niggles", "niggling", "nagging", "tweaky", "tender",
    "achy", "ache", "aches", "aching", "discomfort",
}
_VAGUE_PHRASES = (
    "bothering me", "bothers me", "bothered me", "something is off", "something is wrong",
    "something isnt right", "something is not right", "something is not quite right",
)
_FEEL = {"feel", "feels", "feeling", "felt"}
_ODD = {"off", "odd", "weird", "strange", "funny", "wrong", "iffy", "tweaky", "janky"}
_FILLERS = {
    "a", "little", "bit", "kind", "of", "sort", "slightly", "somewhat", "just", "really", "pretty",
    "quite", "very", "rather", "fairly", "still", "again",
}


def _vague_from_feel(tokens: list[str]) -> str | None:
    """"feels off", "feeling a bit funny", "does not feel right":  a feel word, up to three
    fillers, then an odd word.  A negated odd word ("does not feel off") stays quiet; a negated
    "right" ("does not feel right") is the symptom."""
    for i, token in enumerate(tokens):
        if token not in _FEEL:
            continue
        j = i + 1
        while j < len(tokens) and j - i <= 3 and tokens[j] in _FILLERS:
            j += 1
        if j >= len(tokens):
            continue
        near_negator = any(t in _NEGATORS for t in tokens[max(0, i - 3):i])
        if tokens[j] in _ODD and not near_negator:
            return f"{token} {tokens[j]}"
        if tokens[j] == "right" and any(t in _NEGATORS for t in tokens[max(0, i - 2):i]):
            return f"not {token} right"
    return None


def find_vague(text: str) -> str | None:
    """The first vague symptom wording the user did not negate, or None.

    Checked on the latest message only, after find_trigger found nothing.  Errs toward a
    question:  a false question costs the user one more message; a missed one lets a plan
    through for a body that may be injured.
    """
    tokens = _tokens(text)
    for i, token in enumerate(tokens):
        if token in _VAGUE_WORDS and not _negated(tokens, i, i + 1):
            return token
    for phrase in _VAGUE_PHRASES:
        parts = phrase.split()
        for i in range(len(tokens) - len(parts) + 1):
            if tokens[i:i + len(parts)] == parts:
                own_negation = "not" in parts or "isnt" in parts
                if own_negation or not _negated(tokens, i, i + len(parts)):
                    return phrase
    return _vague_from_feel(tokens)


def find_trigger(text: str) -> str | None:
    """The first trigger word or phrase the user did not negate, or None."""
    tokens = _tokens(text)
    for i, token in enumerate(tokens):
        if token in _WORDS:
            if token == "torn" and tokens[i + 1:i + 2] == ["between"]:
                continue  # "torn between legs and arms"
            if not _negated(tokens, i, i + 1):
                return token
    for phrase in _PHRASES:
        parts = phrase.split()
        for i in range(len(tokens) - len(parts) + 1):
            if tokens[i:i + len(parts)] == parts and not _negated(tokens, i, i + len(parts)):
                return phrase
    return None
