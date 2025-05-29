from logging import info
from typing import IO
from .descriptor import write_descriptor


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


class ChunkLister(object):
    """Handles splitting binary data into chunks and tracking chunk metadata."""

    def __init__(self, chunk_size: int):
        from hashlib import md5
        from base64 import b64encode

        self.encoder = lambda b: b64encode(b).decode()
        self.mdnew = md5
        self.observers = []  #  List of observer objects to notify
        self.chunks: list[dict[str, str | int]] = []  # List of chunk metadata dictionaries
        self.current_md = self.mdnew()  # Current hash object being built
        self.current_n = 0  # Bytes accumulated in current chunk
        self.current_index = 0  # Index of current chunk
        self.current_prefix = None  # First few bytes of current chunk
        self.chunk_size = chunk_size  # Size of chunks in bytes

    def update(self, data: bytes):
        """Process incoming data and distribute to chunks"""
        B = self.chunk_size
        pos = 0
        part = data[pos : B - self.current_n]
        while part:
            if self.current_n == 0:
                assert self.current_prefix is None
                self.current_prefix = part[0:6]
                self.notifyObservers("in")
            l = len(part)
            self.current_md.update(part)
            self.notifyObservers("data", part)
            self.current_n += l
            pos += l
            if self.current_n == B:
                self.push()
            else:
                assert self.current_n < B
                assert self.current_n > 0
            part = data[pos : B - self.current_n]

    def push(self):
        """Finalize current chunk and add to chunks list."""
        d = dict(
            md5=self.current_md.hexdigest(),
            prefix=self.encoder(self.current_prefix),
            size=self.current_n,
            index=self.current_index,
        )
        self.notifyObservers("out", d)
        self.chunks.append(d)
        self.current_index += 1
        self.current_md = self.mdnew()
        self.current_n = 0
        self.current_prefix = None

    def get_chunks(self):
        """Get all completed chunks, finalizing any in-progress chunk.

        Returns:
            list: List of chunk metadata dictionaries
        """
        if self.current_prefix is not None:
            self.push()
        return self.chunks

    def notifyObservers(self, *args):
        """Notify all observers of chunk events.

        Args:
            *args: Event arguments (event_type, data)
        """
        for o in self.observers:
            o.update(self, *args)


