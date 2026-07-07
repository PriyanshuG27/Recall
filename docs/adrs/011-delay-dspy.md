# ADR 011: Delay DSPy

## Context
Prompts in the AI Cascade are currently manually written Jinja templates. DSPy offers mathematical, compiled prompt optimization.

## Decision
Delay the adoption of DSPy.

## Consequences
*   Prompts remain readable and manually tunable.
*   We may leave some LLM accuracy on the table by not auto-optimizing the prompts.

## Alternatives
*   **Adopt DSPy now:** Replace manual templates with compiled teleprompters.

## Tradeoffs
DSPy requires massive, high-quality evaluation datasets to compile effective prompts. We do not yet have these datasets. Adopting it now would be premature optimization resulting in opaque, hard-to-debug code.

## Future review trigger
Once the `Promptfoo` CI/CD evaluation test suites contain >1,000 highly curated Q&A pairs.
