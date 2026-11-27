from dataclasses import dataclass


@dataclass(frozen=True)
class Emission:
    session: str
    fixture: str
    seq: int
    source: str
    kind: str
    action: str
    level: int
    target: str | None


def ensure_emission_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS emissions (
        session TEXT NOT NULL,
        fixture TEXT NOT NULL,
        seq INTEGER NOT NULL CHECK (seq > 0),
        source TEXT NOT NULL CHECK (source IN ('initial', 'desk', 'local')),
        kind TEXT NOT NULL CHECK (kind IN ('initial', 'adjust', 'withdraw')),
        action TEXT NOT NULL,
        level INTEGER NOT NULL CHECK (level BETWEEN 0 AND 100),
        target TEXT,
        PRIMARY KEY (session, seq),
        UNIQUE (session, source, action),
        FOREIGN KEY (session, fixture) REFERENCES lamp_bindings(session, fixture)
    )''')
    db.execute('''CREATE INDEX IF NOT EXISTS emissions_by_fixture
                  ON emissions (session, fixture, seq DESC)''')


def last_sequence(db, session):
    return db.execute('SELECT COALESCE(MAX(seq), 0) FROM emissions WHERE session = ?',
                      (session,)).fetchone()[0]


def append_emission(db, session, fixture, source, kind, action, level, *, target=None):
    seq = last_sequence(db, session) + 1
    db.execute('INSERT INTO emissions VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
               (session, fixture, seq, source, kind, action, level, target))
    return Emission(session, fixture, seq, source, kind, action, level, target)


def read_initial_emissions(db, session):
    rows = db.execute("SELECT * FROM emissions WHERE session = ? AND kind = 'initial' ORDER BY seq",
                      (session,))
    return [Emission(**row) for row in rows]


def read_current(db, session, fixture):
    row = db.execute('''SELECT * FROM emissions WHERE session = ? AND fixture = ?
                        ORDER BY seq DESC LIMIT 1''', (session, fixture)).fetchone()
    return Emission(**row) if row is not None else None


def read_first_emission(db, session, source, action):
    row = db.execute('SELECT * FROM emissions WHERE session = ? AND source = ? AND action = ?',
                     (session, source, action)).fetchone()
    return Emission(**row) if row is not None else None


def read_emissions_through(db, session, cutoff):
    rows = db.execute('SELECT * FROM emissions WHERE session = ? AND seq <= ? ORDER BY seq',
                      (session, cutoff))
    return [Emission(**row) for row in rows]
