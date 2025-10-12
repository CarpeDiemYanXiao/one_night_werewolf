import unittest
from core import game_rules

class TestRules(unittest.TestCase):
    def test_default_validate(self):
        # 使用内置默认规则进行校验
        rules = game_rules.load_rules("resources/roles_config.json")
        self.assertTrue(game_rules.validate_rules(rules))

if __name__ == '__main__':
    unittest.main()
