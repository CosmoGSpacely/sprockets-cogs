import unittest

from specialists.uniblab.capture_fixtures import load_capture_fixtures
from specialists.uniblab.readout_probe import derive_labels


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
