import importlib
import os
from unittest import TestCase
from unittest.mock import patch

import specialists.rosie.loop as agentic_loop


class ModelConfigTests(TestCase):
    def tearDown(self):
        importlib.reload(agentic_loop)

    def test_model_defaults_to_current_local_model(self):
        with patch.dict(os.environ, {}, clear=True):
            reloaded = importlib.reload(agentic_loop)

        self.assertEqual(reloaded.DEFAULT_MODEL, "gemma4:12b-32k-cosmo")
        self.assertEqual(reloaded.MODEL, "gemma4:12b-32k-cosmo")

    def test_model_can_be_overridden_by_environment(self):
        with patch.dict(os.environ, {"SPROCKETS_COGS_MODEL": "test-model:64k"}):
            reloaded = importlib.reload(agentic_loop)

        self.assertEqual(reloaded.MODEL, "test-model:64k")
