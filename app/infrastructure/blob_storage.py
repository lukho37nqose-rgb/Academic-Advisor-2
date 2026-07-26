import hashlib
import os
import re
from typing import Any, AsyncGenerator, Dict

import aiobotocore.session
from botocore.exceptions import ClientError


class BlobStorage:
    # A tiny in-memory mock store for local development when S3 is not configured.
    _store: Dict[str, bytes] = {}
    _TENANT_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    _SHA256_DIGEST = re.compile(r"^[a-f0-9]{64}$")
    _SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,16}$")

    @classmethod
    def tenant_prefix(cls, tenant_id: str) -> str:
        """Returns the only object-storage prefix allowed for newly written tenant data."""
        if not isinstance(tenant_id, str) or not cls._TENANT_IDENTIFIER.fullmatch(tenant_id):
            raise ValueError("Tenant identifier is unsafe for object storage.")
        return f"tenants/{tenant_id}"

    @classmethod
    def _validate_content_address(cls, content_hash: str, suffix: str) -> None:
        if not isinstance(content_hash, str) or not cls._SHA256_DIGEST.fullmatch(content_hash):
            raise ValueError("Object content hash must be a SHA-256 hexadecimal digest.")
        if not isinstance(suffix, str) or not cls._SAFE_SUFFIX.fullmatch(suffix):
            raise ValueError("Object suffix is unsafe.")

    @classmethod
    def _is_s3_configured(cls) -> bool:
        return bool(os.environ.get("S3_BUCKET_NAME"))

    @classmethod
    def direct_uploads_available(cls) -> bool:
        """Direct uploads require shared object storage, never the local mock."""
        return cls._is_s3_configured()

    @classmethod
    def _s3_encryption_options(cls) -> dict[str, str]:
        algorithm = os.environ.get("S3_SERVER_SIDE_ENCRYPTION", "AES256").strip()
        return {"ServerSideEncryption": algorithm} if algorithm else {}

    @classmethod
    async def upload_text(cls, content: str, *, tenant_id: str) -> str:
        """Uploads text to S3 or falls back to the in-memory local store."""
        hash_hex = hashlib.sha256(content.encode("utf-8")).hexdigest()
        key = f"{cls.tenant_prefix(tenant_id)}/evidence/{hash_hex}.txt"

        if cls._is_s3_configured():
            bucket = os.environ["S3_BUCKET_NAME"]
            session = aiobotocore.session.get_session()
            async with session.create_client("s3") as client:
                await client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=content.encode("utf-8"),
                    **cls._s3_encryption_options(),
                )
        else:
            cls._store[key] = content.encode("utf-8")
        return key

    @classmethod
    async def upload_binary(
        cls,
        file_object: Any,
        *,
        tenant_id: str,
        content_hash: str,
        suffix: str,
    ) -> str:
        """Stores a verified source object without converting it to text in the API."""
        cls._validate_content_address(content_hash, suffix)
        key = f"{cls.tenant_prefix(tenant_id)}/sources/{content_hash}{suffix}"
        file_object.seek(0)
        if cls._is_s3_configured():
            bucket = os.environ["S3_BUCKET_NAME"]
            session = aiobotocore.session.get_session()
            async with session.create_client("s3") as client:
                await client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=file_object,
                    **cls._s3_encryption_options(),
                )
        else:
            cls._store[key] = file_object.read()
        return key

    @classmethod
    async def create_presigned_post(
        cls,
        *,
        tenant_id: str,
        key: str,
        content_type: str,
        maximum_size: int,
        expires_in: int,
    ) -> dict[str, Any]:
        """Creates a short-lived, one-object S3 form upload contract."""
        if not cls.direct_uploads_available():
            raise RuntimeError("Direct handbook uploads require configured object storage.")
        staging_prefix = f"{cls.tenant_prefix(tenant_id)}/handbook-staging/"
        if not key.startswith(staging_prefix) or not key.endswith(".pdf"):
            raise ValueError("Direct handbook uploads must use the tenant staging prefix.")

        encryption = cls._s3_encryption_options()
        fields = {"Content-Type": content_type}
        conditions: list[Any] = [
            {"Content-Type": content_type},
            ["content-length-range", 1, maximum_size],
        ]
        if encryption:
            fields["x-amz-server-side-encryption"] = encryption["ServerSideEncryption"]
            conditions.append({"x-amz-server-side-encryption": encryption["ServerSideEncryption"]})

        session = aiobotocore.session.get_session()
        async with session.create_client("s3") as client:
            return await client.generate_presigned_post(
                Bucket=os.environ["S3_BUCKET_NAME"],
                Key=key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expires_in,
            )

    @classmethod
    async def get_object_metadata(cls, key: str) -> dict[str, Any]:
        """Returns storage metadata used before a direct source is queued."""
        if not cls._is_s3_configured():
            raise RuntimeError("Object metadata is unavailable without configured object storage.")

        session = aiobotocore.session.get_session()
        async with session.create_client("s3") as client:
            try:
                response = await client.head_object(Bucket=os.environ["S3_BUCKET_NAME"], Key=key)
            except ClientError as exc:
                raise ValueError("The uploaded handbook object could not be found.") from exc
        return {
            "content_length": int(response["ContentLength"]),
            "content_type": str(response.get("ContentType") or ""),
        }

    @classmethod
    async def get_stream(cls, key: str) -> AsyncGenerator[bytes, None]:
        """Fetches a stream from S3 or falls back to the in-memory local store."""
        if cls._is_s3_configured():
            bucket = os.environ["S3_BUCKET_NAME"]
            session = aiobotocore.session.get_session()
            async with session.create_client("s3") as client:
                try:
                    response = await client.get_object(Bucket=bucket, Key=key)
                    stream = response["Body"]
                    while True:
                        chunk = await stream.read(64 * 1024)
                        if not chunk:
                            break
                        yield chunk
                except ClientError as exc:
                    raise RuntimeError(f"Failed to fetch {key} from S3.") from exc
        elif key in cls._store:
            yield cls._store[key]
        else:
            raise ValueError("Source object was not found in local storage.")

    @classmethod
    async def verify_sha256(cls, key: str, expected_hash: str) -> None:
        """Fail closed when stored source bytes no longer match their evidence record."""
        if not cls._SHA256_DIGEST.fullmatch(expected_hash):
            raise ValueError("Evidence record does not contain a valid SHA-256 digest.")

        digest = hashlib.sha256()
        async for chunk in cls.get_stream(key):
            digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            raise ValueError("Stored source bytes do not match the recorded evidence hash.")
