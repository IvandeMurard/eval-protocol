"""eval-protocol: tiered acceptance criteria, frozen baselines and a canary rule for LLM evaluation."""
from .tiers import (  # noqa: F401
    DEFAULT_PROTOCOL,
    ERROR,
    FAIL,
    PASS,
    WARN,
    Check,
    Protocol,
    Results,
    Tier,
    Verdict,
    evaluate,
    load_protocol,
    load_results,
)

__version__ = "0.1.0"
