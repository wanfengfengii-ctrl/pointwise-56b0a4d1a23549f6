from dataclasses import dataclass

from review.timeline import TimelineEntry
from service_support import Problem


@dataclass(frozen=True)
class SourceRecord:
    seq: int
    fixture: str
    source: str
    kind: str
    action: str
    target: str | None


def collect_sources(timeline: list[TimelineEntry]):
    seen = {}
    sources = []
    for entry in timeline:
        identity = (entry.source, entry.action)
        if identity in seen:
            raise Problem(503, 'cut_inconsistent')
        if entry.kind == 'withdraw':
            target = seen.get(('desk', entry.target))
            if (entry.source != 'desk' or target is None or target.kind != 'adjust'
                    or target.fixture != entry.fixture):
                raise Problem(503, 'cut_inconsistent')
        elif entry.kind == 'adjust':
            if entry.source not in ('desk', 'local') or entry.target is not None:
                raise Problem(503, 'cut_inconsistent')
        elif entry.kind == 'initial':
            if entry.source != 'initial' or entry.action != entry.fixture or entry.target is not None:
                raise Problem(503, 'cut_inconsistent')
        else:
            raise Problem(503, 'cut_inconsistent')
        seen[identity] = entry
        sources.append(SourceRecord(entry.seq, entry.fixture, entry.source, entry.kind,
                                    entry.action, entry.target))
    return sources
