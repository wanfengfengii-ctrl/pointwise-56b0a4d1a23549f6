import json

from service_support import json_text


def ensure_archive_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS reports (
        report TEXT PRIMARY KEY,
        session TEXT NOT NULL UNIQUE REFERENCES sessions(session),
        content_json TEXT NOT NULL
    )''')


def freeze_report(db, candidate):
    session = candidate['session']
    report = {'report': f'report-{session}', **candidate}
    db.execute('''INSERT INTO reports VALUES (?, ?, ?)
                  ON CONFLICT(session) DO NOTHING''',
               (report['report'], session, json_text(report)))
    return find_report_for_session(db, session)


def find_report_for_session(db, session):
    row = db.execute('SELECT content_json FROM reports WHERE session = ?', (session,)).fetchone()
    return json.loads(row['content_json']) if row is not None else None


def read_report(db, report):
    row = db.execute('SELECT content_json FROM reports WHERE report = ?', (report,)).fetchone()
    return json.loads(row['content_json']) if row is not None else None
