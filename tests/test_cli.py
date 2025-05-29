from shutil import rmtree
import unittest
import os
import tempfile
import subprocess
from pathlib import Path


class TestBlobDescriptorCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create test files
        cls.test_dir = tempfile.mkdtemp()
        cls.file1 = os.path.join(cls.test_dir, "apple.bin")
        cls.file2 = os.path.join(cls.test_dir, "banana.bin")

        # Create sample binary files (1MB each)
        with open(cls.file1, "wb") as f:
            f.write(os.urandom(1024 * 1024))
        with open(cls.file2, "wb") as f:
            f.write(os.urandom(1024 * 1024))

    @classmethod
    def tearDownClass(cls):
        # Clean up test directory
        rmtree(cls.test_dir)

    def _run_command(self, cmd_args):
        """Helper to run commands and print output"""
        cmd = ["python", "-m", "blob_descriptor"] + cmd_args
        print(f"\n\nExecuting: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.test_dir)
        print("Output:")
        print(result.stdout)
        if result.stderr:
            print("Error:")
            print(result.stderr)
        return result

    # @unittest.skip("Enable when testing create command")
    def test_create_command(self):
        # Test creating a descriptor with chunks
        result = self._run_command(["create", "--cs", "1m", "--cw", "512k,./chunks", "-o", "test.bd", self.file1, self.file2])
        self.assertEqual(result.returncode, 0)
        subprocess.run(["find", self.test_dir])
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "test.bd")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "chunks")))

    # @unittest.skip("Enable when testing verify command")
    def test_verify_command(self):
        # First create a descriptor
        self._run_command(["create", "--cs", "512k", "-o", "verify_test.bd", self.file1])

        # Then verify it
        result = self._run_command(["verify", "verify_test.bd"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("COMPLETE", result.stdout)

    @unittest.skip("Enable when testing check command")
    def test_check_command(self):
        # First create a descriptor with chunks
        self._run_command(["create", "--cs", "512k", "--cw", "512k,./check_chunks", "-o", "check_test.bd", self.file1])
        subprocess.run(["find", self.test_dir])
        # Then check it
        result = self._run_command(["check", "check_test.bd", "./check_chunks"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("OK", result.stdout)

    # @unittest.skip("Enable when testing assemble command")
    def test_assemble_command(self):
        # First create a descriptor with chunks
        self._run_command(["create", "--cs", "512k", "--cw", "512k,./assemble_chunks", "-o", "assemble_test.bd", self.file1])

        # Then assemble it
        output_file = os.path.join(self.test_dir, "assembled.bin")
        result = self._run_command(["assemble", "assemble_test.bd", "--sink", output_file, "-s", "assemble_chunks"])
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(output_file))
        self.assertEqual(os.path.getsize(output_file), os.path.getsize(self.file1))

    # @unittest.skip("Enable when testing all commands together")
    def test_full_workflow(self):
        # 1. Create descriptor and chunks
        create_result = self._run_command(
            ["create", "--cs", "512k", "--cw", "512k,./workflow_chunks", "-o", "workflow.bd", self.file1, self.file2]
        )
        self.assertEqual(create_result.returncode, 0)

        # 2. Verify
        verify_result = self._run_command(["verify", "workflow.bd", "./workflow_chunks"])
        self.assertEqual(verify_result.returncode, 0)

        # 3. Check
        check_result = self._run_command(["check", "workflow.bd", "./workflow_chunks"])
        self.assertEqual(check_result.returncode, 0)

        # 4. Assemble to new file
        output_file = os.path.join(self.test_dir, "workflow_output.bin")
        assemble_result = self._run_command(
            ["assemble", "workflow.bd", "--sink", output_file, "--delete", "-s", "./workflow_chunks"]
        )
        self.assertEqual(assemble_result.returncode, 0)
        self.assertTrue(os.path.exists(output_file))
        self.assertEqual(os.path.getsize(output_file), os.path.getsize(self.file1) + os.path.getsize(self.file2))


if __name__ == "__main__":
    unittest.main()
