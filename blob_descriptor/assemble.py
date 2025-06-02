from .verify import Verify
from .utils import input_file, sort_condense
from .main import flag
from .finder import ChunkFinder


class Assemble(Verify):

    bxb: bool = flag("bxb", help="Use block by block method for reading urls", default=False)
    delete: bool = flag("Delete finished chunks")
    max_sectors: int = flag("Max sectors to write", metavar="N")
    rm_extra_blocks: bool = flag("Remove uneeded blocks", default=False)
    sink: str = flag("sink", help="Write blob to SINK", metavar="SINK")
    dry_run: bool = flag("dry-run", "not a trial run", default=False)

    def start(self) -> None:

        from os.path import exists
        from .construct import RequestSectorReader, HtttpRangeSectorReader

        # print(app.config_path)
        def get_params():
            p = {}
            if self.bxb:  # block by block
                p["url_sector_reader"] = HtttpRangeSectorReader
            else:
                p["url_sector_reader"] = RequestSectorReader
            if self.check_hash:
                p["check_hash"] = True
            if self.delete:
                p["delete_finished_blocks"] = True
            if self.max_sectors:
                p["max_sectors"] = self.max_sectors
            if self.output_dir == ":":
                self.output_dir = input_file("Enter output dir")
            return p

        # The Chunks
        params = get_params()
        finder = self.find_chunks()

        # print(self.descriptor)
        # print(self.chunks)
        # print(self.config_path)
        # print(self.chunk_paths.keys())

        if self.sink:
            f = self.sink
            if f in (".", ""):
                sink = None
            elif f == "-":
                from sys import stdout
                from os import fdopen

                # sink = stdout.buffer
                sink = fdopen(stdout.fileno(), "wb", closefd=False)
            else:
                if exists(f):
                    raise RuntimeError(f"Not over writing {f:r}")
                else:
                    sink = open(f, "wb")
            if sink:
                with sink:
                    for f in self.descriptor_files():
                        self.write_to_file(f, finder, params, sink)

        else:
            for f in self.descriptor_files():
                self.write_to_dir(f, finder, params)

    def write_to_file(self, path: str, finder: ChunkFinder, params: dict, sink):
        from .construct import Sink

        const = Sink(path)
        const.chunk_finders.append(finder)
        const.construct(sink, **params)

    def write_to_dir(self, path: str, finder: ChunkFinder, params: dict):
        # OUT: Write to directory
        from .construct import SerialConstructor
        from os.path import exists

        const = SerialConstructor(path)
        const.pwd = self.output_dir
        const.chunk_finders.append(finder)
        const.construct(**params)
        if self.rm_extra_blocks:
            from os import unlink

            total_size = const.descriptor["size"]
            ranges = sort_condense(list(const.available_ranges()))
            for v in const.sources:
                for s, e in ranges:
                    b_start = v["offset"]
                    b_tail_size = total_size % v["block_size"]
                    b_count = total_size // v["block_size"] + ((b_tail_size != 0) and 1 or 0)
                    b_index = v["part_index"]
                    b_end0 = b_start + (b_tail_size if (b_count - 1) == b_index else v["block_size"])
                    b_end = min(total_size, b_start + v["block_size"])
                    try:
                        assert b_end == b_end0
                    except Exception:
                        print(b_end, b_end0)
                        raise
                    path = v.get("path", "")
                    if b_start >= s and b_end <= e and path and exists(path):
                        print("RM {}-{} {}-{} {!r}".format(s, e, b_start, b_end, path))
                        if self.dry_run is False:
                            unlink(path)


(__name__ == "__main__") and Assemble().main()
