# Architecture and threat model

## Trust boundaries

Arachnin accepts a URL from an untrusted caller and makes an outbound request from a privileged server network. That transition is the primary security boundary. The system does not treat URL syntax validation as sufficient.

Before each request, including redirects, the worker:

1. accepts only HTTP and HTTPS;
2. rejects embedded credentials;
3. resolves the hostname;
4. rejects every non-global address returned by DNS;
5. pins the connection to the validated address, so DNS cannot rebind to a private host between the check and the connect;
6. disables automatic redirects;
7. bounds redirect count, elapsed request time, and streamed bytes;
8. accepts only HTML response types.

Address pinning closes the DNS-rebinding window in-process, but application validation is still only defense in depth. A public deployment should run workers in a network namespace with explicit egress policy and no route to instance metadata or private service networks.

## State transitions

```text
QUEUED → FETCHING → EXTRACTING → CHUNKING → COMPLETED
   └───────────────────────────────┬──────→ FAILED
                                   └──────→ QUEUED (bounded retry)
```

PostgreSQL owns the state machine. Redis mirrors the current status for inexpensive polling. Cache writes are best effort; cache failure never changes the authoritative state transition.

## Delivery semantics

Celery tasks use late acknowledgement. A worker crash can therefore cause at-least-once execution. Current updates are naturally idempotent for a job identifier: each successful attempt replaces the same result fields. Before supporting side effects such as vector-store writes, the worker should add a content-hash idempotency key at that downstream boundary.

## Extraction and chunk identity

Trafilatura extracts the primary document. Beautiful Soup is a conservative fallback for pages where article extraction yields nothing. Pages with fewer than twenty words are rejected rather than silently producing poor retrieval context.

Content identity is the SHA-256 hash of normalized extracted text. Chunks are deterministic word windows parameterized by size and overlap. A consumer can reproduce them without access to the original HTML.

## Data ownership

| Store | Owns | Recovery behavior |
| --- | --- | --- |
| PostgreSQL | job state, provenance, content, chunks, errors | durable source of truth |
| Redis | current status | repopulated from PostgreSQL on read |
| RabbitMQ | pending task delivery | redelivers unacknowledged work |

## Privacy

Arachnin stores extracted page text. Operators must define retention based on their use case and the source's terms. The first release does not ingest authenticated or private pages and does not accept cookies, which keeps user secrets out of jobs and logs.

## Observability roadmap

The API exposes health probes and structured error codes. A production deployment should add:

- request and task correlation IDs in structured logs;
- queue-depth, task-duration, failure-rate, and cache-hit metrics;
- OpenTelemetry traces across API, broker, and worker;
- alerts tied to user-visible service-level objectives.

Those integrations are deployment-specific and intentionally not simulated in this repository.
