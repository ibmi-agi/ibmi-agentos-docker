"""
Factory for the agent LearningMachine.

One configuration, one factory, one call site per agent. Pass the
result of :func:`get_learning` as ``learning=`` to an
:class:`agno.agent.Agent`.

Extension points:
    * :class:`LearningConfig` fields — custom schemas, per-store modes,
      extra instructions
    * :data:`DEFAULT_CONFIG` — shared default used by every agent
    * :func:`resolve_namespace` — scoping strategy (env-driven by default)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from os import getenv
from typing import Any

from agno.learn import (
    DecisionLogConfig,
    EntityMemoryConfig,
    LearnedKnowledgeConfig,
    LearningMachine,
    LearningMode,
    SessionContextConfig,
    UserMemoryConfig,
    UserProfileConfig,
)

from db.session import get_postgres_db


@dataclass(frozen=True)
class LearningConfig:
    """Declarative config for the LearningMachine.

    Per-agent specialization is possible via
    ``get_learning(LearningConfig(...))`` but should be rare — change a
    field here to change behavior for every agent.
    """

    mode: LearningMode = LearningMode.AGENTIC

    # Schemas — None means "use Agno's generic shape". Override per store
    # with a dataclass when extraction quality needs a domain-specific shape.
    user_profile_schema: type | None = None
    user_memory_schema: type | None = None
    entity_memory_schema: type | None = None
    session_context_schema: type | None = None

    # Per-store mode override
    user_profile_mode: LearningMode | None = None
    user_memory_mode: LearningMode | None = None
    entity_memory_mode: LearningMode | None = None
    session_context_mode: LearningMode | None = None
    decision_log_mode: LearningMode | None = None
    learned_knowledge_mode: LearningMode | None = LearningMode.AGENTIC

    # Per-store enable flags. Disabled stores never register on the
    # LearningMachine, so they never fire an extraction LLM call.
    enable_user_profile: bool = True
    enable_user_memory: bool = True
    enable_session_context: bool = True
    enable_entity_memory: bool = True
    # OFF by default — no shipped knowledge base in the template. Flip on
    # only after wiring a ``Knowledge`` instance via ``db.create_knowledge``
    # and passing it into ``get_learning(..., knowledge=...)``.
    enable_learned_knowledge: bool = False
    # OFF by default — opt in when you want explicit decision capture.
    enable_decision_log: bool = False

    # Model used by every enabled store for extraction. When None, each
    # store falls back to the agent's primary model. Set to a cheaper
    # model (e.g. Haiku) to cut the critical-path extraction cost.
    learning_model: Any = None

    # Optional per-store additional_instructions, keyed by store name:
    #   "user_profile" | "user_memory" | "session_context" |
    #   "entity_memory" | "learned_knowledge" | "decision_log"
    extra_instructions: Mapping[str, str] = field(default_factory=dict)


DEFAULT_CONFIG = LearningConfig(
    # Multi-turn troubleshooting flows benefit from accumulated
    # entity/session memory — keep both on the hot path. Other stores
    # run AGENTIC (the model decides whether to extract) so the
    # blocking tail is small.
    entity_memory_mode=LearningMode.ALWAYS,
    session_context_mode=LearningMode.ALWAYS,
)


def resolve_namespace() -> str:
    """Scoping strategy for learning records.

    Single value across every agent so cross-agent recall works
    automatically. Override with ``LEARNING_NAMESPACE`` for multi-tenant
    isolation (e.g., one namespace per IBM i system).
    """
    return getenv("LEARNING_NAMESPACE", "default")


def get_learning(
    config: LearningConfig = DEFAULT_CONFIG,
    *,
    knowledge: Any = None,
) -> LearningMachine:
    """Return a shared LearningMachine for an agent.

    Pass ``knowledge=`` to enable the ``learned_knowledge`` store —
    typically an :class:`agno.knowledge.Knowledge` built via
    ``db.create_knowledge``. Without it, ``enable_learned_knowledge``
    is forced off.
    """
    ns = resolve_namespace()
    ei = config.extra_instructions
    model = config.learning_model

    user_profile: Any = False
    if config.enable_user_profile:
        user_profile = UserProfileConfig(
            mode=config.user_profile_mode or config.mode,
            schema=config.user_profile_schema,
            additional_instructions=ei.get("user_profile"),
            model=model,
        )

    user_memory: Any = False
    if config.enable_user_memory:
        user_memory = UserMemoryConfig(
            mode=config.user_memory_mode or config.mode,
            schema=config.user_memory_schema,
            additional_instructions=ei.get("user_memory"),
            model=model,
        )

    session_context: Any = False
    if config.enable_session_context:
        session_context = SessionContextConfig(
            mode=config.session_context_mode or config.mode,
            schema=config.session_context_schema,
            additional_instructions=ei.get("session_context"),
            model=model,
        )

    entity_memory: Any = False
    if config.enable_entity_memory:
        entity_memory = EntityMemoryConfig(
            mode=config.entity_memory_mode or config.mode,
            schema=config.entity_memory_schema,
            namespace=ns,
            additional_instructions=ei.get("entity_memory"),
            model=model,
        )

    learned_knowledge: Any = False
    if config.enable_learned_knowledge and knowledge is not None:
        learned_knowledge = LearnedKnowledgeConfig(
            mode=config.learned_knowledge_mode or config.mode,
            namespace=ns,
            additional_instructions=ei.get("learned_knowledge"),
            model=model,
        )

    decision_log: Any = False
    if config.enable_decision_log:
        decision_log = DecisionLogConfig(
            mode=config.decision_log_mode or config.mode,
            additional_instructions=ei.get("decision_log"),
            model=model,
        )

    return LearningMachine(
        db=get_postgres_db(),
        knowledge=knowledge,
        namespace=ns,
        user_profile=user_profile,
        user_memory=user_memory,
        session_context=session_context,
        entity_memory=entity_memory,
        learned_knowledge=learned_knowledge,
        decision_log=decision_log,
    )
