from os.path import relpath, basename
from urllib.parse import urlparse
from . import BlobDescriptor, ChunkWriterDir, ChunkWriterCmd, FileSource, URLSource, shell_quote
from .main import Main, arg, flag
from .utils import filesizep


def abs2rel(path, base):
    try:
        return relpath(path, base)
    except ValueError:
        return basename(path)


class Observer:
    def __init__(self):
        self.when = {}

    def update(self, o, what, *args):
        f = self.when.get(what)
        f and f(*args)


class Create(Main):
    files: "list[str]" = arg("files to add", nargs="+")
    duplicate: bool = flag("link duplicate files", default=None)
    dry_run: bool = flag("dry-run", "not a trial run", default=False)
    base_dir: str = flag("b", "sub directory of files added in descriptor", default="")
    out: str = flag("o", "out", "save descriptor to FILE", metavar="FILE")
    mask: int = flag("m", "mask", "chunks name mask", choices=[1, 2, 3, 4])
    cmd_on_saved: str = flag("on-saved", "run CMD after descriptor file is created", metavar="CMD")
    chunk_sizes: str = flag(
        "chunk-size",
        "cs",
        "include in descriptor block SIZE e.g. '32k', '2M', '1g'",
        metavar="SIZE",
    )
    chunk_write: "list[str]" = flag(
        "chunk-write", "cw", "write block SIZE, in DIR e.g. '25m,/tmp/25MB'", metavar="SIZE,DIR", default=[]
    )
    chunk_call: "list[str]" = flag(
        "chunk-call", "cc", "run CMD in every block SIZE created at TMP file", metavar="SIZE,CMD,TMP", default=[]
    )
    o_stemf: str = flag("o:stemf", "descriptor filename stem part mask", metavar="MASK", default="")
    o_dir: str = flag("o:dir", "descriptor file destination DIRectory", metavar="DIR", default="")

    def start(self) -> None:
        from os import environ
        from logging import basicConfig
        from sys import stdin

        format = environ.get("LOG_FORMAT", "%(levelname)s: %(message)s")
        level = environ.get("LOG_LEVEL", "INFO")
        basicConfig(format=format, level=level)

        bd = BlobDescriptor()
        if self.duplicate is not None:
            bd.no_duplicates = not self.duplicate

        if self.mask:
            from . import set_mask, mask1, mask2, mask3, mask4

            set_mask((mask1, mask2, mask3, mask4)[int(self.mask) - 1])

        if x := self.chunk_sizes:
            bd.chunk_writers.extend([filesizep(x) for x in x.split(",") if x])

        for x in self.chunk_write:
            size, wdir = [v.strip() for v in x.split(",")]
            bd.chunk_writers.append(ChunkWriterDir(filesizep(size), wdir))

        for x in self.chunk_call:
            size, tmp, cmd, *etc = [v.strip() for v in x.split(",")]
            # print("CC", x, (size, tmp, cmd, *etc))
            cwc = ChunkWriterCmd(filesizep(size), cmd, tmp)
            # print(x)
            if etc:
                cwc.ranges = ranges = []
                for r in etc:
                    s, _, e = r.partition("-")
                    if e:
                        ranges.append((int(s), int(e)))
                    else:
                        ranges.append((int(s), int(s)))
                # print(x, cwc.ranges)
            else:
                pass
            bd.chunk_writers.append(cwc)
        obs = Observer()
        if self.cmd_on_saved:
            from shlex import quote
            from subprocess import check_call
            from os.path import split, abspath

            def fn(desc, path, *args):
                pwd, name = split(abspath(path))
                ckw = dict(shell=True)
                environ["NAME"] = name
                environ["FILE"] = path
                environ["DIR"] = pwd
                cmd = self.cmd_on_saved.format(**dict(name=shell_quote(name), file=shell_quote(path), dir=shell_quote(pwd)))
                check_call(cmd, **ckw)

            obs.when["descriptor_saved"] = fn
        if len(obs.when) > 0:
            bd.observers.append(obs)
        # ADD files
        from os.path import isdir

        for f in self.files:
            if not f:
                pass
            elif f.startswith("stdin:///"):
                bd.files.append(FileSource(stdin.buffer, path=urlparse(f)[2].strip("/")))
            elif "://" in f:
                bd.files.append(URLSource(f))
            elif "-" == f:
                for s in stdin:
                    f = s.strip()
                    if not f:
                        continue
                    if self.base_dir:
                        bd.add_file(f, abs2rel(f, self.base_dir))
                    else:
                        bd.add_file(f)
            elif isdir(f):
                bd.add_tree(f)
            elif self.base_dir:
                bd.add_file(f, abs2rel(f, self.base_dir))
            elif f:
                bd.add_file(f)

        p = {}
        if self.o_dir:
            p["dir"] = self.o_dir
        if self.o_stemf:
            p["stemf"] = self.o_stemf
        if self.out:
            p[""] = self.out
        if len(bd.files) > 1:
            bd.files.sort(key=lambda x: x.path)

        if self.dry_run is False:
            bd.save(p)


(__name__ == "__main__") and Create().main()
