"""ZIP scanner tests use in-memory fake archives only."""
from __future__ import annotations

import hashlib
import io
import unittest
import zipfile

from quality_guard.scripts.verify_handoff import inspect_zip


def archive(files: dict[str, bytes]) -> bytes:
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, payload in files.items():
            z.writestr(name, payload)
    return buff.getvalue()


class ArchiveContract(unittest.TestCase):
    def test_basic_crc_manifest_and_nested(self):
        inner = archive({'source/file.py': b'print("ok")'})
        digest = hashlib.sha256(inner).hexdigest()
        outer = archive({'COMPLETE-SOURCE.zip': inner,
                         'SHA256SUMS.txt': f'{digest}  COMPLETE-SOURCE.zip\n'.encode()})
        result = inspect_zip(outer)
        self.assertEqual(result['manifest_entries'], 1)
        self.assertEqual(result['nested'][0]['entries'], 1)

    def test_refuses_traversal(self):
        with self.assertRaisesRegex(ValueError, 'ZIP_PATH_TRAVERSAL'):
            inspect_zip(archive({'../bad.txt': b'no'}))

    def test_refuses_secret_path(self):
        with self.assertRaisesRegex(ValueError, 'SENSITIVE_FILE_PATH_PRESENT'):
            inspect_zip(archive({'DataDir/biometrics.sqlite3': b'secret'}))

    def test_refuses_bad_digest(self):
        with self.assertRaisesRegex(ValueError, 'SHA256SUMS_MISMATCH'):
            inspect_zip(archive({'file.txt': b'a', 'SHA256SUMS.txt': ("0"*64+'  file.txt\n').encode()}))

if __name__ == '__main__': unittest.main()
