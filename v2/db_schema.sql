CREATE TABLE collections (
    source          TEXT    NOT NULL,
    set_id          INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    folder          TEXT    NOT NULL,
    difficulty_raw  TEXT,
    difficulty_num  INTEGER,
    num_problems    INTEGER,
    on_disk         INTEGER NOT NULL DEFAULT 0,
    chapter_count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source, set_id)
);
CREATE TABLE chapters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,
    set_id          INTEGER NOT NULL,
    chapter_num     INTEGER NOT NULL,
    diff_min        INTEGER,
    diff_max        INTEGER,
    diff_avg        INTEGER,
    problem_count   INTEGER NOT NULL DEFAULT 0, name TEXT, mostrar INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source, set_id, chapter_num),
    FOREIGN KEY (source, set_id) REFERENCES collections(source, set_id)
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE problems (
    source          TEXT    NOT NULL,
    problem_id      INTEGER NOT NULL,
    set_id          INTEGER NOT NULL,
    chapter_id      INTEGER,
    order_in_chapter INTEGER,
    sgf_path        TEXT    NOT NULL,
    sgf_exists      INTEGER NOT NULL DEFAULT 0,
    difficulty_raw  TEXT,
    difficulty_num  INTEGER,
    color_to_play   TEXT,               -- 'B', 'W', or NULL
    PRIMARY KEY (source, problem_id),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id)
);
CREATE TABLE attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    problem_id  INTEGER NOT NULL,
    run_id      INTEGER,                -- NULL = intento libre
    result      INTEGER NOT NULL,       -- 1=correct, 0=wrong
    time_ms     INTEGER,                -- tiempo hasta respuesta
    created_at  TEXT    NOT NULL        -- ISO8601
, uuid TEXT);
CREATE TABLE runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    set_id      INTEGER,                -- NULL si es colección virtual
    chapter_id  INTEGER,                -- NULL si es run de colección completa
    vc_id       INTEGER,                -- NULL si no es colección virtual
    type        TEXT    NOT NULL,       -- 'chapter', 'collection', 'virtual'
    status      TEXT    NOT NULL DEFAULT 'open',  -- 'open', 'closed'
    total       INTEGER NOT NULL DEFAULT 0,
    done        INTEGER NOT NULL DEFAULT 0,
    started_at  TEXT    NOT NULL,
    closed_at   TEXT
, uuid TEXT);
CREATE TABLE run_items (
    run_id      INTEGER NOT NULL,
    source      TEXT    NOT NULL,
    problem_id  INTEGER NOT NULL,
    order_in_run INTEGER NOT NULL,
    result      INTEGER,                -- NULL=pendiente, 1=correct, 0=wrong
    PRIMARY KEY (run_id, problem_id),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
CREATE TABLE virtual_collections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);
CREATE TABLE virtual_items (
    vc_id       INTEGER NOT NULL,
    source      TEXT    NOT NULL,
    problem_id  INTEGER NOT NULL,
    PRIMARY KEY (vc_id, source, problem_id),
    FOREIGN KEY (vc_id) REFERENCES virtual_collections(id)
);
CREATE TABLE game_collections (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, folder TEXT NOT NULL);
CREATE TABLE games (id INTEGER PRIMARY KEY AUTOINCREMENT, game_collection_id INTEGER NOT NULL, name TEXT NOT NULL, sgf_path TEXT NOT NULL);
CREATE TABLE sm2_state (
                source      TEXT NOT NULL,
                problem_id  TEXT NOT NULL,
                due_date    TEXT NOT NULL,
                interval    REAL NOT NULL DEFAULT 6,
                easiness    REAL NOT NULL DEFAULT 2.5,
                repetitions INTEGER NOT NULL DEFAULT 0,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (source, problem_id)
            );
CREATE INDEX idx_problems_set   ON problems(source, set_id);
CREATE INDEX idx_problems_diff  ON problems(source, difficulty_num);
CREATE INDEX idx_problems_chap  ON problems(chapter_id);
CREATE INDEX idx_attempts_prob  ON attempts(source, problem_id);
CREATE INDEX idx_attempts_run   ON attempts(run_id);
CREATE INDEX idx_run_items_run  ON run_items(run_id);
CREATE INDEX idx_attempts_source_problem_created ON attempts(source, problem_id, created_at DESC);
CREATE INDEX idx_chapters_mostrar ON chapters(id, mostrar);
CREATE INDEX idx_games_collection ON games(game_collection_id);
CREATE INDEX idx_sm2_updated ON sm2_state(updated_at);
CREATE UNIQUE INDEX idx_attempts_uuid ON attempts(uuid) WHERE uuid IS NOT NULL;
CREATE UNIQUE INDEX idx_runs_uuid ON runs(uuid) WHERE uuid IS NOT NULL;
CREATE VIEW problem_stats AS
SELECT
    source,
    problem_id,
    COUNT(*)                                                    AS total_attempts,
    SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END)          AS total_correct,
    SUM(CASE WHEN result='wrong'   THEN 1 ELSE 0 END)          AS total_wrong,
    ROUND(AVG(CASE WHEN result='correct' THEN 1.0 ELSE 0 END) * 100, 1) AS pct_correct,
    AVG(time_ms)                                                AS avg_time_ms,
    MAX(created_at)                                             AS last_seen
FROM attempts
GROUP BY source, problem_id
/* problem_stats(source,problem_id,total_attempts,total_correct,total_wrong,pct_correct,avg_time_ms,last_seen) */;