# Unit Test Plan: `auth`

## Scope

- user lifecycle and API key lifecycle (`auth/users/service.py`)
- JWT/API key helper behavior
- waitlist and language validation paths
- auth dependencies error behavior

## Priority test suites

1. User creation flow.
- `create_user()` applies default credits/plan from config
- API key is created exactly once per new user

2. OAuth resolution flow.
- existing active user updates login profile
- disabled user raises `UserDisabledException`
- missing user gets created with expected defaults

3. Waitlist enforcement.
- disabled waitlist allows all
- `@ii.inc` bypasses waitlist checks
- non-whitelisted email raises `WaitlistDeniedException`

4. Language update validation.
- supported languages succeed
- invalid language raises typed validation error

5. Token utility behaviors.
- JWT create/verify/expiry cases
- malformed or invalid signature tokens are rejected
- API key generation/verification helpers stay deterministic

6. Dependency/access checks.
- missing credentials -> auth failure
- resource ownership mismatch -> access denied

## Fixtures / mocks

- fake user/API key/waitlist repositories
- frozen time for token expiry checks
- deterministic key generation via monkeypatch

## Proposed test layout

- `src/tests/unit/auth/test_user_service.py`
- `src/tests/unit/auth/test_waitlist.py`
- `src/tests/unit/auth/test_jwt_handler.py`
- `src/tests/unit/auth/test_api_key_utils.py`
- `src/tests/unit/auth/test_dependencies.py`

## Exit criteria

- account security and access control branches covered
- token creation/verification behavior stable across edge cases
