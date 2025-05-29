from logging import info
from .finder import ChunkFinder
from .utils import AutoGet, filesizef2
from .descriptor import read_descriptor


class HtttpRangeSectorReader(AutoGet):
    def __init__(self, url: str, start: int, end: int, sector_size: int, rkw={}):
        self.start = start  # absolute start
        self.end = end  # absolute end
        self.url = url
        self.sector_size = sector_size
        self.rkw = rkw
        self.resp = None
        self.last: list[int] = [None, None]

    def at(self, pos_abs: int):
        from logging import info

        assert pos_abs >= self.start
        assert pos_abs < self.end
        B = self.sector_size
        q, r = divmod(pos_abs, B)
        if self.last[1] == q:
            info("Reuse %s %r", q, self.url)
            b = self.last[0]
            s = q * B
            return b, q, r, s, s + len(b)
        s = q * B
        o = s - self.start
        rkw = self.rkw
        rkw.setdefault("headers", {})["range"] = "bytes=%d-%d" % (o, o + B - 1)
        rkw["stream"] = True
        rkw["allow_redirects"] = True
        with self.http.get(self.url, **rkw) as h:
            c = h.status_code
            if c == 206:
                rh = getattr(h, "history", None)
                b = rh and rh[0].headers.get("Location", "").strip()
                if b:
                    info("Final URL %r --> %r", self.url, b)
                    self.url = b
                b = h.content
            elif c != 200:
                raise RuntimeError("Unexpected http status %r" % c)
            else:
                raise RuntimeError("Http byte range not supported %r" % c)
        self.last[0] = b
        self.last[1] = q
        return b, q, r, s, s + len(b)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _get_http(self, name):
        from requests import session

        return session()


class RequestSectorReader(HtttpRangeSectorReader):
    def __init__(self, url, start, end, sector_size, rkw={}):
        super().__init__(url, start, end, sector_size, rkw)
        self.itr = None
        self.resp = None

    def at(self, pos_abs):
        from logging import info

        assert pos_abs >= self.start
        assert pos_abs < self.end
        B = self.sector_size
        q, r = divmod(pos_abs, B)
        if self.last[1] == q:
            info("Reuse %s %r", q, self.url)
            b = self.last[0]
            s = q * B
            return b, q, r, s, s + len(b)
        s = q * B
        o = s - self.start
        #
        if not self.itr:
            self.itr = self.get_iter(o)
        elif self.pos != o:
            assert self.pos % B == 0
            assert o > self.pos
            # if 0: #TODO: consume up to 'o'
            if (o - self.pos) < (16 * 1024 * 1024):
                info(
                    "Skip read %r->%r @%s %r",
                    (self.pos, self.start + self.pos, divmod(self.start + self.pos, B)),
                    (o, s, divmod(s, B)),
                    q,
                    self.url,
                )
                while self.pos < o:
                    next(self.itr)
                assert self.pos == o
            else:
                info(
                    "Reconnect %r->%r @%s %r",
                    (self.pos, self.start + self.pos, divmod(self.start + self.pos, B)),
                    (o, s, divmod(s, B)),
                    q,
                    self.url,
                )
                self.itr = self.get_iter(o)
            # assert(0)
        self.last[0] = b = next(self.itr)
        self.last[1] = q
        #
        return b, q, r, s, s + len(b)

    def iter_start(self):
        B = self.sector_size
        p = b""
        for c in self.resp.iter_content(B):
            p = p + c
            while len(p) >= B:
                b = p[:B]
                self.pos += len(b)
                yield b
                p = p[B:]
        if p:
            assert len(p) < B
            self.pos += len(p)
            yield p

    def get_iter(self, start):
        B = self.sector_size
        assert start % B == 0
        assert self.end > start
        from logging import info, warn

        rkw = self.rkw
        rkw.setdefault("headers", {})["range"] = "bytes=%d-%d" % (
            start,
            self.end - self.start - 1,
        )
        rkw["stream"] = True
        info(
            "Block fetch %r seek %r %r",
            self.url,
            (start, self.start + start, divmod(self.start + start, B)),
            rkw["headers"]["range"],
        )
        self.close()
        self.resp = r = self.http.get(self.url, **rkw)
        s = r.status_code
        i = self.iter_start()
        if s == 206:
            self.pos = start
        elif s != 200:
            raise RuntimeError("Unexpected http status %r", s)
        else:
            # raise RuntimeError("Http byte range not supported %r", s)
            warn("Byte range not supported %r walking up to %r", self.url, start)
            self.pos = 0
            while self.pos < start:
                next(i)
            assert self.pos == start
        return i

    def close(self):
        if self.resp:
            from logging import info

            info("Closing connection %r", self.url)
            self.resp = self.resp.close() and None


