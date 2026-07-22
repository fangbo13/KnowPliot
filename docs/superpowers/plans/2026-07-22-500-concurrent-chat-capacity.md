# 500 Concurrent Chat Capacity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make KnowPilot accept and sustain 500 simultaneous chat-generation streams with bounded resources, recoverable SSE v3 delivery, graceful overload, and reproducible capacity evidence.

**Architecture:** Keep v1/v2 unchanged while adding a v3 accept-and-stream protocol. Web requests create durable Turns and enqueue work; dedicated Celery workers generate into Redis Streams; an ASGI endpoint replays and tails those streams without holding model or database work. PgBouncer, split Redis roles, admission control, metrics, and an isolated load stack make the capacity bounded and measurable.

**Tech Stack:** Django 5.0/DRF, Celery, Redis 7 Streams/Lua, PostgreSQL 16 + pgvector, PgBouncer, Gunicorn, Uvicorn ASGI, React 18/Zustand/TypeScript, Vitest, k6, Node.js SSE load runner, Docker Compose, Prometheus.

## Global Constraints

- Work only on `test/pre-launch-audit-2026-07-22` in `E:\KnowPliot`; preserve unrelated dirty-worktree changes and use path-scoped staging.
- The sustained target is 500 different users sending within 60 seconds and holding 500 simulated AI streams for 30 minutes.
- Configure `CHAT_GENERATION_TARGET_ACTIVE=500`, `CHAT_GENERATION_MAX_OUTSTANDING=625`, and a 180-second renewable reservation TTL.
- A 1000-user, two-minute spike may reject excess load only with `429 generation_capacity_reached` plus `Retry-After`; it must recover within 60 seconds.
- Keep v1/v2 behavior for one release. v3 remains behind backend `CHAT_STREAM_V3` and frontend `VITE_CHAT_STREAM_V3`, both default-off.
- Preserve current Turn idempotency, session single-writer safety, space authorization, safe SSE event names, and the prohibition on prompt/raw reasoning/CoT exposure.
- Validate platform capacity with a deterministic mock provider. Real-provider testing is opt-in and capped at 20 users, one turn each, 300 input characters, and 512 output tokens.
- Do not claim production 500-stream certification without rerunning on the eventual production hardware; this plan produces a per-replica capacity model and replica formula.
- Every behavior change follows red-green-refactor. Each task commits only its named files after focused and adjacent tests pass.

---

## File and Responsibility Map

- `backend/apps/chat/capacity.py`: Redis-backed outstanding-Turn reservations and retry hints.
- `backend/apps/chat/stream_events_v3.py`: Redis Stream append/replay/blocking-read contract and answer-delta batching.
- `backend/apps/chat/generation.py`: transport-neutral, re-entrant Turn execution generator.
- `backend/apps/chat/tasks.py`: Celery v3 generation task, retries, cleanup, and queue routing.
- `backend/apps/chat/v3_views.py`: v3 acceptance, live ASGI SSE, cancellation, and authentication boundaries.
- `frontend/src/stream/ChatStreamV3Transport.ts`: 202 acceptance, authenticated SSE consumption, cursor resume, cancel.
- `backend/apps/core/prometheus.py`: bounded, label-safe service and generation metrics.
- `docker-compose.capacity.yml` plus `deploy/capacity/`: isolated PgBouncer/Redis/gateway/provider/monitoring topology.
- `tests/stress/`: seed, REST, SSE, fault, real-provider guard, orchestration, and report generation.

---

### Task 1: Add the v3 Turn contract and capacity settings

**Files:**
- Modify: `backend/apps/chat/models.py`
- Modify: `backend/apps/chat/serializers.py`
- Create: `backend/apps/chat/migrations/0019_chatturn_protocol_version.py`
- Modify: `backend/config/settings/base.py`
- Modify: `.env.example`
- Create: `backend/apps/chat/test_chat_v3_contract.py`

**Interfaces:**
- Produces: `ChatTurn.protocol_version: PositiveSmallIntegerField` with allowed values 1, 2, 3 and default 1.
- Produces settings: `CHAT_STREAM_V3`, `CHAT_EVENTS_REDIS_URL`, `CHAT_CAPACITY_REDIS_URL`, `CHAT_GENERATION_TARGET_ACTIVE`, `CHAT_GENERATION_MAX_OUTSTANDING`, `CHAT_GENERATION_RESERVATION_TTL_SECONDS`, `CHAT_GENERATION_RETRY_AFTER_SECONDS`, `CHAT_GENERATION_WORKER_CONCURRENCY`, `CHAT_EVENT_V3_TTL_SECONDS`, `CHAT_EVENT_V3_MAXLEN`, `PROVIDER_HTTP_MAX_CONNECTIONS`, and `PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS`.
- Extends: `ChatMessageRequestSerializer.protocol_version` to accept 3 without changing defaults.

- [ ] **Step 1: Write the failing contract tests**

```python
class ChatV3ContractTest(SimpleTestCase):
    def test_serializer_accepts_v3_but_keeps_v1_default(self):
        explicit = ChatMessageRequestSerializer(data={"content": "hello", "protocol_version": 3})
        self.assertTrue(explicit.is_valid(), explicit.errors)
        self.assertEqual(explicit.validated_data["protocol_version"], 3)
        legacy = ChatMessageRequestSerializer(data={"content": "hello"})
        self.assertTrue(legacy.is_valid(), legacy.errors)
        self.assertEqual(legacy.validated_data["protocol_version"], 1)

    def test_capacity_defaults_match_approved_spec(self):
        self.assertEqual(settings.CHAT_GENERATION_TARGET_ACTIVE, 500)
        self.assertEqual(settings.CHAT_GENERATION_MAX_OUTSTANDING, 625)
        self.assertEqual(settings.CHAT_GENERATION_RESERVATION_TTL_SECONDS, 180)
        self.assertFalse(settings.CHAT_STREAM_V3)
```

