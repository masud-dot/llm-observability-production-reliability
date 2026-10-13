# Wrenholt error budget policy

Agreed by Linnet's product owner and the platform, assistant and
help-centre teams (Chapter 12). It covers the objectives in
`src/wrenholt/slo/objectives.yaml`, each over a 28-day rolling
window, and is reviewed with them every quarter. A change to an
objective needs the product owner's approval; the rules regenerate
from the file.

Adapted from the example policy in Google's *The Site Reliability
Workbook*.

## Goals

- Protect customers from repeated misses of the same objective.
- Give each owner a reason to trade features for reliability, and
  the evidence to make the case.

## Not goals

- Punishing a team for a missed objective.
- Stopping change for its own sake: a freeze has costs too.

## When a budget runs low

- Under half left: the owner brings the trend and its cause, if
  known, to the weekly operations review.
- Exhausted: the owner's releases stop, except fixes for the cause
  and security fixes, until the 28-day SLI is back within its
  objective. Other teams carry on.
- Spent by something the owner does not control, such as a provider
  outage: no freeze; the evidence goes to the review instead.

## Single incidents

- An incident that spends more than 20 per cent of any budget gets
  a postmortem with at least one action on its cause.

## Disagreements

- About how a budget was calculated: the head of engineering
  decides, from the recording rules and the raw counts.

## Measured without an objective

- Resolution and provider attempts carry no objective and spend no
  budget. They are read at the weekly review; nothing is frozen on
  them.
