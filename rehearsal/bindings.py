from dataclasses import dataclass


@dataclass(frozen=True)
class SessionBinding:
    fixture: str
    initial: int


def ensure_binding_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS session_bindings (
        session TEXT NOT NULL REFERENCES sessions(session),
        fixture TEXT NOT NULL REFERENCES fixtures(fixture),
        initial INTEGER NOT NULL CHECK (initial BETWEEN 0 AND 100),
        PRIMARY KEY (session, fixture)
    )''')


def bind_session_fixtures(db, session, levels):
    db.executemany('INSERT INTO session_bindings VALUES (?, ?, ?)',
                   ((session, fixture, initial) for fixture, initial in levels.items()))


def read_bindings(db, session):
    rows = db.execute('''SELECT fixture, initial FROM session_bindings
                         WHERE session = ? ORDER BY fixture''', (session,))
    return [SessionBinding(**row) for row in rows]


def has_binding(db, session, fixture):
    row = db.execute('SELECT 1 FROM session_bindings WHERE session = ? AND fixture = ?',
                     (session, fixture)).fetchone()
    return row is not None
