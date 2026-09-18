# Durable synthetic workflow

The workflow adds executable case processing alongside the existing text-based rubric evaluator. It is new synthetic portfolio work, not a client system, live provider test or historical employment evidence.

```
requested → context_retrieved → proposed → validated
  → awaiting_approval → approved → executed → completed
```

A request that does not require approval moves from validated to approved. Every step before a committed effect has a job deadline. Once execution commits, report completion remains recoverable after that deadline; reporting a committed effect as a failed job would invite an unsafe retry. Invalid or unavailable context/tool output retries the same step at most three times by default (configurable from one to ten), then fails. Calling `advance` is an explicit retry; there is no hidden scheduler or backoff claim. Successful steps reset the per-step attempt counter. Expired approval returns to awaiting approval. The overall deadline still applies.

`Workflow(database, tenant)` is a trusted application-side handle. A real service must authenticate the principal and choose this tenant before invoking the API. Passing an arbitrary tenant string is not authentication. SQL reads, reports and effects scope data to that handle; cross-tenant job/memory access is denied. Versioned memory is immutable and carries an explicit synthetic source URI. Requests pin a version, so later versions do not silently change an action.

`request` accepts a request key, case ID, memory key/version, boolean approval requirement, bounded attempts and finite timeout. `advance(..., tool_output=...)` accepts only the documented action shape: `kind=case_note`, tenant, case ID, body, source, memory version. Extra fields, wrong types, mismatched tenants and conflicting provenance fail validation. The deterministic default adapter constructs the same schema without an API key. It does not use an LLM.

The approval digest covers the canonical complete action, including tenant, case ID, body and context attribution. `approve` requires that exact digest and a finite expiry inside the job deadline. Execution revalidates the action and its digest. Approval is a trusted local API, not a public unauthenticated endpoint.

The sandbox effect is a SQLite case-note row. The unique job ID, effect insertion and execution state share one transaction; repeated events or process exits between committed steps cannot duplicate this local effect. Concurrent connections use SQLite transactions, with at most ten seconds waiting for its single writer. This is a single-host demonstration, not a distributed queue. A real remote API would require an idempotent downstream API or transactional outbox; this implementation makes no exactly-once claim for external services. Database administrators can alter the file, so the audit is append-only through the API, not tamper-proof storage.

`report` returns schema version, synthetic classification, job state, exact action/digest, local effects, ordered audit events and actual measured operation-body latency in milliseconds. Timing includes database acquisition and operation body before the audit insert; it excludes transaction commit. The fixed fixture clock controls deadlines independently of the real monotonic latency clock. Token usage and cost are null because no model is invoked. `compare_traces` compares transitions and recorded latency sums; token/cost deltas remain unknown.

## Reproduce

```bash
python3 scripts/verify.py
PYTHONPATH=src python3 -m agentic_eval_ops.workflow_demo --report /tmp/workflow-report.json
```

Use `--database /tmp/workflow.db` to keep state and rerun the same request. The demo approves its own synthetic note to test the pipeline; this is not evidence of a human approving a real action. The tests use real temporary SQLite files, controlled concurrent threads and repeated child-process termination between workflow steps. They cover replay, failed work, immutable context, tenant access, malformed output, deadline and approval expiry, exact-action binding, independent requests, trace comparison and recovery without duplicate local effects.

## Existing integration boundaries

The Vapi/OpenClaw/Hermes and n8n files remain design blueprints. No authorized live provider, booking/calendar service, n8n/Make import or platform workspace was tested. Existing transcript keyword scores are review aids and do not establish execution or authorization. This workflow implements only its explicit local synthetic contract. Docker-based verification is isolation for trusted fixtures, not a hardened hostile-code sandbox.

## Interview prompts

1. Why must the local effect and job transition commit in one transaction?
2. What extra contract is required to preserve duplicate suppression for a remote API?
3. Which fields bind approval to an action, and how does expiry interact with restart?
4. Where must tenant authentication occur, and what does the SQL scoping prove?
5. Which latency is measured, and why are token counts and cost unknown?
