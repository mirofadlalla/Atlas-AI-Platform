from app.agent.utils.circuit_breaker import CircuitBreaker


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker("test", failure_threshold=2, recovery_timeout_seconds=60)

    def fail():
        raise ConnectionError("down")

    for _ in range(2):
        try:
            breaker.call(fail)
        except ConnectionError:
            pass

    try:
        breaker.call(fail)
        assert False, "expected circuit open"
    except RuntimeError as exc:
        assert "open" in str(exc).lower()


def test_circuit_breaker_resets_on_success():
    breaker = CircuitBreaker("test2", failure_threshold=3, recovery_timeout_seconds=60)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("retry")
        return "ok"

    try:
        breaker.call(flaky)
    except TimeoutError:
        pass
    assert breaker.call(flaky) == "ok"
