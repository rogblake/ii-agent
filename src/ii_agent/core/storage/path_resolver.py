"""Pure-Python path builder for storage objects. No I/O.

All storage paths go through here — single source of truth for the
subfolder structure within the one shared bucket::

    bucket/
    ├── users/{user_id}/
    │   ├── uploads/{file_id}.{ext}         ← direct uploads + external imports
    │   ├── files/{file_id}.{ext}           ← LLM / code interpreter outputs
    │   ├── generated/{file_id}.{ext}       ← AI-generated images/videos
    │   ├── attachments/{file_id}.{ext}     ← agent message attachments
    │   ├── storybook/{file_id}.{ext}       ← storybook assets & backgrounds
    │   ├── skills/{skill_name}.zip         ← custom skills
    │   └── agent_state/{session_id}.json   ← agent conversation state
    │
    ├── public/
    │   ├── avatars/{user_id}.{ext}         ← user profile pictures
    │   └── shared/{asset_id}.{ext}         ← published user content
    │
    ├── content/
    │   ├── templates/{category}/{file}.{ext}  ← media templates
    │   └── slides/
    │       ├── assets/{content_hash}.{ext} ← slide assets (content-addressed)
    │       └── designs/{design_id}.{ext}   ← slide design files
    │
    ├── system/
    │   ├── seeds/{filename}.{ext}          ← database seed data
    │   └── {category}/{filename}.{ext}     ← other system assets
    │
    └── tmp/{token}/{filename}.{ext}        ← ephemeral, auto-cleaned
"""

from __future__ import annotations


class PathResolver:
    """Pure-Python path builder for storage objects. No I/O."""

    # ── User content ──

    def user_upload(self, user_id: str, file_id: str, ext: str) -> str:
        return f"users/{user_id}/uploads/{file_id}.{ext}"

    def user_file(self, user_id: str, file_id: str, ext: str) -> str:
        return f"users/{user_id}/files/{file_id}.{ext}"

    def user_generated(self, user_id: str, file_id: str, ext: str) -> str:
        return f"users/{user_id}/generated/{file_id}.{ext}"

    def user_attachment(self, user_id: str, file_id: str, ext: str) -> str:
        return f"users/{user_id}/attachments/{file_id}.{ext}"

    def user_storybook(self, user_id: str, file_id: str, ext: str) -> str:
        return f"users/{user_id}/storybook/{file_id}.{ext}"

    def user_skill(self, user_id: str, skill_name: str) -> str:
        return f"users/{user_id}/skills/{skill_name}.zip"

    # ── Public ──

    def public_avatar(self, user_id: str, ext: str) -> str:
        return f"public/avatars/{user_id}.{ext}"

    def public_shared(self, asset_id: str, ext: str) -> str:
        return f"public/shared/{asset_id}.{ext}"

    # ── Content ──

    def content_template(self, category: str, filename: str, ext: str) -> str:
        return f"content/templates/{category}/{filename}.{ext}"

    def slide_asset(self, content_hash: str, ext: str) -> str:
        return f"content/slides/assets/{content_hash}.{ext}"

    def slide_design(self, design_id: str, ext: str) -> str:
        return f"content/slides/designs/{design_id}.{ext}"

    # ── System ──

    def system_asset(self, category: str, filename: str, ext: str) -> str:
        return f"system/{category}/{filename}.{ext}"

    def system_seed(self, filename: str, ext: str) -> str:
        return f"system/seeds/{filename}.{ext}"

    # ── Temp ──

    def temp_file(self, token: str, filename: str, ext: str) -> str:
        return f"tmp/{token}/{filename}.{ext}"

    # ── Queries ──

    def is_public(self, path: str) -> bool:
        return path.startswith("public/")

    def is_user_content(self, path: str) -> bool:
        """True for any path under users/. Used to detect GCS-stored user data."""
        return path.startswith("users/")

    def user_prefix(self, user_id: str) -> str:
        return f"users/{user_id}/"

    def user_generated_prefix(self, user_id: str) -> str:
        """Prefix for a user's generated files. Useful for DB LIKE queries."""
        return f"users/{user_id}/generated/"

    def user_generated_pattern(self) -> str:
        """SQL LIKE pattern matching any user's generated files."""
        return "users/%/generated/%"


# Module-level singleton — stateless, safe to share
path_resolver = PathResolver()
