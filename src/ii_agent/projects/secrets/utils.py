import json
from typing import Any, Dict, Optional

from ii_agent.core.secrets.encryption import encryption_manager


def _encrypt_secrets_payload(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if payload is None:
        return None
    serialized = json.dumps(payload)
    encrypted = encryption_manager.encrypt(serialized)
    return {"encrypted_data": encrypted}


def _decrypt_secrets_payload(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not payload:
        return None

    encrypted_value = payload.get("encrypted_data") if isinstance(payload, dict) else None
    if not encrypted_value:
        return payload

    decrypted = encryption_manager.decrypt(encrypted_value)
    if not decrypted:
        return None
    try:
        return json.loads(decrypted)
    except json.JSONDecodeError:
        return None
