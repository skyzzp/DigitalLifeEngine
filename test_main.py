"""DigitalLifeEngine V0.5 核心逻辑自动测试。"""

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


class UserProfileTests(unittest.TestCase):
    def make_record(self, day, mood=3, energy=3, stress=3,
                    state="平稳", study_hours=2,
                    tasks_completed=2, interactions=3):
        return {
            "date": f"2026-08-{day:02d}",
            "mood": mood,
            "energy": energy,
            "stress": stress,
            "inferred_state": state,
            "study_hours": study_hours,
            "game_minutes": 60,
            "tasks_completed": tasks_completed,
            "interactions": interactions
        }

    def test_profile_maturity_uses_subjective_sample_count(self):
        old_record = {
            "date": "2026-08-01",
            "study_hours": 2,
            "game_minutes": 30,
            "tasks_completed": 1,
            "interactions": 1
        }
        records = [old_record, self.make_record(2), self.make_record(3)]
        profile = main.build_user_profile(records, "2026-08-03")

        self.assertEqual(profile["maturity"], "数据积累中")
        self.assertEqual(profile["sample_size"]["total_days"], 3)
        self.assertEqual(profile["sample_size"]["subjective_days"], 2)

    def test_seven_days_create_stable_profile_and_growth_strategy(self):
        records = [
            self.make_record(
                day, mood=5, energy=4, stress=1,
                state="充实", study_hours=5,
                tasks_completed=4, interactions=6
            )
            for day in range(1, 8)
        ]
        profile = main.build_user_profile(records, "2026-08-07")

        self.assertEqual(profile["maturity"], "画像较稳定")
        self.assertEqual(profile["long_term"]["dominant_state"], "充实")
        self.assertEqual(profile["care_strategy"]["mode"], "growth")
        self.assertIn("学习投入较高", profile["traits"])
        self.assertIn("乐于与桌宠互动", profile["traits"])

    def test_profile_is_recalculated_after_record_change(self):
        records = [self.make_record(1, stress=1), self.make_record(2, stress=1)]
        original = main.build_user_profile(records, "2026-08-02")

        records[1] = self.make_record(2, stress=5)
        corrected = main.build_user_profile(records, "2026-08-02")

        self.assertEqual(original["sample_size"], corrected["sample_size"])
        self.assertNotEqual(
            original["long_term"]["avg_stress"],
            corrected["long_term"]["avg_stress"]
        )

    def test_profile_context_is_attached_to_recommendation(self):
        records = [
            self.make_record(day, stress=5, state="压力偏高")
            for day in range(1, 4)
        ]
        profile = main.build_user_profile(records, "2026-08-03")
        record = {
            "inferred_state": "压力偏高",
            "recommendation": {"title": "放松", "difficulty": 2}
        }

        main.apply_profile_to_recommendation(record, profile)

        self.assertEqual(record["recommendation"]["difficulty"], 1)
        self.assertIn("profile_context", record["recommendation"])

    def test_incomplete_legacy_behavior_fields_do_not_break_profile(self):
        records = [
            {
                "date": f"2026-08-{day:02d}",
                "mood": 3,
                "energy": 3,
                "stress": 3,
                "inferred_state": "平稳"
            }
            for day in range(1, 4)
        ]

        profile = main.build_user_profile(records, "2026-08-03")

        self.assertEqual(profile["maturity"], "画像形成中")
        self.assertIsNone(profile["long_term"]["avg_study_hours"])


if __name__ == "__main__":
    unittest.main()