- [ ] **Step 2: Run the focused test and confirm red**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_chat_v3_contract --settings=config.settings.test`

Expected: FAIL because protocol 3 and settings do not exist.

- [ ] **Step 3: Add the persisted protocol and exact configuration**

```python
# models.py, on ChatTurn
protocol_version = models.PositiveSmallIntegerField(default=1)

# serializers.py
protocol_version = serializers.ChoiceField(choices=[1, 2, 3], default=1, required=False)

# base.py
CHAT_STREAM_V3 = env_bool("CHAT_STREAM_V3", default=False)
CHAT_EVENTS_REDIS_URL = os.environ.get("CHAT_EVENTS_REDIS_URL", CHAT_COORDINATION_REDIS_URL)
CHAT_CAPACITY_REDIS_URL = os.environ.get("CHAT_CAPACITY_REDIS_URL", CHAT_EVENTS_REDIS_URL)
CHAT_GENERATION_TARGET_ACTIVE = int(os.environ.get("CHAT_GENERATION_TARGET_ACTIVE", "500"))
CHAT_GENERATION_MAX_OUTSTANDING = int(os.environ.get("CHAT_GENERATION_MAX_OUTSTANDING", "625"))
CHAT_GENERATION_RESERVATION_TTL_SECONDS = int(os.environ.get("CHAT_GENERATION_RESERVATION_TTL_SECONDS", "180"))
CHAT_GENERATION_RETRY_AFTER_SECONDS = int(os.environ.get("CHAT_GENERATION_RETRY_AFTER_SECONDS", "5"))
CHAT_GENERATION_WORKER_CONCURRENCY = int(os.environ.get("CHAT_GENERATION_WORKER_CONCURRENCY", "25"))
CHAT_EVENT_V3_TTL_SECONDS = int(os.environ.get("CHAT_EVENT_V3_TTL_SECONDS", "900"))
CHAT_EVENT_V3_MAXLEN = int(os.environ.get("CHAT_EVENT_V3_MAXLEN", "4096"))
PROVIDER_HTTP_MAX_CONNECTIONS = int(os.environ.get("PROVIDER_HTTP_MAX_CONNECTIONS", "32"))
PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS = int(os.environ.get("PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS", "16"))
```

Raise `ImproperlyConfigured` at startup when max provider connections is below generation-worker concurrency, keep-alive exceeds max connections, target active exceeds max outstanding, or any limit/TTL is non-positive. Add every setting with the same default to `.env.example`.

The migration adds the field and a check constraint named `chat_turn_protocol_version_ck` enforcing `protocol_version__in=(1, 2, 3)`.

- [ ] **Step 4: Validate migration and configuration**

Run: `docker compose exec -T backend python manage.py makemigrations --check --dry-run`

Expected: `No changes detected`.

Run: `docker compose exec -T backend python manage.py test apps.chat.test_chat_v3_contract --settings=config.settings.test`

Expected: PASS.

- [ ] **Step 5: Commit the v3 contract**

```powershell
git add -- backend/apps/chat/models.py backend/apps/chat/serializers.py backend/apps/chat/migrations/0019_chatturn_protocol_version.py backend/config/settings/base.py .env.example backend/apps/chat/test_chat_v3_contract.py
git commit -m "feat(chat): add stream v3 turn contract"
```

---

### Task 2: Implement bounded Redis generation admission

**Files:**
- Create: `backend/apps/chat/capacity.py`
- Create: `backend/apps/chat/test_generation_capacity.py`
- Modify: `backend/apps/chat/test_redis_integration.py`

**Interfaces:**
- Produces: `GenerationCapacityController(client, *, max_outstanding, ttl_seconds, clock=time.time)`.
- Produces: `reserve(turn_id) -> CapacityReservation`, `renew(turn_id) -> bool`, `release(turn_id) -> bool`, `outstanding() -> int`.
- Produces: immutable `CapacityReservation(accepted: bool, outstanding: int, retry_after_seconds: int)`.
- Redis key: `chat:v3:generation:outstanding`; members are Turn UUID strings and scores are expiry Unix seconds.

- [ ] **Step 1: Write unit tests for admission, renewal, expiry, and release**

```python
def test_reserve_rejects_at_limit_and_prunes_expired(fake_redis):
    now = [1000.0]
    gate = GenerationCapacityController(
        fake_redis, max_outstanding=2, ttl_seconds=180, clock=lambda: now[0]
    )
    self.assertTrue(gate.reserve("turn-a").accepted)
    self.assertTrue(gate.reserve("turn-b").accepted)
    rejected = gate.reserve("turn-c")
    self.assertFalse(rejected.accepted)
    self.assertEqual(rejected.retry_after_seconds, 5)
    now[0] += 181
    self.assertTrue(gate.reserve("turn-c").accepted)
    self.assertEqual(gate.outstanding(), 1)
```

Also assert idempotent reserve does not increment count, renew fails for absent members, release is idempotent, and Redis errors raise `GenerationCapacityUnavailable` rather than allowing generation.

- [ ] **Step 2: Run the test and confirm red**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_generation_capacity --settings=config.settings.test`

Expected: FAIL because `apps.chat.capacity` does not exist.

- [ ] **Step 3: Implement the atomic reservation scripts**

```python
_RESERVE_SCRIPT = """
local now = tonumber(ARGV[1])
local expires = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZSCORE', KEYS[1], ARGV[4]) then
  redis.call('ZADD', KEYS[1], expires, ARGV[4])
  return {1, redis.call('ZCARD', KEYS[1])}
end
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then return {0, count} end
redis.call('ZADD', KEYS[1], expires, ARGV[4])
return {1, count + 1}
"""

@dataclass(frozen=True)
class CapacityReservation:
    accepted: bool
    outstanding: int
    retry_after_seconds: int
```

Use compare-free idempotent membership because `turn_id` is globally unique. Wrap every Redis exception as `GenerationCapacityUnavailable` and never return accepted on an indeterminate result.

- [ ] **Step 4: Add a live Redis multi-client test**

Create 32 clients contending for a limit of 8. Assert exactly 8 distinct Turn IDs are accepted, `outstanding()==8`, renew does not change count, and releasing all members returns zero.

