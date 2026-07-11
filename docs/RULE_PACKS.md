# Rule packs and promotion

A pack manifest binds pack ID/version, jurisdiction, kind/status, governing dates, rule/source/config file hashes, content digest, source commit, and inventory.

The runtime keeps two distinct sets:

- corpus: all retained rules available for governance, cleaning, lookup, and training export;
- reasoning-eligible: rules with explicit source anchors that pass pack integrity and official admission.

Rules without an authority field remain `UNVERIFIED + CANDIDATE_ONLY`. JC never guesses a source from a rule name or description. Governance may report promotion blockers but cannot promote automatically.

Current bundled inventories are read from manifests/runtime rather than prose. `cn-legacy-corpus` contains 21,144 candidate rules and zero reasoning-eligible rules. `cn-official` contains zero rules and is intentionally not reasoning-ready. HK/US legacy packs are also corpus material, not silent formal fallbacks.
