from lamp.levels import advance_level
from service_support import Problem, TransportError


def make_lamp_command(request):
    command = {
        'session': request.session,
        'action': request.action,
        'fixture': request.fixture,
        'kind': request.kind,
    }
    if request.kind == 'withdraw':
        command['target'] = request.parameter
    return command


def send_request(lamp, request):
    try:
        saved = find_lamp_receipt(lamp, request)
        if saved is not None:
            return saved
        command = make_lamp_command(request)
        if request.kind == 'adjust':
            current = lamp.read_current(request.session, request.fixture)
            level = advance_level(current['level'], request.parameter)
        else:
            plan = lamp.preview_withdrawal(request.session, request.fixture, request.parameter)
            level = plan['level']
        return lamp.submit_command({**command, 'level': level})
    except TransportError:
        return None
    except Problem as exc:
        if exc.status >= 500:
            return None
        raise


def find_lamp_receipt(lamp, request):
    try:
        return lamp.read_first_emission(request.session, 'desk', request.action)
    except TransportError:
        return None
    except Problem as exc:
        if exc.status == 404 or exc.status >= 500:
            return None
        raise
