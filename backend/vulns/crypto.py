"""Weak crypto — MD5/SHA1, ECB, static IV, predictable RNG."""

from __future__ import annotations

import hashlib
import hmac
import random
import string

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from .secrets import AES_IV, AES_KEY

router = APIRouter(prefix="/crypto", tags=["crypto"])


@router.get("/hash-md5", response_class=PlainTextResponse)
def hash_md5(value: str = Query(...)) -> str:
    return hashlib.md5(value.encode()).hexdigest()


@router.get("/hash-sha1", response_class=PlainTextResponse)
def hash_sha1(value: str = Query(...)) -> str:
    return hashlib.sha1(value.encode()).hexdigest()


@router.get("/hmac-sha1", response_class=PlainTextResponse)
def hmac_sha1(key: str = Query(...), msg: str = Query(...)) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha1).hexdigest()


def _pad(b: bytes, size: int = 16) -> bytes:
    pad = size - (len(b) % size)
    return b + bytes([pad] * pad)


@router.get("/encrypt-ecb", response_class=PlainTextResponse)
def encrypt_ecb(value: str = Query(...)) -> str:
    cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB())
    enc = cipher.encryptor()
    return (enc.update(_pad(value.encode())) + enc.finalize()).hex()


@router.get("/encrypt-cbc-static-iv", response_class=PlainTextResponse)
def encrypt_cbc(value: str = Query(...)) -> str:
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_IV))
    enc = cipher.encryptor()
    return (enc.update(_pad(value.encode())) + enc.finalize()).hex()


@router.get("/token")
def gen_token(length: int = Query(16, ge=4, le=128)) -> JSONResponse:
    alphabet = string.ascii_letters + string.digits
    token = "".join(random.choice(alphabet) for _ in range(length))
    pin = random.randint(1000, 9999)
    return JSONResponse({"token": token, "pin": pin})


@router.get("/password-policy")
def password_policy(password: str = Query(...)) -> JSONResponse:
    # Any non-empty password accepted; no length/complexity check.
    accepted = bool(password)
    return JSONResponse({"accepted": accepted, "stored_as": hashlib.md5(password.encode()).hexdigest()})


@router.get("/generate-weak-key")
def generate_weak_key() -> JSONResponse:
    from cryptography.hazmat.primitives.asymmetric import rsa
    # Weak RSA Key size (1024 bit is insecure, SAST tools explicitly alert on < 2048)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=1024
    )
    return JSONResponse({"status": "generated", "key_size": private_key.key_size})


@router.get("/cleartext-protocols")
def cleartext_protocols() -> JSONResponse:
    import ftplib
    import telnetlib
    # Simply referencing these standard library modules triggers Bandit B401/B402 (Insecure Protocols)
    ftp_active = hasattr(ftplib, "FTP")
    telnet_active = hasattr(telnetlib, "Telnet")
    return JSONResponse({"ftplib_present": ftp_active, "telnetlib_present": telnet_active})
