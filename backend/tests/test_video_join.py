import unittest
import numpy as np
from backend.video_join import join_overlap


class JoinTest(unittest.TestCase):
    def test_overlap_preserves_timing_and_sharp_edges(self):
        a = np.zeros((10, 8, 8, 3), np.uint8); a[:, :, 2:4] = 255
        b = np.zeros((12, 8, 8, 3), np.uint8); b[:, :, 4:6] = 255
        previous, incoming = join_overlap(a, b, 4)
        self.assertEqual((len(previous), len(incoming)), (10, 8))
        # A dissolve would create intermediate values and double contours.
        self.assertTrue(set(np.unique(previous)).issubset({0, 255}))
        self.assertTrue(set(np.unique(incoming)).issubset({0, 255}))

    def test_identical_overlap_is_kept_once(self):
        rng = np.random.default_rng(42)
        source = rng.integers(0, 256, (18, 8, 8, 3), dtype=np.uint8)
        a, b = join_overlap(source[:10], source[6:], 4)
        np.testing.assert_array_equal(np.concatenate((a, b)), source)

    def test_invalid_overlap_rejected(self):
        with self.assertRaises(ValueError):
            join_overlap(np.zeros((2, 8, 8, 3)), np.zeros((2, 8, 8, 3)), 3)
