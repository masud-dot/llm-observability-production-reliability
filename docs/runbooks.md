# Wrenholt runbooks

One runbook for each SLO that can alert (Chapter 14). A page and a
ticket for the same SLO share a runbook: the cause is the same, the
urgency is not. A page means the budget would be gone in days at
this rate; act now. A ticket means it would be gone before the
28-day window ends; act this week. Every alert carries `slo`,
`severity`, `window` and `owner` labels and links here.

For every alert:

1. Open the SLOs and error budgets dashboard: budget left, burn
   rate over the last hour, valid events per hour.
2. Write the alert, the time and the first finding in the incident
   record.
3. Follow the SLO's runbook below. Find traces by trace ID in Tempo
   and logs by trace ID in Loki; never search them by content.
4. Close when the burn rate is back under 1 and the cause is in the
   record. The error budget policy says what follows a spent budget.

## availability

Answers that failed: 5xx, streams cut off in the middle and the
spend limit's 429s (Chapter 12). Owner: platform.

- Look first: the LLM gateway dashboard's attempts by error type
  and provider; calls refused at a spend limit on the cost
  dashboard.
- Likely causes: the provider is down or failing (FS-03); a tenant
  reached its spend limit; the orders service is failing.
- Act: for a provider outage, move traffic to another provider or
  model; for a spend limit, ask the budget owner before raising
  it.
- Chapter 16: on the chat spans of failed answers,
  `wrenholt.retry.decision` `breaker_open`, `limit_full` or
  `deadline` means the gateway refused the call itself; a
  `wrenholt.breaker` event shows when the breaker opened, and its
  next probe is at most 30 s later.
- Chapter 17: the gateway falls back to provider B by itself. Answers
  it made there carry `wrenholt.degraded.mode` `fallback_model`; a
  trace whose reason is `exercise` and mode `full` is a fallback that
  failed its daily exercise: fix it before relying on it.

## ttfc_interactive

First chunks of interactive answers later than 2.5 s. Owner:
platform.

- Look first: request duration p95 by provider on the LLM gateway
  dashboard; a slow trace's attempt spans.
- Likely causes: a provider brownout (FS-02); retries before the
  first chunk; slow retrieval.
- Act: move traffic to a faster provider or model; check that
  retries are not spending the customer's time before the first
  chunk.

## ttfc_critical_action

First chunks of refunds on a named order later than 4.0 s. Owner:
platform.

- Look first and act: as for `ttfc_interactive`. A refund is a
  critical action: the customer is waiting on money.

## decision_validity

Refund calls Linnet made with invalid arguments (FS-05). Owner:
assistant.

- Look first: refund tool spans with `error.type` set to
  `invalid_arguments`; the prompt version and model on their
  traces.
- Likely causes: a prompt or model change; a provider changing how
  the model formats arguments.
- Act: roll back the last prompt or model change; until then, send
  refunds to a person.

## not_refused

Questions the guardrail refused (FS-17). Owner: assistant.

- Look first: refusals by guardrail version and rule ID on the
  guardrail spans; the rule IDs, never the customers' words.
- Likely causes: a new guardrail version blocking ordinary
  questions.
- Act: set `WRENHOLT_GUARDRAIL_VERSION` back to the last version
  that held its objective.

## groundedness

Evaluated policy answers labelled ungrounded (Chapter 13). Tickets
only: results arrive late and few. Owner: assistant.

- Look first: the evaluation dashboard; evaluation events in Loki
  by scope, with their prompt and index versions.
- Likely causes: a prompt change; an index build missing articles.
- Act: compare slices by version before changing anything; a new
  evaluator version starts a new baseline.

## policy_freshness

Answers that used passages older than the policy in force (FS-09).
Tickets only. Owner: help-centre.

- Look first: the SLI on the SLO dashboard; the index version on
  retrieval spans.
- Act: finish the index swap, or rebuild the index from the
  help-centre articles in force.

## answer_cost

Answers that cost more than the SLO's threshold. Tickets only: the
spend limit stops a runaway bill within the hour. Owner: platform.

- Look first: the cost dashboard's output tokens per call and spend
  by prompt version and model.
- Likely causes: verbose answers or a growing context (FS-12); a
  sustained fallback to the large model (FS-13).
- Act: roll back the prompt; find out why traffic is on the large
  model.
