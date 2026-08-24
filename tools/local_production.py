#!/usr/bin/env python3
"""Local V4 production lifecycle commands."""

from __future__ import annotations

import argparse
from base64 import b64decode, b64encode
from binascii import Error as Base64Error
import getpass
import os
from pathlib import Path
import subprocess
import sys

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.canonical_serialization import canonical_bytes, parse_json_document


ROOT_FIELDS = {
    "schema_version", "scope", "signing_mode", "independent_human_review",
    "activated_at", "expires_at", "private_seed_base64",
}
TRUST_FIELDS = {
    "schema_version", "scope", "production_allowed", "signing_mode",
    "independent_human_review", "verification_time", "runtime_identity",
    "trust_policy", "trust_keys",
}


def _derive(master: bytes, name: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=b"jc-v4-local-production-v1",
        info=f"juris-calculus/local-production/{name}".encode("ascii"),
    ).derive(master)


def _harden_key_acl(path: Path) -> None:
    if os.name != "nt":
        return
    domain = os.environ.get("USERDOMAIN")
    account = f"{domain}\\{getpass.getuser()}" if domain else getpass.getuser()
    subprocess.run(
        [
            "icacls", str(path), "/inheritance:r", "/grant:r",
            f"{account}:(F)", "*S-1-5-18:(F)", "*S-1-5-32-544:(F)",
        ],
        check=True, capture_output=True,
    )


def initialize_service_key(root_path: Path, output_path: Path, trust_path: Path) -> None:
    """Derive the runtime-only service key; this is the sole root-seed reader."""

    root = parse_json_document(root_path.read_bytes())
    trust = parse_json_document(trust_path.read_bytes())
    if type(root) is not dict or set(root) != ROOT_FIELDS:
        raise ValueError("local production root fields are not exact")
    if type(trust) is not dict or set(trust) != TRUST_FIELDS:
        raise ValueError("local production trust fields are not exact")
    if root["schema_version"] != "jc/local-production-root/1.0":
        raise ValueError("local production root schema is unsupported")
    try:
        seed = _derive(b64decode(root["private_seed_base64"], validate=True), "service")
    except (Base64Error, TypeError, ValueError) as exc:
        raise ValueError("local production root seed is invalid") from exc
    private_key = Ed25519PrivateKey.from_private_bytes(seed)
    public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    service = next((row for row in trust["trust_keys"]
                    if row.get("key_id") == "local-production-service-key"), None)
    if service is None or b64decode(service["public_key_base64"], validate=True) != public:
        raise ValueError("derived service key does not match production trust")
    document = {
        "schema_version": "jc/local-production-service-key/1.0",
        "key_id": service["key_id"], "issuer": service["issuer"],
        "principal_id": service["principal_id"],
        "private_seed_base64": b64encode(seed).decode("ascii"),
        "public_key_base64": b64encode(public).decode("ascii"),
    }
    encoded = canonical_bytes(document)
    if output_path.is_file():
        if output_path.read_bytes() != encoded:
            raise ValueError("existing service runtime key differs from derived identity")
        _harden_key_acl(output_path)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encoded)
    _harden_key_acl(output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init_key = commands.add_parser("init-service-key")
    init_key.add_argument("--root", type=Path, required=True)
    init_key.add_argument("--output", type=Path, required=True)
    init_key.add_argument("--trust", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init-service-key":
            initialize_service_key(args.root, args.output, args.trust)
    except (OSError, TypeError, ValueError) as exc:
        print(f"local production failed: {exc}", file=sys.stderr)
        return 1
    print(f"local production {args.command} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
