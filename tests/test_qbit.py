import hashlib
import unittest

from app.integrations.qbit import hash_from_magnet, infohash_from_torrent


def _bencode(value):
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return _bencode(value.encode())
    if isinstance(value, list):
        return b"l" + b"".join(_bencode(item) for item in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(_bencode(key) + _bencode(value[key]) for key in sorted(value)) + b"e"
    raise TypeError(type(value))


class InfohashTests(unittest.TestCase):
    def test_infohash_matches_sha1_of_info_dict(self):
        info = {b"name": b"book.epub", b"piece length": 262144, b"pieces": b"\x00" * 20, b"length": 42}
        torrent = {b"announce": b"http://tracker.example/announce", b"comment": b"x", b"info": info}
        expected = hashlib.sha1(_bencode(info)).hexdigest()
        self.assertEqual(infohash_from_torrent(_bencode(torrent)), expected)

    def test_infohash_rejects_non_torrent_bytes(self):
        self.assertIsNone(infohash_from_torrent(b"not a torrent"))
        self.assertIsNone(infohash_from_torrent(b""))
        self.assertIsNone(infohash_from_torrent(None))


class MagnetHashTests(unittest.TestCase):
    def test_hash_from_magnet_reads_btih(self):
        magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=x"
        self.assertEqual(hash_from_magnet(magnet), "0123456789abcdef0123456789abcdef01234567")

    def test_hash_from_magnet_ignores_non_magnet(self):
        self.assertIsNone(hash_from_magnet("https://example.test/torrent"))
        self.assertIsNone(hash_from_magnet(None))


if __name__ == "__main__":
    unittest.main()
