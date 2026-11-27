from dataclasses import dataclass

from service_support import Problem


@dataclass(frozen=True)
class Session:
    session: str
    edition: str
    state: str


def ensure_session_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS sessions (
        session TEXT PRIMARY KEY,
        edition TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('opening', 'open', 'closing', 'closed'))
    )''')


def read_session(db, session):
    row = db.execute('SELECT session, edition, state FROM sessions WHERE session = ?',
                     (session,)).fetchone()
    return Session(**row) if row is not None else None


def reserve_session(db, session, edition):
    found = read_session(db, session)
    if found is not None:
        if found.edition != edition:
            raise Problem(409, 'session_edition_conflict')
        return found, False
    db.execute("INSERT INTO sessions VALUES (?, ?, 'opening')", (session, edition))
    return Session(session, edition, 'opening'), True


def mark_open(db, session):
    db.execute("UPDATE sessions SET state = 'open' WHERE session = ? AND state = 'opening'",
               (session,))


def begin_closing(db, session):
    found = read_session(db, session)
    if found is None:
        raise Problem(404, 'unknown_session')
    if found.state == 'opening':
        raise Problem(409, 'session_not_open')
    if found.state == 'open':
        db.execute("UPDATE sessions SET state = 'closing' WHERE session = ?", (session,))
        return Session(found.session, found.edition, 'closing')
    return found


def mark_closed(db, session):
    cursor = db.execute("UPDATE sessions SET state = 'closed' WHERE session = ? AND state = 'closing'",
                        (session,))
    if cursor.rowcount != 1:
        raise Problem(503, 'closing_state_unavailable')
