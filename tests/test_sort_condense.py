import unittest
from blob_descriptor.utils import sort_condense


class TestSortCondense(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(sort_condense([]), [])

    def test_single_interval(self):
        self.assertEqual(sort_condense([(1, 3)]), [(1, 3)])

    def test_single_reversed_interval(self):
        self.assertEqual(sort_condense([(3, 1)]), [(1, 3)])

    def test_non_overlapping_intervals(self):
        self.assertEqual(sort_condense([(1, 3), (4, 6), (7, 9)]), [(1, 9)])

    def test_adjacent_intervals(self):
        self.assertEqual(sort_condense([(1, 3), (3, 5), (5, 7)]), [(1, 7)])

    def test_overlapping_intervals(self):
        self.assertEqual(sort_condense([(1, 4), (2, 5), (6, 8)]), [(1, 8)])

    def test_nested_intervals(self):
        self.assertEqual(sort_condense([(1, 10), (2, 5), (3, 4)]), [(1, 10)])

    def test_mixed_order_intervals(self):
        self.assertEqual(sort_condense([(5, 8), (1, 3), (2, 4), (6, 9)]), [(1, 9)])

    def test_reversed_and_normal_intervals(self):
        self.assertEqual(sort_condense([(7, 2), (3, 5), (1, 4)]), [(1, 7)])

    def test_single_point_intervals(self):
        self.assertEqual(sort_condense([(1, 1), (2, 2), (3, 3)]), [(1, 3)])

    def test_consecutive_single_points(self):
        self.assertEqual(
            sort_condense([(1, 1), (2, 2), (3, 3), (4, 4)]),
            [(1, 4)],
        )

    def test_large_numbers(self):
        self.assertEqual(sort_condense([(1000, 2000), (1500, 2500)]), [(1000, 2500)])

    def test_negative_numbers(self):
        self.assertEqual(sort_condense([(-5, -1), (-3, 0), (1, 2)]), [(-5, 2)])

    def test_duplicate_intervals(self):
        self.assertEqual(sort_condense([(1, 3), (1, 3), (1, 3)]), [(1, 3)])

    def test_very_close_intervals(self):
        self.assertEqual(sort_condense([(1, 2), (2, 3), (3, 4), (5, 6)]), [(1, 6)])

    def test_no_intervals(self):
        self.assertEqual(sort_condense([(1, 2), (4, 5), (7, 8)]), [(1, 2), (4, 5), (7, 8)])
        self.assertEqual(sort_condense([(1, 2), (3, 5), (7, 8)]), [(1, 5), (7, 8)])
        self.assertEqual(sort_condense([(1, 2), (2, 5), (7, 8)]), [(1, 5), (7, 8)])


if __name__ == "__main__":
    unittest.main()
