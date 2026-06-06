-- rt-yt-automations · migration 0001 · initial schema
--
-- Mirrors the 7 Notion databases under "YouTube Automations" 1:1, plus a
-- stage_events event log that is *the* learning corpus over time.
--
-- Source of truth: Postgres. Notion mirrors via the Rust sync adapter.
-- If Postgres and Notion disagree, Postgres wins.
--
-- Concurrency: every bot must hold a SELECT ... FOR UPDATE lock on the
-- target row before mutating it. Enforced at the adapter layer; see
-- docs/lock-patterns.md. The schema does NOT trust callers to do this --
-- the adapter is the single chokepoint that holds the lock.
--
-- Naming: snake_case columns. notion_page_id on every entity table so the
-- sync adapter can match rows by Notion ID without a second lookup.
--
-- Required Postgres extensions: pgcrypto (for gen_random_uuid).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================
-- ENUMS
-- =============================================================

CREATE TYPE pillar AS ENUM (
    'Faceless',
    'Talking-Head',
    'Music',
    'Lifestyle',
    'Other'
);

CREATE TYPE channel_status AS ENUM (
    'Planning',
    'Live',
    'Paused',
    'Killed'
);

CREATE TYPE trend_status AS ENUM (
    'Rising',
    'Flat',
    'Declining'
);

CREATE TYPE topic_status AS ENUM (
    'Researching',
    'Ranked',
    'Locked',
    'Killed'
);

CREATE TYPE trends_check AS ENUM (
    'Pass',
    'Fail',
    'Pending'
);

CREATE TYPE video_stage AS ENUM (
    '01-Niche',
    '02-Topic',
    '03-Script',
    '04-VO',
    '05-Thumb',
    '06-Broll',
    '07-Assembly',
    '08-Publish',
    '09-Measure',
    '10-Repurpose',
    'Complete',
    'Killed'
);

CREATE TYPE gate_status AS ENUM (
    'Pending',
    'Approved',
    'Blocked',
    'Killed'
);

CREATE TYPE script_status AS ENUM (
    'Briefed',
    'Drafting',
    'QA',
    'Locked',
    'N/A'
);

CREATE TYPE format_type AS ENUM (
    'Listicle',
    'Documentary',
    'Tutorial',
    'Story',
    'Other'
);

CREATE TYPE tool_status AS ENUM (
    'Active',
    'Trial',
    'Sunset',
    'Considering'
);

-- =============================================================
-- TRIGGER: keep updated_at fresh on every UPDATE
-- =============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================
-- 1. niches
-- =============================================================

