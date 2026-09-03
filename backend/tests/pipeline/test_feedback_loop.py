"""Counterexample feedback loop: Stage 5 refutations flow back into Stage 3's next
round, without disturbing the cacheable static prompt prefix."""

import json
from unittest.mock import MagicMock

from app.pipeline.stage3_hypotheses.generator import generate_hypotheses
from app.pipeline.stage3_hypotheses.prompt import build_user_prompt
from app.pipeline.stage5_solver.schema import Verdict
from app.pipeline.stage5_solver.solver import prove_all, refutation_summary
from tests.pipeline.solver_fixtures import BOLA, INVARIANTS, MODEL, SAME_ACTOR


def _client_returning(hypotheses: list[dict[str, object]]) -> MagicMock:
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps({"hypotheses": hypotheses})
    response = MagicMock()
    response.choices[0].message.tool_calls = [tool_call]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def test_feedback_is_appended_after_the_byte_identical_static_prefix() -> None:
    base = build_user_prompt(MODEL, INVARIANTS)
    with_feedback = build_user_prompt(MODEL, INVARIANTS, refuted=["[unsat] order: x. Reason: y"])
    assert with_feedback.startswith(base)
    assert "CANNOT violate" in with_feedback
    assert "- [unsat] order: x. Reason: y" in with_feedback
    assert build_user_prompt(MODEL, INVARIANTS, refuted=[]) == base


def test_generate_hypotheses_forwards_refutations_into_the_user_message() -> None:
    client = _client_returning([BOLA.model_dump(mode="json")])
    result = generate_hypotheses(MODEL, INVARIANTS, client=client, refuted=["[unsat] order: z"])
    assert result == [BOLA]
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert "[unsat] order: z" in messages[1]["content"]


def test_two_round_loop_refutes_then_proves() -> None:
    # Round 1: the LLM proposes a same-actor chain — Z3 refutes it.
    round1 = [SAME_ACTOR]
    results = prove_all(MODEL, round1, INVARIANTS)
    assert [r.verdict for r in results] == [Verdict.UNSAT]

    # Round 2: the refutation goes back in; the LLM (mocked) proposes a real BOLA.
    feedback = [refutation_summary(h, r) for h, r in zip(round1, results, strict=True)]
    client = _client_returning([BOLA.model_dump(mode="json")])
    round2 = generate_hypotheses(MODEL, INVARIANTS, client=client, refuted=feedback)
    sent = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "victim POST /orders -> victim GET /orders/{order_id}" in sent
    assert "owned by victim" in sent  # the *reason*, not just the chain, reaches the model

    results += prove_all(MODEL, round2, INVARIANTS, index_offset=len(round1))
    assert [(r.hypothesis_index, r.verdict) for r in results] == [
        (0, Verdict.UNSAT),
        (1, Verdict.SAT),
    ]
