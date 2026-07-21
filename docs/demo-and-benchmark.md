# Public demo and benchmark

The public demo uses a single host with one exposed component: Caddy. Caddy provisions TLS and forwards requests to the React workbench; the workbench forwards `/api/` to FastAPI. PostgreSQL, Redis, RabbitMQ, the API, and the worker have no host ports. Only the worker joins a separate egress network so it can fetch public pages.

## Prerequisites

- A Linux host with Docker Engine and Compose v2
- A DNS `A`/`AAAA` record pointing the demo hostname to that host
- Inbound TCP 80 and TCP/UDP 443 allowed by the host firewall

The production profile is provider-neutral. Record the host size and worker concurrency beside benchmark results so another person can interpret them.

## Deploy

Clone the repository on the host, then create the production environment file:

```bash
cp deploy/.env.production.example deploy/.env.production
chmod 600 deploy/.env.production
```

Replace both passwords with independent random values and set `DOMAIN` and `ACME_EMAIL`.

The production stack runs pre-built, multi-architecture images published to GHCR by the `Release` workflow (the same digest runs on x86 or Ampere/arm64 hosts, so nothing is compiled on the box). Deploy and redeploy with the helper script:

```bash
./deploy/deploy.sh
```

It validates the compose file, pulls the referenced images, applies pending migrations through the `api` entrypoint, restarts the stack, and prunes superseded images. It is idempotent and safe to re-run or schedule.

If the GHCR packages are private, authenticate the host once before the first deploy:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u m1hawk005 --password-stdin
```

Pin an explicit release for reproducible deploys and easy rollback by setting `BACKEND_IMAGE` / `FRONTEND_IMAGE` in `deploy/.env.production` (see the example file). To build from source on the host instead of pulling, point those variables at locally built tags.

Verify the externally visible paths:

```bash
curl --fail https://demo.example.com/api/openapi.json
curl --fail https://demo.example.com/api/docs
```

Do not publish the RabbitMQ management interface or a data-store port. Keep the host patched, restrict SSH at the firewall, and arrange encrypted volume backups before treating submitted content as durable.

## Build a representative dataset

`benchmark/urls.example.csv` is a smoke-test dataset, not evidence for a final portfolio claim. Copy it to `benchmark/urls.csv` and expand it to 100 permitted public pages across the categories the project is intended to ingest. Keep the file stable between releases and record material dataset changes in version control.

Avoid pages that require authentication, execute primarily in JavaScript, prohibit automated access, or contain personal/confidential data. A defensible dataset includes different publishers, page lengths, document structures, and redirect behavior rather than 100 near-identical documentation pages.

## Run the benchmark

The runner uses only the Python standard library and exercises the public API, RabbitMQ-backed worker, PostgreSQL state, Redis status cache, network boundary, extraction, and result endpoint.

```bash
python benchmark/run.py \
  --base-url https://demo.example.com \
  --urls benchmark/urls.csv \
  --concurrency 2
```

It writes `benchmark/results/latest.json` with raw measurements and `benchmark/results/latest.md` with a human-readable evidence report. Commit dated reports when they support a release; regenerate headline numbers from raw measurements rather than editing them.

## Interpreting results

The success rate counts only jobs that reach `COMPLETED` and whose result can be retrieved. End-to-end latency begins immediately before submission and ends after result retrieval. SSRF probes count as blocked only when the public endpoint returns HTTP 422 with the expected stable code.

Run at least three trials after the deployment is warm. Report the median trial, host specification, worker concurrency, dataset commit, and timestamp. Treat publisher throttling, remote downtime, and unsupported page types as named failure categories rather than deleting them after seeing the result.

An evidence-backed portfolio statement can then be generated directly from the report, for example:

> On a 100-page, versioned evaluation set, Arachnin completed 96% of jobs, blocked 7/7 direct SSRF probes, and produced retrieval-ready chunks at 2.4 seconds median end-to-end latency (2-worker demo deployment, July 2026).

Use actual report values in place of the example. This benchmark validates ingestion reliability and security behavior; it does not claim retrieval relevance. A later evaluation should measure downstream retrieval quality against a labelled question set.