Run: `docker compose exec -T backend python manage.py test apps.chat.test_redis_integration.GenerationCapacityRedisTest --settings=config.settings.docker`

Expected: PASS against the Compose Redis instance.

- [ ] **Step 5: Run adjacent coordination tests and commit**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_generation_capacity apps.chat.test_stream_coordination apps.chat.test_redis_integration --settings=config.settings.test`

Expected: PASS.

```powershell
git add -- backend/apps/chat/capacity.py backend/apps/chat/test_generation_capacity.py backend/apps/chat/test_redis_integration.py
git commit -m "feat(chat): bound outstanding generation turns"
```

---

### Task 3: Add v3 Redis Streams and server-side delta batching

**Files:**
- Create: `backend/apps/chat/stream_events_v3.py`
- Create: `backend/apps/chat/test_stream_events_v3.py`
- Modify: `backend/apps/chat/test_redis_integration.py`

**Interfaces:**
- Produces: `RedisTurnStreamV3(client, turn_id, *, ttl_seconds, max_length, checkpoint=None)`.
- Produces: `append(name, data, terminal=False) -> SSEEvent`, `replay(after=0) -> list[SSEEvent]`, and `read(after=0, block_ms=15000) -> list[SSEEvent]`.
- Produces: `AnswerDeltaBatcher(max_delay_seconds=0.05, max_chars=256, clock=time.monotonic)` with `push(text) -> str | None` and `flush() -> str | None`.
- Keeps: the existing v2 `RedisTurnEventStore` and integer SSE IDs unchanged.

- [ ] **Step 1: Write failing stream and batching tests**

```python
def test_stream_replays_then_blocks_from_integer_cursor(redis_client):
    store = RedisTurnStreamV3(redis_client, TURN_ID, ttl_seconds=900, max_length=4096)
    first = store.append("phase", {"phase": "queued"})
    second = store.append("answer_delta", {"text": "hello"})
    self.assertEqual([first.sequence, second.sequence], [1, 2])
    self.assertEqual([event.sequence for event in store.replay(after=1)], [2])

def test_delta_batcher_flushes_on_size_or_50ms():
    clock = FakeClock()
    batch = AnswerDeltaBatcher(max_delay_seconds=.05, max_chars=5, clock=clock)
    self.assertIsNone(batch.push("ab"))
    self.assertEqual(batch.push("cde"), "abcde")
    self.assertIsNone(batch.push("x"))
    clock.advance(.05)
    self.assertEqual(batch.push("y"), "xy")
```

Also test forbidden payload keys, terminal checkpoint, 4096-entry trim, 15-minute TTL, malformed records, and Redis failure closure.

- [ ] **Step 2: Run and confirm red**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_stream_events_v3 --settings=config.settings.test`

Expected: FAIL because the v3 store is missing.

- [ ] **Step 3: Implement atomic append and cursor reads**

```python
_APPEND_V3_SCRIPT = """
local seq = tonumber(redis.call('GET', KEYS[1]) or '0') + 1
local id = tostring(seq) .. '-0'
redis.call('SET', KEYS[1], seq, 'EX', ARGV[3])
redis.call('XADD', KEYS[2], id, 'event', ARGV[1], 'data', ARGV[2])
redis.call('XTRIM', KEYS[2], 'MAXLEN', '~', ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[3])
return seq
"""

class RedisTurnStreamV3:
    def append(self, name, data, *, terminal=False) -> SSEEvent:
        validate_event(name, data)
        sequence = int(self.client.eval(
            _APPEND_V3_SCRIPT, 2, self.sequence_key, self.events_key,
            name, json.dumps(data, ensure_ascii=False),
            self.ttl_seconds, self.max_length,
        ))
        if terminal or sequence % EVENT_CHECKPOINT_INTERVAL == 0:
            self.checkpoint(sequence)
        return SSEEvent(sequence, name, data)

    def replay(self, *, after=0) -> list[SSEEvent]:
        rows = self.client.xrange(self.events_key, min=f"({after}-0", max="+")
        return decode_stream_rows(rows)

    def read(self, *, after=0, block_ms=15000) -> list[SSEEvent]:
        result = self.client.xread(
            {self.events_key: f"{after}-0"}, block=block_ms, count=256
        )
        return decode_xread_result(result)
```

`read()` uses `XREAD BLOCK <block_ms> STREAMS <events_key> <after>-0`; it returns an empty list on heartbeat timeout, not an exception. Reuse `_validate_safe_payload` and `SSEEvent` from `stream_events.py` rather than duplicating the safety contract.

- [ ] **Step 4: Prove concurrent writers preserve one sequence**

Run 20 threads across distinct Redis clients, each appending 10 events to one Turn. Assert sequences are exactly 1 through 200, replay order is stable, and no v2 key is created.

Run: `docker compose exec -T backend python manage.py test apps.chat.test_redis_integration.RedisTurnStreamV3IntegrationTest --settings=config.settings.docker`

Expected: PASS.

