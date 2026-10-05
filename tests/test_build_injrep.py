import json
import unittest
from datetime import datetime
from pathlib import Path

from nbainjuries import injury
from nbainjuries._constants import expected_cols
from nbainjuries._exceptions import DataValidationError
from nbainjuries._util import _build_injrep

FIXTURES = Path(__file__).parent / 'fixtures'
ROWGAP = 18.0


def _line(top, *texts):
    """One printed line as tabula's json output gives it: a cell per column, an empty cell at top 0."""
    cells = list(texts) + [''] * (len(expected_cols) - len(texts))
    return [{'top': top if text else 0.0, 'text': text} for text in cells]


def _player(top, name, status, reason='', date='', time='', matchup='', team=''):
    return _line(top, date, time, matchup, team, name, status, reason)


def _reason(top, text):
    return _line(top, '', '', '', '', '', '', text)


def _page(*lines):
    return {'data': list(lines)}


def _firstpage(*lines):
    return _page(_line(60.0, *expected_cols), *lines)


def _records(*pages, rowgap=ROWGAP):
    df = _build_injrep(list(pages), len(pages), rowgap)
    return json.loads(df.to_json(orient='records'))


class buildinjrep_test(unittest.TestCase):
    """Rows rebuilt from where each printed line sits on the page."""

    def test_onelinerows_carry_game_and_team(self):
        records = _records(_firstpage(
            _player(83.8, 'Davis, Anthony', 'Questionable', 'Injury/Illness - Left Calf; Strain',
                    '11/08/2025', '07:00 (ET)', 'DAL@WAS', 'Dallas Mavericks'),
            _player(105.8, 'Irving, Kyrie', 'Out', 'Injury/Illness - Left Knee; Surgery'),
        ))
        self.assertEqual(records, [
            {'Game Date': '11/08/2025', 'Game Time': '07:00 (ET)', 'Matchup': 'DAL@WAS', 'Team': 'Dallas Mavericks',
             'Player Name': 'Davis, Anthony', 'Current Status': 'Questionable',
             'Reason': 'Injury/Illness - Left Calf; Strain'},
            {'Game Date': '11/08/2025', 'Game Time': '07:00 (ET)', 'Matchup': 'DAL@WAS', 'Team': 'Dallas Mavericks',
             'Player Name': 'Irving, Kyrie', 'Current Status': 'Out',
             'Reason': 'Injury/Illness - Left Knee; Surgery'},
        ])

    def test_twolinereason_joins_the_lines_around_the_name(self):
        records = _records(_firstpage(
            _reason(83.8, 'Injury/Illness - Left Knee; Surgery'),
            _player(90.8, 'George, Paul', 'Out'),
            _reason(97.8, 'Recovery'),
            _player(119.9, 'White, Coby', 'Out', 'Injury/Illness - Right Calf; Strain'),
        ))
        self.assertEqual([r['Reason'] for r in records],
                         ['Injury/Illness - Left Knee; Surgery Recovery', 'Injury/Illness - Right Calf; Strain'])

    def test_threelinereason_keeps_every_line(self):
        records = _records(_firstpage(
            _reason(119.9, 'Injury/Illness - Right Thumb; Surgery'),
            _player(133.9, 'McCain, Jared', 'Available', 'Recovery - Splint; Left Knee Surgery'),
            _reason(148.0, 'Recovery - Brace'),
            _player(170.0, 'Sallis, Hunter', 'Available', '-'),
            _reason(193.0, 'Injury/Illness - Left Scaphoid;'),
            _player(200.1, 'Collins, Zach', 'Out'),
            _reason(207.1, 'Fracture'),
        ))
        self.assertEqual([(r['Player Name'], r['Reason']) for r in records], [
            ('McCain, Jared', 'Injury/Illness - Right Thumb; Surgery Recovery - Splint; Left Knee Surgery Recovery - Brace'),
            ('Sallis, Hunter', '-'),
            ('Collins, Zach', 'Injury/Illness - Left Scaphoid; Fracture'),
        ])

    def test_row_split_by_a_page_break_continues_on_the_next_page(self):
        records = _records(
            _firstpage(_player(495.6, 'Kornet, Luke', 'Doubtful', 'Injury/Illness - Right Hamstring;')),
            _page(_reason(81.8, 'Tightness'), _player(103.8, 'Peterson, Drew', 'Available', '-')),
        )
        self.assertEqual([(r['Player Name'], r['Reason']) for r in records], [
            ('Kornet, Luke', 'Injury/Illness - Right Hamstring; Tightness'),
            ('Peterson, Drew', '-'),
        ])

    def test_not_yet_submitted_is_kept_as_a_team_row(self):
        records = _records(_firstpage(
            _line(79.0, '11/28/2021', '03:30 (ET)', 'GSW@LAC', 'Golden State Warriors', '', '', 'NOT YET SUBMITTED'),
            _line(97.0, '', '', '', 'LA Clippers', '', '', 'NOT YET SUBMITTED'),
        ), rowgap=11.0)
        self.assertEqual(records, [
            {'Game Date': '11/28/2021', 'Game Time': '03:30 (ET)', 'Matchup': 'GSW@LAC',
             'Team': 'Golden State Warriors', 'Player Name': None, 'Current Status': None,
             'Reason': 'NOT YET SUBMITTED'},
            {'Game Date': '11/28/2021', 'Game Time': '03:30 (ET)', 'Matchup': 'GSW@LAC',
             'Team': 'LA Clippers', 'Player Name': None, 'Current Status': None,
             'Reason': 'NOT YET SUBMITTED'},
        ])

    def test_repeated_header_on_a_later_page_is_dropped(self):
        records = _records(
            _firstpage(_player(79.0, 'Carey Jr., Vernon', 'Out', 'Health and Safety Protocols')),
            _page(_line(60.0, *expected_cols), _player(79.0, 'Brogdon, Malcolm', 'Questionable', 'Rest')),
        )
        self.assertEqual([r['Player Name'] for r in records], ['Carey Jr., Vernon', 'Brogdon, Malcolm'])

    def test_rowgap_decides_where_a_row_ends(self):
        page = _firstpage(
            _reason(115.0, 'Injury/Illness - Left Ankle; Injury recovery; Health & safety'),
            _player(119.0, 'Carter-Williams, Michael', 'Out'),
            _reason(123.0, 'protocols'),
            _player(141.0, 'Fultz, Markelle', 'Out', 'Injury/Illness - Left Knee; Injury recovery'),
        )
        records = _records(page, rowgap=11.0)
        self.assertEqual([r['Reason'] for r in records], [
            'Injury/Illness - Left Ankle; Injury recovery; Health & safety protocols',
            'Injury/Illness - Left Knee; Injury recovery',
        ])

    def test_raises_on_two_names_in_one_row(self):
        with self.assertRaises(DataValidationError):
            _records(_firstpage(
                _player(83.8, 'Davis, Anthony', 'Out', 'Rest'),
                _player(90.8, 'Irving, Kyrie', 'Out', 'Rest'),
            ))

    def test_raises_on_a_nameless_line_mid_page(self):
        with self.assertRaises(DataValidationError):
            _records(_firstpage(
                _player(83.8, 'Davis, Anthony', 'Out', 'Rest'),
                _reason(105.8, 'Strain'),
            ))

    def test_raises_on_a_continuation_with_no_row_before_it(self):
        with self.assertRaises(DataValidationError):
            _records(_firstpage(
                _reason(83.8, 'Tightness'),
                _player(105.8, 'Peterson, Drew', 'Available', '-'),
            ))

    def test_raises_on_a_continuation_that_carries_other_columns(self):
        with self.assertRaises(DataValidationError):
            _records(
                _firstpage(_player(495.6, 'Kornet, Luke', 'Doubtful', 'Injury/Illness - Right Hamstring;')),
                _page(_line(81.8, '', '', '', 'Boston Celtics', '', '', 'Tightness'),
                      _player(103.8, 'Peterson, Drew', 'Available', '-')),
            )

    def test_raises_when_page_one_does_not_start_with_the_header(self):
        with self.assertRaises(DataValidationError):
            _records(_page(_player(83.8, 'Davis, Anthony', 'Out', 'Rest')))

    def test_raises_on_a_line_with_the_wrong_number_of_cells(self):
        with self.assertRaises(DataValidationError):
            _records(_firstpage(_player(83.8, 'Davis, Anthony', 'Out', 'Rest')[:-1]))

    def test_raises_when_a_page_has_no_table(self):
        with self.assertRaises(DataValidationError):
            _build_injrep([_firstpage(_player(83.8, 'Davis, Anthony', 'Out', 'Rest'))], 2, ROWGAP)


