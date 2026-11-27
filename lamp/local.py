from lamp.commands import apply_delta
from service_support import integer_field, text_field


def submit_local_adjustment(path, body):
    session = text_field(body, 'session')
    fixture = text_field(body, 'fixture')
    action = text_field(body, 'action')
    delta = integer_field(body, 'delta')
    return apply_delta(path, session, fixture, 'local', action, delta)
