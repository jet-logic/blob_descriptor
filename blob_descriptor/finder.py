class ChunkFinder(object):
    from re import compile as compile_re

    refnchunk1 = compile_re(
        r"""(?ix)
        (?P<checksum>[0-9a-zA-Z]+)[-_]
        (?P<size>\d+)[\._]+
        (?P<block_size>\d+)[-_]
        (?P<part_index>\d+)[-_\.]
        (?P<part_checksum>\w{5,5})
        (?:\.\w{3,4})?"""
    )
    refnchunk3 = compile_re(
        r"""(?ix)
        (?P<checksum>[0-9a-zA-Z]+)_(?P<size>\d+)
        (?:_s(?P<start>[0-9a-zA-Z]+))
        (?:_e(?P<end>[0-9a-zA-Z]+))?
        (?:\.\w{3,4})?"""
    )
    refnchunk2 = compile_re(
        r"(?ix)"
        r"(?P<checksum>[0-9a-zA-Z]+)"
        r"[-_](?P<block_size>\d+[BMGT])(?P<part_index>\d+)"
        r"(?:[-_](?P<part_checksum>\w{5,5}))?"
        r"[-_](?P<size>\d+)"
        r"(?:\.\w{3,4})?"
    )
    # 7149a_15M122_1b476_4663073622
    re_url = compile_re(r"(?P<scheme>https?|ftp)\:\/\/.+")

    def __init__(self):
        self.map_sizes: "dict[int, dict[str, dict[int, dict[int, list[dict]]]]] " = {}
        self.map_parts = {}

    def iter_url_name(self, url):
        from urllib.parse import urlsplit, parse_qs

        v = urlsplit(url)
        if v[3]:
            q = parse_qs(v[3])
            if q.get("filename") and q.get("disposition"):
                # https://s334myt.storage.yandex.net/...&filename=..&disposition=..
                yield q["filename"][0]
        if v[4]:  # fragment
            yield v[4]
        if v[2]:  # path
            v = v[2].rpartition("/")
            if v[2]:
                yield v[2]

    def match(self, name, pwd):
        m = self.re_def(name)
        # print("match", name, m)
        if not m:
            return None
        h = {"basename": name}
        if pwd:
            from os.path import join

            h["path"] = join(pwd, name)
            h["pwd"] = pwd
            from os import stat

            h["part_size"] = stat(h["path"]).st_size
        for k, v in m.groupdict().items():
            if k in ("size", "block_size", "part_index"):
                if v[-1].isalpha():
                    for i, x in enumerate("bkmgtpezy"):
                        if v[-1].lower().endswith(x):
                            h[k] = int(v[0:-1]) * (2 ** (10 * i))
                            break
                else:
                    h[k] = int(v, base=10)
            elif k in ("group", "id"):
                h[k] = v.replace("_", ":").replace(".", ":").replace("-", ":").replace("::", ":")
            else:
                h[k] = v
        return h

    def match_file(self, path, pwd=None):
        if pwd:
            name = path
        else:
            from os.path import split

            pwd, name = split(path)
        if name:
            return self.match(name, pwd)

    def re_def(self, name):
        return self.refnchunk1.search(name) or self.refnchunk2.search(name) or self.refnchunk3.search(name)

    def match_url(self, url, name=None):
        m = None
        if name:
            m = self.re_def(name)
        else:
            for name in self.iter_url_name(url):
                if name:
                    m = self.re_def(name)
                if m:
                    break
        if not m:
            m = self.re_def(url)
        if not m:
            from logging import warn

            warn("Bad URL %r", url)
            return None
        h = {"url": url}
        for k, v in m.groupdict().items():
            if k in ("size", "block_size", "part_index", "start", "end"):
                if v[-1].isalpha():
                    for i, x in enumerate("bkmgtpezy"):
                        if v[-1].lower().endswith(x):
                            h[k] = int(v[0:-1]) * (2 ** (10 * i))
                            break
                else:
                    h[k] = int(v, base=10)
            elif k in ("group", "id"):
                h[k] = v.replace("_", ":").replace(".", ":").replace("-", ":").replace("::", ":")
            else:
                h[k] = v
        # print(h)
        return h

    def accept(self, m):
        return m

    def check_url(self, url):
        m = self.accept(self.match_url(url))
        m and self.add(m)

    def check_file(self, *args):
        m = self.accept(self.match_file(*args))
        m and self.add(m)
        # print('check_file', args, m)

    def search(self, *args):
        from os import listdir

        col = self.map_sizes  # size map_sizes
        for pwd in args:
            m = self.re_url.match(pwd)
            if m:
                self.check_url(pwd)
            else:
                for n in listdir(pwd):
                    self.check_file(n, pwd)
        return self

    def add(self, m):
        try:
            if "block_size" in m:
                (
                    self.map_sizes.setdefault(m["size"], {})
                    .setdefault(m["checksum"], {})
                    .setdefault(m["block_size"], {})
                    .setdefault(m["part_index"], [])
                ).append(m)
            else:
                (self.map_parts.setdefault(m["size"], {}).setdefault(m["checksum"], {}).setdefault(m["start"], [])).append(m)
        except:
            print("Error adding {!r}".format(m))
            raise

    def items(self, md5: str, size: int, part_len: "None | int" = None):
        size_map = self.map_sizes.get(size) or {}
        for md5_prefix in size_map:
            if not md5.startswith(md5_prefix):
                continue
            md5_map = size_map[md5_prefix]
            for block_size in md5_map:
                if part_len and block_size != part_len:
                    continue
                block_size_map = md5_map[block_size]
                for block_index in block_size_map:
                    parts_list = block_size_map[block_index]
                    for part in parts_list:
                        part["offset"] = block_index * block_size
                        yield part
        part_map = self.map_parts.get(size, "")
        for md5_prefix in part_map:
            if not md5.startswith(md5_prefix):
                continue
            md5_map = part_map[md5_prefix]
            for start in md5_map:
                start_map = md5_map[start]
                for part in start_map:
                    part["offset"] = part["start"]
                    yield part

    def all(self):
        for size, size_map in self.map_sizes.items():
            for md5, md5_map in size_map.items():
                for block_size, block_size_map in md5_map.items():
                    for block_index, parts_list in block_size_map.items():
                        for part in parts_list:
                            yield part

    def make_map_file(self, pwd):
        if not pwd:
            from tempfile import gettempdir

            pwd = gettempdir()
        from os.path import join

        for size, size_map in self.map_sizes.items():
            for md5, md5_map in size_map.items():
                maph = {"length": size}
                parts = maph["parts"] = []
                for block_size, block_size_map in md5_map.items():
                    for block_index, parts_list in block_size_map.items():
                        for part in parts_list:
                            s = block_index * block_size
                            parts.append((s, s + block_size, part["path"]))
                name = md5[:5] + "_" + str(size) + ".parts.json"
                ext = ".bin"
                map_file = join(pwd, name + ext)
                with open(map_file, "w") as f:
                    from json import dump

                    dump(maph, f, sort_keys=True, indent=4)

    def make_desc_file(self, pwd):
        if not pwd:
            from tempfile import gettempdir

            pwd = gettempdir()
        from os.path import join

        for size, size_map in self.map_sizes.items():
            for md5, md5_map in size_map.items():
                maph = {"size": size, "md5": md5}
                chunks = maph["chunks"] = {}
                files = maph["files"] = []
                name = md5[:5] + "_" + str(size) + "_desc"
                ext = ".bin" and ""
                files.append(dict(md5=md5, offset=0, size=size, path=md5[:5] + "_" + str(size)))
                for block_size, block_size_map in md5_map.items():
                    for block_index, parts_list in block_size_map.items():
                        parts = chunks.setdefault(block_size, [])
                        for part in parts_list:
                            d = dict(
                                index=part["part_index"],
                                md5=part["part_checksum"],
                                size=part["size"],
                            )
                            for k in ("url", "path"):
                                v = part.get(k)
                                if v:
                                    d[k] = v
                            parts.append(d)
                map_file = join(pwd, name + ext)
                with open(map_file, "wb") as f:
                    from pprint import pformat

                    b = pformat(maph).encode("UTF-8")
                    f.write(b)
