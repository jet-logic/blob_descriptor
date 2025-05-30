from typing import Any


def list_ranges(indexes):
    # indexes must be sorted, mutable, tempoary list
    r = []
    while indexes:
        x = indexes.pop(0)
        if r:
            a, b = r[-1]
            assert len(r[-1]) == 2
            assert r[-1][0] <= r[-1][1], r[-1]
            assert r[-1][0] >= 0
            # print(x, r[-1])
            if x <= b and x >= a:
                pass
                # r[-1][0] = x
            elif b + 1 == x:
                r[-1][1] = x
            else:
                r.append([x, x])
        else:
            r.append([x, x])
    return r


# Idea by Ben Voigt in:
# https://stackoverflow.com/questions/32869247/a-container-for-integer-intervals-such-as-rangeset-for-c


def sort_condense(ivs):
    if len(ivs) == 0:
        return []
    if len(ivs) == 1:
        if ivs[0][0] > ivs[0][1]:
            return [(ivs[0][1], ivs[0][0])]
        else:
            return ivs
    # eps = sorted(x for xx in (
    #       ((min(iv), False), (max(iv), True)) for iv in ivs)
    #           for x in xx)
    eps = []
    for iv in ivs:
        eps.append((min(iv), False))
        eps.append((max(iv), True))
    eps.sort()
    ret = []
    i = level = 0
    while i < len(eps) - 1:
        if not eps[i][1]:
            level = level + 1
            if level == 1:
                left = eps[i][0]
        else:
            if level == 1:
                if not eps[i + 1][1] and eps[i + 1][0] == eps[i][0] + 1:
                    i = i + 2
                    continue
                right = eps[i][0]
                ret.append((left, right))
            level = level - 1
        i = i + 1
    ret.append((left, eps[len(eps) - 1][0]))
    return ret


def filesizep(s: str):
    if s[0].isnumeric() or s[0].startswith("."):
        q = s.lower()
        if q.endswith("b"):
            q = q[0:-1]
        for i, v in enumerate("kmgtpezy"):
            if q[-1].endswith(v):
                return int(float(q[0:-1]) * (2 ** (10 * (i + 1))))
        return int(q)
    return int(s)


def filesizef2(s):
    x = ""
    t = ["B", "K", "M", "G", "T", "P", "E", "Z", "Y"]
    i = len(t)
    while i > 0:
        i -= 1
        p = i * 10
        b = 1 << p
        if s >= b:
            # x = (x and (x + '.') or '') + str(s>>p) + t[i]
            if x:
                x += str(s >> p) + t[i].lower()
            else:
                x = str(s >> p) + t[i].upper()
            # x = x + str(s>>p) + t[i]
            s %= b
    return x or "0"


class AutoGet:

    def __getattr__(self, name: str) -> object:
        if not name.startswith("_get_"):
            f = getattr(self, f"_get_{name}", None)
            if f:
                setattr(self, name, None)
                v = f()
                setattr(self, name, v)
                return v
        try:
            m = super().__getattr__
        except AttributeError:
            raise AttributeError(f"{self.__class__.__name__} has no attribute {name}") from None
        else:
            return m(name)


def input_file(msg=""):
    from sys import stdin, stderr
    from os.path import exists

    while 1:
        print(f"{msg}: ", file=stderr, flush=True, end="")
        x = stdin.readline().strip()
        if not exists(x) and (x.startswith('"') and x.endswith('"')) or (x.startswith("'") and x.endswith("'")):
            x = x[1:-1]
        if exists(x):
            return x
        print(f"{x!r} not found", file=stderr, flush=True, end="")
