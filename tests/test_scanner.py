import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import editorial_score, make_queries, title_is_noise, query_url, MARKETS, normalize
import json

class TestScanner(unittest.TestCase):
    def setUp(self):
        self.c=json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text(encoding='utf-8'))
    def test_roster(self):
        self.assertEqual(len(self.c['athletes']),47)
        self.assertEqual(len({a['name'] for a in self.c['athletes']}),47)
    def test_queries_rotate(self):
        a,cursor=make_queries(self.c['athletes'],0,34)
        b,_=make_queries(self.c['athletes'],cursor,34)
        self.assertEqual(len(a),34)
        self.assertNotEqual([x[0]['name'] for x in a],[x[0]['name'] for x in b])
    def test_good_news_not_rejected(self):
        title='Checo Pérez reveals contract negotiations ahead of next season'
        self.assertFalse(title_is_noise(title,editorial_score(title,'')))
    def test_result_only_filtered(self):
        title='Final score: 49ers 21-14 Seahawks'
        self.assertTrue(title_is_noise(title,editorial_score(title,'')))
    def test_unicode(self):
        self.assertEqual(normalize('Muñoz'),normalize('Munoz'))
    def test_url(self):
        self.assertIn('when%3A2d',query_url('"Canelo Alvarez"',MARKETS[0],48))

if __name__=='__main__':unittest.main()