- [ ] **Step 5: Run stream suites and commit**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_stream_events_v3 apps.chat.test_stream_coordination apps.chat.test_stream_v2_views --settings=config.settings.test`

Expected: PASS.

```powershell
git add -- backend/apps/chat/stream_events_v3.py backend/apps/chat/test_stream_events_v3.py backend/apps/chat/test_redis_integration.py
git commit -m "feat(chat): add replayable v3 redis streams"
```

---

### Task 4: Extract transport-neutral, re-entrant Turn generation

**Files:**
- Create: `backend/apps/chat/generation.py`
- Create: `backend/apps/chat/test_generation_service.py`
- Modify: `backend/apps/chat/views.py`
- Modify: `backend/apps/chat/services.py`
- Modify: `backend/apps/chat/test_stream_v2_views.py`
- Modify: `backend/apps/chat/test_stream_coordination.py`

**Interfaces:**
- Produces: immutable `GenerationEvent(name: str, data: dict | list, terminal: bool = False)`.
- Produces: `iter_chat_turn(turn_id, *, cancellation_probe=None) -> Iterator[GenerationEvent]`.
- Produces: `RedisCancellationProbe(client, turn_id)` with `request()`, `requested()`, and `clear()`.
- Preserves: all v2 event order, Turn transitions, citations, metrics, safe errors, model policy, and session lease behavior.

- [ ] **Step 1: Characterize the current v2 generator before moving code**

Add tests asserting this exact domain order for a successful mocked pipeline:

```python
events = list(iter_chat_turn(turn.id, cancellation_probe=NeverCancelled()))
self.assertEqual(
    [event.name for event in events],
    ["phase", "citations", "quality", "answer_delta", "done"],
)
self.assertEqual(ChatTurn.objects.get(pk=turn.id).status, ChatTurn.STATUS_COMPLETED)
self.assertEqual(Message.objects.filter(session=turn.session, role="assistant").count(), 1)
```

Add cancellation before retrieval, cancellation after partial answer, lease loss, provider failure, persistence failure, and duplicate re-entry tests. A cancelled Turn must have no assistant message and must yield terminal `error {code: cancelled, retryable: false}`.

- [ ] **Step 2: Run the new service tests and confirm red**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_generation_service --settings=config.settings.test`

Expected: FAIL because `iter_chat_turn` is missing.

- [ ] **Step 3: Move post-accept execution into `generation.py`**

```python
@dataclass(frozen=True)
class GenerationEvent:
    name: str
    data: dict[str, Any] | list[Any]
    terminal: bool = False

def iter_chat_turn(turn_id, *, cancellation_probe=None):
    turn = ChatTurn.objects.select_related(
        "session", "space", "user", "question_message"
    ).get(pk=turn_id)
    probe = cancellation_probe or NeverCancelled()
    lease = RedisSessionLease(create_redis_client(), turn.session_id)
    if not lease.acquire():
        raise SessionBusyError()
    lease.start_renewal()
    try:
        probe.raise_if_requested()
        yield GenerationEvent("phase", {"phase": "retrieving"})
        pipeline = build_pipeline_from_turn(turn)
        for event in pipeline_events(turn, pipeline):
            probe.raise_if_requested()
            lease.ensure_owned()
            yield event
        probe.raise_if_requested()
        done_payload = persist_completed_turn(turn)
        yield GenerationEvent("done", done_payload, terminal=True)
    except GenerationCancelled:
        mark_turn_cancelled(turn)
        yield GenerationEvent(
            "error", {"code": "cancelled", "retryable": False}, terminal=True
        )
    finally:
        lease.release()
```

The function must check cancellation before retrieval, before each pipeline event, and before the saving transaction. It must close stale DB connections before external model waits and release lease/probe resources in `finally`.

- [ ] **Step 4: Adapt v2 to the shared generator without changing its wire contract**

Keep the existing v2 `meta` creation in `views.py`. Replace the duplicated retrieval/generation/persistence body with a formatter that maps `GenerationEvent("answer_delta", {"text": value})` back to v2 `answer_delta` and v1 `token` as appropriate. Snapshot existing v1/v2 tests before and after; no v1/v2 response status, header, event name, or error code may change.

- [ ] **Step 5: Run focused and full chat suites**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_generation_service apps.chat.test_stream_v2_views apps.chat.test_stream_coordination apps.chat.test_chat_turn_contract apps.rag.test_chat_generation_policy --settings=config.settings.test`

Expected: PASS.

- [ ] **Step 6: Commit the extraction**

```powershell
git add -- backend/apps/chat/generation.py backend/apps/chat/test_generation_service.py backend/apps/chat/views.py backend/apps/chat/services.py backend/apps/chat/test_stream_v2_views.py backend/apps/chat/test_stream_coordination.py
git commit -m "refactor(chat): extract reentrant turn generation"
```

---

### Task 5: Add the dedicated v3 Celery generation task

**Files:**
- Create: `backend/apps/chat/tasks.py`
- Create: `backend/apps/chat/test_generation_task.py`
- Modify: `backend/config/celery.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/apps/chat/metrics.py`
- Modify: `backend/apps/rag/embedding.py`
- Create: `backend/apps/rag/test_provider_pool_capacity.py`

**Interfaces:**
- Produces: `generate_chat_turn_v3(turn_id: str)` Celery task named `apps.chat.tasks.generate_chat_turn_v3`.
- Produces: `enqueue_chat_turn_v3(turn_id) -> AsyncResult`.
- Consumes: `iter_chat_turn`, `RedisTurnStreamV3`, `AnswerDeltaBatcher`, `GenerationCapacityController`.
- Queue: `chat_generation`; broker visibility timeout 180 seconds; task hard deadline 90 seconds enforced in application logic.

- [ ] **Step 1: Write task lifecycle tests**

Assert that a successful task writes `phase: queued`, generation events, flushed final delta, and one `done`; releases capacity and cancellation keys; and acknowledges only after terminal persistence. Assert worker loss/retry cannot create a second assistant message. Assert Redis/event-store failure marks the Turn `failed` with a safe retryable code and releases capacity.

```python
@patch("apps.chat.tasks.iter_chat_turn")
def test_task_batches_deltas_and_releases_capacity(self, generate):
    generate.return_value = iter([
        GenerationEvent("answer_delta", {"text": "a"}),
        GenerationEvent("answer_delta", {"text": "b"}),
        GenerationEvent("done", DONE, terminal=True),
    ])
    generate_chat_turn_v3.run(str(self.turn.id))
    self.assertEqual(self.replayed_names(), ["phase", "answer_delta", "done"])
    self.assertEqual(self.replayed()[1].data, {"text": "ab"})
    self.assertEqual(self.capacity.outstanding(), 0)
```

- [ ] **Step 2: Run and confirm red**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_generation_task --settings=config.settings.test`

Expected: FAIL because the task module is missing.

- [ ] **Step 3: Implement the task and routing**

