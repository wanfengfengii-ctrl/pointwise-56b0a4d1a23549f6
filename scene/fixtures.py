from service_support import Problem


def ensure_fixture_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS fixtures (
        fixture TEXT PRIMARY KEY,
        label TEXT NOT NULL
    )''')


def find_fixture(db, fixture):
    row = db.execute('SELECT fixture, label FROM fixtures WHERE fixture = ?', (fixture,)).fetchone()
    return dict(row) if row is not None else None


def register_fixture(db, fixture, label):
    db.execute('''INSERT INTO fixtures (fixture, label) VALUES (?, ?)
                  ON CONFLICT(fixture) DO NOTHING''', (fixture, label))
    registered = find_fixture(db, fixture)
    if registered['label'] != label:
        raise Problem(409, 'fixture_conflict')
    return registered
