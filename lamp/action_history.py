from lamp.emissions import read_emissions_through
from lamp.levels import replay_levels


def ensure_action_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS adjustment_receipts (
        session TEXT NOT NULL,
        seq INTEGER NOT NULL,
        delta TEXT NOT NULL,
        PRIMARY KEY (session, seq),
        FOREIGN KEY (session, seq) REFERENCES emissions(session, seq)
    )''')


def record_receipt_delta(db, emission, delta):
    db.execute('INSERT INTO adjustment_receipts VALUES (?, ?, ?)',
               (emission.session, emission.seq, str(delta)))


def find_receipt_delta(db, emission):
    row = db.execute('SELECT delta FROM adjustment_receipts WHERE session = ? AND seq = ?',
                     (emission.session, emission.seq)).fetchone()
    return int(row['delta']) if row is not None else None


def project_withdrawal(db, current, initial, target):
    rows = [row for row in read_emissions_through(db, current.session, current.seq)
            if row.fixture == current.fixture]
    withdrawn = {row.target for row in rows if row.kind == 'withdraw'}
    withdrawn.add(target)
    previous = initial
    movements = []
    for row in rows:
        if row.kind == 'adjust' and (row.source == 'local' or row.action not in withdrawn):
            movements.append(row.level - previous)
        previous = row.level
    return replay_levels(initial, movements)
