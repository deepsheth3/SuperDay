# Sequence diagrams (Mermaid)

## 1) Sync chat request (happy path)

```mermaid
sequenceDiagram
  participant C as Client
  participant API as ChatApi
  participant R as Redis
  participant DB as AlloyDB
  participant V as VertexVector
  participant O as OpenSearch
  participant L as LLM

  C->>API: POST /api/chat (request_id, message)
  API->>R: GET session state
  API->>DB: resolve account (bounded timeout)
  API->>DB: metadata candidates + activity_timeline
  par lexical
    API->>O: BM25 (timeout)
  and vector
    API->>V: ANN (timeout)
  end
  API->>API: fuse + rerank
  API->>DB: hydrate chunks/comms
  API->>L: compose (timeout)
  API->>DB: txn persist turn + refs + session
  API->>C: 200 ChatResponse
```

## 2) Normalization transaction

```mermaid
sequenceDiagram
  participant W as NormalizeWorker
  participant DB as AlloyDB
  participant Q as PubSub

  W->>DB: BEGIN
  W->>DB: upsert communications + threads + participants + chunks + timeline
  W->>DB: update ingestion_events status
  W->>DB: COMMIT
  W->>Q: publish EmbedJobV1
```

## 3) Embed + index flow (LOCKED: vector + lexical in embed worker)

```mermaid
sequenceDiagram
  participant W as EmbedWorker
  participant DB as AlloyDB
  participant V as Vertex
  participant O as OpenSearch

  W->>DB: load chunk (idempotent by chunk_id+embedding_version)
  W->>W: embed text
  W->>V: upsert vector doc
  W->>O: upsert lexical doc
  W->>DB: update chunk embedding_status indexed
```

## 4) Replay flow

```mermaid
sequenceDiagram
  participant Op as Operator
  participant API as AdminReplay
  participant Q as PubSub
  participant W as NormalizeWorker
  participant DB as AlloyDB

  Op->>API: trigger replay(event_id or window)
  API->>DB: verify raw_s3_key exists
  API->>Q: publish IngestEventV1 (same idempotency)
  W->>DB: stage-aware resume from failed_stage
```

## 5) Correction / remap flow

```mermaid
sequenceDiagram
  participant A as AdminCorrection
  participant DB as AlloyDB
  participant Q as PubSub

  A->>DB: BEGIN remap + audit_log
  A->>DB: COMMIT
  A->>Q: publish ReindexJobV1 (partial scope)
```

## 6) Archiver flow

```mermaid
sequenceDiagram
  participant S as Scheduler
  participant W as ArchiverWorker
  participant V as Vertex
  participant DB as AlloyDB
  participant S3 as S3

  S->>W: ArchiveJobV1
  W->>DB: select chunks occurred_at < cutoff
  W->>S3: verify manifest / raw
  W->>V: delete vector docs (batch)
  W->>DB: update retention_state / storage_tier
```

## 7) Rehydration flow

```mermaid
sequenceDiagram
  participant C as Client
  participant API as ChatApi
  participant Q as PubSub
  participant W as RehydrationWorker
  participant S3 as S3
  participant V as Vertex

  C->>API: POST /api/rehydration/request
  API->>Q: publish RehydrationJobV1
  W->>S3: read cold raw
  W->>W: normalize + chunk + embed
  W->>V: temporary hot vectors (TTL policy)
  W->>API: job status polled
```
