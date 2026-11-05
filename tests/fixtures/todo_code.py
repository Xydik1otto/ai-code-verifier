# TODO: implement caching for hot paths


def add(a, b):
    return a + b


def total(items):
    # FIXME: quadratic scan — replace with a set index
    found = []
    for x in items:
        if x not in found:
            found.append(x)
    return found


x = 1  # FIXME: placeholder value  # aicv: ignore
