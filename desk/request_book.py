from dataclasses import dataclass
import json

from service_support import Problem, json_text


@dataclass(frozen=True)
class DeskRequest:
    session: str
    action: str
    fixture: str
    kind: str
    parameter: int | str
    state: str
    result: dict | None


def ensure_request_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS desk_requests (
        session TEXT NOT NULL REFERENCES sessions(session),
        action TEXT NOT NULL,
        fixture TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('adjust', 'withdraw')),
        parameter_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('pending', 'applied', 'rejected')),
        result_json TEXT,
        PRIMARY KEY (session, action),
        FOREIGN KEY (session, fixture) REFERENCES session_bindings(session, fixture)
    )''')


def read_request(db, session, action):
    row = db.execute('''SELECT fixture, kind, parameter_json, state, result_json
                        FROM desk_requests WHERE session = ? AND action = ?''',
                     (session, action)).fetchone()
    if row is None:
        return None
    result = None if row['result_json'] is None else json.loads(row['result_json'])
    return DeskRequest(session, action, row['fixture'], row['kind'],
                       json.loads(row['parameter_json']), row['state'], result)


def bind_request(db, session, action, fixture, kind, parameter):
    request = read_request(db, session, action)
    if request is not None:
        if (request.fixture, request.kind, request.parameter) != (fixture, kind, parameter):
            raise Problem(409, 'request_conflict')
        return request
    db.execute('''INSERT INTO desk_requests VALUES (?, ?, ?, ?, ?, 'pending', NULL)''',
               (session, action, fixture, kind, json_text(parameter)))
    return DeskRequest(session, action, fixture, kind, parameter, 'pending', None)


def _finish(db, request, state, result):
    db.execute('''UPDATE desk_requests SET state = ?, result_json = ?
                  WHERE session = ? AND action = ? AND state = 'pending' ''',
               (state, json_text(result), request.session, request.action))
    return read_request(db, request.session, request.action)


def settle_request(db, request, result):
    return _finish(db, request, 'applied', result)


def reject_request(db, request, status, code):
    return _finish(db, request, 'rejected', {'status': status, 'error': code})
