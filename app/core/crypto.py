import hashlib
import json
import os
import base64
from typing import Any, AsyncGenerator

# Use standard cryptography library for PKI
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)
from cryptography.exceptions import InvalidSignature

class CryptoService:
    def __init__(self):
        # We must load a real private key from the environment.
        # Failing if missing prevents accidental unauthorized release signing.
        key_data = os.environ.get("GOVERNANCE_PRIVATE_KEY")
        if not key_data:
            raise ValueError("GOVERNANCE_PRIVATE_KEY environment variable is missing. Cannot initialize CryptoService.")
            
        try:
             # Secret managers commonly return either a PEM value (with escaped
             # newlines) or a base64-encoded PEM. Support both explicitly.
             normalized_key_data = key_data.replace("\\n", "\n")
             if normalized_key_data.lstrip().startswith("-----BEGIN"):
                 pem_data = normalized_key_data.encode("utf-8")
             else:
                 pem_data = base64.b64decode(normalized_key_data, validate=True)

             self.private_key = load_pem_private_key(pem_data, password=None)
             if not isinstance(self.private_key, rsa.RSAPrivateKey):
                 raise ValueError("GOVERNANCE_PRIVATE_KEY must be an RSA private key for RSA-PSS release signing.")
        except Exception as e:
             raise ValueError(f"Failed to load GOVERNANCE_PRIVATE_KEY: {e}")

        self.public_key_pem = self.private_key.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        fingerprint = hashlib.sha256(self.public_key_pem.encode("ascii")).hexdigest()
        self.key_id = os.environ.get("GOVERNANCE_KEY_ID") or f"sha256:{fingerprint}"

    @staticmethod
    def _canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
        """Produces the stable bytes signed and later verified by an auditor."""
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def sign_payload(self, payload: dict) -> tuple[str, str]:
        """
        Hashes and signs a policy payload to guarantee immutability.
        Returns (signature_hex, hash_hex).
        """
        payload_bytes = self._canonical_payload_bytes(payload)
        
        # Calculate SHA-256 Hash
        digest = hashes.Hash(hashes.SHA256())
        digest.update(payload_bytes)
        hash_bytes = digest.finalize()
        hash_hex = hash_bytes.hex()
        
        # Sign the hash using RSA PSS
        signature = self.private_key.sign(
            payload_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        signature_hex = signature.hex()
        
        return signature_hex, hash_hex

    @classmethod
    def verify_signed_payload(
        cls,
        *,
        payload: dict[str, Any],
        signature_hex: str,
        expected_hash: str,
        public_key_pem: str,
    ) -> bool:
        """Verifies a release using the public key snapshot stored with it."""
        payload_bytes = cls._canonical_payload_bytes(payload)
        actual_hash = hashlib.sha256(payload_bytes).hexdigest()
        if actual_hash != expected_hash:
            return False
        try:
            public_key = load_pem_public_key(public_key_pem.encode("ascii"))
            if not isinstance(public_key, rsa.RSAPublicKey):
                return False
            public_key.verify(
                bytes.fromhex(signature_hex),
                payload_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        except (TypeError, ValueError, InvalidSignature):
            return False
        return True

async def hash_evidence_stream(evidence_stream: AsyncGenerator[bytes, None]) -> str:
    """
    Computes a SHA-256 hash of an async byte stream without loading it all into memory.
    """
    hasher = hashlib.sha256()
    async for chunk in evidence_stream:
        hasher.update(chunk)
    return hasher.hexdigest()
