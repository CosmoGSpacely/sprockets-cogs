import json
import math
import unittest

from specialists.uniblab.capture_fixtures import load_capture_fixtures
from specialists.uniblab.readout_probe import (
    NODE_TYPES,
    apply_hand_labels,
    classify_rule_text,
    derive_labels,
    letter_probs,
    q1_options,
    readout,
)


class FakeChat:
    """Returns scripted top-k logprobs for one generated token."""

    def __init__(self, top):
        self.top = top
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        top = [{"token": t, "logprob": v} for t, v in self.top]
        return {"logprobs": [{"token": top[0]["token"], "logprob": top[0]["logprob"],
                              "top_logprobs": top}],
                "prompt_eval_count": 200}


class LetterProbsTest(unittest.TestCase):
    def test_renormalises_over_option_letters_only(self):
        top = [{"token": "A", "logprob": math.log(0.6)},
               {"token": "<|channel>", "logprob": math.log(0.2)},
               {"token": "B", "logprob": math.log(0.2)}]
        probs, missing, outside = letter_probs(top, ["A", "B"])
        self.assertAlmostEqual(probs["A"], 0.75)
        self.assertAlmostEqual(probs["B"], 0.25)
        self.assertEqual(missing, ())
        self.assertAlmostEqual(outside, 0.2)

    def test_missing_letter_is_floored_and_flagged(self):
        top = [{"token": "A", "logprob": -0.01}, {"token": "B", "logprob": -5.0},
               {"token": "x", "logprob": -17.0}]
        probs, missing, _ = letter_probs(top, ["A", "B", "C"])
        self.assertEqual(missing, ("C",))
        self.assertAlmostEqual(probs["C"] / probs["A"], math.exp(-17.0 + 0.01))
        self.assertAlmostEqual(sum(probs.values()), 1.0)


class ReadoutTest(unittest.TestCase):
    def test_maps_letters_back_to_option_ids_in_reverse_order(self):
        chat = FakeChat([("E", -0.1), ("A", -2.4), ("D", -9.0)])
        result = readout("ev", "crit", q1_options("reverse"), chat_client=chat, model="m")
        self.assertEqual(result.letters["cogs/daily"], "E")
        self.assertEqual(result.answer, "cogs/daily")
        self.assertEqual(set(result.missing), {"sprockets/entity", "sprockets/contact"})
        call = chat.calls[0]
        self.assertEqual((call["think"], call["top_logprobs"], call["options"]["num_predict"]),
                         (False, 20, 1))
        user = json.loads(call["messages"][1]["content"])
        self.assertEqual(user["options"][0], {"letter": "A", "description":
                         "sprockets/note: reference or idea, no action"})

    def test_rejects_too_many_options(self):
        with self.assertRaises(ValueError):
            readout("ev", "crit", [(str(i), "x") for i in range(17)], chat_client=FakeChat([]))

    def test_rule_text_is_lifted_from_classify_system(self):
        types, tasks = classify_rule_text()
        self.assertEqual(set(types), set(NODE_TYPES))
        self.assertIn("Do not also put it on a day.", tasks)


class HandLabelTest(unittest.TestCase):
    def _labelled(self):
        return [derive_labels(load_capture_fixtures(only=("contact-and-task",))[0],
                              [{"raw": "Text Jon about truck"}, {"raw": "Jon"}])]

    def test_applies_only_to_ambiguous_items_and_reports_unused(self):
        labelled = self._labelled()
        unused = apply_hand_labels(labelled, [
            {"fixture_id": "contact-and-task", "raw": "Jon", "q1": "sprockets/contact",
             "reason": "r"},
            {"fixture_id": "contact-and-task", "raw": "Call Jon", "q1": "sprockets/task",
             "reason": "r"},
        ])
        jon = labelled[0]["items"][1]
        self.assertEqual((jon["status"], jon["source"], jon["q1"]),
                         ("labelled", "hand", "sprockets/contact"))
        self.assertEqual(labelled[0]["items"][0]["status"], "ambiguous")
        self.assertEqual(unused, ["contact-and-task: 'Call Jon'"])


def _fixture(fixture_id):
    (fixture,) = load_capture_fixtures(only=(fixture_id,))
    return fixture


class LabelDerivationTest(unittest.TestCase):
    def test_project_task_list_items_are_undated_tasks(self):
        fixture = _fixture("project-task-list")
        items = [{"raw": line, "type_hint": "task"} for line in fixture.content.splitlines()[1:]]
        labels = derive_labels(fixture, items)
        self.assertEqual([i["status"] for i in labels["items"]], ["labelled"] * 7)
        self.assertEqual({(i["q1"], i["q2"]) for i in labels["items"]}, {("sprockets/task", "no")})
        self.assertEqual(labels["missed"], [])

    def test_contact_and_task_is_ambiguous_not_guessed(self):
        # Every expected node must include "jon", so the matcher cannot say
        # which item carries the task and which the contact.
        labels = derive_labels(
            _fixture("contact-and-task"),
            [{"raw": "Text Jon about truck"}, {"raw": "Jon"}],
        )
        self.assertEqual([i["status"] for i in labels["items"]], ["ambiguous", "ambiguous"])
        self.assertEqual([i["q1"] for i in labels["items"]], [None, None])

    def test_one_item_carrying_task_daily_and_contact_is_mixed(self):
        labels = derive_labels(_fixture("contact-and-task"), [{"raw": "Text Jon about truck"}])
        (item,) = labels["items"]
        self.assertEqual((item["status"], item["q1"], item["q2"]), ("mixed", None, None))

    def test_unmatched_item_and_missed_node_are_reported(self):
        labels = derive_labels(_fixture("project-task-list"), [{"raw": "Sweep floor"}])
        self.assertEqual(labels["items"][0]["status"], "unmatched")
        self.assertEqual(len(labels["missed"]), 7)


if __name__ == "__main__":
    unittest.main()
