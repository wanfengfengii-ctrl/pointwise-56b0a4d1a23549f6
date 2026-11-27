from contextlib import closing, contextmanager
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler
import json
import sqlite3
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener


class Problem(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


class TransportError(Exception):
    pass


@contextmanager
def database(path, *, write=False):
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        with db:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db


def text_field(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise Problem(400, f'invalid_{key}')
    return value


def integer_field(data, key):
    value = data.get(key)
    if type(value) is not int:
        raise Problem(400, f'invalid_{key}')
    return value


def level_map(data):
    levels = data.get('levels')
    if not isinstance(levels, dict):
        raise Problem(400, 'invalid_levels')
    return levels


def valid_level(value):
    return type(value) is int and 0 <= value <= 100


def json_text(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def _invalid_constant(value):
    raise ValueError(value)


class JsonHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def read_body(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 1_048_576:
                raise ValueError('invalid body size')
            data = json.loads(self.rfile.read(size), parse_constant=_invalid_constant)
        except (ValueError, RecursionError) as exc:
            raise Problem(400, 'invalid_json') from exc
        if not isinstance(data, dict):
            raise Problem(400, 'expected_object')
        return data

    def read_query(self):
        params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if any(len(values) != 1 for values in params.values()):
            raise Problem(400, 'repeated_query_parameter')
        return {key: values[0] for key, values in params.items()}

    def respond(self, operation):
        try:
            result = operation()
            status = 202 if result.get('status') == 'pending' else 200
        except Problem as exc:
            result = {'error': exc.code}
            status = exc.status
        payload = json_text(result).encode('utf-8')
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            return


def request_json(base, path, *, body=None, query=None, timeout=20):
    url = base + path
    if query is not None:
        url += '?' + urlencode(query)
    payload = None if body is None else json_text(body).encode('utf-8')
    request = Request(url, data=payload, headers={'Content-Type': 'application/json'})
    opener = build_opener(ProxyHandler({}))
    try:
        try:
            response = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            response = exc
        with response:
            status = response.code
            result = json.loads(response.read(), parse_constant=_invalid_constant)
        if not isinstance(result, dict):
            raise ValueError('expected a JSON object')
        if status >= 400:
            code = result.get('error')
            if not isinstance(code, str):
                raise ValueError('missing error code')
            raise Problem(status, code)
        return result
    except (ValueError, OSError, HTTPException) as exc:
        raise TransportError('no usable HTTP result') from exc
