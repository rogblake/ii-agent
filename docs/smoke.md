# Smoke Test Plan

## Objective

Provide a fast deploy gate that detects broken startup, routing, authentication, and core persistence wiring within minutes.

## Runtime budget

- target <= 5 minutes total in CI
- no external network dependency

## Smoke scenarios (ordered)

1. App startup + health route.
- app boot succeeds
- `/health` returns `{"status": "ok"}`

2. DB + migration sanity.
- can open async DB session
- core tables are queryable after migration/bootstrap

3. Auth sanity.
- issue token and verify token
- invalid token path returns auth failure

4. Session sanity.
- create session
- fetch session by owner

5. File service sanity.
- generate upload URL (without external upload)
- reject oversize payload with expected error

6. LLM settings sanity.
- create one user model setting
- retrieve and resolve into runtime config

7. Realtime socket sanity.
- connect with valid auth
- join session
- send ping command and receive pong/system event

8. Billing config sanity.
- invalid/missing Stripe config branches return typed error (no network)

## Failure policy

- any smoke failure blocks deployment
- flaky smoke tests must be fixed or removed from smoke set (not retried indefinitely)

## Exit criteria

- smoke suite is green on every release candidate
- each smoke scenario maps to an operational readiness signal
