from dataclasses import dataclass
import json

from service_support import json_text


@dataclass(frozen=True)
class SceneEdition:
    edition: str
    scene: str
    levels: dict


def ensure_edition_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS editions (
        number INTEGER PRIMARY KEY,
        scene TEXT NOT NULL,
        levels_json TEXT NOT NULL
    )''')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS editions_code ON editions ('E' || number)")


def freeze_edition(db, scene, levels):
    snapshot = dict(sorted(levels.items()))
    cursor = db.execute('INSERT INTO editions (scene, levels_json) VALUES (?, ?)',
                        (scene, json_text(snapshot)))
    return SceneEdition(f'E{cursor.lastrowid}', scene, snapshot)


def read_edition(db, edition):
    row = db.execute("SELECT scene, levels_json FROM editions WHERE 'E' || number = ?",
                     (edition,)).fetchone()
    if row is None:
        return None
    return SceneEdition(edition, row['scene'], json.loads(row['levels_json']))
