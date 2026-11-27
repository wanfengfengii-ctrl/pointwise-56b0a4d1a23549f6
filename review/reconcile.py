from dataclasses import asdict

from review.manifest import collect_sources
from review.timeline import build_timeline
from service_support import Problem


def reconcile_cut(session, edition, bindings, cutoff, cut):
    if (cut.get('session') != session or type(cut.get('cutoff')) is not int
            or cut['cutoff'] != cutoff):
        raise Problem(503, 'cut_inconsistent')
    timeline = build_timeline(session, cutoff, cut.get('emissions'))
    initial = timeline[:len(bindings)]
    expected = [(item.fixture, item.initial, 'initial') for item in bindings]
    if [(row.fixture, row.level, row.kind) for row in initial] != expected:
        raise Problem(503, 'cut_inconsistent')
    bound = {item.fixture for item in bindings}
    for row in timeline[len(bindings):]:
        if row.fixture not in bound or row.kind == 'initial':
            raise Problem(503, 'cut_inconsistent')
    return {
        'session': session, 'edition': edition, 'cutoff': cutoff,
        'timeline': [asdict(entry) for entry in timeline],
        'sources': [asdict(source) for source in collect_sources(timeline)],
    }
