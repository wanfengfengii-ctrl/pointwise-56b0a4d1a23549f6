from desk.dispatch import find_lamp_receipt, make_lamp_command, send_request
from desk.request_book import read_request, reject_request, settle_request
from service_support import Problem, database, valid_level


def _present(request, *, lookup=False):
    if request.state == 'applied':
        return {'status': 'applied', **request.result}
    if request.state == 'rejected':
        if lookup:
            raise Problem(404, 'unknown_receipt')
        raise Problem(request.result['status'], request.result['error'])
    return {'status': 'pending', 'session': request.session, 'action': request.action}


def _matches(request, reply):
    if reply is None or reply.get('source') != 'desk':
        return False
    seq = reply.get('seq')
    if type(seq) is not int or seq < 1 or not valid_level(reply.get('level')):
        return False
    if request.kind == 'adjust':
        if type(reply.get('delta')) is not int or reply.get('target') is not None:
            return False
    return all(reply.get(key) == value for key, value in make_lamp_command(request).items())


def record_lamp_reply(path, request, reply):
    with database(path, write=True) as db:
        if _matches(request, reply):
            if request.kind == 'adjust':
                reply = {**reply, 'delta': request.parameter}
            return settle_request(db, request, reply)
        return read_request(db, request.session, request.action)


def deliver_request(path, lamp, request):
    if request.state != 'pending':
        return _present(request)
    try:
        reply = send_request(lamp, request)
    except Problem as exc:
        with database(path, write=True) as db:
            resolved = reject_request(db, request, exc.status, exc.code)
    else:
        resolved = record_lamp_reply(path, request, reply)
    return _present(resolved)


def read_receipt(path, lamp, session, action):
    with database(path) as db:
        request = read_request(db, session, action)
    if request is None:
        raise Problem(404, 'unknown_receipt')
    if request.state == 'pending':
        reply = find_lamp_receipt(lamp, request)
        request = record_lamp_reply(path, request, reply)
    return _present(request, lookup=True)
