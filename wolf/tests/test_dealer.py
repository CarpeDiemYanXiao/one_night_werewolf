import unittest
from core.werewolf_dealer import WerewolfDealer

class TestDealer(unittest.TestCase):
    def setUp(self):
        self.dealer = WerewolfDealer()

    def test_deal_counts(self):
        for n in range(4,10):
            if str(n) in self.dealer.rules:
                players, center = self.dealer.deal(n)
                self.assertEqual(len(players), n)
                self.assertEqual(len(center), 3)

    def test_invalid_player_count(self):
        with self.assertRaises(ValueError):
            self.dealer.deal(2)
        with self.assertRaises(ValueError):
            self.dealer.deal(11)

if __name__ == '__main__':
    unittest.main()
