# Lock patterns

Four Claudes (Eric's, Glitch's, Jay's, Smathers') will eventually write to the same `videos` rows. The schema does not trust callers to do the right thing. The Rust sync adapter is the single chokepoint that holds the row lock.

## The rule

> Every write that depends on the current state of a `videos` row must hold `SELECT ... FOR UPDATE` on that row inside a transaction. The lock is released when the transaction commits or rolls back.

If you're writing a fire-and-forget log entry to `stage_events`, you don't need the lock — `stage_events` is append-only.

If you're advancing a stage, flipping a gate, or writing any computed-from-current-state field, you need the lock.

## The canonical pattern (Rust, sqlx)

```rust
let mut tx = pool.begin().await?;

// 1. Lock the row. This blocks until any other writer commits.
let video = sqlx::query_as::<_, Video>(
    "SELECT * FROM videos WHERE id = $1 FOR UPDATE"
)
.bind(video_id)
.fetch_one(&mut *tx)
.await?;

// 2. Check current state against expected. If another writer raced ahead,
//    bail out and let the caller retry.
if video.stage != expected_stage {
    tx.rollback().await?;
    return Err(LockError::StaleRead { expected: expected_stage, actual: video.stage });
}

// 3. Mutate.
sqlx::query("UPDATE videos SET stage = $1, gate_status = $2 WHERE id = $3")
    .bind(next_stage)
    .bind(gate_status::Pending)
    .bind(video_id)
    .execute(&mut *tx)
    .await?;

// 4. Append event log entry in the same transaction.
sqlx::query("INSERT INTO stage_events (video_id, actor, from_stage, to_stage, event_type) VALUES ($1, $2, $3, $4, $5)")
    .bind(video_id)
    .bind(actor)
    .bind(video.stage)
    .bind(next_stage)
    .bind("stage_advance")
    .execute(&mut *tx)
    .await?;

tx.commit().await?;
```

## Why this works

`SELECT ... FOR UPDATE` puts a row-level lock on the targeted row. Other transactions that try to `SELECT ... FOR UPDATE` the same row will block until this transaction commits or rolls back. Reads without `FOR UPDATE` are not affected — Postgres' MVCC means they see the pre-transaction state.

This means:

1. Two bots cannot simultaneously advance the same video to different next-stages.
2. The event log and the videos table never disagree, because both are written in the same transaction.
3. If a write races, the stale-read check at step 2 catches it and the caller retries with fresh state.

## Why not advisory locks

Advisory locks (`pg_advisory_lock`) are cheaper but require disciplined cleanup and don't tie to row state. `SELECT ... FOR UPDATE` is automatically released on transaction end and is the standard Postgres pattern for this exact problem.

## Why not optimistic concurrency

We could add a `version` column and `WHERE version = $expected`. That works but requires every writer to remember to bump the version. The lock is uglier syntactically but harder to get wrong — and a stage advance is rarely the hot path.

## Notion sync

Notion → Postgres direction: when a webhook fires from Notion, the adapter takes a lock on the matching row by `notion_page_id`, reads the Notion state, and writes through.

Postgres → Notion direction: a background task scans `stage_events` for entries newer than the last-synced cursor and pushes the matching `videos` row state up to Notion. Read-only on Postgres, no lock needed.

If the two directions race (Notion edit + Postgres write at the same instant), Postgres wins on the next reconciliation pass because Postgres is the source of truth.
