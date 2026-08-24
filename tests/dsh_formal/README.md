# DSH formal-profile tests

The files in this directory are an out-of-tree-shaped, test/local reference adapter. They
pin the four JC MCP tools, fail closed on startup/session drift, and permit a formal marker
only for exact bytes re-read after current-session verification.

They do not configure or claim a production DSH deployment. DSH release pinning, separate
service identity, authenticated transport, and topology remain H9-00 inputs.