```python
@shared_task(
    bind=True,
    name="apps.chat.tasks.generate_chat_turn_v3",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(TransientGenerationInfrastructureError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def generate_chat_turn_v3(self, turn_id: str):
    capacity = generation_capacity_controller()
    if not capacity.renew(turn_id):
        raise GenerationReservationLost(turn_id)
    stream = v3_event_store(turn_id)
    batch = AnswerDeltaBatcher(max_delay_seconds=0.05, max_chars=256)
    try:
        for event in iter_chat_turn(turn_id, cancellation_probe=cancel_probe(turn_id)):
            if event.name == "answer_delta":
                text = batch.push(event.data["text"])
                if text:
                    stream.append("answer_delta", {"text": text})
                continue
            pending = batch.flush()
            if pending:
                stream.append("answer_delta", {"text": pending})
            stream.append(event.name, event.data, terminal=event.terminal)
    finally:
        capacity.release(turn_id)
        cancel_probe(turn_id).clear()
```

Add `apps.chat` to Celery autodiscovery and route only this task to `chat_generation`. Set `CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"] = 180` and `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` so one worker does not hoard long tasks.

- [ ] **Step 4: Add stable generation metrics**

Extend the safe metrics contract with `queue_wait_ms`, `task_attempt`, `worker_recovered`, and `delta_batch_count`. Reject booleans for numeric values and arbitrary label strings.

- [ ] **Step 5: Make the provider HTTP pool capacity-configurable**

Replace both hard-coded `httpx.Limits(max_connections=20, max_keepalive_connections=10)` constructions with:

```python
httpx.Limits(
    max_connections=settings.PROVIDER_HTTP_MAX_CONNECTIONS,
    max_keepalive_connections=settings.PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS,
    keepalive_expiry=60,
)
```

Test defaults 32/16, an override 64/32, and startup rejection when max connections is less than worker concurrency.

- [ ] **Step 6: Run task, provider-pool, metrics, and eager-mode integration tests**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_generation_task apps.chat.test_part2_metrics apps.chat.test_generation_service apps.rag.test_provider_pool_capacity --settings=config.settings.test`

Expected: PASS.

- [ ] **Step 7: Commit the generation task**

```powershell
git add -- backend/apps/chat/tasks.py backend/apps/chat/test_generation_task.py backend/config/celery.py backend/config/settings/base.py backend/apps/chat/metrics.py backend/apps/rag/embedding.py backend/apps/rag/test_provider_pool_capacity.py
git commit -m "feat(chat): run v3 generation on dedicated queue"
```

---

### Task 6: Implement v3 acceptance, live ASGI SSE, and cancellation APIs

**Files:**
- Create: `backend/apps/chat/v3_views.py`
- Create: `backend/apps/chat/test_v3_views.py`
- Modify: `backend/apps/chat/views.py`
- Modify: `backend/apps/chat/urls.py`
- Modify: `backend/apps/chat/serializers.py`
- Modify: `backend/config/asgi.py`
- Modify: `backend/apps/chat/test_chat_turn_status_view.py`

**Interfaces:**
- v3 POST success: `202` JSON with `turn_id`, `session_id`, `client_request_id`, `status`, `events_url`, `status_url`, `cancel_url`; `Location` equals `status_url`.
- Capacity rejection: `429 {code: generation_capacity_reached, retryable: true, retry_after_seconds: 5}` plus `Retry-After: 5`.
- Existing endpoint becomes live for v3: `GET /api/v1/chat/turns/{turn_id}/events/?after=N`.
- New endpoint: `POST /api/v1/chat/turns/{turn_id}/cancel/` returning idempotent `202 {status: cancelling}`.

- [ ] **Step 1: Write failing acceptance and authorization tests**

Cover successful 202, transaction-on-commit enqueue, duplicate request reuse, completed duplicate reuse, admission rejection, Redis unavailable 503, enqueue failure cleanup, cross-user 404, revoked-space denial, and v1/v2 unchanged.

```python
response = self.client.post(
    reverse("chat-send-message", kwargs={"session_id": self.session.id}),
    {"content": "hello", "client_request_id": str(CLIENT_ID), "protocol_version": 3},
    format="json",
)
self.assertEqual(response.status_code, 202)
self.assertEqual(response.data["status"], "accepted")
self.assertEqual(response["Location"], response.data["status_url"])
self.assertEqual(ChatTurn.objects.get(pk=response.data["turn_id"]).protocol_version, 3)
```

- [ ] **Step 2: Run and confirm red**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_v3_views --settings=config.settings.test`

Expected: FAIL because the v3 branch and cancel route are absent.

- [ ] **Step 3: Add the v3 accept branch before legacy lease acquisition**

After `begin_chat_turn` dispositions are resolved but before the current request-owned session lease, dispatch protocol 3 to `accept_chat_turn_v3(turn)`. The function must:

```python
def accept_chat_turn_v3(turn, *, capacity, event_store, enqueue):
    reservation = capacity.reserve(turn.id)
    if not reservation.accepted:
        transition_chat_turn(turn, ChatTurn.STATUS_FAILED, error_code="capacity_reached")
        return capacity_response()
    event_store.append("meta", v3_meta(turn))
    event_store.append("phase", {"phase": "queued"})
    transaction.on_commit(lambda: enqueue_with_failure_cleanup(turn.id))
    return accepted_response(turn)
```

If `CHAT_STREAM_V3` is false, a protocol 3 request returns `409 {code: stream_protocol_unavailable}` and does not create model work.

- [ ] **Step 4: Implement authenticated ASGI stream iteration**

Use a plain Django async view so `StreamingHttpResponse` receives an async iterator under ASGI. Authenticate JWT and load the owned Turn through `sync_to_async(load_owned_turn, thread_sensitive=True)`. For v3, replay once and call the Redis async client's blocking `xread`; yield `: heartbeat\n\n` after 15 seconds without data. Recheck current space authorization every 30 seconds and end silently if revoked. For v1/v2 Turns, return the existing finite replay semantics.

- [ ] **Step 5: Implement idempotent explicit cancellation**

For active owned Turns, set the Redis cancellation key with the Turn TTL and return `cancelling`. For already cancelled return the same response; for completed/failed return `409 turn_not_cancellable`. Never treat an SSE disconnect as cancellation.

