from dataclasses import asdict

from lamp.action_history import (
    ensure_action_schema,
    find_receipt_delta,
    project_withdrawal,
    record_receipt_delta,
)
from lamp.emissions import (
    append_emission,
    ensure_emission_schema,
    last_sequence,
    read_current,
    read_emissions_through,
    read_first_emission,
    read_initial_emissions,
)
from lamp.levels import advance_level
from service_support import Problem, database, integer_field, text_field, valid_level


def initialize_execution_store(path):
    with database(path, write=True) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS lamp_sessions (
            session TEXT PRIMARY KEY,
            edition TEXT NOT NULL,
            cutoff INTEGER
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS lamp_bindings (
            session TEXT NOT NULL REFERENCES lamp_sessions(session),
            fixture TEXT NOT NULL,
            initial INTEGER NOT NULL CHECK (initial BETWEEN 0 AND 100),
            PRIMARY KEY (session, fixture)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS target_refusals (
            session TEXT NOT NULL,
            action TEXT NOT NULL,
            fixture TEXT NOT NULL,
            target TEXT NOT NULL,
            PRIMARY KEY (session, action),
            FOREIGN KEY (session, fixture) REFERENCES lamp_bindings(session, fixture)
        )''')
        ensure_emission_schema(db)
        ensure_action_schema(db)


def _session(db, session):
    return db.execute('SELECT edition, cutoff FROM lamp_sessions WHERE session = ?',
                      (session,)).fetchone()


def initialize_session(path, session, edition, levels):
    if not levels or any(not fixture.strip() or not valid_level(level)
                         for fixture, level in levels.items()):
        raise Problem(400, 'invalid_initial_bindings')
    with database(path, write=True) as db:
        existing = _session(db, session)
        if existing is None:
            db.execute('INSERT INTO lamp_sessions (session, edition) VALUES (?, ?)',
                       (session, edition))
            for fixture, initial in sorted(levels.items()):
                db.execute('INSERT INTO lamp_bindings VALUES (?, ?, ?)',
                           (session, fixture, initial))
                append_emission(db, session, fixture, 'initial', 'initial', fixture, initial)
        else:
            rows = db.execute('SELECT fixture, initial FROM lamp_bindings WHERE session = ?',
                              (session,))
            saved = {row['fixture']: row['initial'] for row in rows}
            if existing['edition'] != edition or saved != levels:
                raise Problem(409, 'initialization_conflict')
        initial = [asdict(row) for row in read_initial_emissions(db, session)]
    return {'session': session, 'edition': edition, 'initial': initial}


def _active_binding(db, session, fixture):
    state = _session(db, session)
    if state is None:
        raise Problem(404, 'unknown_session')
    if state['cutoff'] is not None:
        raise Problem(409, 'session_closed')
    return _binding_initial(db, session, fixture)


def _binding_initial(db, session, fixture):
    row = db.execute('SELECT initial FROM lamp_bindings WHERE session = ? AND fixture = ?',
                     (session, fixture)).fetchone()
    if row is None:
        raise Problem(404, 'unknown_binding')
    return row['initial']


def _receipt(db, emission):
    result = asdict(emission)
    if emission.kind == 'adjust':
        delta = find_receipt_delta(db, emission)
        if delta is None:
            raise Problem(503, 'adjustment_receipt_unavailable')
        result['delta'] = delta
    return result


def read_execution_receipt(db, session, source, action):
    emission = read_first_emission(db, session, source, action)
    if emission is None:
        raise Problem(404, 'unknown_emission')
    return _receipt(db, emission)


def _repeat(db, session, fixture, source, action, kind, target=None):
    emission = read_first_emission(db, session, source, action)
    if emission is None:
        return None
    if (emission.fixture, emission.kind, emission.target) != (fixture, kind, target):
        raise Problem(409, 'request_conflict')
    return _receipt(db, emission)


def _refusal(db, session, action):
    return db.execute('SELECT fixture, target FROM target_refusals WHERE session = ? AND action = ?',
                      (session, action)).fetchone()


def apply_delta(path, session, fixture, source, action, delta):
    with database(path, write=True) as db:
        prior = _repeat(db, session, fixture, source, action, 'adjust')
        if prior is not None:
            if prior['delta'] != delta:
                raise Problem(409, 'request_conflict')
            return prior
        _active_binding(db, session, fixture)
        current = read_current(db, session, fixture)
        level = advance_level(current.level, delta)
        emitted = append_emission(db, session, fixture, source, 'adjust', action, level)
        record_receipt_delta(db, emitted, delta if level != current.level else 0)
        return _receipt(db, emitted)


def preview_withdrawal(path, session, fixture, target):
    with database(path) as db:
        initial = _binding_initial(db, session, fixture)
        current = read_current(db, session, fixture)
        return {'level': project_withdrawal(db, current, initial, target)}


def _apply_desk_level(db, session, fixture, action, kind, level, target_action):
    prior = _repeat(db, session, fixture, 'desk', action, kind, target_action)
    if prior is not None:
        return prior
    refusal = _refusal(db, session, action)
    if refusal is not None:
        if (refusal['fixture'], refusal['target']) != (fixture, target_action):
            raise Problem(409, 'request_conflict')
        return None
    _active_binding(db, session, fixture)
    if kind == 'withdraw':
        target = read_first_emission(db, session, 'desk', target_action)
        if target is None or target.fixture != fixture or target.kind != 'adjust':
            db.execute('INSERT INTO target_refusals VALUES (?, ?, ?, ?)',
                       (session, action, fixture, target_action))
            return None
    previous = read_current(db, session, fixture)
    emitted = append_emission(db, session, fixture, 'desk', kind, action, level, target=target_action)
    if kind == 'adjust':
        record_receipt_delta(db, emitted, level - previous.level)
    return _receipt(db, emitted)


def execute_desk_command(path, body):
    session = text_field(body, 'session')
    fixture = text_field(body, 'fixture')
    action = text_field(body, 'action')
    kind = text_field(body, 'kind')
    if kind not in ('adjust', 'withdraw'):
        raise Problem(400, 'invalid_kind')
    level = integer_field(body, 'level')
    if not valid_level(level):
        raise Problem(400, 'invalid_level')
    target = text_field(body, 'target') if kind == 'withdraw' else None
    with database(path, write=True) as db:
        result = _apply_desk_level(db, session, fixture, action, kind, level, target)
    if result is None:
        raise Problem(404, 'unknown_target')
    return result


def seal_session(path, session):
    with database(path, write=True) as db:
        state = _session(db, session)
        if state is None:
            raise Problem(404, 'unknown_session')
        cutoff = state['cutoff']
        if cutoff is None:
            cutoff = last_sequence(db, session)
            db.execute('UPDATE lamp_sessions SET cutoff = ? WHERE session = ?', (cutoff, session))
    return {'session': session, 'cutoff': cutoff}


def read_sealed_cut(path, session, cutoff):
    with database(path) as db:
        state = _session(db, session)
        if state is None:
            raise Problem(404, 'unknown_session')
        if state['cutoff'] is None or state['cutoff'] != cutoff:
            raise Problem(409, 'cutoff_conflict')
        rows = read_emissions_through(db, session, cutoff)
    return {'session': session, 'cutoff': cutoff, 'emissions': [asdict(row) for row in rows]}
