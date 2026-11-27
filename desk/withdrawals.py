from desk.adjustments import submit_desk_request
from service_support import text_field


def submit_withdrawal(path, lamp, body):
    target = text_field(body, 'target')
    return submit_desk_request(path, lamp, body, 'withdraw', target)
