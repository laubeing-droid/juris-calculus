# Security policy

Report suspected vulnerabilities privately through GitHub Security Advisories for this repository. Do not include client facts, private legal materials, credentials, signing keys, or production artifacts in a public issue.

The supported release line is 5.0.0 (public protocol jc/5.0). V3 and V4 runtime or replay paths are not supported or maintained. A passing local or CI build is not a production release: production adoption additionally requires the protected `release` environment, repository governance, an authorized production Ed25519 release-attestor key, and exact tag-to-commit verification in the reusable promotion workflow.
