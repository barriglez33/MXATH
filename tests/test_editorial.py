import json
import unittest
from pathlib import Path
from main import editorial_score, queries

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'config.json').read_text())

class TestCollector(unittest.TestCase):
    def test_result_only_rejected(self):
        self.assertLess(editorial_score('Rays defeat Brewers 5-3 in World Series Game 2', '', CONFIG), CONFIG['min_editorial_score'])
    def test_interview_accepted(self):
        self.assertGreaterEqual(editorial_score('Junior Caminero reveals clubhouse reaction after World Series', '', CONFIG), CONFIG['min_editorial_score'])
    def test_editorial_fallback(self):
        self.assertGreaterEqual(editorial_score('Brewers star opens up before World Series', '', CONFIG), CONFIG['min_editorial_score'])
    def test_all_players_rotated(self):
        q = [term for r in range(3) for term in queries(CONFIG, r)]
        for team, players in CONFIG['teams'].items():
            for name in players:
                self.assertTrue(any(f'"{name}"' in item for item in q), name)

if __name__ == '__main__':
    unittest.main()
