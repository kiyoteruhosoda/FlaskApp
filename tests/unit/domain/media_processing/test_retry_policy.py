import pytest

from bounded_contexts.photonest.domain.media_processing import ThumbnailRetryPolicy


def test_decide_allows_retry_before_limit():
    policy = ThumbnailRetryPolicy(max_attempts=3)

    decision = policy.decide(1)

    assert decision.can_retry is True
    assert decision.attempt_number == 2
    assert decision.reason is None
    assert decision.keep_record is False


def test_decide_blocks_retry_at_limit():
    policy = ThumbnailRetryPolicy(max_attempts=2)

    decision = policy.decide(2)

    assert decision.can_retry is False
    assert decision.attempt_number == 2
    assert decision.reason == "max_attempts"
    assert decision.keep_record is True


def test_decide_validates_negative_attempts():
    policy = ThumbnailRetryPolicy(max_attempts=2)

    with pytest.raises(ValueError):
        policy.decide(-1)
