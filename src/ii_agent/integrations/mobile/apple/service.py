"""Service helpers for Apple credentials."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import uuid

from ii_agent.core.db import get_db_session_local
from ii_agent.integrations.mobile.apple.models import AppleAuthState, AppleCredential
from ii_agent.integrations.mobile.apple.repository import AppleCredentialRepository
from ii_agent.core.secrets.encryption import encryption_manager


class AppleCredentialService:
    """Credential lifecycle service for Apple auth/TestFlight."""

    def __init__(self, repo: AppleCredentialRepository | None = None) -> None:
        self._repo = repo or AppleCredentialRepository()

    async def save_or_update_credential(
        self,
        user_id: uuid.UUID,
        apple_id: str,
        auth_state: str,
        session_data: dict | None = None,
        team_id: str | None = None,
        team_name: str | None = None,
        available_teams: list | None = None,
        session_expiry: datetime | None = None,
    ) -> AppleCredential:
        encrypted_session = None
        if session_data:
            encrypted_session = encryption_manager.encrypt(json.dumps(session_data))

        async with get_db_session_local() as db:
            credential = await self._repo.get_by_user_and_apple_id(db, user_id, apple_id)

            if not credential:
                pending = await self._repo.get_by_user_and_apple_id(db, user_id, "pending")
                if pending:
                    credential = pending
                    credential.apple_id = apple_id

            if credential:
                credential.auth_state = auth_state
                if encrypted_session is not None:
                    credential.encrypted_session_data = encrypted_session
                if team_id is not None:
                    credential.selected_team_id = team_id
                if team_name is not None:
                    credential.team_name = team_name
                if available_teams is not None:
                    credential.available_teams = available_teams
                if session_expiry is not None:
                    credential.session_expiry = session_expiry
                credential.updated_at = datetime.now(timezone.utc)
                await db.flush()
                await db.refresh(credential)
            else:
                credential = AppleCredential(
                    user_id=user_id,
                    apple_id=apple_id,
                    auth_state=auth_state,
                    encrypted_session_data=encrypted_session,
                    selected_team_id=team_id,
                    team_name=team_name,
                    available_teams=available_teams,
                    session_expiry=session_expiry,
                )
                db.add(credential)
                await db.flush()
                await db.refresh(credential)

            db.expunge(credential)
            return credential

    async def get_user_credential(
        self,
        user_id: uuid.UUID,
        apple_id: str | None = None,
    ) -> AppleCredential | None:
        async with get_db_session_local() as db:
            if apple_id:
                credential = await self._repo.get_by_user_and_apple_id(db, user_id, apple_id)
            else:
                credential = await self._repo.get_latest_by_user(db, user_id)

            if credential:
                await db.refresh(credential)
                db.expunge(credential)
            return credential

    async def get_active_session(self, user_id: uuid.UUID) -> AppleCredential | None:
        async with get_db_session_local() as db:
            credential = await self._repo.get_latest_authenticated_by_user(db, user_id)
            if not credential:
                return None

            if credential.session_expiry and credential.session_expiry < datetime.now(timezone.utc):
                credential.auth_state = AppleAuthState.EXPIRED.value
                await db.flush()
                return None

            await db.refresh(credential)
            db.expunge(credential)
            return credential

    async def delete_credential(self, user_id: uuid.UUID, apple_id: str) -> bool:
        async with get_db_session_local() as db:
            credential = await self._repo.get_by_user_and_apple_id(db, user_id, apple_id)
            if not credential:
                return False
            await db.delete(credential)
            await db.flush()
            return True

    def get_decrypted_session_data(self, credential: AppleCredential) -> dict | None:
        if not credential.encrypted_session_data:
            return None

        decrypted = encryption_manager.decrypt(credential.encrypted_session_data)
        if not decrypted:
            return None

        try:
            return json.loads(decrypted)
        except json.JSONDecodeError:
            return None

    async def update_auth_state(self, user_id: uuid.UUID, auth_state: str) -> bool:
        async with get_db_session_local() as db:
            credential = await self._repo.get_latest_by_user(db, user_id)
            if not credential:
                return False

            credential.auth_state = auth_state
            credential.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return True

    async def clear_session_password(self, user_id: uuid.UUID) -> bool:
        async with get_db_session_local() as db:
            credential = await self._repo.get_latest_by_user(db, user_id)
            if not credential or not credential.encrypted_session_data:
                return False

            decrypted = encryption_manager.decrypt(credential.encrypted_session_data)
            if not decrypted:
                return False

            try:
                session_data = json.loads(decrypted)
            except json.JSONDecodeError:
                return False

            session_data.pop("_temp_password", None)
            session_data.pop("_temp_2fa_code", None)

            credential.encrypted_session_data = encryption_manager.encrypt(json.dumps(session_data))
            credential.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return True

    async def save_expo_token(self, user_id: uuid.UUID, expo_token: str) -> bool:
        async with get_db_session_local() as db:
            credential = await self._repo.get_latest_by_user(db, user_id)

            if not credential:
                credential = AppleCredential(
                    user_id=user_id,
                    apple_id="pending",
                    auth_state=AppleAuthState.PENDING_LOGIN.value,
                )
                db.add(credential)

            credential.encrypted_expo_token = encryption_manager.encrypt(expo_token)
            credential.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return True

    def get_decrypted_expo_token(self, credential: AppleCredential) -> str | None:
        if not credential.encrypted_expo_token:
            return None
        return encryption_manager.decrypt(credential.encrypted_expo_token)

    async def save_app_specific_password(
        self,
        user_id: uuid.UUID,
        app_specific_password: str,
    ) -> bool:
        async with get_db_session_local() as db:
            credential = await self._repo.get_latest_by_user(db, user_id)

            if not credential:
                credential = AppleCredential(
                    user_id=user_id,
                    apple_id="pending",
                    auth_state=AppleAuthState.PENDING_LOGIN.value,
                )
                db.add(credential)

            credential.encrypted_app_specific_password = encryption_manager.encrypt(
                app_specific_password
            )
            credential.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return True

    def get_decrypted_app_specific_password(self, credential: AppleCredential) -> str | None:
        if not credential.encrypted_app_specific_password:
            return None
        return encryption_manager.decrypt(credential.encrypted_app_specific_password)

    async def save_ios_credentials(
        self,
        user_id: uuid.UUID,
        bundle_identifier: str,
        p12_base64: str,
        p12_password: str,
        provisioning_profile_base64: str,
        certificate_id: str | None = None,
        certificate_expiry: datetime | None = None,
    ) -> bool:
        async with get_db_session_local() as db:
            credential = await self._repo.get_latest_by_user(db, user_id)
            if not credential:
                return False

            credential.encrypted_ios_p12 = encryption_manager.encrypt(p12_base64)
            credential.encrypted_ios_p12_password = encryption_manager.encrypt(p12_password)
            credential.encrypted_ios_provisioning_profile = encryption_manager.encrypt(
                provisioning_profile_base64
            )
            credential.ios_bundle_identifier = bundle_identifier
            credential.ios_certificate_expiry = certificate_expiry or (
                datetime.now(timezone.utc) + timedelta(days=365)
            )
            credential.ios_certificate_id = certificate_id
            credential.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return True

    def get_ios_credentials(
        self,
        credential: AppleCredential,
        bundle_identifier: str,
    ) -> dict | None:
        if credential.ios_bundle_identifier != bundle_identifier:
            return None

        if credential.ios_certificate_expiry and credential.ios_certificate_expiry < datetime.now(
            timezone.utc
        ):
            return None

        if not (
            credential.encrypted_ios_p12
            and credential.encrypted_ios_p12_password
            and credential.encrypted_ios_provisioning_profile
        ):
            return None

        p12_base64 = encryption_manager.decrypt(credential.encrypted_ios_p12)
        p12_password = encryption_manager.decrypt(credential.encrypted_ios_p12_password)
        provisioning_profile_base64 = encryption_manager.decrypt(
            credential.encrypted_ios_provisioning_profile
        )

        if not p12_base64 or p12_password is None or not provisioning_profile_base64:
            return None

        return {
            "p12_base64": p12_base64,
            "p12_password": p12_password,
            "provisioning_profile_base64": provisioning_profile_base64,
            "certificate_id": credential.ios_certificate_id,
            "certificate_expiry": (
                credential.ios_certificate_expiry.isoformat()
                if credential.ios_certificate_expiry
                else None
            ),
        }


AppleCredentials = AppleCredentialService()