CREATE TABLE niches (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                      TEXT NOT NULL UNIQUE,
    rpm_estimate              NUMERIC(10, 2),
    passes_seven_rpm_gate     BOOLEAN NOT NULL DEFAULT FALSE,
    top_competitors           TEXT,
    trend_status              trend_status,
    validated_by              TEXT,
    notes                     TEXT,
    notion_page_id            TEXT UNIQUE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER niches_updated_at
    BEFORE UPDATE ON niches
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX niches_notion_page_id_idx ON niches (notion_page_id);
CREATE INDEX niches_passes_gate_idx ON niches (passes_seven_rpm_gate) WHERE passes_seven_rpm_gate = TRUE;

-- =============================================================
-- 2. channels
-- =============================================================

CREATE TABLE channels (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    niche_id            UUID REFERENCES niches(id) ON DELETE SET NULL,
    pillar              pillar,
    status              channel_status NOT NULL DEFAULT 'Planning',
    yt_url              TEXT,
    subs                INTEGER,
    monthly_revenue     NUMERIC(12, 2),
    launch_date         DATE,
    owner               TEXT DEFAULT 'Glitch',
    notion_page_id      TEXT UNIQUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER channels_updated_at
    BEFORE UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX channels_notion_page_id_idx ON channels (notion_page_id);
CREATE INDEX channels_niche_id_idx ON channels (niche_id);
CREATE INDEX channels_status_idx ON channels (status);

-- =============================================================
-- 3. topics
-- =============================================================

CREATE TABLE topics (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    working_title            TEXT NOT NULL,
    niche_id                 UUID REFERENCES niches(id) ON DELETE SET NULL,
    status                   topic_status NOT NULL DEFAULT 'Researching',
    source_prompt_output     TEXT,
    google_trends_check      trends_check NOT NULL DEFAULT 'Pending',
    locked_by                TEXT,
    notion_page_id           TEXT UNIQUE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER topics_updated_at
    BEFORE UPDATE ON topics
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX topics_notion_page_id_idx ON topics (notion_page_id);
CREATE INDEX topics_niche_id_idx ON topics (niche_id);
CREATE INDEX topics_status_idx ON topics (status);

-- =============================================================
-- 4. videos  (the main pipeline row)
-- =============================================================
--
-- 28 properties mirroring the Notion Videos DB. Scripts and Assets are
-- folded in as columns rather than separate tables to reduce relation hops
-- (fewer places for an agent to drift). Split out at v2 if volume demands.
--
-- creative_input_requested_from is a multi-select in Notion (Jay / Eric /
-- None) -- stored as TEXT[] here.
--
-- thumbnail_urls stored as TEXT[] so the variants can be addressed
-- individually for A/B testing later.

CREATE TABLE videos (
    id                                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title                              TEXT NOT NULL,
    channel_id                         UUID REFERENCES channels(id) ON DELETE SET NULL,
    stage                              video_stage NOT NULL DEFAULT '01-Niche',
    gate_status                        gate_status NOT NULL DEFAULT 'Pending',
    gate_owner                         TEXT NOT NULL DEFAULT 'Glitch',
    stage_entry_checklist_met          BOOLEAN NOT NULL DEFAULT FALSE,
    next_action                        TEXT,
    blocked_reason                     TEXT,
    creative_input_requested_from      TEXT[] NOT NULL DEFAULT '{}',
    script_status                      script_status NOT NULL DEFAULT 'N/A',
    script_writer                      TEXT,
    script_word_count                  INTEGER,
    script_drive_link                  TEXT,
    editor                             TEXT,
    vo_url                             TEXT,
    thumbnail_urls                     TEXT[] NOT NULL DEFAULT '{}',
    broll_folder                       TEXT,
    master_mp4                         TEXT,
    yt_url                             TEXT,
    ctr_pct                            NUMERIC(5, 2),
    apv_pct                            NUMERIC(5, 2),
    subs_gained                        INTEGER,
    est_revenue                        NUMERIC(12, 2),
    pillar                             pillar,
    notion_page_id                     TEXT UNIQUE,
    created_at                         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Computed: agents read this to know where to advance the row.
    -- Mirrors the Notion formula but evaluated in SQL so the adapter and
    -- skills layer can agree without re-implementing the rule. NULL means
    -- the row is at a terminal state or is blocked -- check blocked_reason.
    allowed_next_stage TEXT GENERATED ALWAYS AS (
        CASE
            WHEN stage = 'Killed' OR stage = 'Complete' THEN NULL
            WHEN stage = '01-Niche'    AND gate_status = 'Approved' THEN '02-Topic'
            WHEN stage = '02-Topic'    AND gate_status = 'Approved' THEN '03-Script'
            WHEN stage = '03-Script'   AND script_status = 'Locked' AND gate_status = 'Approved' THEN '04-VO'
            WHEN stage = '04-VO'       AND vo_url IS NOT NULL AND vo_url <> '' THEN '05-Thumb / 06-Broll (parallel)'
            WHEN stage = '05-Thumb'    AND COALESCE(array_length(thumbnail_urls, 1), 0) > 0 AND gate_status = 'Approved' THEN '07-Assembly'
            WHEN stage = '06-Broll'    AND broll_folder IS NOT NULL AND broll_folder <> '' THEN '07-Assembly'
            WHEN stage = '07-Assembly' AND master_mp4 IS NOT NULL AND master_mp4 <> '' AND gate_status = 'Approved' THEN '08-Publish'
            WHEN stage = '08-Publish'  AND yt_url IS NOT NULL AND yt_url <> '' THEN '09-Measure'
            WHEN stage = '09-Measure'  AND ctr_pct IS NOT NULL AND ctr_pct > 0 THEN '10-Repurpose'
            WHEN stage = '10-Repurpose' THEN 'Complete'
            ELSE NULL
        END
    ) STORED
);

CREATE TRIGGER videos_updated_at
    BEFORE UPDATE ON videos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX videos_notion_page_id_idx ON videos (notion_page_id);
CREATE INDEX videos_channel_id_idx ON videos (channel_id);
CREATE INDEX videos_stage_idx ON videos (stage);
CREATE INDEX videos_gate_status_idx ON videos (gate_status);
CREATE INDEX videos_blocked_idx ON videos (gate_status) WHERE gate_status = 'Blocked';
CREATE INDEX videos_winners_idx ON videos (ctr_pct DESC, apv_pct DESC)
    WHERE ctr_pct >= 10 AND apv_pct >= 30;

-- =============================================================
-- 5. winning_patterns  (Stage 09 learning loop output)
-- =============================================================

CREATE TABLE winning_patterns (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_name        TEXT NOT NULL,
    source_video_id     UUID REFERENCES videos(id) ON DELETE SET NULL,
    ctr_pct             NUMERIC(5, 2),
    apv_pct             NUMERIC(5, 2),
    format_type         format_type,
    replicable_to       pillar[] NOT NULL DEFAULT '{}',
    notes               TEXT,
    notion_page_id      TEXT UNIQUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER winning_patterns_updated_at
    BEFORE UPDATE ON winning_patterns
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX winning_patterns_notion_page_id_idx ON winning_patterns (notion_page_id);
CREATE INDEX winning_patterns_source_video_id_idx ON winning_patterns (source_video_id);
CREATE INDEX winning_patterns_format_type_idx ON winning_patterns (format_type);

-- =============================================================
-- 6. channel_teardowns  (summer reverse-engineering sprint)
-- =============================================================

CREATE TABLE channel_teardowns (
    id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_name                  TEXT NOT NULL,
    yt_url                        TEXT,
    niche_id                      UUID REFERENCES niches(id) ON DELETE SET NULL,
    subs_growth_6mo               INTEGER,
    format_notes                  TEXT,
    transcript_frame_extracted    BOOLEAN NOT NULL DEFAULT FALSE,
    format_library_entry          TEXT,
    owner                         TEXT DEFAULT 'Glitch',
    notion_page_id                TEXT UNIQUE,
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER channel_teardowns_updated_at
    BEFORE UPDATE ON channel_teardowns
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX channel_teardowns_notion_page_id_idx ON channel_teardowns (notion_page_id);
CREATE INDEX channel_teardowns_niche_id_idx ON channel_teardowns (niche_id);
CREATE INDEX channel_teardowns_subs_growth_idx ON channel_teardowns (subs_growth_6mo DESC);

-- =============================================================
-- 7. tool_stack_budget
-- =============================================================

CREATE TABLE tool_stack_budget (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool                TEXT NOT NULL,
    use_case            TEXT,
    monthly_cost        NUMERIC(10, 2),
    stage_used_in       TEXT[] NOT NULL DEFAULT '{}',
    status              tool_status NOT NULL DEFAULT 'Considering',
    notion_page_id      TEXT UNIQUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER tool_stack_budget_updated_at
    BEFORE UPDATE ON tool_stack_budget
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX tool_stack_budget_notion_page_id_idx ON tool_stack_budget (notion_page_id);
CREATE INDEX tool_stack_budget_status_idx ON tool_stack_budget (status);

-- =============================================================
-- 8. stage_events  (event log -- this IS the learning corpus)
-- =============================================================
--
-- Every stage transition writes a row. Append-only. Nothing in the system
-- updates or deletes from this table -- if you find yourself wanting to,
-- write a corrective event instead.
--
-- payload is the full snapshot of the video row at write time so that the
-- log is self-contained and replayable.

CREATE TABLE stage_events (
    id                       BIGSERIAL PRIMARY KEY,
    video_id                 UUID REFERENCES videos(id) ON DELETE CASCADE,
    actor                    TEXT NOT NULL,                  -- which bot or human: 'erics-claude', 'glitch-claude', 'jay-claude', 'smaths-bot', 'eric', 'glitch', 'jay', etc.
    from_stage               video_stage,
    to_stage                 video_stage,
    gate_status_before       gate_status,
    gate_status_after        gate_status,
    event_type               TEXT NOT NULL,                  -- 'stage_advance', 'gate_flip', 'blocked', 'unblocked', 'killed', 'creative_input_requested', 'gap_filled'
    blocked_reason           TEXT,
    notes                    TEXT,
    payload                  JSONB NOT NULL DEFAULT '{}',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX stage_events_video_id_idx ON stage_events (video_id, created_at DESC);
CREATE INDEX stage_events_actor_idx ON stage_events (actor, created_at DESC);
CREATE INDEX stage_events_event_type_idx ON stage_events (event_type, created_at DESC);
CREATE INDEX stage_events_payload_gin_idx ON stage_events USING GIN (payload);

-- =============================================================
-- comments (for human + bot readers via \d+ / information_schema)
-- =============================================================

COMMENT ON TABLE  niches IS 'Validated YouTube niches with $7 RPM gate state.';
COMMENT ON TABLE  channels IS 'YouTube channels owned/operated by the lab.';
COMMENT ON TABLE  topics IS 'Stage 02 outputs -- ranked video topics per niche.';
COMMENT ON TABLE  videos IS 'Main pipeline row. One row per video, 10 stages, Glitch gates all.';
COMMENT ON TABLE  winning_patterns IS 'Stage 09 outputs -- CTR/APV winners that feed back into Stage 02.';
COMMENT ON TABLE  channel_teardowns IS 'Reverse-engineered competitor channels (summer sprint corpus).';
COMMENT ON TABLE  tool_stack_budget IS 'Active toolset with monthly burn.';
COMMENT ON TABLE  stage_events IS 'Append-only event log. Every stage transition writes here. THE learning corpus.';

COMMENT ON COLUMN videos.gate_owner IS 'Always Glitch in v1. Field exists to make ownership explicit per row.';
COMMENT ON COLUMN videos.allowed_next_stage IS 'Computed. Mirrors the Notion formula. NULL = terminal or blocked.';
COMMENT ON COLUMN videos.creative_input_requested_from IS 'Multi-select: Jay / Eric / None. Pipeline does NOT wait on these.';

COMMIT;