class BlobDescriptor(object):
    def __init__(self):
        self.files: list[Source] = []  # List of Source objects to process
        self.no_duplicates = None  # hether to check for duplicates
        self.observers = []  # List of observer objects
        self.chunk_writers: list[int | ChunkWriter] = [
            512 * 1024,
        ]  # List of chunk writer configurations

    def make_descriptor(self, **kwargs):
        """Generate descriptor dictionary for all files."""
        block_size = kwargs.get("block_size", 16384)
        desc = kwargs.setdefault("descriptor", {})
        files = desc.setdefault("files", [])
        cwmap: dict[int, ChunkLister] = {}
        for cw in self.chunk_writers:
            if isinstance(cw, ChunkWriter):
                cs = cw.chunk_size
            else:
                cs = cw
                cw = None
            if cs in cwmap:
                cl = cwmap[cs]
            else:
                cl = cwmap[cs] = ChunkLister(cs)
            if cw is not None:
                if cw not in cl.observers:
                    cl.observers.append(cw)
                if cw not in self.observers:
                    self.observers.append(cw)

        chunk_gen = cwmap.values()
        # self.notifyObservers('chunk_listers', chunk_gen)
        from hashlib import md5 as mdnew

        total_hash = mdnew()
        total_size = 0
        for f in self.iter_files():
            _file_size = self.no_duplicates and getattr(f, "size", None)
            # info("DUP check %r", [self.no_duplicates, _file_size])
            if _file_size and any(1 for v in files if v["size"] == _file_size):
                # info("DUP _file_size %r", _file_size)
                _md5 = getattr(f, "md5", None)
                if _md5:
                    # info("DUP _md5 %r", _md5)
                    _item = next(
                        filter(
                            (lambda v: v["size"] == _file_size and v["md5"] == _md5),
                            files,
                        ),
                        0,
                    )
                    if _item:
                        info("DUP _item %r", _item)
                        files.append(dict(_item, path=f.path))
                        continue

            file_hash = mdnew()
            file_size = 0
            offset = total_size
            for b in f.iter_chunks(block_size):
                l = len(b)
                file_size += l
                total_size += l
                file_hash.update(b)
                total_hash.update(b)
                for g in chunk_gen:
                    g.update(b)
            md5 = file_hash.hexdigest()
            if not self.no_duplicates:
                _file_size = getattr(f, "size", None)
                if _file_size is not None and file_size != _file_size:
                    raise RuntimeError("Unexpected size %r" % ((_file_size, file_size),))
                else:
                    _md5 = getattr(f, "md5", None)
                    if _md5 is not None and md5 != _md5:
                        raise RuntimeError(f"Unexpected hash {(_md5, md5)!r} for {f!r}")
            files.append(dict(md5=md5, size=file_size, path=f.path, offset=offset))
        desc["md5"] = total_hash.hexdigest()
        desc["size"] = total_size
        desc["chunks"] = dict((g.chunk_size, g.get_chunks()) for g in chunk_gen)
        return desc

    def format_descriptor_path(self, dir="", prefix="", suffix="", stem="desc", ext=".bd"):
        """Generate path for descriptor file"""

        if not dir:

            from tempfile import gettempdir

            dir = gettempdir()

        from os.path import join

        return join(dir, prefix + stem + suffix + ext)

    def save(self, path: str | dict, **kwargs):
        """Save descriptor to file"""
        desc = self.make_descriptor(**kwargs)
        if not path:
            from os.path import join
            from tempfile import gettempdir

            path = join(gettempdir(), "%s_%s_desc" % (desc["md5"][:5], desc["size"]))
        elif isinstance(path, dict):
            if path.get(""):
                path = path.get("")
            else:
                f = path.pop("stemf", None)
                hash = desc["md5"][:5]
                size = desc["size"]
                if f:
                    path = self.format_descriptor_path(stem=f.format(hash=hash, size=size), **path)
                else:
                    path = self.format_descriptor_path(stem="{}_{}".format(hash, size), **path)
        assert isinstance(path, str)

        info("Saving descriptor {!r}".format(path))
        write_descriptor(desc, path, chunk_size=False, chunk_index=False) and self.notifyObservers(
            "descriptor_saved", desc, path
        )

    def add_file(self, file, path="", **kwargs):
        """Add file to be processed.
        Args:
            file (str|file-like): File path or object
            path (str): Alternate path to store in descriptor
        """
        if not path:
            from os.path import basename

            path = basename(file)
        if self.no_duplicates:
            self.files.append(RegSource(file=file, path=path))
        else:
            self.files.append(FileSource(file=file, path=path))

    def iter_files(self):
        """Iterate through all registered files."""
        for f in self.files:
            yield f

    def notifyObservers(self, *args):
        """Notify all observers of descriptor events."""
        for o in self.observers:
            o.update(self, *args)

    def add_tree(self, path, **kwargs):
        """Recursively add all files in directory tree.

        Args:
            path (str): Root directory path
            **kwargs: Filter options:
                excludes: Patterns to exclude
                includes: Patterns to include
        """
        from pathlib import Path
        from logging import info

        top = Path(path)
        excludes = kwargs.get("excludes")
        includes = kwargs.get("includes")
        if self.no_duplicates:
            Source = RegSource
        else:
            Source = FileSource

        for sub in top.rglob("*"):
            if sub.is_dir():
                continue
            if excludes:
                if any(m for m in excludes if sub.match(m)):
                    continue
            if sub and includes:
                if any(m for m in includes if not sub.match(m)):
                    continue
            if sub:
                r = sub.relative_to(top)
                info("Add %r as %r", str(sub), str(r))
                self.files.append(Source(file=str(sub), path=str(r)))


from hashlib import md5
from os import environ, stat


class Source(AutoGet):
    """Base class for data sources."""

    path: str  # Logical path for the source
    md5: str | None
    size: int | None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.path!r})"

    def iter_chunks(self, block_size: int):
        yield b""


class RegSource(Source):
    """Source for regular files with on-demand hash calculation."""

    def __init__(self, file="", path=""):
        self.file = file
        self.path = path

    def _get_size(self):
        return stat(self.file).st_size

    def _get_md5(self):
        return self.calc_md5()

    def iter_chunks(self, block_size: int):
        with open(self.file, "rb") as h:
            b = h.read(block_size)
            while b:
                yield b
                b = h.read(block_size)

    def calc_md5(self, block_size=131072):
        m = md5()
        with open(self.file, "rb") as h:
            b = h.read(block_size)
            while b:
                m.update(b)
                b = h.read(block_size)
        return m.hexdigest()


class FileSource(Source):
    """Source for file-like objects with pre-known metadata."""

    def __init__(self, file, path: str = None, size: int | None = None, md5: str = ""):
        self.file = file
        self.path = path
        if size is not None:
            self.size = size
        if md5:
            self.md5 = md5

    def iter_chunks(self, block_size: int):
        if hasattr(self.file, "read"):
            h = self.file
        else:
            h = open(self.file, "rb")
        if h:
            b = h.read(block_size)
            while b:
                yield b
                b = h.read(block_size)


