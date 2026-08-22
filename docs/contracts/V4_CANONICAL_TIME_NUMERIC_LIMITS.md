# V4 canonical identity, time, numeric, limits, and platform contract

Machine authority is split by concern without duplicating values:

- `tests/fixtures/golden/jcs-v4-vectors.json` freezes canonical bytes and digest vectors.
- `tests/fixtures/golden/v4-foundation-contract.json` freezes time, numeric, admission-limit, and target-platform rules.
- `tests/fixtures/golden/v4-resource-limit-probe.json` is the measured local basis for the admission limits.
- `tests/fixtures/golden/v4-artifact-page-probe.json` is the measured local basis for the bounded resolver page.

## Canonical identity

`DigestV4` has one wire grammar: `sha256:<64 lowercase hex>`. Bare hex, `sha256-`, uppercase hex, wrong length, and surrounding whitespace are invalid.

JC formal JSON uses the RFC 8785 string escaping, recursive UTF-16 code-unit property ordering, no-whitespace output, and UTF-8 generation rules, with a stricter JC numeric admission profile: only integers in `[-(2^53-1), 2^53-1]` are admitted. Float tokens, non-finite values, duplicate property names, top-level scalars, and lone surrogates are rejected before canonicalization. Unicode is preserved byte-for-byte; NFC and NFD are not normalized.

This is not a claim that the current W0 reference checker implements RFC 8785's complete IEEE-754 number serialization. W1 must use one production serializer and a separate official-number-vector conformance lane if the implementation claims full RFC 8785 compatibility. The formal admission wrapper continues to reject float. See [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html) and [RFC 7493](https://www.rfc-editor.org/rfc/rfc7493.html).

Python and Node independently reproduce all positive canonical bytes and digests. Python's raw parser also proves duplicate-key and lexical float rejection. The Node oracle reports `duplicate_key=declaration-only`; `JSON.parse` is not evidence that duplicate property names were rejected.

## Time and numeric rules

The only instant wire form is uppercase UTC `Z`: `YYYY-MM-DDTHH:MM:SS[.fraction]Z`. Fraction precision is one through nine digits and its last digit cannot be zero; an absent fraction means zero nanoseconds. Offsets, lowercase `z`, leap seconds, invalid calendar values, missing seconds, and more than nine fraction digits are invalid.

An instant is represented and compared as `(epoch_seconds, nanosecond)`. The fractional value must not be passed through Python `datetime` microseconds or JavaScript `Date` milliseconds. Intervals are half-open `[start,end)`, including the effective start and excluding the effective end.

JSON integers use the same safe range as canonical identity. Money is `{currency, minor_units}` with a three-uppercase-letter currency code and integer minor units. Rational values are `{numerator, denominator}` with a positive denominator and lowest-term normalization; zero is exactly `0/1`. Float money, negative/zero denominators, and unreduced fractions are invalid.

## Resource limits

The committed probe contains 48 deterministic Windows/CPython 3.12 sizing samples. The sole runner hard-freezes the probe file and payload digests, regenerates every raw sample, and independently recomputes its byte digest and structural observations; recorded timing distributions are checked for a valid measurement shape but are not expected to reproduce bit-for-bit. The historical `logic_sha256` binds the methodology description, while the committed runner source is the executable reproduction logic.

The request probe informs 13 request-admission defaults and hard maxima covering transport bytes, depth, nodes, object/array/string/reference counts, typed reference fields, and the admission deadline. Probe names record generator scale, not an admission result: for example, 32 nested arrays have observed depth 33 because the root value is depth 1, and a `references_2048` request also carries two scalar references. The policy independently defines every limit as inclusive; the corresponding enforcement task must prove that the exact limit passes and `limit+1` returns the named stable error code. The W0 sizing probe itself does not claim that those runtime rejection paths already exist.

The required enforcement order is byte check before decode/parse, bounded depth pre-scan, strict parse, one iterative structural pass, typed contract validation, and a deadline spanning every admission stage. The request probe is local sizing evidence, not a throughput or latency service-level objective.

W1-04 separately freezes `artifact_page_bytes` at a 65,536-byte default and 262,144-byte hard maximum for `ArtifactResolverV4.resolve_handle.length`. The deterministic local probe measures SHA-256 plus RFC 4648 Base64 primitives over 16 KiB, 64 KiB, 256 KiB, and 1 MiB payloads. A 64 KiB payload encodes to 87,384 bytes; a 256 KiB payload encodes to 349,528 bytes; a 1 MiB payload encodes to 1,398,104 bytes. This is policy-sizing reference evidence only: the resolver rehashes the full registered artifact per read, the page limit does not bound resident content or `resolve_content`, and the probe does not prove MCP framing, concurrent throughput, memory use, or an SLO. W4-03 owns bundle-bound read-artifact handle/chunk semantics; W4-06 owns cross-stage privacy/error/resource closure; W5-CUTOVER owns actual `jc_read_artifact` MCP wiring and keeps P1-15 RED until the full production budget closes. W5-01 and W5-06 only verify contracts/matrices.

Five operational limits still lack an implementation-specific benchmark: solver deadline, worker queue, in-flight runs, state quota, and retention. They remain `DEFERRED_UNBENCHMARKED` with `value=null` and a concrete closure task. No downstream task may replace `null` with a guessed number.

## Platform boundary

The target runtime matrix is Ubuntu and Windows on Python 3.11 and 3.12. Node 22/24 is a contract oracle, not a wheel runtime dependency. W0 freezes that target but does not claim all four runtime combinations ran locally; W6-05 must attach the cross-platform execution receipts.
