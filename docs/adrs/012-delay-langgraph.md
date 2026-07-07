# ADR 012: Delay LangGraph

## Context
Agentic workflows (agents interacting in loops to solve problems) are becoming popular. LangGraph provides state machines for LLMs.

## Decision
Delay LangGraph. Enforce the strict, linear AI Cascade Orchestrator.

## Consequences
*   Recall's background tasks remain highly predictable and deterministic.
*   We cannot easily deploy autonomous agents that "browse the web" indefinitely.

## Alternatives
*   **LangGraph / CrewAI:** Fun, highly autonomous, but hallucination-prone.

## Tradeoffs
We trade unbounded autonomous capabilities for strict reliability, bounded cloud costs, and predictable user experiences.

## Future review trigger
If the product vision pivots from a "Personal Knowledge OS" to an "Autonomous Personal Assistant" requiring multi-step, days-long cyclic reasoning loops.
