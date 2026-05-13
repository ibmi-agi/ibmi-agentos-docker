"""Learning infrastructure (Agno-backed) for IBM i agents.

Single entry point: :func:`get_learning`. Pass it as ``learning=`` to an
:class:`agno.agent.Agent` to enable Agno's extraction pipeline — user
profile, user memory, session context, and entity memory are persisted
to Postgres at the end of each turn.

Defaults are intentionally generic:
    * ``enable_learned_knowledge=False`` — no shipped knowledge base
    * ``enable_decision_log=False`` — opt in only when you want it
    * Fixed namespace ``"default"`` — override via the
      ``LEARNING_NAMESPACE`` env var if you want multi-tenant isolation

Custom schemas, per-store mode overrides, and an explicit extraction
model live on :class:`LearningConfig`.
"""

from learning.factory import DEFAULT_CONFIG, LearningConfig, get_learning

__all__ = [
    "DEFAULT_CONFIG",
    "LearningConfig",
    "get_learning",
]
