import re
import unittest
import os
import tempfile
import subprocess
from pathlib import Path
import shutil


class TestBlobDescriptorCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create test directory structure
        cls.test_dir = Path(tempfile.mkdtemp())
        cls.other_dir = Path(tempfile.mkdtemp())
        # Create multi-level directory structure
        cls.input_dir = cls.test_dir / "input"
        cls.input_dir.mkdir()
        (cls.input_dir / "subdir").mkdir()
        (cls.input_dir / "subdir2").mkdir()

        # Create test files at different levels
        cls.file1 = cls.input_dir / "file1.bin"
        cls.file2 = cls.input_dir / "subdir" / "file2.bin"
        cls.file3 = cls.input_dir / "subdir2" / "nested" / "file3.bin"
        cls.file3.parent.mkdir()  # Create nested dir

        # Create sample binary files (1MB each)
        for f in [cls.file1, cls.file2, cls.file3]:
            with f.open("wb") as fh:
                fh.write(os.urandom(1024 * 1024))

    @classmethod
    def tearDownClass(cls):
        # Clean up test directory
        shutil.rmtree(cls.test_dir)
        shutil.rmtree(cls.other_dir)

    def _run_command(self, cmd_args):
        """Helper to run commands and print output"""
        cmd = [str(x) for x in (["python", "-m", "blob_descriptor"] + cmd_args)]
        print(f"\n\nExecuting: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.test_dir))
        print("Output:")
        print(result.stdout)
        if result.stderr:
            print("Error:")
            print(result.stderr)
        return result

    # @unittest.skip("Enable when testing create command with multi-level dirs")
    def test_create_with_directory_tree(self):
        # Test creating descriptor from directory tree
        result = self._run_command(
            ["create", "--mask", "1", "--cw", "1M,./chunks_1m", "-o", "tree_test.bd", str(self.input_dir)]
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.test_dir / "tree_test.bd").exists())
        self.assertTrue((self.test_dir / "chunks_1m").exists())
        a = [*(self.test_dir / "chunks_1m").iterdir()]
        # subprocess.run(["find", self.test_dir])
        print(a)
        for x in a:
            self.assertRegex(x.name, r"^\w+_\d+_\d+_\d+_\w+$")
        self.assertTrue(a)

        # Verify all files were included
        self.assertIn("file1.bin", result.stderr)
        self.assertIn("subdir/file2.bin", result.stderr)
        self.assertIn("subdir2/nested/file3.bin", result.stderr)

    # @unittest.skip("Enable when testing create command")
    def test_create_command(self):
        # Test creating a descriptor with chunks
        result = self._run_command(
            [
                "create",
                "--cw",
                "1M,./chunks",
                "--mask",
                "2",
                "--o:dir",
                self.other_dir,
                "--on-saved",
                "python -c \"open('saved.txt', 'w').write(r'{name} {file} {dir}')\"",
                str(self.file1),
                str(self.file2),
            ]
        )
        subprocess.run(["find", self.test_dir])
        subprocess.run(["cat", self.test_dir / "saved.txt"])
        self.assertEqual(result.returncode, 0)
        with (self.test_dir / "saved.txt").open() as f:
            n, f, d = f.read().split()
            self.assertEqual(self.other_dir, Path(d))
            self.assertEqual(Path(f).parent, Path(d))
            self.assertEqual(Path(f).name, n)
        # self.assertTrue((self.test_dir / "test.bd").exists())
        self.assertTrue((self.test_dir / "chunks").exists())

    # @unittest.skip("Enable when testing verify command")
    def test_verify_command(self):
        # First create a descriptor
        self._run_command(["create", "--cw", "1M,1MChunks", "-o", "verify_test.bd", str(self.file1)])
        subprocess.run(["find", self.test_dir])
        # Then verify it
        result = self._run_command(["verify", "verify_test.bd", self.test_dir / "1MChunks", "-d", self.file1.parent])
        self.assertEqual(result.returncode, 0)
        self.assertIn("COMPLETE", result.stdout)

    @unittest.skip("Enable when testing check command")
    def test_check_command(self):
        # First create a descriptor with chunks
        self._run_command(["create", "--cs", "512k", "--cw", "512k,./check_chunks", "-o", "check_test.bd", str(self.file1)])

        # Then check it
        result = self._run_command(["check", "check_test.bd", "./check_chunks"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("OK", result.stdout)

    @unittest.skip("Enable when testing assemble command")
    def test_assemble_command(self):
        # First create a descriptor with chunks
        self._run_command(
            ["create", "--cs", "512k", "--cw", "512k,./assemble_chunks", "-o", "assemble_test.bd", str(self.file1)]
        )

        # Then assemble it
        output_file = self.test_dir / "assembled.bin"
        result = self._run_command(["assemble", "assemble_test.bd", "--sink", str(output_file)])
        self.assertEqual(result.returncode, 0)
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.stat().st_size, self.file1.stat().st_size)

    @unittest.skip("Enable when testing all commands together")
    def test_full_workflow(self):
        # 1. Create descriptor and chunks
        create_result = self._run_command(
            ["create", "--cs", "512k", "--cw", "512k,./workflow_chunks", "-o", "workflow.bd", str(self.file1), str(self.file2)]
        )
        self.assertEqual(create_result.returncode, 0)

        # 2. Verify
        verify_result = self._run_command(["verify", "workflow.bd", "./workflow_chunks"])
        self.assertEqual(verify_result.returncode, 0)

        # 3. Check
        check_result = self._run_command(["check", "workflow.bd", "./workflow_chunks"])
        self.assertEqual(check_result.returncode, 0)

        # 4. Assemble to new file
        output_file = self.test_dir / "workflow_output.bin"
        assemble_result = self._run_command(["assemble", "workflow.bd", "--sink", str(output_file), "--delete"])
        self.assertEqual(assemble_result.returncode, 0)
        self.assertTrue(output_file.exists())
        self.assertEqual(output_file.stat().st_size, self.file1.stat().st_size + self.file2.stat().st_size)


if __name__ == "__main__":
    unittest.main()