- [ ] **Step 6: Run API, auth, and compatibility suites**

Run: `docker compose exec -T backend python manage.py test apps.chat.test_v3_views apps.chat.test_chat_turn_status_view apps.chat.test_stream_v2_views --settings=config.settings.test`

Expected: PASS with v1/v2 snapshots unchanged.

- [ ] **Step 7: Commit the v3 API**

```powershell
git add -- backend/apps/chat/v3_views.py backend/apps/chat/test_v3_views.py backend/apps/chat/views.py backend/apps/chat/urls.py backend/apps/chat/serializers.py backend/config/asgi.py backend/apps/chat/test_chat_turn_status_view.py
git commit -m "feat(chat): add async v3 accept and live event APIs"
```

---

### Task 7: Add the frontend v3 transport and preserve background Turns

**Files:**
- Create: `frontend/src/stream/ChatStreamV3Transport.ts`
- Create: `frontend/src/stream/ChatStreamV3Transport.test.ts`
- Modify: `frontend/src/stream/ChatStreamProtocol.ts`
- Modify: `frontend/src/stream/ChatStreamProtocol.test.ts`
- Modify: `frontend/src/store/chatStore.ts`
- Modify: `frontend/src/store/__tests__/chatStore.stream-recovery.test.ts`
- Modify: `frontend/src/store/__tests__/chatStore.stream-lifecycle.test.ts`
- Modify: `frontend/src/components/chat/ChatComposer.tsx`
- Modify: `frontend/src/i18n/locales/en/chat.json`
- Modify: `frontend/src/i18n/locales/zh/chat.json`
- Modify: `.env.example`

**Interfaces:**
- Produces: `AcceptedChatTurnV3` with exact API fields from Task 6.
- Produces: `ChatStreamV3Transport.accept()`, `.consume()`, `.cancel()`, and `.detach()`.
- Extends: `SessionTurnState.protocolVersion` to `1 | 2 | 3 | null`.
- Feature flag: `VITE_CHAT_STREAM_V3=false` by default.

- [ ] **Step 1: Write transport tests before integration**

```typescript
it('accepts 202 then resumes SSE from the last confirmed sequence', async () => {
  const transport = new ChatStreamV3Transport({ fetch: fetchMock, baseUrl: '/api/v1' });
  const accepted = await transport.accept(request);
  await transport.consume(accepted, { after: 7, onEvent });
  expect(fetchMock).toHaveBeenNthCalledWith(2,
    `${accepted.events_url}?after=7`,
    expect.objectContaining({ headers: expect.objectContaining({ 'Last-Event-ID': '7' }) }),
  );
});
```

Also cover 202 schema validation, 429 Retry-After, mismatched identities, duplicate event IDs, 1/2/4/8-second reconnect, terminal stop, detach without cancel, explicit cancel, and revoked 403.

- [ ] **Step 2: Run and confirm red**

Run: `npm.cmd test -- --run src/stream/ChatStreamV3Transport.test.ts`

Workdir: `frontend`

Expected: FAIL because the transport does not exist.

- [ ] **Step 3: Implement the isolated v3 transport**

```typescript
export interface AcceptedChatTurnV3 {
  turn_id: string;
  session_id: string;
  client_request_id: string;
  status: 'accepted' | 'completed';
  events_url: string;
  status_url: string;
  cancel_url: string;
}

export class ChatStreamV3Transport {
  accept(request: V3SendRequest, signal?: AbortSignal): Promise<AcceptedChatTurnV3>;
  consume(turn: AcceptedChatTurnV3, options: ConsumeV3Options): Promise<V3Terminal>;
  cancel(turn: AcceptedChatTurnV3): Promise<void>;
  detach(sessionId: string): void;
}
```

Use authenticated `fetch`, not native `EventSource`, because JWT and `X-Space-Id` headers are required. Reuse `StoreSSEDecoder` and the existing safe event validator after extending `meta.protocol_version` to allow 3.

- [ ] **Step 4: Integrate v3 behind the default-off flag**

When enabled, `sendMessage` sends protocol 3, records the accepted identity, and delegates stream consumption. Route changes detach only the visible consumer; `turnsBySession` retains the cursor and state. Returning to a session reconnects from `lastEventSeq`. The Stop action invokes cancel for v3 and preserves the current local abort behavior for v1/v2.

- [ ] **Step 5: Add overload UX without automatic retry storms**

Map `generation_capacity_reached` to localized text that includes the server-provided retry seconds. Enable the send button after the countdown, but do not automatically POST again. Add exact English and Chinese strings.

- [ ] **Step 6: Run frontend stream and store suites**

Run: `npm.cmd test -- --run src/stream/ChatStreamV3Transport.test.ts src/stream/ChatStreamProtocol.test.ts src/store/__tests__/chatStore.stream-recovery.test.ts src/store/__tests__/chatStore.stream-lifecycle.test.ts`

Workdir: `frontend`

Expected: PASS.

- [ ] **Step 7: Commit the frontend v3 client**

```powershell
git add -- frontend/src/stream/ChatStreamV3Transport.ts frontend/src/stream/ChatStreamV3Transport.test.ts frontend/src/stream/ChatStreamProtocol.ts frontend/src/stream/ChatStreamProtocol.test.ts frontend/src/store/chatStore.ts frontend/src/store/__tests__/chatStore.stream-recovery.test.ts frontend/src/store/__tests__/chatStore.stream-lifecycle.test.ts frontend/src/components/chat/ChatComposer.tsx frontend/src/i18n/locales/en/chat.json frontend/src/i18n/locales/zh/chat.json .env.example
git commit -m "feat(frontend): consume recoverable chat stream v3"
```

---

