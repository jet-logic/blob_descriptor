from .verify import Verify
from .construct import SerialConstructor
from .finder import ChunkFinder
from .utils import sort_condense


class Check(Verify):

    def CHECK(self, path: str, finder: "ChunkFinder") -> None:
        from hashlib import md5 as mdnew

        const = SerialConstructor(path)
        const.pwd = self.output_dir
        const.chunk_finders.append(finder)
        print("chunks", const.descriptor["chunks"].keys())

        total_size = const.descriptor["size"]
        block_sizes = set(x["block_size"] for x in const.sources)
        has_ranges = sort_condense(list(const.available_ranges()))
        print("available_ranges", has_ranges, *const.descriptor.keys())
        non_ranges = sort_condense(list(const.non_available_ranges()))
        print("non_available_ranges", non_ranges)

        bmap = dict((s, {}) for s in block_sizes)

        for s in block_sizes:
            total_blocks = total_size // s + (1 if (total_size % s) else 0)
            bmap[s]["index_map"] = index_map = dict((i, None) for i in range(total_blocks))
            print("block_size:", s, total_blocks)
            for a, b in non_ranges:
                d = b - a
                assert d > 0
                last_index = (b // s) + (1 if (b % s) else 0)
                first_index = a // s
                print("\t", sorted(set([first_index, last_index])))
                assert first_index <= last_index
                i = first_index
                while i <= last_index:
                    index_map[i] = False
                    i += 1

        r = []
        for f in const.chunk_finders:
            for x in f.all():
                if not const.descriptor["md5"].startswith(x["checksum"]):
                    continue
                # print(
                #     x["path"],
                #     x["part_index"],
                #     x["block_size"] == x["part_size"],
                # )
                s = x["block_size"]
                bmap[s]["index_map"][x["part_index"]] = False
                if x["block_size"] == x["part_size"]:
                    r.append([x["part_index"], x["part_index"] + 1])
                    if s in bmap:
                        h = x.get("part_checksum")
                        if not h:
                            h = const.descriptor["chunks"][s][x["part_index"]]["md5"]
                        # if h:
                        #     md = mdnew()
                        #     md.update(open(x["path"], "rb").read())
                        #     if not md.hexdigest().startswith(h):
                        #         continue
                        #     print(x["path"], "hexdigest", h)

                        # TODO: check hash
                        bmap[s]["index_map"][x["part_index"]] = True
                    pass
        print("\t", sort_condense(sorted(r)))
        for s, m in bmap.items():
            print("bmap:", s, [k for (k, v) in m["index_map"].items() if v is False])

        # const.check()

    def start(self) -> None:
        finder = self.find_chunks()
        for f in self.descriptor_files():
            self.VERIFY(f, finder)

        a = {}
        for x in finder.all():
            p = a.get(x["checksum"])
            if p is None:
                p = a[x["checksum"]] = []
            p.append(x)
        for f in self.descriptor_files():
            self.CHECK(f, finder)
