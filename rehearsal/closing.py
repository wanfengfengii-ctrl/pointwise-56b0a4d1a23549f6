from rehearsal.bindings import read_bindings
from rehearsal.sessions import begin_closing, mark_closed
from review.archive import find_report_for_session, freeze_report
from review.reconcile import reconcile_cut
from service_support import Problem, TransportError, database


def close_session(path, lamp, session):
    with database(path, write=True) as db:
        existing = find_report_for_session(db, session)
        if existing is not None:
            return {'session': session, 'report': existing['report']}
        closing = begin_closing(db, session)
        bindings = read_bindings(db, session)

    try:
        sealed = lamp.seal_session(session)
        cutoff = sealed.get('cutoff')
        if sealed.get('session') != session or type(cutoff) is not int or cutoff < 1:
            raise Problem(503, 'invalid_cutoff')
        cut = lamp.read_cut(session, cutoff)
        candidate = reconcile_cut(session, closing.edition, bindings, cutoff, cut)
    except (Problem, TransportError) as exc:
        if isinstance(exc, Problem) and exc.code == 'cut_inconsistent':
            raise
        raise Problem(503, 'close_unconfirmed') from exc

    with database(path, write=True) as db:
        existing = find_report_for_session(db, session)
        if existing is None:
            existing = freeze_report(db, candidate)
            mark_closed(db, session)
        return {'session': session, 'report': existing['report']}
