from dataclasses import dataclass
import json

from service_support import json_text


@dataclass(frozen=True)
class SceneDraft:
    scene: str
    levels: dict


def ensure_draft_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS drafts (
        scene TEXT PRIMARY KEY,
        levels_json TEXT NOT NULL
    )''')


def save_draft(db, scene, levels):
    db.execute('''INSERT INTO drafts (scene, levels_json) VALUES (?, ?)
                  ON CONFLICT(scene) DO UPDATE SET levels_json = excluded.levels_json''',
               (scene, json_text(levels)))
    return SceneDraft(scene, levels)


def read_draft(db, scene):
    row = db.execute('SELECT levels_json FROM drafts WHERE scene = ?', (scene,)).fetchone()
    if row is None:
        return None
    return SceneDraft(scene, json.loads(row['levels_json']))
