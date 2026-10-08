-- Family ledger. Planned lessons are not stored; only facts are.

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    login_name TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE families (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    owner_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE family_members (
    family_id INTEGER NOT NULL REFERENCES families(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('owner', 'member')),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (family_id, user_id)
);

CREATE INDEX idx_members_user ON family_members(user_id);

CREATE TABLE invitations (
    id INTEGER PRIMARY KEY,
    family_id INTEGER NOT NULL REFERENCES families(id),
    code_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_by INTEGER REFERENCES users(id),
    used_at TEXT,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE courses (
    id INTEGER PRIMARY KEY,
    family_id INTEGER NOT NULL REFERENCES families(id),
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    teacher TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    current_package_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_courses_family ON courses(family_id);

CREATE TABLE course_schedules (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    local_time TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_schedules_course ON course_schedules(course_id);

CREATE TABLE course_packages (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    title TEXT NOT NULL,
    total_units INTEGER NOT NULL CHECK (total_units > 0),
    opening_consumed_units INTEGER NOT NULL DEFAULT 0
        CHECK (opening_consumed_units >= 0),
    start_date TEXT,
    expiry_date TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    CHECK (opening_consumed_units <= total_units)
);

CREATE INDEX idx_packages_course ON course_packages(course_id);

CREATE TABLE lesson_records (
    id INTEGER PRIMARY KEY,
    family_id INTEGER NOT NULL REFERENCES families(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    package_id INTEGER NOT NULL REFERENCES course_packages(id),
    local_date TEXT NOT NULL,
    local_time TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('planned', 'manual')),
    status TEXT NOT NULL CHECK (status IN ('attended', 'leave', 'canceled')),
    consumed_units INTEGER NOT NULL CHECK (consumed_units >= 0),
    idempotency_key TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    updated_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    voided_at TEXT,
    voided_by INTEGER REFERENCES users(id)
);

-- One active fact per class slot. Voided rows keep the key so the
-- ledger remains, and the same slot can be checked in again.
CREATE UNIQUE INDEX idx_lesson_active_key
    ON lesson_records(idempotency_key)
    WHERE voided_at IS NULL;

CREATE INDEX idx_lessons_course_date
    ON lesson_records(course_id, local_date);

CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY,
    actor_user_id INTEGER NOT NULL REFERENCES users(id),
    family_id INTEGER NOT NULL REFERENCES families(id),
    target_type TEXT NOT NULL,
    target_id INTEGER,
    action TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_audit_family ON audit_logs(family_id, id);
