import hashlib
import unittest
import os
import tempfile
from hashlib import md5
from blob_descriptor import RegSource


class TestRegSource(unittest.TestCase):
    def setUp(self):
        # Create a temporary file with known content
        self.test_content = b"hello world" * 1000  # 11,000 bytes
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.write(self.test_content)
        self.tmp.close()
        self.regsource = RegSource(self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)  # Cleanup

    def test_size(self):
        self.assertEqual(self.regsource.size, len(self.test_content))

    def test_md5(self):
        expected = md5(self.test_content).hexdigest()
        self.assertEqual(self.regsource.md5, expected)

    def test_iter_chunks(self):
        chunks = list(self.regsource.iter_chunks(1024))
        joined = b"".join(chunks)
        self.assertEqual(joined, self.test_content)
        self.assertTrue(all(len(chunk) <= 1024 for chunk in chunks))

    def test_unknown_attribute(self):
        with self.assertRaises(AttributeError):
            _ = self.regsource.unknown_attribute


class TestRegSource2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a temporary file for testing
        cls.temp_file = tempfile.NamedTemporaryFile(delete=False)
        cls.test_data = b"This is some test data for RegSource"
        cls.temp_file.write(cls.test_data)
        cls.temp_file.close()

        # Calculate expected MD5
        cls.expected_md5 = hashlib.md5(cls.test_data).hexdigest()
        # Get expected size
        cls.expected_size = len(cls.test_data)

    @classmethod
    def tearDownClass(cls):
        # Clean up the temporary file
        os.unlink(cls.temp_file.name)

    def test_initialization(self):
        # Test initialization with file path
        source = RegSource(file=self.temp_file.name, path="test_path")
        self.assertEqual(source.file, self.temp_file.name)
        self.assertEqual(source.path, "test_path")

        # Test initialization without path
        source = RegSource(file=self.temp_file.name)
        # self.assertEqual(source.path, os.path.basename(self.temp_file.name))

    def test_size_property(self):
        source = RegSource(file=self.temp_file.name)
        # Test size property (lazy loading)
        self.assertEqual(source.size, self.expected_size)
        # Test that it's cached
        self.assertTrue("size" in source.__dict__)

    def test_md5_property(self):
        source = RegSource(file=self.temp_file.name)
        # Test md5 property (lazy loading)
        self.assertEqual(source.md5, self.expected_md5)
        # Test that it's cached
        self.assertTrue("md5" in source.__dict__)

    def test_iter_chunks(self):
        source = RegSource(file=self.temp_file.name)
        block_size = 10  # Small block size for testing

        # Test iter_chunks yields correct data
        chunks = list(source.iter_chunks(block_size))
        combined = b"".join(chunks)
        self.assertEqual(combined, self.test_data)

        # Test chunk sizes (last chunk may be smaller)
        for chunk in chunks[:-1]:
            self.assertEqual(len(chunk), block_size)
        self.assertLessEqual(len(chunks[-1]), block_size)

    def test_calc_md5(self):
        source = RegSource(file=self.temp_file.name)
        # Test calc_md5 method directly
        self.assertEqual(source.calc_md5(), self.expected_md5)

        # Test with custom block size
        self.assertEqual(source.calc_md5(block_size=5), self.expected_md5)

    def test_repr(self):
        source = RegSource(file=self.temp_file.name, path="test_path")
        # Test string representation
        self.assertEqual(repr(source), f"RegSource('test_path')")

    def test_nonexistent_file(self):
        # Test behavior with non-existent file
        with self.assertRaises(FileNotFoundError):
            source = RegSource(file="nonexistent_file")
            _ = source.size  # Should raise FileNotFoundError when trying to get size

    def test_invalid_attribute(self):
        source = RegSource(file=self.temp_file.name)
        # Test accessing invalid attribute
        with self.assertRaises(AttributeError):
            _ = source.invalid_attr


if __name__ == "__main__":
    unittest.main()
