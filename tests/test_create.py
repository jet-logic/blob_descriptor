import unittest


def make_chunks():
    import os, hashlib

    h_all = hashlib.new("md5")

    m = {}
    a = []
    blobs = [os.urandom(512 * 1024) for i in range(5)]
    blobs.append(os.urandom(1024 // 4))

    for i, blob in enumerate(blobs):
        h_cur = hashlib.new("md5")
        h_cur.update(blob)

        a.append(dict(index=i, blob=blob, hash=h_cur.hexdigest()))
        h_all.update(blob)

    m["hash"] = h_all.hexdigest()
    m["blob"] = b"".join(x.pop("blob") for x in a)
    m["512"] = a
    return m


class Test(unittest.TestCase):
    def test_cmd(self):
        import pprint
        from tempfile import mkdtemp, TemporaryDirectory, NamedTemporaryFile
        from os import chdir, urandom
        from subprocess import run

        with TemporaryDirectory() as temp_dir:
            self._create(temp_dir)
        with TemporaryDirectory() as temp_dir:
            self._create(temp_dir, "files")

    def _create(self, wdir, var=None):
        import pprint, random, os
        from tempfile import mkdtemp, TemporaryDirectory, NamedTemporaryFile
        from os import chdir, urandom, listdir
        from subprocess import run, check_output
        from random import uniform

        chdir(wdir)

        def shell(s, **kwargs):
            return run(s, shell=True, check=True, **kwargs)

        cdata = make_chunks()

        if var == "files":
            apple = urandom(int(uniform(1024 * 1024, 1024 * 1024 * 3)))
            with open("apple", "wb") as w:
                w.write(apple)
            banana = urandom(int(uniform(1024 * 1024, 1024 * 1024 * 3)))
            with open("banana", "wb") as w:
                w.write(banana)
            carrot = urandom(int(uniform(1024 * 1024, 1024 * 1024 * 3)))
            with open("carrot", "wb") as w:
                w.write(carrot)
            shell(
                "python3 -m blob_descriptor create -o file.bd --cw 1m,1M carrot apple banana",
            )
            total_size = sum(len(x) for x in [apple, banana, carrot])

        else:
            tf = NamedTemporaryFile()
            tf.write(cdata["blob"])
            tf.seek(0)
            total_size = len(cdata["blob"])

            try:
                shell(
                    "python3 -m blob_descriptor create -o file.bd --cs 700k --cw 1m,1M stdin:///input",
                    stdin=tf,
                )
            except Exception:
                cdata.pop("blob")

                pprint.pprint(cdata)
                raise
        shell(
            "ls -1shR .",
        )

        self.assertEqual(sum(os.stat(f"1M/{x}").st_size for x in os.listdir("1M")), total_size)

        shell(
            "python3 -m blob_descriptor verify file.bd",
        )


if __name__ == "__main__":
    unittest.main()
