import unittest

from specialists.rudi.vector_math import cosine_similarity


class VectorMathTests(unittest.TestCase):
    def test_cosine_similarity_scores_same_direction(self):
        self.assertAlmostEqual(cosine_similarity((1.0, 0.0), (0.9, 0.1)), 0.9938837347)

    def test_cosine_similarity_returns_zero_for_zero_vector(self):
        self.assertEqual(cosine_similarity((0.0, 0.0), (1.0, 0.0)), 0.0)

    def test_cosine_similarity_rejects_dimension_mismatch(self):
        with self.assertRaisesRegex(ValueError, "dimensions do not match"):
            cosine_similarity((1.0,), (1.0, 0.0))


if __name__ == "__main__":
    unittest.main()
