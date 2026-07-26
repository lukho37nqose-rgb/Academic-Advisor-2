import hashlib
import os
from typing import Any, AsyncGenerator, Dict

import aiobotocore.session
from botocore.exceptions import ClientError


class BlobStorage:
    # A tiny in-memory mock store for local development when S3 is not configured.
    _store: Dict[str, bytes] = {}

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
    async def upload_text(cls, content: str) -> str:
        """Uploads text to S3 or falls back to the in-memory local store."""
        hash_hex = hashlib.md5(content.encode("utf-8")).hexdigest()
        key = f"s3_{hash_hex}_payload.json"

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
    async def upload_binary(cls, file_object: Any, *, content_hash: str, suffix: str) -> str:
        """Stores a verified source object without converting it to text in the API."""
        key = f"sources/{content_hash}{suffix}"
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
        key: str,
        content_type: str,
        maximum_size: int,
        expires_in: int,
    ) -> dict[str, Any]:
        """Creates a short-lived, one-object S3 form upload contract."""
        if not cls.direct_uploads_available():
            raise RuntimeError("Direct handbook uploads require configured object storage.")

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
