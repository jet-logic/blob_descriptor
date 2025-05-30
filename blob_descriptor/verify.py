from configparser import ConfigParser
from .finder import ChunkFinder
from .main import Main, arg, flag
from .utils import filesizef2, input_file, list_ranges


class Verify(Main):
    descriptor: str = arg("Descriptor file")
    chunks: "list[str]" = arg("Chunks for the descriptor", nargs="*")
    output_dir: str = flag("d", "Output files to DIRectory", default=".", metavar="DIR")
    check_hash: bool = flag("check-hash", "Verify hashes after assemble")
    search_dirs: "list[str]" = flag("search", "s", "Search DIR for chunks", metavar="DIR", default=[])

    config: "ConfigParser"
    config_path: str
    chunk_paths: "dict[str, str]"

    def _get_config_path(self):
        from os import environ
        from os.path import expanduser

        return environ.get("BLOB_DESCRIPTOR_CONF") or expanduser("~/.config/blob_descriptor.conf")

    def _get_config(self):
        from configparser import ConfigParser
        from os.path import exists

        config = ConfigParser()
        if exists(self.config_path):
            config.read(self.config_path)
        return config

    def _get_chunk_paths(self):
        from os.path import expanduser, isdir, abspath

        def enum():
            try:
                dirs = self.config.get("blob_descriptor", "search").splitlines()
            except Exception:
                pass
            else:
                for v in dirs:
                    if v:
                        v = expanduser(v)
                        if isdir(v):
                            yield v
            try:
                dirs = self.search_dirs or ()
            except Exception:
                pass
            else:
                for v in dirs:
                    if v and isdir(v):
                        yield v

        return dict((abspath(x), x) for x in enum())  # dict as ordered set

    def find_chunks(self):
        from .finder import ChunkFinder
        from os.path import isdir

        finder = ChunkFinder()
        for a in self.chunks:
            if isdir(a):
                self.chunk_paths[a] = a
            elif "://" in a:
                # print('check_url', a)
                finder.check_url(a)
            else:
                finder.check_file(a)
        for d in self.chunk_paths:
            # print("SD", d)
            finder.search(d)
        return finder

    def ready(self) -> None:
        from logging import basicConfig
        from os import environ

        format = environ.get("LOG_FORMAT", "%(levelname)s: %(message)s")
        level = environ.get("LOG_LEVEL", "INFO")
        basicConfig(format=format, level=level)
        return super().ready()

    def descriptor_files(self):
        from os.path import exists, isabs, join, isfile

        path = self.descriptor
        if not path:
            return
        elif path == ":":
            path = input_file("Enter bd file")
        elif not exists(path) and not isabs(path):
            for d in self.chunk_paths.keys():
                a = join(d, path)
                if isfile(a):
                    yield a
        if exists(path):
            yield path
        else:
            raise RuntimeError(f"Not found {path}")

    def VERIFY(self, path: str, finder: "ChunkFinder"):
        from os.path import exists
        from os import stat
        from hashlib import md5 as mdnew
        from logging import info
        from .construct import SerialConstructor

        const = SerialConstructor(path)
        const.pwd = self.output_dir
        const.chunk_finders.append(finder)

        desc = const.descriptor
        total_size = desc["size"]
        block_sizes: set[int] = set(x for x in desc["chunks"].keys())
        files = desc["files"]

        if 1:
            block_sizes_map: "dict[int, dict[str, object]]" = dict((s, {}) for s in block_sizes)
            # print(block_sizes_map)
            for s in block_sizes:
                total_blocks = total_size // s + (1 if (total_size % s) else 0)
                block_sizes_map[s]["index_map"] = index_map = dict((i, None) for i in range(total_blocks))

        def tick_byte_range(a, b, f, val=True):
            for s, m in block_sizes_map.items():
                # print("\t", sorted(set([first_index, last_index])))
                last_index = ((b + 1) // s) + (0 if ((b + 1) % s) else -1)
                first_index = a // s  # + (1 if (a % s) else 0)
                assert first_index <= last_index
                i = first_index
                while i <= last_index:
                    m["index_map"][i] = val
                    i += 1

        print(f"{desc['md5']} {path}")
        print(
            f"     {len(desc['files'])} files {desc['size']} bytes",
            ",".join(f"{filesizef2(s)}x{len(m)}" for s, m in desc["chunks"].items()),
            "chunks",
        )
        N = len(str(total_size))

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
            p = const.get_full_path(f)
            first_byte = f["offset"]
            past_byte = f["offset"] + size
            last_byte = f["offset"] + size - 1
            end_byte = -1

            print(f"  {f['md5']} {f['path']}")

            def enum():
                yield f"%{N}d" % (f["offset"],)
                yield f"%{N}db" % size
                for s, m in desc["chunks"].items():
                    last_index = (past_byte // s) + (0 if (past_byte % s) else -1)
                    first_index = f["offset"] // s
                    total_blocks = last_index - first_index + 1
                    if first_index == last_index:
                        yield (f"{filesizef2(s)}({first_index})")
                    elif end_byte > 0:
                        end_index = end_byte // s
                        yield (f"{filesizef2(s)}({first_index}-{end_index}-{last_index})")
                    else:
                        yield (f"{filesizef2(s)}({first_index}-{last_index})")
                    assert first_index >= 0
                    assert last_index >= first_index
                    assert total_blocks > 0
                    assert (
                        (last_index - first_index) + 1
                    ) == total_blocks, f"{first_index}-{last_index}, {total_blocks}, {f!r}"

            indc = ""

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
                elif current_size < size:
                    end_byte = first_byte + current_size
                    tick_byte_range(end_byte, last_byte, f)
                    indc = f"PARTIAL({filesizef2(current_size)})"
                else:
                    # TODO: check hash
                    indc = "COMPLETE"
                    if self.check_hash:
                        md = mdnew()
                        with open(p, "rb") as fh:
                            md.update(fh.read())
                        if md.hexdigest() == f["md5"]:
                            indc = f"VALID"
                        else:
                            indc = f"INVALID Hash {md.hexdigest()!r}"
            else:
                tick_byte_range(first_byte, last_byte, f)
                indc = "ABSENT"

            print(f"    ", *enum(), indc)

            pos += size
        # From the found checksum (Not working)
        for s, m in block_sizes_map.items():
            parts = [
                x
                for f in const.chunk_finders
                for x in f.all()
                if desc["md5"].startswith(x["checksum"]) and x["block_size"] == s
            ]
            for x in parts:
                i = x.get("part_index", -1)
                if i > -1:
                    # TODO: check hash
                    print(i, x["path"], m["index_map"][i])
                    m["index_map"][i] = None
        # setup missing
        for s, m in block_sizes_map.items():
            if any(x for i, x in m["index_map"].items() if x):
                m["missing"] = list_ranges(sorted(i for i, x in m["index_map"].items() if x))

        head = None
        for s, m in block_sizes_map.items():
            d = m.get("missing")
            if not d:
                continue
            elif not head:
                print("Missing:")
                head = True
            # exclude chunks
            n = sum(((b - a) + 1) for a, b in d)

            print(
                " ",
                f"{filesizef2(s)} x{n}",
                ",".join(f"{a}{'' if a==b else '-%s'%(b)}" for (a, b) in m["missing"]),
                filesizef2(n * s),
            )

    def start(self) -> None:
        finder = self.find_chunks()
        for f in self.descriptor_files():
            self.VERIFY(f, finder)
