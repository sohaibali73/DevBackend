"""Azure Blob Storage helper — replaces Supabase Storage buckets.

Bucket name == container name. The four historical buckets map 1:1 to
containers: user-uploads, presentations, brain-docs, skills-bundles.

Auth (in priority order):
    1. AZURE_STORAGE_CONNECTION_STRING (local/dev)
    2. AZURE_STORAGE_ACCOUNT + Managed Identity / DefaultAzureCredential (Azure)

All methods are synchronous (mirrors the old supabase-py storage client, which
the callers used synchronously inside asyncio.to_thread).
"""

from __future__ import annotations

import datetime as _dt
import logging
import threading
from typing import Any, Dict, List, Optional

from config import get_settings

logger = logging.getLogger(__name__)

try:
    from azure.storage.blob import (
        BlobServiceClient,
        ContentSettings,
        generate_blob_sas,
        BlobSasPermissions,
    )
    from azure.identity import DefaultAzureCredential
    _AZURE_AVAILABLE = True
except Exception as _exc:  # pragma: no cover
    BlobServiceClient = None  # type: ignore
    _AZURE_AVAILABLE = False
    logger.warning("azure-storage-blob not available — Blob storage disabled (%s)", _exc)


class BlobStoreError(Exception):
    pass


_service: Optional["BlobServiceClient"] = None
_service_lock = threading.Lock()
_ensured_containers: set[str] = set()


def _get_service() -> "BlobServiceClient":
    global _service
    if _service is not None:
        return _service
    if not _AZURE_AVAILABLE:
        raise BlobStoreError("azure-storage-blob is not installed")
    s = get_settings()
    with _service_lock:
        if _service is None:
            if s.azure_storage_connection_string:
                _service = BlobServiceClient.from_connection_string(
                    s.azure_storage_connection_string
                )
            elif s.azure_storage_account:
                account_url = f"https://{s.azure_storage_account}.blob.core.windows.net"
                cred = DefaultAzureCredential() if s.azure_storage_use_managed_identity else None
                _service = BlobServiceClient(account_url=account_url, credential=cred)
            else:
                raise BlobStoreError(
                    "Azure Blob not configured: set AZURE_STORAGE_CONNECTION_STRING "
                    "or AZURE_STORAGE_ACCOUNT"
                )
    return _service


def _ensure_container(container: str) -> None:
    if container in _ensured_containers:
        return
    svc = _get_service()
    try:
        svc.create_container(container)
    except Exception:
        pass  # already exists (or no permission to create — assume it exists)
    _ensured_containers.add(container)


def upload(container: str, path: str, data: bytes, content_type: Optional[str] = None) -> None:
    _ensure_container(container)
    svc = _get_service()
    blob = svc.get_blob_client(container=container, blob=path)
    cs = ContentSettings(content_type=content_type) if content_type else None
    blob.upload_blob(data, overwrite=True, content_settings=cs)


def download(container: str, path: str) -> bytes:
    svc = _get_service()
    blob = svc.get_blob_client(container=container, blob=path)
    return blob.download_blob().readall()


def delete(container: str, path: str) -> None:
    svc = _get_service()
    blob = svc.get_blob_client(container=container, blob=path)
    try:
        blob.delete_blob()
    except Exception as exc:
        logger.warning("Blob delete failed for %s/%s: %s", container, path, exc)


def list_prefix(container: str, prefix: str = "") -> List[Dict[str, Any]]:
    svc = _get_service()
    cclient = svc.get_container_client(container)
    out: List[Dict[str, Any]] = []
    for b in cclient.list_blobs(name_starts_with=prefix):
        # mimic supabase list(): name is the last path segment
        out.append({"name": b.name.split("/")[-1], "path": b.name, "size": b.size})
    return out


def signed_url(container: str, path: str, expires_in: int = 3600) -> Optional[str]:
    """Generate a read-only SAS URL. Works with account-key (connection string)
    or user-delegation key (Managed Identity)."""
    svc = _get_service()
    s = get_settings()
    account = svc.account_name
    expiry = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=expires_in)
    perms = BlobSasPermissions(read=True)
    try:
        if svc.credential and getattr(svc.credential, "account_key", None):
            sas = generate_blob_sas(
                account_name=account, container_name=container, blob_name=path,
                account_key=svc.credential.account_key, permission=perms, expiry=expiry,
            )
        else:
            start = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=5)
            udk = svc.get_user_delegation_key(start, expiry)
            sas = generate_blob_sas(
                account_name=account, container_name=container, blob_name=path,
                user_delegation_key=udk, permission=perms, expiry=expiry,
            )
        return f"https://{account}.blob.core.windows.net/{container}/{path}?{sas}"
    except Exception as exc:
        logger.warning("Could not generate SAS URL for %s/%s: %s", container, path, exc)
        return None
