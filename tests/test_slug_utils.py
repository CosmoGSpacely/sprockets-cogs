import unittest

from slug_utils import slugify


class SlugUtilsTests(unittest.TestCase):
    def test_slugify_normalizes_punctuation_whitespace_and_case(self):
        self.assertEqual(slugify("  Hello, Sprockets & Cogs!  "), "hello-sprockets-cogs")

    def test_slugify_truncates_to_canonical_sixty_characters(self):
        title = "This is a very long hierarchy proposal title that should be truncated consistently"

        self.assertEqual(slugify(title), "this-is-a-very-long-hierarchy-proposal-title-that-should-be")
        self.assertLessEqual(len(slugify(title)), 60)
