import unittest
from menu_public_payload import public_menu_payload, validate_public_payload


class PublicMenuPayloadTests(unittest.TestCase):
    def test_removes_internal_metadata_and_lineage(self):
        menu = {"generated_at": "2026-09-18T08:46:10Z", "inventory_source": "/private/export.csv",
                "pricing_workbook": "/private/pricing.xlsm", "rows": [{"product_name": "Example",
                "thc_display": "25%", "gram": "$5", "quantity": 200,
                "source_product_ids": ["private-product"], "source_skus": ["private-sku"],
                "meta": {"access_token": "private-token"}}]}
        result = public_menu_payload(menu)
        self.assertEqual(result, {"generated_at": menu["generated_at"], "rows": [{
            "product_name": "Example", "thc_display": "25%", "gram": "$5"}]})
        validate_public_payload(result)

    def test_rejects_private_metadata_on_readback(self):
        with self.assertRaises(ValueError):
            validate_public_payload({"inventory_source": "/private", "rows": []})

    def test_rejects_private_row_on_readback(self):
        with self.assertRaises(ValueError):
            validate_public_payload({"rows": [{"product_name": "Example", "quantity": 10}]})

    def test_rejects_nested_data_in_customer_field(self):
        with self.assertRaises(ValueError):
            validate_public_payload({"rows": [{"product_name": {"provider_id": "private"}}]})

    def test_preserves_customer_price_and_treatment(self):
        row = {"product_name": "Example - Example Farm", "brand": "Example Farm", "closeout": True,
               "gram": "$14", "eighth": "$44", "quarter": "$84", "half": "$160", "ounce": "$295",
               "feeling": "Balanced", "looking_for": "Chill"}
        self.assertEqual(public_menu_payload({"rows": [row]})["rows"], [row])

    def test_preserves_cartridge_format_and_missing_source_potency(self):
        row = {"product_name": "Example", "brand": "Example Farm", "format": "AIO", "size": "1g",
               "process": "Live Resin", "price": "$30", "thc": None, "thc_display": "—"}
        result = public_menu_payload({"screen": 1, "rotation_seconds": 20, "brands": ["Example Farm"], "rows": [row]})
        validate_public_payload(result)
        self.assertEqual(result["rows"], [row])


if __name__ == "__main__":
    unittest.main()
