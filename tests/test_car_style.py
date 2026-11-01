import unittest
from types import SimpleNamespace
from services.car_style import comparison_styles,team_key,rgb


class CarStyleTests(unittest.TestCase):
    def lap(self,team,code='HAM',color='#778899'):
        return SimpleNamespace(team=team,code=code,color=color)

    def test_hamilton_follows_session_team_not_driver_code(self):
        a=comparison_styles([self.lap('Mercedes')])[0]
        b=comparison_styles([self.lap('Ferrari')])[0]
        self.assertEqual(a['body'],'#9da4ac')
        self.assertEqual(b['body'],'#e52235')

    def test_known_teams_and_historical_names(self):
        for name,key in [('Red Bull Racing','redbull'),('McLaren','mclaren'),
                         ('Mercedes-AMG Petronas','mercedes'),('RB F1 Team','racingbulls'),
                         ('Racing Bulls','racingbulls'),('AlphaTauri','racingbulls'),
                         ('Stake F1 Team Kick Sauber','sauber'),('Aston Martin','astonmartin'),
                         ('Alfa Romeo','alfaromeo'),('Renault','renault'),('Audi','audi')]:
            self.assertEqual(team_key(name),key)

    def test_teammates_share_body_but_have_distinct_accents_and_markers(self):
        laps=[self.lap('Ferrari','LEC'),self.lap('Ferrari','HAM')]
        a,b=comparison_styles(laps)
        self.assertEqual(a['body'],b['body'])
        self.assertNotEqual(a['accent'],b['accent'])
        self.assertNotEqual(a['display'],b['display'])
        self.assertEqual(laps[0].color,'#778899')

    def test_unknown_team_retains_valid_session_color(self):
        a=comparison_styles([self.lap('Unlisted Team')])[0]
        self.assertEqual(a['body'],'#778899')
        self.assertEqual(comparison_styles([self.lap('',color=None)])[0]['body'],'#a7b4c2')

    def test_linear_rgb_conversion_is_not_a_second_brightening(self):
        self.assertEqual(rgb('#000000'),(0.,0.,0.))
        self.assertEqual(rgb('#ffffff'),(1.,1.,1.))
        self.assertLess(rgb('#808080')[0],.22)


if __name__=='__main__':unittest.main()