### Task 8: Add capacity topology, connection bounds, and metrics

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/config/settings/base.py`
- Create: `backend/apps/core/prometheus.py`
- Create: `backend/apps/core/test_prometheus.py`
- Modify: `backend/apps/core/urls.py`
- Create: `docker-compose.capacity.yml`
- Create: `deploy/capacity/pgbouncer.ini`
- Create: `deploy/capacity/userlist.txt.example`
- Create: `deploy/capacity/nginx.conf`
- Create: `deploy/capacity/prometheus.yml`

**Interfaces:**
- Adds runtime packages: `uvicorn[standard]>=0.30,<1` and `prometheus-client>=0.20,<1`.
- Internal metrics: `GET /api/v1/internal/metrics/`, guarded by `PROMETHEUS_METRICS_TOKEN` and never exposed through the public frontend proxy.
- Capacity services: `pgbouncer`, `redis-broker`, `redis-events`, `web`, `stream-gateway`, `chat-generation-worker`, and `prometheus`.

- [ ] **Step 1: Write metric-label and authorization tests**

Assert missing/wrong metric token returns 404, correct internal token returns Prometheus text, route labels use resolved route names rather than raw UUID paths, and no user ID/session ID/Turn ID appears as a metric label.

- [ ] **Step 2: Run and confirm red**

Run: `docker compose exec -T backend python manage.py test apps.core.test_prometheus --settings=config.settings.test`

Expected: FAIL because the metrics endpoint is absent.

- [ ] **Step 3: Implement bounded metrics**

Define counters/histograms/gauges for HTTP route/status/latency, SSE connections/reconnects, generation outstanding/queued/active, queue wait, first event, first answer, total duration, provider failures, task retries, lease loss, and cancellation. Labels are fixed enums or Django route names only.

- [ ] **Step 4: Build the isolated capacity overlay**

The overlay must use project name `knowpliot-capacity`, separate named volumes, and explicit resource limits. PgBouncer uses transaction pooling, pool size 80, reserve pool 10; Django capacity settings use `CONN_MAX_AGE=0` and `DISABLE_SERVER_SIDE_CURSORS=True`. `redis-broker` uses `noeviction`; `redis-events` uses an explicit memory ceiling and `volatile-lru`.

Start commands:

```yaml
stream-gateway:
  command: uvicorn config.asgi:application --host 0.0.0.0 --port 8001 --workers 2
chat-generation-worker:
  command: celery -A config worker -Q chat_generation --pool=threads --concurrency=25 --prefetch-multiplier=1 -l info
