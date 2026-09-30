import runpy
import unittest
from pathlib import Path


EXTRACTOR = runpy.run_path(str(Path(__file__).with_name("extract-flower-menu")))
annotate_hidden_gems = EXTRACTOR["annotate_hidden_gems"]


class HiddenGemTests(unittest.TestCase):
    def test_matches_birkly_pilot_and_respects_treatment_priority(self):
        rows = [
            {"product_name": "Purple Churro", "quantity": 99, "closeout": False, "aged_inventory": False},
            {"product_name": "Double Blue Jager", "quantity": 1, "closeout": False, "aged_inventory": False},
            {"product_name": "Mendo Breath", "closeout": True, "aged_inventory": False},
            {"product_name": "Cherry Paloma", "closeout": False, "aged_inventory": True},
            {"product_name": "Other Flower", "closeout": False, "aged_inventory": False},
        ]

        result = annotate_hidden_gems(rows)

        self.assertEqual(result["products"], ["Purple Churro", "Double Blue Jager"])
        self.assertEqual([bool(row.get("hidden_gem")) for row in rows], [True, True, False, False, False])
        self.assertTrue(all(row["no_recent_sales"] is False for row in rows))

    def test_other_pilot_names_qualify_when_no_higher_treatment_applies(self):
        rows = [
            {"product_name": "Mendo Breath", "closeout": False, "aged_inventory": False},
            {"product_name": "Cherry Paloma", "closeout": False, "aged_inventory": False},
        ]

        self.assertEqual(
            annotate_hidden_gems(rows)["products"],
            ["Mendo Breath", "Cherry Paloma"],
        )


if __name__ == "__main__":
    unittest.main()
