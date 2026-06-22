"""#17: PluginRegistry unit tests."""
import unittest
from compiler_core.plugin_registry import registry


class TestPluginRegistry(unittest.TestCase):

    def test_discover_finds_addons(self):
        """discover() finds CN, HK, US addons."""
        installed = registry.list_installed()
        self.assertIn("cn", installed)
        self.assertIn("hk", installed)
        self.assertIn("us", installed)

    def test_get_cn_adapter(self):
        """get('cn') returns a CNAdapter instance."""
        adapter = registry.get("cn")
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.jurisdiction, "CN")

    def test_get_hk_adapter(self):
        """get('hk') returns an HKAdapter instance."""
        adapter = registry.get("hk")
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.jurisdiction, "HK")

    def test_get_us_adapter(self):
        """get('us') returns a USAdapter instance."""
        adapter = registry.get("us")
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.jurisdiction, "US")

    def test_get_nonexistent_returns_none(self):
        """get('nonexistent') returns None."""
        adapter = registry.get("nonexistent")
        self.assertIsNone(adapter)

    def test_is_installed_true(self):
        """is_installed returns True for registered addons."""
        self.assertTrue(registry.is_installed("cn"))
        self.assertTrue(registry.is_installed("hk"))
        self.assertTrue(registry.is_installed("us"))

    def test_is_installed_false(self):
        """is_installed returns False for unknown codes."""
        self.assertFalse(registry.is_installed("eu"))
        self.assertFalse(registry.is_installed("jp"))

    def test_get_rules_path(self):
        """get_rules_path returns a path for registered addons."""
        path = registry.get_rules_path("cn")
        self.assertIsNotNone(path)
        self.assertIn("rules.yaml", path)

    def test_get_by_family(self):
        """get_by_family returns a dict (may be empty if no family metadata set)."""
        result = registry.get_by_family("common_law")
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
