# ADR 004: Reject LangChain

## Context
LangChain is the industry-standard framework for building LLM applications, offering thousands of pre-built prompts, tools, and chains.

## Decision
Reject LangChain entirely from the core AI execution paths.

## Consequences
*   We must build our own prompt templating, retry logic, and tool-calling wrappers.
*   The codebase remains lean, deterministic, and highly debuggable.

## Alternatives
*   **Adopt LangChain:** Faster initial prototyping.

## Tradeoffs
We trade developmental speed (which LangChain provides) for long-term maintainability. LangChain's abstractions are notoriously leaky, making deep debugging of production RAG errors nearly impossible.

## Future review trigger
Never. We own our state and orchestration.