```

The capacity Nginx routes only `/api/v1/chat/turns/*/events/` to `stream-gateway`; all other API traffic goes to `web`. Buffering is off and heartbeat-compatible timeouts are 120 seconds.

- [ ] **Step 5: Validate configuration without starting load**

Run: `docker compose -p knowpliot-capacity -f docker-compose.capacity.yml config --quiet`

Expected: exit 0.

Run: `docker compose -p knowpliot-capacity -f docker-compose.capacity.yml build web stream-gateway chat-generation-worker`

Expected: all images build successfully.

- [ ] **Step 6: Run metric tests and dependency checks**

Run: `docker compose exec -T backend python manage.py test apps.core.test_prometheus --settings=config.settings.test`

Expected: PASS.

- [ ] **Step 7: Commit capacity infrastructure**

```powershell
git add -- backend/pyproject.toml backend/config/settings/base.py backend/apps/core/prometheus.py backend/apps/core/test_prometheus.py backend/apps/core/urls.py docker-compose.capacity.yml deploy/capacity/pgbouncer.ini deploy/capacity/userlist.txt.example deploy/capacity/nginx.conf deploy/capacity/prometheus.yml
git commit -m "feat(platform): add bounded capacity topology and metrics"
```

---

### Task 9: Create the isolated 500-stream load laboratory

**Files:**
- Create: `tests/stress/mock-provider.mjs`
- Create: `tests/stress/k6-rest-capacity.js`
- Create: `tests/stress/sse-capacity.mjs`
- Create: `tests/stress/run-capacity.mjs`
- Create: `tests/stress/fault-capacity.mjs`
- Create: `tests/stress/report-capacity.mjs`
- Create: `tests/stress/capacity-profile.json`
- Create: `backend/apps/chat/management/commands/seed_capacity_data.py`
- Create: `backend/apps/chat/test_seed_capacity_data.py`
- Modify: `tests/stress/README.md`
- Modify: `docker-compose.capacity.yml`

**Interfaces:**
- Seeder creates 5000 deterministic users, 10 spaces, 20 sessions per user, 40 messages per session, and synthetic notification/audit data in the isolated database only.
- Mock provider implements compatible `/v1/embeddings` and streaming `/v1/chat/completions`; delay, token count, error rate, and disconnect rate are environment controlled.
- Orchestrator emits `artifacts/capacity/latest/summary.json` and `report.md` with no credentials.

- [ ] **Step 1: Write deterministic seeder and mock-provider tests**

Assert two seed runs produce the same row counts without duplicates. Assert the mock provider streams exactly the configured safe tokens and never logs Authorization headers or prompts.

- [ ] **Step 2: Implement exact load profiles**

`capacity-profile.json` contains:

```json
{
  "smoke": {"users": 10, "streams": 2, "durationSeconds": 120},
  "stairs": {"streams": [50, 100, 200, 300, 400, 500], "secondsPerStage": 300},
  "steady": {"users": 500, "streams": 500, "rampSeconds": 60, "durationSeconds": 1800},
  "spike": {"from": 500, "to": 1000, "durationSeconds": 120},
  "realProvider": {"users": 20, "turnsPerUser": 1, "maxInputChars": 300, "maxOutputTokens": 512}
}
```

The REST mix uses fixed arrival rates for spaces, sessions, messages, unread count, Turn status, and v3 acceptance. The SSE runner verifies strictly increasing IDs, one terminal event, no duplicate answer text, and cursor recovery after controlled disconnect.

- [ ] **Step 3: Encode automatic SLO thresholds**

The runner exits nonzero if send acceptance p95 exceeds 800ms, ordinary reads p95 exceeds 500ms, read p99 exceeds 1.5s, first application event p95 exceeds 1.5s, successful terminal rate is below 99%, unexpected errors exceed 0.1%, or any duplicate/lost event occurs. During the 1000-user spike, expected capacity 429s do not count as errors only when every response includes `Retry-After` and baseline recovers in 60 seconds.

- [ ] **Step 4: Add guarded real-provider mode**

Real calls require all of `ENABLE_REAL_PROVIDER_STRESS=1`, `REAL_PROVIDER_MAX_USERS=20`, and a nonempty provider key. The runner rejects larger values before network access, truncates prompts to 300 characters, requests at most 512 output tokens, and never prints the credential.

- [ ] **Step 5: Add fault injection**

At 500-stream steady state, restart exactly one `web`, then one `stream-gateway`, then one `chat-generation-worker`. Assert cursor reconnect, task redelivery, single assistant persistence, and recovery to baseline within 60 seconds. Never restart PostgreSQL or delete volumes in the fault scenario.

- [ ] **Step 6: Prove smoke load and cleanup**

Run: `node tests/stress/run-capacity.mjs --profile smoke --cleanup`

Expected: exit 0, smoke SLO pass, temporary project `knowpliot-capacity` stopped, isolated volumes removed, current `knowpliot` Compose project untouched.

- [ ] **Step 7: Commit the load laboratory**

```powershell
git add -- tests/stress/mock-provider.mjs tests/stress/k6-rest-capacity.js tests/stress/sse-capacity.mjs tests/stress/run-capacity.mjs tests/stress/fault-capacity.mjs tests/stress/report-capacity.mjs tests/stress/capacity-profile.json tests/stress/README.md backend/apps/chat/management/commands/seed_capacity_data.py backend/apps/chat/test_seed_capacity_data.py docker-compose.capacity.yml
git commit -m "test(capacity): add isolated 500-stream load laboratory"
```

---

### Task 10: Run full regression, capacity discovery, and final certification report

**Files:**
- Create: `audit_reports/performance/500-concurrent-chat-capacity-report.md`
- Modify: `docs/superpowers/plans/2026-07-22-500-concurrent-chat-capacity.md` (checkboxes only)
- Modify only source/test/config files required to fix evidenced failures from the commands below.

**Interfaces:**
- Produces: measured safe concurrency `C` for one generation-worker replica and recommended replica count `ceil(500 / (C * 0.7))`.
- Produces: separate platform/mock-provider result and 20-user real-provider sample result.

- [ ] **Step 1: Run all backend checks and tests**

Run:

```powershell
docker compose exec -T backend python manage.py check --deploy --settings=config.settings.prod
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py test --settings=config.settings.test
```

Expected: all exit 0. Pre-existing deployment warnings must be listed in the report; no new warning may be ignored.

- [ ] **Step 2: Run the complete frontend quality gate**

Run:

```powershell
Set-Location frontend
npm.cmd test -- --run
npm.cmd run typecheck
npm.cmd run build
Set-Location ..
```

Expected: all tests pass, TypeScript exits 0, production build and bundle budget pass, and no unexplained application `console.error` appears.

- [ ] **Step 3: Capture the single-replica baseline and staircase**

Run:

```powershell
node tests/stress/run-capacity.mjs --profile smoke
node tests/stress/run-capacity.mjs --profile stairs --replicas 1
```

Expected: the runner identifies the highest stage satisfying all SLOs and records CPU, RSS, DB connections, Redis memory, provider pool wait, queue wait, and errors. Do not extrapolate from a stage that violates an SLO.

- [ ] **Step 4: Calculate and provision the measured replica count**

Let `C` be the highest safe single-replica stream count. Compute `N = ceil(500 / (C * 0.7))`; scale generation workers to `N`, then scale Web and stream-gateway replicas until their peak CPU is below 70% and p95 thresholds pass. Record exact Compose scale commands and resource limits in the report.

- [ ] **Step 5: Run the 500-stream steady and 1000-stream spike tests**

Run:

```powershell
node tests/stress/run-capacity.mjs --profile steady --replicas $env:CAPACITY_WORKER_REPLICAS
node tests/stress/run-capacity.mjs --profile spike --replicas $env:CAPACITY_WORKER_REPLICAS
```

Expected: all Section 1 spec thresholds pass; excess spike requests are bounded 429s with Retry-After; baseline recovers within 60 seconds.

- [ ] **Step 6: Run fault injection at target load**

Run: `node tests/stress/run-capacity.mjs --profile fault --replicas $env:CAPACITY_WORKER_REPLICAS`

Expected: no duplicate assistant message, no lost confirmed event, reconnect succeeds, redelivered task converges, and each component restart recovers within 60 seconds.

- [ ] **Step 7: Run the opt-in 20-user real-provider sample only when credentials and cost authorization are present**

Run:

```powershell
$env:ENABLE_REAL_PROVIDER_STRESS='1'
$env:REAL_PROVIDER_MAX_USERS='20'
node tests/stress/run-capacity.mjs --profile real-provider
```

Expected: no more than 20 model calls. Report provider 429s, time to first answer, completion latency, token usage, and estimated cost separately. If credentials or explicit authorization are absent, record `not run: external cost authorization unavailable`; do not substitute mock results.

- [ ] **Step 8: Write the final report and verify cleanup**

The report must include hardware/container limits, Git commit, dataset size, every command, SLO table, per-stage metrics, failure boundary, replica formula, 30% headroom, spike/fault evidence, real-provider status, remaining risks, and the statement that production hardware is not yet certified.

Run:

```powershell
docker compose -p knowpliot-capacity -f docker-compose.capacity.yml ps -a
git diff --check
git status --short
```

Expected: no capacity containers or temporary volumes remain; no credentials, generated tokens, database dumps, or unowned files are staged.

- [ ] **Step 9: Commit only verified task-owned closure files**

```powershell
git add -- audit_reports/performance/500-concurrent-chat-capacity-report.md docs/superpowers/plans/2026-07-22-500-concurrent-chat-capacity.md
git commit -m "docs(capacity): record 500-stream verification evidence"
```

Do not stage the whole worktree. If a failure requires changing a file that already contains unrelated user edits, stage only the exact task-owned hunks and mention the overlap in the final handoff.
