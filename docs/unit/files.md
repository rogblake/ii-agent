# Unit Test Plan: `files`

## Scope

- `FileService` upload, completion, retrieval, streaming, and URL generation
- Storage-path routing between default/media storage
- File/session authorization checks

## Priority test suites

1. Upload URL generation.
- rejects over-size payloads (`FileSizeLimitExceededError`)
- returns stable schema with generated `id` and upload URL

2. Upload completion.
- missing object raises `FileUploadNotFoundError`
- successful completion writes DB record and returns signed download URL

3. Stream access control.
- user-owned file streams successfully with headers
- non-owner path raises `FileAccessDeniedError`
- public session stream requires matching `session_id`

4. Agent file preparation.
- file IDs are linked to session when needed
- image/media classification based on `content_type`
- records without URL are skipped safely

5. Batch signed URL behavior.
- supports mixed URL/path inputs
- fallback to permanent URL when batch signing fails
- `force_signed=True` prevents permanent-url fallback

6. Media library pagination contract.
- `total`, `limit`, `offset`, `has_more` correctness
- source classification (`generated` vs `upload`)

## Fixtures / mocks

- fake file/session repositories
- fake storage clients (`read`, `write`, `get_download_signed_url`, batch signing)
- in-memory file-like object for stream chunking tests

## Proposed test layout

- `src/tests/unit/files/test_upload_flow.py`
- `src/tests/unit/files/test_streaming.py`
- `src/tests/unit/files/test_agent_file_helpers.py`
- `src/tests/unit/files/test_signed_url_batch.py`
- `src/tests/unit/files/test_media_library.py`

## Exit criteria

- Access-control and data-integrity branches are covered
- Storage fallback logic validated under failure injection
