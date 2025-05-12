import unittest


class Test(unittest.TestCase):
    def test_size_and_offsets(self):
        s = total_size = 11
        b = block_size = 3

        def total_blocks():
            return s // b + (1 if (s % b) else 0)

        def last_index():
            return s // b + (0 if (s % b) else -1)

        def last_index_off(s, B, o):
            return ((o + s) // B) + (0 if ((o + s) % B) else -1)

        def past_index_off(s, B, o):
            return ((o + s) // B) + (((o + s) % B) and 1 or 0)

        def first_index_off(o, B):
            return o // B

        # def first_index_off(o, B):
        #     return ((o + s) // B) - (o // B)

        for x, i in [(11, 4), (9, 3), (1, 1), (2, 1), (3, 1), (4, 2)]:
            s = total_size = x
            self.assertEqual(
                total_blocks(),
                i,
                f"total blocks total_size={total_size}, block_size={block_size}",
            )

        for x, i in [(4, 1), (2, 0), (5, 1), (6, 1)]:
            s = total_size = x
            self.assertEqual(
                last_index(),
                i,
                f"last index total_size={total_size}, block_size={block_size}",
            )

        s = total_size = 11
        b = block_size = 3
        # print(first_index_off(4, 3, 2))

        for offset, size, index_first, index_last in [
            (0, 2, 0, 0),
            (0, 1, 0, 0),
            (0, 3, 0, 0),
            (0, 4, 0, 1),
            (0, 5, 0, 1),
            (0, 6, 0, 1),
            (2, 1, 0, 0),
            (2, 4, 0, 1),
            (4, 4, 1, 2),
            (3, 6, 1, 2),
            (6, 3, 2, 2),
            (0, 0, 0, -1),
        ]:
            self.assertEqual(
                first_index_off(offset, block_size),
                index_first,
                f"first_index_off {(offset, size, index_first, index_last)!r}, {(total_size, block_size)!r}",
            )
            x = last_index_off(size, block_size, offset)
            self.assertEqual(
                x,
                index_last,
                f"last_index_off {(offset, size, index_first, index_last)!r}, {(total_size, block_size)!r}",
            )
            self.assertEqual(
                past_index_off(size, block_size, offset),
                x + 1,
                f"past_index_off {(offset, size, index_first, index_last)!r}, {(total_size, block_size)!r}",
            )

    def test_list_ranges(self):
        from blob_descriptor.utils import list_ranges

        for indexes, ranges in [
            [[0, 1, 2, 3, 4], [[0, 4]]],
            [[0, 2, 4], [[0, 0], [2, 2], [4, 4]]],
            [[0, 2, 3, 4], [[0, 0], [2, 4]]],
            [[0, 1, 2, 4], [[0, 2], [4, 4]]],
            [[0, 1, 4, 5], [[0, 1], [4, 5]]],
        ]:
            self.assertEqual(
                ranges,
                list_ranges(indexes),
                f"list_ranges {indexes!r}, {ranges!r}",
            )


if __name__ == "__main__":
    unittest.main()