def _report(timestamp):
    return injury.get_reportdata(timestamp, local=True, localdir=str(FIXTURES), return_df=True)


def _reasonof(df, player):
    reasons = df.loc[df['Player Name'] == player, 'Reason'].tolist()
    if len(reasons) != 1:
        raise AssertionError(f'{player}: {len(reasons)} rows')
    return reasons[0]


class reportfixtures_test(unittest.TestCase):
    """Cached reports whose wrapped reasons the text-only cleaner stored wrongly."""

    def test_20251108_matches_its_golden_file(self):
        parsed = json.loads(injury.get_reportdata(datetime(2025, 11, 8, 17, 0), local=True, localdir=str(FIXTURES)))
        with open(FIXTURES / 'Injury-Report_2025-11-08_05PM.json', encoding='utf-8') as f:
            self.assertEqual(parsed, json.load(f))

    def test_20251108_threeline_reason_and_the_row_below_it(self):
        df = _report(datetime(2025, 11, 8, 17, 0))
        self.assertEqual(_reasonof(df, 'McCain, Jared'),
                         'Injury/Illness - Right Thumb; Surgery Recovery - Splint; Left Knee Surgery Recovery - Brace')
        self.assertEqual(_reasonof(df, 'Sallis, Hunter'), '-')

    def test_20241108_row_split_across_pages_3_and_4(self):
        df = _report(datetime(2024, 11, 8, 17, 0))
        self.assertEqual(_reasonof(df, 'Kornet, Luke'), 'Injury/Illness - Right Hamstring; Tightness')
        self.assertEqual(_reasonof(df, 'Peterson, Drew'), '-')
        self.assertEqual(_reasonof(df, 'Porzingis, Kristaps'),
                         'Injury/Illness - Left Posterior Tibialis Tendon; Surgery Rehabilitation')

    def test_20251102_row_split_across_pages_2_and_3(self):
        df = _report(datetime(2025, 11, 2, 17, 0))
        self.assertEqual(_reasonof(df, 'Barlow, Dominick'), 'Injury/Illness - Right Elbow; Laceration')
        self.assertEqual(_reasonof(df, 'Broome, Johni'), '-')
        self.assertEqual(_reasonof(df, 'Embiid, Joel'), 'Injury/Illness - Left Knee; Injury Recovery')

    def test_20211127_older_layout_wraps_and_team_rows(self):
        df = _report(datetime(2021, 11, 27, 19, 0))
        self.assertEqual(_reasonof(df, 'Carter-Williams, Michael'),
                         'Injury/Illness - Left Ankle; Injury recovery; Health & safety protocols')
        self.assertEqual(_reasonof(df, 'Davis, Anthony'),
                         'Injury/Illness - Head; contusion, right side temporal region. No concussive symptoms.')
        unsubmitted = df.loc[df['Reason'] == 'NOT YET SUBMITTED', ['Matchup', 'Team', 'Player Name']]
        self.assertIn(('GSW@LAC', 'Golden State Warriors'), list(zip(unsubmitted['Matchup'], unsubmitted['Team'])))
        self.assertIn(('GSW@LAC', 'LA Clippers'), list(zip(unsubmitted['Matchup'], unsubmitted['Team'])))
        self.assertTrue(unsubmitted['Player Name'].isna().all())


if __name__ == '__main__':
    unittest.main()
