import unittest
import os
from event_voting_bot.database import Database

class TestDatabase(unittest.TestCase):
    TEST_DB = 'test_events.db'

    def setUp(self):
        if os.path.exists(self.TEST_DB):
            os.remove(self.TEST_DB)
        self.db = Database(self.TEST_DB)

    def tearDown(self):
        if os.path.exists(self.TEST_DB):
            os.remove(self.TEST_DB)

    def test_create_event(self):
        event_id = self.db.create_event('Test Event', '', 123, '2025-01-01', 5, 0)
        event = self.db.get_event(event_id, 0)
        self.assertIsNotNone(event)
        self.assertEqual(event[1], 'Test Event')
        self.assertEqual(event[5], 5)  # event_limit

    def test_set_event_limit(self):
        event_id = self.db.create_event('Test Event', '', 123, '2025-01-01', 5, 0)
        self.db.set_event_limit(event_id, 10)
        event = self.db.get_event(event_id, 0)
        self.assertEqual(event[5], 10)

    def test_set_event_description(self):
        event_id = self.db.create_event('Test Event', '', 123, '2025-01-01', 5, 0)
        self.db.set_event_description(event_id, 'desc')
        event = self.db.get_event(event_id, 0)
        self.assertEqual(event[2], 'desc')

if __name__ == '__main__':
    unittest.main() 