from scene.drafts import read_draft
from scene.editions import freeze_edition
from scene.fixtures import find_fixture
from service_support import Problem, valid_level


def proof_scene(db, scene):
    draft = read_draft(db, scene)
    if draft is None:
        raise Problem(404, 'unknown_draft')
    if not draft.levels:
        raise Problem(400, 'empty_scene')
    for fixture, level in draft.levels.items():
        if find_fixture(db, fixture) is None:
            raise Problem(400, 'unknown_scene_fixture')
        if not valid_level(level):
            raise Problem(400, 'invalid_initial_level')
    return freeze_edition(db, scene, draft.levels)
