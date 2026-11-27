from rehearsal.bindings import bind_session_fixtures, read_bindings
from rehearsal.sessions import mark_open, reserve_session
from scene.editions import read_edition
from service_support import Problem, TransportError, database, valid_level


def _verify_initial(reply, session, edition, bindings):
    rows = reply.get('initial')
    if (reply.get('session') != session or reply.get('edition') != edition
            or not isinstance(rows, list) or len(rows) != len(bindings)):
        raise Problem(503, 'opening_unconfirmed')
    for seq, (binding, row) in enumerate(zip(bindings, rows), 1):
        expected = {
            'session': session, 'fixture': binding.fixture, 'seq': seq,
            'source': 'initial', 'kind': 'initial', 'action': binding.fixture,
            'level': binding.initial, 'target': None,
        }
        if row != expected or type(row['seq']) is not int or not valid_level(row['level']):
            raise Problem(503, 'opening_unconfirmed')
    return rows


def open_session(path, lamp, session, edition):
    with database(path, write=True) as db:
        selected = read_edition(db, edition)
        if selected is None:
            raise Problem(404, 'unknown_edition')
        _, created = reserve_session(db, session, edition)
        if created:
            bind_session_fixtures(db, session, selected.levels)
        bindings = read_bindings(db, session)
    levels = {binding.fixture: binding.initial for binding in bindings}
    try:
        reply = lamp.initialize_session(session, edition, levels)
    except TransportError as exc:
        raise Problem(503, 'opening_unconfirmed') from exc
    except Problem as exc:
        if exc.status == 409:
            raise
        raise Problem(503, 'opening_unconfirmed') from exc
    initial = _verify_initial(reply, session, edition, bindings)
    with database(path, write=True) as db:
        mark_open(db, session)
    return {'session': session, 'edition': edition, 'bindings': levels, 'initial': initial}
