# Architecture

Agentic Eval Ops Kit is intentionally small, dependency-free, and export-friendly.

## Flow

```text
transcript / trace / workflow answer
        |
        v
scenario JSON
        |
        v
agentic_eval_ops.evaluator
        |
        v
scorecard: text / markdown / json
```

## Why Scenario JSON

Scenario JSON keeps the toolkit platform-neutral. A Vapi call transcript, OpenClaw trace, Hermes skill run, or AI video workflow answer can all be represented as events:

- `message`
- `tool_call`
- `tool_result`
- `action`
- `handoff`

That means the same scoring engine can review different agent systems without requiring API credentials.

## Check Types

Built-in checks:

- Required terms.
- Forbidden terms.
- Required tools.
- Forbidden tools.
- Required sequence.
- Expected fields.
- Domain defaults.
- Custom rubric checks.

Custom rubric kinds:

- `contains_all`
- `contains_any`
- `tool_any`

## Design Choices

- No API keys.
- No SDK dependency.
- No live calls.
- No scraping.
- No private browser storage.
- Public-safe synthetic examples.

The goal is to demonstrate evaluation judgment and workflow design, not to expose private client traces.