class FileSectorReader(object):
    def __init__(self, path, start, end, sector_size):
        self.start = start
        self.end = end
        self.path = path
        self.sector_size = sector_size
        self.last = [-1, -1]
        self.src = None

    def at(self, pos_abs):
        assert pos_abs >= self.start, f"{pos_abs} {self.start}..{self.end}"
        assert pos_abs < self.end, f"{pos_abs} {self.start}..{self.end}"
        B = self.sector_size
        q, r = divmod(pos_abs, B)
        if self.last[1] == q:
            from logging import debug

            debug("B reuse %s %r", q, self.path)
            b = self.last[0]
            s = q * B
            return b, q, r, s, s + len(b)
        s = q * B
        o = s - self.start
        if not self.src:
            from logging import debug

            debug("B open %r seek %s", self.path, o)
            self.src = open(self.path, "rb")
            self.src.seek(o)
        elif self.src.tell() != o:
            from logging import debug

            debug("B reseek %s->%s %r", self.src.tell(), o, self.path)
            self.src.seek(o)
            assert 0
        self.last[0] = b = self.src.read(B)
        self.last[1] = q
        return b, q, r, s, s + len(b)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self.src:
            from logging import debug, info

            if getattr(self, "remove", None) is True:
                debug("B gone %r", self.path)
                self.src = self.src.close() and None
                from os import unlink

                try:
                    unlink(self.path)
                except Exception:
                    from sys import exc_info

                    info("Failed to delete %r, %s", self.path, str(exc_info()[1]))
            else:
                debug("B done %r", self.path)
                self.src = self.src.close() and None

    def remove_after(self):
        self.remove = True


def vfinal(f, because):
    if f.get("fh"):
        from logging import info

        info("Closing %r, %s", f["path"], because or "")
        f.pop("fh").close()
        assert "_oo_seek" not in f  # on open seek


def vopen(f):
    h = f.get("fh")
    if not h:
        from logging import info

        p = f["_path"]
        o = f.pop("_oo_seek")
        if o > 0:
            info("Appending %r @%s", p, filesizef2(o))
            m = "r+b"
        elif o < 0:
            from os.path import split, isdir

            d, n = split(p)
            if isdir(d):
                info("Creating %r", p)
            else:
                info("Creating %r at %r", n, d)
                from os import makedirs

                makedirs(d)
            m = "wb"
        else:
            info("Open %r", p)
            m = "r+b"
            # m = "wb"
        try:
            h = f["fh"] = open(p, m)
        except Exception:
            from logging import exception

            h = None
            exception("Failed ot open %r", p)
        else:
            (o > 0) and h.seek(o)
    assert "_oo_seek" not in f  # on open seek
    return h


