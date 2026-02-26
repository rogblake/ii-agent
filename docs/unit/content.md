# Unit Test Plan: `content`

## Scope

- media template service and caching
- skills management and GitHub import flow
- slides write/read/pdf conversion orchestration
- storybook CRUD and generation-response assembly

## Priority test suites

1. Media templates/tools.
- list/get cache hit and cache miss behavior
- preview URL mapping and image limit mapping
- reference image generation session vs user-storage branch

2. Skill lifecycle.
- GitHub import parses/downloads/creates expected DB model
- duplicate skill name raises `SkillAlreadyExistsError`
- built-in toggle creates/removes per-user override correctly
- built-in delete protection (`BuiltinSkillDeleteError`)

3. Slides service.
- unauthorized session access returns structured failure response
- successful slide write persists through repository
- PDF conversion returns bytes or progress payloads

4. Storybook service.
- page/storybook serialization helpers map fields correctly
- generation status transitions (`generating`, `completed`, `failed`)
- separate-page numbering conversion correctness

## Fixtures / mocks

- fake storage service and cache backend
- mocked GitHub download service and upload function
- mocked PDF conversion functions
- in-memory repository doubles for storybook/slide flows

## Proposed test layout

- `src/tests/unit/content/test_media_service.py`
- `src/tests/unit/content/test_skill_service.py`
- `src/tests/unit/content/test_slide_service.py`
- `src/tests/unit/content/test_storybook_service.py`

## Exit criteria

- major content-generation state transitions verified
- per-user permission and override semantics covered
