# Engineering verification — 14 October 2026

The application is suitable for a **public portfolio presentation as a local, single-user MVP**. This is not a production-readiness or vulnerability-free certification. See [security scope and dependency findings](../SECURITY.md).

## Repository reviewed

The continuation started on `main` with a clean working tree at `ed20e85` (`Update 2`). GitHub's `main` matched that commit. It already included the preceding review's fixes: inflection-aware demo paragraph selection, stricter Origin validation, Latin-1 header decoding, hidden configuration input values in validation errors, regression tests, and updated pip installation instructions.

The [CI run for that application commit](https://github.com/batuhanozen/ai-document-assistant-rag/actions/runs/38469943629) completed successfully. The earlier `6d64dc0` run failed; it is not the current application state. The final publication commit adds these verification notes, security documentation, and a matching pip upgrade in the Makefile. Its CI result must be checked against its exact SHA, not inferred from the preceding run.

## Executed checks

| Check | Result and scope |
| --- | --- |
| Complete Pytest suite | **63 passed**, **93% statement coverage**, Python 3.12.7/macOS; rerun on 14 October |
| Ruff lint | Passed for `app`, `tests`, and `scripts` |
| Ruff formatting | Passed; 24 Python files already formatted |
| JavaScript syntax | `node --check app/static/app.js` passed |
| Dependency consistency | `python -m pip check` passed |
| Fresh installation | A fresh temporary Python 3.12 environment installed `.[dev]` successfully during the preceding review; that environment was reused for the final checks because the repository `.venv` had been removed |
| Server startup | Uvicorn started successfully on loopback port 8014 with an isolated temporary data directory and demo/hash settings |
| Live HTTP workflows | Health, synthetic PDF upload, retrieval, page-2 citation, history persistence, document deletion, removal of cited history, rejection of deleted document selection, malformed PDF rejection all passed |
| Chroma HTTP exposure | The Chroma server collection-management path returned 404; this app uses embedded persistent storage |
| Secret/history inspection | Pattern scan of all **53 reachable Git blobs** at the reviewed baseline found no recognized API tokens/private keys; no `.env`, private documents, or database files were tracked in that history |
| Dependency advisory audit | Completed against 96 package records in the clean demo/development environment; four distinct ChromaDB advisories remain, described in `SECURITY.md` |
| GitHub verification | Public repository, `main` branch, remote SHA match, and the successful `ed20e85` Actions result were read from GitHub |

The test suite uses temporary SQLite and Chroma databases and mocked LLM HTTP responses. It performs no paid requests or embedding-model downloads. It covers extraction, page metadata, chunk coverage/overlap, scoped retrieval, all synthetic acceptance questions, validation, upload limits, citation provenance, failure recovery, provider error/timeout handling, and deletion during answer generation.

The real Sentence Transformers integration was separately executed during the preceding review on 13 October using cached `all-MiniLM-L6-v2`: 384-dimensional normalized vectors, paraphrase similarity **0.512**, unrelated similarity **0.051**, successful Chroma retrieval and vector deletion. This was not a live LLM test and was not rerun after removal of the AI-enabled repository virtual environment.

## Browser verification and limits

During the preceding review, the real browser successfully loaded the synthetic samples, returned the corrected Aurora start date, expanded its citation, preserved history after reload, filtered to the Atlas handbook, returned the learning-budget passage, and abstained on the unsupported quantum-reactor question.

A later attempt to test the browser's file chooser for a PDF upload was **not executed**. Automatic approval review failed because its usage limit had been reached. This was not a finding that the application was unsafe. That specific browser interaction remains unverified; the successful PDF API tests do not substitute for it. Browser access was not retried through another mechanism.

## Docker assessment

Docker is not installed in this environment. No image build, `docker compose config`, container startup, health check, or volume-persistence test is claimed.

Static inspection found the intended arrangement: Python 3.12 slim image, pip upgrade before package installation, required application/static resources copied, non-root runtime user, owned data directory, one Uvicorn worker, loopback-only host port mapping, named data volume, and an HTTP health check. `.env` and private data are excluded from the image build context. Optional semantic mode still needs its first model download.

Before advertising Docker support as tested, run on a Docker-enabled machine:

```bash
cp .env.example .env  # only when no local .env already exists
# Inspect the generated configuration locally; it can include secrets from .env.
docker compose config --quiet
docker compose up --build -d
curl --fail http://127.0.0.1:8000/api/health
# Upload the supplied synthetic documents, ask a question, restart, and verify persistence.
docker compose restart
curl --fail http://127.0.0.1:8000/api/health
docker compose down
```

## Commands and environment restrictions

Network reads and loopback binding/HTTP requests initially encountered sandbox restrictions. The authorized escalated retries succeeded. GitHub metadata reads, advisory lookups, dependency installation, startup, and API smoke tests were therefore possible. The browser file-chooser action above was the only automatic-approval rejection that left a verification step incomplete. Docker absence is an environment limitation, not an approval rejection.

## Remaining scope

- No paid or live external LLM generation was exercised; provider integration was tested with mocks.
- Citation validation proves source identity and verbatim quote provenance, not entailment of every generated claim.
- Default demo answers are lexical/extractive. They must not be presented as generated semantic answers.
- No authentication, tenant isolation, rate limiting, OCR, migrations, distributed coordination, or OS-level PDF memory sandbox.
- Run one worker per data directory and keep the app on loopback. History is persistent but questions are independent turns.
- Chroma advisories remain visible in security scans. No ignore rule or unsupported downgrade was added.
- A heuristic secret scan is not a guarantee that every possible credential format was detected.

## Repeat locally

From the repository root, after following the README installation instructions:

```bash
python -m pytest --cov=app --cov-report=term-missing
ruff check app tests scripts
ruff format --check app tests scripts
node --check app/static/app.js
python -m pip check
```

To audit dependencies in a separate tooling environment, install `pip-audit` there and use `pip-audit --path <application-site-packages>`. Inspect the full results rather than treating an exit code as proof of exploitability or safety. Do not upload private documents or secrets to scanners.
