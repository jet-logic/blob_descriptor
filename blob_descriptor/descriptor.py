def read_descriptor(file):
    from re import match, compile as regex
    from ast import literal_eval

    if hasattr(file, "read"):
        desc = h.read()
    elif match(r"https?\:\/\/.+", file):
        from requests import get

        with get(file) as r:
            desc = r.content
    else:
        with open(file, "rb") as h:
            desc = h.read()

    if desc.startswith(b"files"):
        lines = desc.decode("UTF-8").splitlines()
        bd = {"files": [], "chunks": {}}
        _files = _chunks = _chunk_size = None
        m_chunks = regex(r"^\s*(\w+)(\@\d+)?(\:\d+)?\s+(.+)\s*$")
        m_files = regex(r"^\s*(\w+)(@\d+)?(:\d+)\s+(.+)\s*$")
        for x in lines:
            x = x.strip()
            if x == "files":
                _files = _chunks = None
                _files = bd["files"]
                # print(x, "files", _files)
            elif x.startswith("chunks:"):
                _files = _chunks = None
                _, size = x.split(":")
                _chunk_size = int(size)
                _chunks = bd["chunks"].setdefault(_chunk_size, [])
                # print(x, "chunks", _chunks)
            elif x:
                # print(x, bool(_files), bool(_chunks))
                assert _files is not None or _chunks is not None
                if _files is not None:
                    m = m_files.match(x)
                    checksum = m.group(1)
                    offset = m.group(2)
                    size = m.group(3)
                    path = m.group(4)
                    size = None if size is None else int(size.lstrip(":"))
                    if path == ".":
                        bd["md5"] = checksum
                        bd["size"] = size
                    else:
                        _files.append(
                            dict(
                                path=path,
                                offset=(
                                    (0 if len(_files) < 1 else _files[-1]["offset"] + _files[-1]["size"])
                                    if offset is None
                                    else int(offset.lstrip("@"))
                                ),
                                size=size,
                                md5=checksum,
                            )
                        )
                elif _chunks is not None:
                    m = m_chunks.match(x)
                    checksum = m.group(1)
                    index = m.group(2)
                    size = m.group(3)
                    prefix = m.group(4)
                    entry = dict(
                        prefix=prefix,
                        md5=checksum,
                    )

                    if index is None:
                        entry["index"] = len(_chunks)
                        _chunks.append(entry)
                    else:
                        index = int(index.lstrip("@"))
                        entry["index"] = index
                        diff = (index + 1) - len(_chunks)
                        if diff > 0:
                            _chunks.extend([None] * diff)
                        _chunks[index] = entry
                    if size is None:
                        # s = (entry["index"] + 1) * _chunk_size
                        remain = bd["size"] % _chunk_size
                        last_index = (bd["size"] // _chunk_size) + (1 if remain != 0 else 0) - 1

                        if entry["index"] == last_index:
                            size = remain if remain != 0 else _chunk_size
                        else:
                            size = _chunk_size
                    else:
                        size = int(size.lstrip(":"))
                    entry["size"] = size

        return bd
    else:
        return literal_eval(desc.decode("UTF-8"))


def _iter_descriptor(bd, file_offset=None, chunk_size=None, chunk_index=None):
    yield f"files"
    yield f'{bd["md5"]}:{bd["size"]} .'
    for x in bd["files"]:
        yield f'{x["md5"]}' + (
            "" if file_offset is False or x["offset"] is None else "@%d" % x["offset"]
        ) + f':{x["size"]} {x["path"]}'
    for size, chunks in bd["chunks"].items():
        yield f"chunks:{size}"
        for x in chunks:
            yield f'{x["md5"]}' + ("" if chunk_index is False or x["index"] is None else "@%d" % x["index"]) + (
                "" if chunk_size is False or x["size"] is None else ":%d" % x["size"]
            ) + f' {x["prefix"]}'


def write_descriptor(bd: dict, file: str, compact=None, **kwargs):
    if compact is None:
        with open(file, "w") as h:
            for x in _iter_descriptor(bd, **kwargs):
                h.write(f"{x}\n")
        bd2 = read_descriptor(file)
        assert bd == bd2
        # try:
        #     bd2 = read_descriptor(file)
        #     assert bd == bd2
        # except AssertionError:
        #     from unittest import TestCase

        #     import pprint

        #     pprint.pprint(bd)
        #     pprint.pprint(bd2)
        #     TestCase().assertDictEqual(bd, bd2)

    else:
        if compact:
            b = repr(bd).encode("UTF-8")
        else:
            from pprint import pformat

            b = pformat(bd).encode("UTF-8")
        with open(file, "wb") as h:
            h.write(b)
    return True


# ['files', 'md5', 'size', 'chunks']

# bd['files'][0].keys()
# dict_keys(['md5', 'size', 'path', 'offset'])

# bd['chunks'].keys()
# dict_keys([524288, 26214400])

# bd['chunks'][524288][0].keys()
# dict_keys(['md5', 'prefix', 'size', 'index'])

# bd['chunks'][26214400][0].keys()
# dict_keys(['md5', 'prefix', 'size', 'index'])

# [ (x,type(bd[x])) for x in bd.keys() ]
# [('files', list), ('md5', str), ('size', int), ('chunks', dict)]
