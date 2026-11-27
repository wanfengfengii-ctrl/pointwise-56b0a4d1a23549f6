MIN_LEVEL = 0
MAX_LEVEL = 100


def advance_level(level, delta):
    return min(MAX_LEVEL, max(MIN_LEVEL, level + delta))


def replay_levels(initial, deltas):
    value = initial
    for delta in deltas:
        value = advance_level(value, delta)
    return value
