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
    # 撤去只排除本轮同灯位指定的控台调光动作；同一目标即使被多笔撤去
    # 指向，也只在有效历史中排除一次。
    rows = [row for row in read_emissions_through(db, current.session, current.seq)
            if row.fixture == current.fixture]
    withdrawn = {row.target for row in rows if row.kind == 'withdraw'}
    withdrawn.add(target)
    # 从固定初值按原序重放仍有效的调光动作，使用各动作受理时登记的原
    # 增量（饱和处与零增量同样保留），而不是实显差值，这样此前已受理
    # 的现场动作不会被抹掉。撤去本身不携带增量，不参与重放。
    movements = []
    for row in rows:
        if row.kind == 'adjust' and (row.source == 'local'
                                     or row.action not in withdrawn):
            movements.append(find_receipt_delta(db, row))
    return replay_levels(initial, movements)
