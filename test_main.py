"""DigitalLifeEngine V0.4 核心逻辑自动测试。"""

import unittest

import main


class IndexTests(unittest.TestCase):
    def test_indexes_are_capped_at_100(self):
        self.assertEqual(main.calculate_study_index(20), 100)
        self.assertEqual(main.calculate_activity_index(1000, 20), 100)
        self.assertEqual(main.calculate_interaction_index(20), 100)

    def test_behavior_status_boundaries(self):
        self.assertEqual(main.determine_status(70, 70, 70), "积极")
        self.assertEqual(main.determine_status(40, 40, 40), "一般")
        self.assertEqual(main.determine_status(39, 39, 39), "低活跃")


class StateInferenceTests(unittest.TestCase):
    def make_user(self, mood=3, energy=3, stress=3,
                  study_hours=2, tasks_completed=1):
        return {
            "mood": mood,
            "energy": energy,
            "stress": stress,
            "study_hours": study_hours,
            "tasks_completed": tasks_completed
        }

    def test_four_main_states(self):
        cases = [
            (self.make_user(stress=4), "压力偏高", "comfort"),
            (self.make_user(energy=2), "疲惫", "rest"),
            (self.make_user(mood=5, energy=4, stress=1), "充实", "celebrate"),
            (self.make_user(), "平稳", "encourage")
        ]

        for user_data, expected_state, expected_reaction in cases:
            with self.subTest(expected_state=expected_state):
                result = main.infer_user_state(user_data, [])
                self.assertEqual(result["state"], expected_state)
                self.assertEqual(result["pet_reaction"], expected_reaction)
                self.assertTrue(result["reasons"])
                self.assertIn("title", result["recommendation"])

    def test_old_records_without_subjective_fields_are_compatible(self):
        old_record = {
            "date": "2026-08-20",
            "study_hours": 2,
            "study_index": 20,
            "status": "低活跃"
        }
        result = main.infer_user_state(
            self.make_user(energy=2), [old_record]
        )
        self.assertEqual(result["state"], "疲惫")

    def test_recent_change_adds_explanation(self):
        history = [
            {"date": "2026-08-21", "mood": 4, "energy": 4, "stress": 2},
            {"date": "2026-08-22", "mood": 4, "energy": 5, "stress": 1}
        ]
        result = main.infer_user_state(
            self.make_user(energy=2, stress=3), history
        )
        self.assertIn("今日精力比近期平均水平明显下降", result["reasons"])
        self.assertIn("今日压力比近期平均水平明显上升", result["reasons"])


class HistoryAndGrowthTests(unittest.TestCase):
    def test_consecutive_days_do_not_depend_on_list_order(self):
        records = [
            {"date": "2026-08-25"},
            {"date": "2026-08-23"},
            {"date": "2026-08-24"}
        ]
        self.assertEqual(main.calculate_consecutive_days(records), 3)

    def test_level_boundaries(self):
        self.assertEqual(main.calculate_level(99), 1)
        self.assertEqual(main.calculate_level(100), 2)
        self.assertEqual(main.calculate_level(700), 6)

    def test_intimacy_has_expected_daily_bonus(self):
        record = {
            "interactions": 2,
            "tasks_completed": 1,
            "study_index": 70
        }
        self.assertEqual(main.calculate_daily_intimacy(record), 6)


if __name__ == "__main__":
    unittest.main()
