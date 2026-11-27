from dataclasses import dataclass

from service_support import Problem, valid_level


@dataclass(frozen=True)
class TimelineEntry:
    session: str
    fixture: str
    seq: int
    source: str
    kind: str
    action: str
    level: int
    target: str | None


def build_timeline(session, cutoff, rows):
    if not isinstance(rows, list) or len(rows) != cutoff:
        raise Problem(503, 'cut_inconsistent')
    timeline = []
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != TimelineEntry.__dataclass_fields__.keys():
            raise Problem(503, 'cut_inconsistent')
        if row['session'] != session or type(row['seq']) is not int or row['seq'] != position:
            raise Problem(503, 'cut_inconsistent')
        for key in ('fixture', 'source', 'kind', 'action'):
            if not isinstance(row[key], str) or not row[key].strip():
                raise Problem(503, 'cut_inconsistent')
        target = row['target']
        if target is not None and (not isinstance(target, str) or not target.strip()):
            raise Problem(503, 'cut_inconsistent')
        if not valid_level(row['level']):
            raise Problem(503, 'cut_inconsistent')
        timeline.append(TimelineEntry(**row))
    return timeline