class SerialConstructor(AutoGet):
    pwd: str

    def __init__(self, file):
        self.descriptor = read_descriptor(file)
        self.chunk_finders: list[ChunkFinder] = []

    def _get_sources(self):
        from itertools import chain

        return sorted(
            chain(*(c.items(self.descriptor["md5"], self.descriptor["size"]) for c in self.chunk_finders)),
            key=lambda x: x["offset"],
        )

    def _get_sector_size(self):
        from logging import info

        v = min(self.descriptor["chunks"].keys())
        info("Using sector_size %s", filesizef2(v))
        return v

    def _get_sector_size(self):
        from logging import info

        v = min(self.descriptor["chunks"].keys())
        info("Using sector_size %s", filesizef2(v))
        return v

    def _get_sector_map(self):

        return self.descriptor["chunks"][self.sector_size]

    def _get_pwd(self):

        from os.path import join
        from tempfile import gettempdir

        desc = self.descriptor
        pwd = join(gettempdir(), "%s-%s.tree" % (desc["md5"][:5], desc["size"]))
        info("Constructing at %t", pwd)
        return pwd

    def files_enum(self, start, end):
        from os import stat
        from os.path import join, exists
        from logging import info

        files = self.descriptor["files"]
        pos = 0

        def in_range(s, e):
            assert e >= s
            return s < end and e >= start and end > e
            # return (((s > end) and (end <= e)) or ((s >= start) and (start < e)))

        for f in files:
            # if "offset" in f:
            #     assert pos == f["offset"], f'NEQ {pos}, {f["offset"]} {f} '
            # else:
            #     f["offset"] = pos
            if "_path" not in f:
                f["_path"] = join(self.pwd, f["path"])
            size = f["size"]
            if size < 1:
                info("Zero size %r", f["path"])
                continue
            fh = f.get("fh")
            f_end = pos + size
            if fh:
                if in_range(pos, pos + fh.tell()):
                    yield f
                else:
                    vfinal(
                        f,
                        "@{} Outside {}-{}".format(filesizef2(fh.tell()), filesizef2(start), filesizef2(end)),
                    )
            elif exists(f["_path"]):
                current_size = stat(f["_path"]).st_size
                if current_size > size:
                    raise RuntimeError(
                        "Size %s expected not %s for %r"
                        % (
                            size,
                            current_size,
                            f["_path"],
                        )
                    )
                elif current_size == size:
                    if "_done" not in f:
                        f["_done"] = True
                        info("Done %r size %s", f["path"], filesizef2(current_size))
                elif in_range(pos, pos + current_size):  # current_size < size
                    f["_oo_seek"] = current_size
                    yield f
            elif in_range(pos, pos):
                f["_oo_seek"] = -1
                yield f
            pos += size

    def construct(self, **kwargs):
        from logging import error, info, exception
        from time import time
        from hashlib import md5 as mdnew

        B = self.sector_size
        S = self.sector_map
        url_sector_reader = kwargs.get("url_sector_reader") or RequestSectorReader

        def get_md(b):
            m = mdnew()
            m.update(b)
            return m.hexdigest()

        def block_name(v):
            _ = v.get("url")
            if _:
                return _
            return v["path"]

        def reader(v):
            _ = v.get("url", "")
            if _.startswith("file://"):
                from urllib.request import url2pathname
                from urllib.parse import urlparse

                v["path"] = url2pathname(urlparse(_)[2])
            elif _:
                return url_sector_reader(_, b_start, b_end, B)
            return FileSectorReader(v["path"], b_start, b_end, B)

        delete = kwargs.get("delete_finished_blocks")
        desc = self.descriptor
        check_hash = kwargs.get("check_hash")
        max_sectors = kwargs.get("max_sectors")
        total_size = desc["size"]
        for i, v in enumerate(self.sources):
            assert v["offset"] >= 0
            i_cur = None
            started = time()
            if "block_size" in v:
                assert v["offset"] % B == 0
                assert v["block_size"] > 0
                b_start = v["offset"]
                b_tail_size = total_size % v["block_size"]
                b_count = total_size // v["block_size"] + ((b_tail_size != 0) and 1 or 0)
                b_index = v["part_index"]
                assert b_count > 0
                assert b_index < b_count
                # b_end = b_start + v['block_size']
                b_end = b_start + (b_tail_size if b_index > 0 and (b_count - 1) == b_index else v["block_size"])
                b_fin = total_size if ((b_count - 1) == b_index) else (b_start + v["block_size"])
                assert b_count == 1 or b_fin == b_end, f"{b_fin} != {b_end}"
                info(
                    "B#%s %s-%s %s %s/%s %s",
                    i,
                    filesizef2(b_start),
                    filesizef2(b_end),
                    filesizef2(v["block_size"]),
                    b_index + 1,
                    b_count,
                    block_name(v),
                )
            else:
                b_start = v["offset"]
                b_end = v["end"]
                info("P#%s %s-%s", i, filesizef2(b_start), filesizef2(b_end))

            with reader(v) as sr:
                for j, f in enumerate(self.files_enum(b_start, b_end)):
                    h = vopen(f)
                    if not h:
                        continue
                    f_pos = f["offset"]
                    f_tell = h.tell()
                    f_start = f_pos + f_tell
                    f_end = f_pos + f["size"]
                    assert f_end > f_start
                    f_size = f_end - f_start
                    assert b_end > f_start
                    x_end = min(b_end, f_end)
                    info(
                        "F %s %s-%s-%s %r",
                        i,
                        filesizef2(f_pos),
                        filesizef2(f_start),
                        filesizef2(f_end),
                        f["path"],
                    )
                    i_cur = f_start
                    while i_cur < x_end:
                        try:
                            b, q, r, s, e = sr.at(i_cur)
                            md1 = S[q].get("md5")
                            if md1:
                                md0 = get_md(b)
                                if md0 != md1:
                                    error(
                                        "Wrong hash at sector %s expected %r got %r",
                                        q,
                                        md0,
                                        md1,
                                    )
                                    b = False
                        except Exception:
                            exception(
                                "B %r, F %r, C %r, %r",
                                (b_start, b_end),
                                (f_start, f_end),
                                (i_cur, x_end),
                                v.get("path"),
                            )
                            raise
                        if b is False:
                            break
                        b = b[r : min(e, x_end) - s]
                        # info("BUF %r", (r, s, e, x_end, i_cur, len(b), q))
                        if len(b) < 1:
                            raise RuntimeError("Empty sector %r" % ((r, s, e, x_end, i_cur, q),))
                        # print(" <W" , i_cur, len(b), f["fh"])
                        assert len(b)
                        h.write(b)
                        if max_sectors:
                            max_sectors -= 1
                            if max_sectors <= 0:
                                break
                        i_cur += len(b)
                        now = time()
                        if (now - started) > 30:
                            started = now
                            info(
                                "F %s %s-%s-%s",
                                i,
                                filesizef2(f_start),
                                filesizef2(i_cur),
                                filesizef2(f_end),
                            )
                    if i_cur == f_end:
                        vfinal(f, "At end")
                        if check_hash:
                            vcheck(f)
                if i_cur == b_end:
                    if delete:
                        sr.remove = True
                    # info("Delete? {!r}".format(v['path']))
        #
        for f in self.files_enum(self.descriptor["size"], self.descriptor["size"] + 1):
            pass  # close the last file
        #

    def check(self, chunk_size=25 * 1024 * 1024):
        from os.path import join, exists
        from os import stat
        from hashlib import md5 as mdnew

        files = self.descriptor["files"]
        n = max(len(str(f["size"])) for f in files)
        i = len(str(len(files)))
        mask = "{0:" + str(i) + "d} {md5} {size:" + str(n) + "d} {path}"
        # print(mask)
        c_not_found = 0
        c_size = 0
        c_hash = 0

        def range_clue(f, size_partial=0):
            n = f["offset"] + f["size"]
            last_index = (n // chunk_size) + (1 if (n % chunk_size) else 0) - 1
            n = f["offset"] + size_partial
            first_index = n // chunk_size
            return "-".join(str(x) for x in sorted(set([first_index, last_index])))

        for i, f in enumerate(files):
            full = join(self.pwd, f["path"])
            print(mask.format(i, **f))
            if not exists(full):
                # print(f"\t!NotFound offset:{f['offset']}")
                print(f"{f['offset']:>16} !! NotFound {range_clue(f)}")
                c_not_found += 1
                continue
            st = stat(full)
            if st.st_size != f["size"]:
                c_size += 1
                print(f"{f['offset']:>16} !! Size:{st.st_size} diff:{f['size']-st.st_size} {range_clue(f, st.st_size)}")
                continue
            md = mdnew()
            md.update(open(full, "rb").read())
            if md.hexdigest() != f["md5"]:
                print(f"{f['offset']:>16} !! MD {md.hexdigest()}")
                c_hash += 1
                continue
            print(f"{f['offset']:>16} OK")
        if (c_not_found + c_size + c_hash) == 0:
            print("No Errors")

    def available_ranges(self):
        from os import stat
        from os.path import exists
        from logging import info

        files = self.descriptor["files"]
        pos = 0
        for i, f in enumerate(files):
            if "offset" in f:
                assert pos == f["offset"]
            else:
                f["offset"] = pos
            size = f["size"]
            if size < 1:
                info("Zero size %r", f["path"])
                continue
            p = self.get_full_path(f)
            if exists(p):
                current_size = stat(p).st_size
                if current_size > size:
                    raise RuntimeError(
                        "Size %s expected not %s for %r"
                        % (
                            size,
                            current_size,
                            p,
                        )
                    )
                else:
                    yield (f["offset"], f["offset"] + current_size - 1)
            pos += size

    def non_available_ranges(self):
        from os import stat
        from os.path import exists
        from logging import info

        files = self.descriptor["files"]
        pos = 0
        for i, f in enumerate(files):
            if "offset" in f:
                assert pos == f["offset"]
            else:
                f["offset"] = pos
            size = f["size"]
            if size < 1:
                info("Zero size %r", f["path"])
                continue
            p = self.get_full_path(f)
            first_byte = f["offset"]
            last_byte = f["offset"] + size - 1
            if not exists(p):
                print(f"not exists({p!r})")
                yield (first_byte, last_byte)
            else:
                current_size = stat(p).st_size
                if current_size > size:
                    raise RuntimeError(
                        "Size %s expected not %s for %r"
                        % (
                            size,
                            current_size,
                            p,
                        )
                    )
                elif current_size < size:
                    print(f"current_size:{current_size} size:{size} {p}")
                    yield (first_byte + current_size, last_byte)
            pos += size

    def get_full_path(self, item):
        p = item.get("_path")
        if not p:
            from os.path import join

            p = item["_path"] = join(self.pwd, item["path"])
        return p


def vcheck(f, chunksize=131072):
    from hashlib import md5 as mdnew
    from os import stat
    from logging import info

    p = f["_path"]
    st = stat(p)
    if st.st_size == f["size"]:
        info("Checking hash of %r", p)
        md = mdnew()
        with open(p, "rb") as h:
            b = h.read(chunksize)
            while b:
                md.update(b)
                b = h.read(chunksize)
        if md.hexdigest() == f["md5"]:
            print(
                "Ok {!r} {!r}".format(
                    p,
                    [f["md5"], f["size"]],
                )
            )
        else:
            print("Invalid Hash {!r} {!r}".format(p, [f["md5"], md.hexdigest()]))
    else:
        print("Invalid Size {!r} {!r}".format(p, [f["size"], st.st_size, st.st_size - f["size"]]))


class Sink(object):
    def __init__(self, file):
        self.descriptor = read_descriptor(file)
        self.chunk_finders = []

    def construct(self, out, **kwargs):
        from itertools import chain
        from logging import info
        from hashlib import md5 as mdnew

        l = sorted(
            chain(*(c.items(self.descriptor["md5"], self.descriptor["size"]) for c in self.chunk_finders)),
            key=lambda x: x["offset"],
        )

        desc = self.descriptor
        B = min(self.descriptor["chunks"].keys())
        S = self.descriptor["chunks"][B]

        info("md5 %r", desc["md5"])
        info("size %r", desc["size"])
        url_sector_reader = kwargs.get("url_sector_reader") or RequestSectorReader
        total_size = desc["size"]

        def get_md(b):
            m = mdnew()
            m.update(b)
            return m.hexdigest()

        def block_name(v):
            _ = v.get("url")
            if _:
                return _
            return v["path"]

        def reader(v):
            _ = v.get("url", "")
            if _.startswith("file://"):
                from urllib.request import url2pathname
                from urllib.parse import urlparse

                v["path"] = url2pathname(urlparse(_)[2])
            elif _:
                return url_sector_reader(_, b_start, b_end, B)
            return FileSectorReader(v["path"], b_start, b_end, B)

        def enum():
            pos = 0
            for i, v in enumerate(l):
                if not v:
                    continue
                b_start = v["offset"]
                b_tail_size = total_size % v["block_size"]
                b_count = total_size // v["block_size"] + ((b_tail_size != 0) and 1 or 0)
                b_index = v["part_index"]
                assert b_count > 0
                assert b_index < b_count
                b_end = total_size if ((b_count - 1) == b_index) else (b_start + v["block_size"])
                if pos < b_start:
                    continue
                elif pos >= b_end:
                    s[i] = 0
                    continue
                elif pos == b_start:
                    pos = b_end
                    yield b_start, b_end, v
                else:
                    # pos >= off
                    # pos < end
                    pass
                    yield b_start, b_end, v

        def get_reader(v, start, end, B):
            _ = v.get("url")
            if _:
                return url_sector_reader(_, start, end, B)
            return FileSectorReader(v["path"], start, end, B)

        e = -1
        for i, (s, e, v) in enumerate(enum()):
            info("%r\t%r\t%r\t%r", i, s, e, block_name(v))
        if e == desc["size"]:
            for i, (b_start, b_end, v) in enumerate(enum()):
                info("%r\t%r\t%r\t%r", i, s, e, block_name(v))
                with get_reader(v, b_start, b_end, B) as sr:
                    pos = b_start
                    while pos < b_end:
                        j = "."
                        b, q, r, s, e = sr.at(pos)
                        md1 = S[q].get("md5")
                        if md1:
                            md0 = get_md(b)
                            j = "o" if md0 == md1 else "x"
                        if out:
                            out.write(b)
                        else:
                            print(j, end="", sep="")
                        pos += B
