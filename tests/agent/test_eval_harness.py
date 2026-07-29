from app.agent.eval.harness import evaluate_routing_cases, load_golden_questions


def test_golden_routing_eval_passes():
    cases = load_golden_questions()
    report = evaluate_routing_cases(cases)
    assert report["failed"] == 0
    assert report["pass_rate"] == 1.0