class URLSource(Source):
    """Source for remote URLs."""

    def __init__(self, url, path="", size=-1, md5=""):
        self.url = url
        from urllib.parse import urlparse

        u = urlparse(url.strip("/"))
        self.path = path or u.path.split("/")[-1]

    def iter_chunks(self, block_size: int):
        from requests import get as fetch

        return fetch(self.url).iter_content(block_size)


def mask1(md5: str, total_size: int, block_size: int):  #
    return "{md5:.5}_{total_size}_{block_size}_{{index:0{block_ipad}d}}_{{md5:.5}}".format(
        block_ipad=len(str(total_size // block_size + (0 if (total_size % block_size != 0) else -1))),
        md5=md5,
        total_size=total_size,
        block_size=block_size,
    )


def mask2(md5: str, total_size: int, block_size: int):  #
    s = block_size
    for x in "BKMGTPEZY":
        v, r = divmod(s, 1024)
        if r != 0:
            break
        s = v
    if md5:
        return "{md5:.5}_{block_size}{{index:0{block_ipad}d}}_{{md5:.5}}_{total_size}".format(
            block_ipad=len(str(total_size // block_size + (0 if (total_size % block_size != 0) else -1))),
            md5=md5,
            total_size=total_size,
            block_size=str(s) + x,
        )
    else:
        return "{total_size}{block_size}{{index:0{block_ipad}d}}".format(
            block_ipad=len(str(total_size // block_size + (0 if (total_size % block_size != 0) else -1))),
            total_size=total_size,
            block_size=str(s) + x,
        )


def mask3(md5: str, total_size: int, block_size: int):  #
    s = block_size
    for x in "BKMGTPEZY":
        v, r = divmod(s, 1024)
        if r != 0:
            break
        s = v
    if md5:
        return "{md5:.5}_{block_size}{{index:0{block_ipad}d}}_{total_size}".format(
            block_ipad=len(str(total_size // block_size + (0 if (total_size % block_size != 0) else -1))),
            md5=md5,
            total_size=total_size,
            block_size=str(s) + x,
        )
    else:
        return "{total_size}{block_size}{{index:0{block_ipad}d}}".format(
            block_ipad=len(str(total_size // block_size + (0 if (total_size % block_size != 0) else -1))),
            total_size=total_size,
            block_size=str(s) + x,
        )


def mask4(md5: str, total_size: int, block_size: int):  #
    s = block_size
    for x in "BKMGTPEZY":
        v, r = divmod(s, 1024)
        if r != 0:
            break
        s = v
    block_ipad = len(str(total_size // block_size + (0 if (total_size % block_size != 0) else -1)))
    if md5:
        return "{md5:.5}_{block_size}{{index:0{block_ipad}d}}".format(block_ipad=block_ipad, md5=md5, block_size=str(s) + x)
    else:
        return "{total_size}{block_size}{{index:0{block_ipad}d}}".format(
            block_ipad=block_ipad, total_size=total_size, block_size=str(s) + x
        )


name_fmt = mask1


def set_mask(x):
    global name_fmt
    name_fmt = x


class ChunkWriter(AutoGet):
    chunk_size: int


class ChunkWriterDir(ChunkWriter):
    def __init__(self, chunk_size: int, dir: str):
        self.files = {}
        self.chunk_size = chunk_size
        self.target_dir = dir

    def update(self, o, what, *args):
        if isinstance(o, ChunkLister):
            if self.chunk_size != o.chunk_size:
                pass
            elif what == "in":  #  New chunk started
                # Create new temp file for incoming chunk
                assert o.current_index not in self.files
                from tempfile import NamedTemporaryFile as TempFile

                if self.target_dir:
                    from os.path import isdir

                    if not isdir(self.target_dir):
                        from os import makedirs

                        makedirs(self.target_dir)
                self.files[o.current_index] = TempFile(dir=self.target_dir, delete=None)
            elif what == "out":  # Chunk completed
                #  Closes temp file, stores path
                assert isinstance(o, ChunkLister)
                self.files[o.current_index].close()
                self.files[o.current_index] = self.files[o.current_index].name
            elif what == "data":  # Chunk data received
                assert isinstance(o, ChunkLister)
                # Writes chunk data to temp file
                self.files[o.current_index].write(args[0])
        elif isinstance(o, BlobDescriptor):
            if what == "descriptor_saved":
                # Renames all chunks using descriptor metadata
                desc: dict[str:object] = args[0]
                block_size = self.chunk_size
                mask = name_fmt(desc["md5"], desc["size"], block_size)
                for i, c in enumerate(desc["chunks"][block_size]):
                    path = self.files[i]
                    name = mask.format(index=i, md5=c["md5"])
                    self.final_name(path, name)

    def final_name(self, path, name):
        from os.path import split, join
        from os import rename
        from logging import info

        pwd, _ = split(path)
        path2 = join(pwd, name)
        info("Renaming %r to %r", path, path2)
        rename(path, path2)


class ChunkWriterCmd(ChunkWriter):
    """A chunk writer that executes shell commands for each processed chunk.

    This writer handles chunk processing by:
    1. Buffering chunk data in temporary storage (memory/file)
    2. Executing user-provided shell commands when chunks are complete
    3. Supporting range-based filtering for partial processing
    4. Handling both memory and file-based temporary storage

    """

    tmp: IO

    def __init__(self, chunk_size: int, cmd, source_tmp: None | str = None, ranges: None | list[tuple[int, int]] = None):
        self.cmd = cmd
        self.chunk_size = chunk_size
        self.ranges = ranges
        if source_tmp is not None:
            self.source_tmp = source_tmp

    def _get_source_tmp(self):
        return "file"

    def _get_tmp(self):
        _ = self.source_tmp
        if not _:
            from tempfile import TemporaryFile as TempFile

            return TempFile()
        elif _ == "mem":
            from io import BytesIO

            return BytesIO()
        else:
            return open(_, "wb")

    def allow(self, d: dict[str, object]):
        """Check if chunk should be processed based on index ranges."""
        ranges = self.ranges
        if ranges:
            i: int = d["index"]
            for x in ranges:
                if i >= x[0] and i <= x[1]:
                    return True
            return False
        return True

    def update(self, o, what, *args):
        """Handle chunk processing events."""
        if isinstance(o, BlobDescriptor):
            if what == "descriptor_saved":
                self.again(o, args[0])
                pass
        elif isinstance(o, ChunkLister):
            if getattr(self, "chunk_lister", None) != o:
                pass
            elif self.chunk_size != o.chunk_size:
                assert 0
            elif what == "in":
                self.tmp.seek(0)
                self.tmp.truncate()
            elif what == "out":
                assert isinstance(o, ChunkLister)
                d = args[0]
                assert d["size"] == self.tmp.tell()
                self.tmp.seek(0)
                r = self.descriptor["chunks"][self.chunk_size][d["index"]]
                for n in ("md5", "size", "index", "prefix"):
                    if not (d[n] == r[n]):
                        raise RuntimeError("{} not equal {!r} {!r}".format(n, d, r))
                name = self.mask.format(index=d["index"], md5=d["md5"])
                if self.allow(d):
                    self.upload(self.tmp, name)
            elif what == "data":
                assert isinstance(o, ChunkLister)
                self.tmp.write(args[0])

    def again(self, bd: BlobDescriptor, desc: dict[str, object]):
        """Re-process descriptor to trigger command execution."""
        total_size = desc["size"]
        block_size = self.chunk_size
        block_count = total_size // block_size + ((total_size % block_size != 0) and 1 or 0)
        _block_ilast = block_count - 1
        self.chunk_lister = cl = ChunkLister(self.chunk_size)
        self.descriptor = desc
        self.current = {}
        self.mask = name_fmt(desc["md5"], desc["size"], block_size)
        cl.observers.append(self)
        buf_size = 64 * 1024
        total_size = 0
        for f in bd.iter_files():
            file_size = 0
            _offset = total_size
            for b in f.iter_chunks(buf_size):
                l = len(b)
                file_size += l
                total_size += l
                cl.update(b)
        cl.get_chunks()  # push the last

    def upload(self, src: IO, name: str):
        """Execute the configured command for a completed chunk."""
        from logging import info
        from shlex import quote
        from subprocess import Popen, check_call, PIPE

        kwa = dict(name=quote(name), size=str(self.chunk_size))
        ckw = dict(shell=True)
        if self.source_tmp == "mem":
            ckw["stdin"] = PIPE
            kwa["file"] = "-"
        elif self.source_tmp:
            kwa["file"] = self.source_tmp
        else:
            ckw["stdin"] = src
            kwa["file"] = "-"
        cmd = self.cmd.format(**kwa)
        info("Calling {!r}".format(cmd))
        environ["FILE"] = kwa["file"]
        environ["NAME"] = name
        environ["SIZE"] = kwa["size"]

        if self.source_tmp == "mem":
            Popen(cmd, **ckw).communicate(src.getvalue())
        else:
            check_call(cmd, **ckw)
