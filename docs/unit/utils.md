# Unit Test Plan: `utils`

## Scope

- encryption, dictionary, indentation, schema conversion, workspace path helpers
- stateless utility behavior that is reused across domains

## Priority test suites

1. Encryption manager.
- encrypt/decrypt roundtrip
- `encrypt_raw`/`decrypt_raw` roundtrip
- invalid ciphertext decrypt returns empty string
- `is_encrypted` heuristic true/false edge cases

2. Dictionary utilities.
- `drop_none(recursive=True)` removes nested `None` and empty nested dicts
- `drop_none(recursive=False)` only removes top-level `None`

3. Indentation utilities.
- detect tab/space/mixed indentation
- normalize/apply indent transformations preserve code content
- mixed indentation guard assertions

4. Gemini schema conversion.
- `oneOf`/`anyOf`/`allOf` handling
- enum object/array conversions
- unsupported/null-type fallback behavior

5. Workspace path translation.
- local -> container path conversion
- container -> local path conversion
- relative path behavior for out-of-root input

## Fixtures / mocks

- pure-function tests with table-driven inputs
- monkeypatched environment for encryption key derivation edge cases

## Proposed test layout

- `src/tests/unit/utils/test_encryption.py`
- `src/tests/unit/utils/test_dict_utils.py`
- `src/tests/unit/utils/test_indent_utils.py`
- `src/tests/unit/utils/test_gemini_schema.py`
- `src/tests/unit/utils/test_workspace_manager.py`

## Exit criteria

- utility functions are deterministic and side-effect free under edge input
- schema and indent helpers covered with representative matrix tests
