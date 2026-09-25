"""Small regression checks for scientific validity boundaries in the new tools."""
import unittest
import pandas as pd
from evaluate_weka import name_components
from validate_annotations import assess, unique_labels


class ValidationTests(unittest.TestCase):
    def test_unknown_is_not_a_negative_and_duplicates_do_not_inflate_recall(self):
        keys = [('2026-01-01 00:00:00', 'A'), ('2026-01-01 00:00:00', 'A'),
                ('2026-01-01 00:00:01', 'A')]
        manual = pd.DataFrame([(*k, v) for k, v in zip(keys, ['active', 'active', 'unknown'])], columns=['Timestamp', 'Badge_Name', 'activity_label'])
        auto = pd.DataFrame([(*k, 'active') for k in keys], columns=['Timestamp', 'Badge_Name', 'auto_activity_label'])
        result = assess(manual, auto)
        self.assertEqual(result['matched_unique_keys'], 2)
        self.assertEqual(result['annotated_active_keys'], 1)
        self.assertEqual(result['unannotated_keys'], 1)
        self.assertEqual(result['recall_on_annotated_active_keys'], 1)
        self.assertIsNone(result['precision'])
        self.assertIsNone(result['overall_binary_accuracy'])

    def test_conflicting_duplicate_labels_are_excluded(self):
        frame = pd.DataFrame([('2026-01-01', 'A', 'active'), ('2026-01-01', 'A', 'not_active')], columns=['Timestamp', 'Badge_Name', 'activity_label'])
        clean, audit = unique_labels(frame, 'activity_label')
        self.assertTrue(clean.empty)
        self.assertEqual(audit['conflicting_keys_excluded'], 1)

    def test_participant_grouping_is_transitive(self):
        self.assertEqual(name_components({'one': {'A'}, 'two': {'A', 'B'}, 'three': {'B'}, 'four': {'C'}}), [['four'], ['one', 'three', 'two']])


if __name__ == '__main__':
    unittest.main()
