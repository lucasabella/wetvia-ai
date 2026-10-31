"""Reciprocal-rank-fusion constants and pure scoring helper."""

RRF_K = 60


def reciprocal_rank_score(rank: int, *, k: int = RRF_K) -> float:
    """Return the RRF contribution for a one-based rank."""
    if rank <= 0:
        raise ValueError("RRF ranks are one-based positive integers")
    if k < 0:
        raise ValueError("RRF k must be non-negative")
    return 1.0 / (k + rank)


__all__ = ["RRF_K", "reciprocal_rank_score"]
