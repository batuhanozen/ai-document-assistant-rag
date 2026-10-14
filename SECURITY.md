# Security scope and known dependency findings

This project is a **local, single-user portfolio application**. It is not designed for public network deployment. Bind to loopback, use synthetic demonstration documents, and keep `.env`, data directories, private documents, and model caches out of Git.

## Audit snapshot: 14 October 2026

`pip-audit` completed against the clean demo/development installation. It reported five advisory records for `chromadb==1.5.9`, representing **four distinct advisories** because one record was duplicated. No patched versions were supplied by the audit for those findings. The project itself is unpublished on PyPI and cannot be checked against PyPI advisories; its source was reviewed separately.

| Advisory | Reported issue |
| --- | --- |
| [CVE-2026-45829 / GHSA-f4j7-r4q5-qw2c](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c) | Chroma server collection creation can load attacker-specified remote model code |
| [CVE-2026-45833 / GHSA-36p7-vc44-83pf](https://github.com/advisories/GHSA-36p7-vc44-83pf) | Chroma server collection updates can load attacker-specified remote model code |
| [CVE-2026-45830 / GHSA-2wm9-hf6c-p5cr](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr) | Missing tenant-level authorization validation in the Chroma server |
| [CVE-2026-45831 / GHSA-xph7-9rjv-w5fr](https://github.com/advisories/GHSA-xph7-9rjv-w5fr) | Chroma server RBAC does not scope permissions to individual resources |

**Applicability assessment:** the reviewed application constructs an embedded `PersistentClient`, supplies its own embeddings, sets the collection's embedding function to `None`, and does not launch or mount Chroma's HTTP server. Users cannot configure model repositories through the application API. The separately configured Sentence Transformer uses `trust_remote_code=False`. A live request to Chroma's collection-management HTTP path returned 404.

These observations mean the server attack paths described above were not exposed by the reviewed application configuration. They do **not** remove the vulnerable dependency or prove it is safe in other deployments. Do not expose a separate Chroma server using this installation. Reassess these findings before adding remote Chroma, collection configuration APIs, multi-tenancy, or public access. Upgrade when a verified fix is available. The audit is intentionally not silenced with ignore rules.

The previous environment's `pip==24.2` also had known advisories. It was upgraded to `26.2.1`; the subsequent scan no longer flagged pip. README, CI, Docker, and Makefile setup instructions request `pip>=26.2` before installing application dependencies.

## Existing controls

- Bounded request and upload sizes; file-extension/signature/encoding checks; sanitized display names.
- Separate PDF parsing process with a timeout; page, extracted-character, and chunk limits.
- Validated question schemas; same-origin mutation checks including scheme; loopback host allowlist.
- Plain-text frontend rendering, content-security policy, no framing, and no-store response headers.
- Server-side provider secrets; sanitized provider errors; configuration errors hide raw input values.
- Retrieved content is untrusted context. Generated citations must reference retrieved IDs and exact quotes.
- Failed/deleting documents are excluded from retrieval; interrupted storage operations have recovery paths.

## Limitations

There is no authentication, authorization, rate limiting, tenant isolation, or operating-system memory limit on the PDF subprocess. Local processes that can access the API are trusted. Prompt injection defenses and citation checks are best effort; neither proves that all generated statements are true. Provider timeouts are I/O inactivity limits, not an end-to-end generation deadline. SQLite/Chroma deletion is logical deletion rather than forensic erasure.

Full LLM mode sends questions and retrieved excerpts to the configured provider. Do not use private documents without evaluating that provider's data handling. The default demo makes no LLM calls.

## Reporting a concern

Do not post credentials, private documents, or working exploit payloads in a public issue. Use GitHub's private vulnerability reporting mechanism if enabled for this repository; otherwise contact the repository owner privately before sharing sensitive details.

See [verification notes](docs/verification.md) for the checks actually executed and the remaining browser, Docker, and live-LLM test limitations.
