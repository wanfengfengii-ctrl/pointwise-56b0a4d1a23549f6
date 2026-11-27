from desk.receipts import deliver_request
from desk.request_book import bind_request, read_request
from rehearsal.bindings import has_binding
from rehearsal.sessions import read_session
from service_support import Problem, database, integer_field, text_field


def submit_desk_request(path, lamp, body, kind, parameter):
    session = text_field(body, 'session')
    action = text_field(body, 'action')
    fixture = text_field(body, 'fixture')
    with database(path, write=True) as db:
        if read_request(db, session, action) is None:
            current = read_session(db, session)
            if current is None:
                raise Problem(404, 'unknown_session')
            if current.state != 'open':
                raise Problem(409, 'session_not_open')
            if not has_binding(db, session, fixture):
                raise Problem(404, 'unknown_binding')
        request = bind_request(db, session, action, fixture, kind, parameter)
    return deliver_request(path, lamp, request)


def submit_adjustment(path, lamp, body):
    delta = integer_field(body, 'delta')
    return submit_desk_request(path, lamp, body, 'adjust', delta)
