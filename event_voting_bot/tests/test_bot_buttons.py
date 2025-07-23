import unittest
from unittest.mock import MagicMock, AsyncMock
from event_voting_bot.database import Database
from event_voting_bot.bot import handle_event_selection, handle_editdesc, db
from types import SimpleNamespace
import logging
import os

LOG_DIR = os.path.join(os.path.dirname(__file__), '../log')
LOG_PATH = os.path.abspath(os.path.join(LOG_DIR, 'test_bot_buttons.log'))
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(LOG_PATH, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger('test_bot_buttons')

class TestBotButtons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Database('test_events.db')
        cls.db.init_db()
        # Подменяем глобальный db в event_voting_bot.bot
        import event_voting_bot.bot as bot_module
        bot_module.db = cls.db
        # Создаём тестовое мероприятие
        cls.event_id = cls.db.create_event('Test', '', 123, '2025-08-01', 2, 1)
        cls.user_id = 111
        cls.username = 'testuser'
        cls.db.vote_for_event(cls.event_id, cls.user_id, cls.username, 1)
        # Логируем все события
        import sqlite3
        with sqlite3.connect('test_events.db') as conn:
            rows = conn.execute('SELECT * FROM events').fetchall()
            import logging
            logging.info(f"EVENTS IN DB: {rows}")

    @classmethod
    def tearDownClass(cls):
        import os
        if os.path.exists('test_events.db'):
            os.remove('test_events.db')

    def make_query(self, data, user_id=None):
        query = MagicMock()
        query.data = data
        query.from_user.id = user_id or self.user_id
        query.from_user.username = self.username
        query.from_user.first_name = 'Test'
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock()
        query.message.chat_id = 1
        query.message.message_id = 1
        query.message.reply_text = AsyncMock()
        # Добавляем effective_chat для корректной работы get_chat_id
        query.effective_chat = MagicMock()
        query.effective_chat.id = 1
        return query

    def test_vote_yes(self):
        query = self.make_query(f'vote_yes_{self.event_id}')
        update = SimpleNamespace(callback_query=query)
        context = MagicMock()
        self.db.vote_for_event(self.event_id, self.user_id, self.username, 0)  # reset
        self.assertTrue(self.db.vote_for_event(self.event_id, self.user_id, self.username, 1))

    def test_vote_no(self):
        query = self.make_query(f'vote_no_{self.event_id}')
        update = SimpleNamespace(callback_query=query)
        context = MagicMock()
        self.db.vote_for_event(self.event_id, self.user_id, self.username, 1)  # reset
        self.assertTrue(self.db.vote_for_event(self.event_id, self.user_id, self.username, 0))

    def test_vote_maybe(self):
        query = self.make_query(f'vote_maybe_{self.event_id}')
        update = SimpleNamespace(callback_query=query)
        context = MagicMock()
        self.assertTrue(self.db.vote_for_event(self.event_id, self.user_id, self.username, 2))

    def test_plus(self):
        self.db.vote_for_event(self.event_id, self.user_id, self.username, 1)
        self.db.set_plus(self.event_id, self.user_id, -10)  # сбросить plus_count
        self.db.set_plus(self.event_id, self.user_id, 1)
        row = self.db.get_voters_list(self.event_id, 1)
        self.assertIn('testuser (+1)', row[0])

    def test_minus(self):
        self.db.vote_for_event(self.event_id, self.user_id, self.username, 1)
        self.db.set_plus(self.event_id, self.user_id, 2)
        self.db.set_plus(self.event_id, self.user_id, -1)
        row = self.db.get_voters_list(self.event_id, 1)
        self.assertIn('testuser (+1)', row[0])

    def test_resetplus(self):
        self.db.vote_for_event(self.event_id, self.user_id, self.username, 1)
        self.db.set_plus(self.event_id, self.user_id, 2)
        self.db.reset_all_plus(self.event_id)
        row = self.db.get_voters_list(self.event_id, 1)
        self.assertIn('testuser', row[0])
        self.assertNotIn('(+', row[0])

    def test_limit_buttons_in_event_card(self):
        logger.info('START test_limit_buttons_in_event_card')
        from event_voting_bot.bot import handle_event_selection
        context = SimpleNamespace(user_data={})
        context.user_data['setlimit_event'] = self.event_id
        context.user_data['limit_value'] = 10
        for action, expected in [
            ('plus_limit', 11),
            ('plus5_limit', 16),
            ('minus_limit', 15),
            ('minus5_limit', 10)
        ]:
            logger.info(f'Action: {action}, before: {context.user_data["limit_value"]}')
            query = self.make_query(action)
            update = SimpleNamespace(callback_query=query)
            import asyncio; asyncio.run(handle_event_selection(update, context))
            logger.info(f'After action: {context.user_data["limit_value"]}')
            # confirm
            context.user_data['setlimit_event'] = self.event_id
            query = self.make_query('confirm_limit')
            update = SimpleNamespace(callback_query=query)
            import asyncio; asyncio.run(handle_event_selection(update, context))
            event = self.db.get_event(self.event_id)
            logger.info(f'After confirm: {event[5]}')
            self.assertEqual(event[5], expected)
            context.user_data['limit_value'] = expected
        context.user_data['setlimit_event'] = self.event_id
        context.user_data['limit_value'] = 20
        query = self.make_query('confirm_limit')
        update = SimpleNamespace(callback_query=query)
        import asyncio; asyncio.run(handle_event_selection(update, context))
        event = self.db.get_event(self.event_id)
        logger.info(f'Final confirm: {event[5]}')
        self.assertEqual(event[5], 20)

    def test_limit_buttons_default(self):
        logger.info('START test_limit_buttons_default')
        from event_voting_bot.bot import handle_limit_buttons
        context = SimpleNamespace(user_data={'default_limit_value': 10})
        user_id = self.user_id
        for action, expected in [
            ('plus_default_limit', 11),
            ('plus5_default_limit', 16),
            ('minus_default_limit', 15),
            ('minus5_default_limit', 10)
        ]:
            logger.info(f'Action: {action}, before: {context.user_data["default_limit_value"]}')
            query = self.make_query(action, user_id=user_id)
            update = SimpleNamespace(callback_query=query)
            import asyncio; asyncio.run(handle_limit_buttons(update, context))
            logger.info(f'After action: {context.user_data["default_limit_value"]}')
            context.user_data['default_limit_value'] = expected
            query = self.make_query('confirm_default_limit', user_id=user_id)
            update = SimpleNamespace(callback_query=query)
            import asyncio; asyncio.run(handle_limit_buttons(update, context))
            val = self.db.get_default_limit(user_id)
            logger.info(f'After confirm: {val}')
            self.assertEqual(val, expected)
            context.user_data['default_limit_value'] = expected
        context.user_data['default_limit_value'] = 22
        query = self.make_query('confirm_default_limit', user_id=user_id)
        update = SimpleNamespace(callback_query=query)
        import asyncio; asyncio.run(handle_limit_buttons(update, context))
        val = self.db.get_default_limit(user_id)
        logger.info(f'Final confirm: {val}')
        self.assertEqual(val, 22)

    def test_open_event(self):
        """Проверяет, что лимит увеличивается на 1 при нажатии на кнопку 'открыть набор'"""
        from event_voting_bot.bot import handle_event_selection
        # Установим лимит 2
        self.db.set_event_limit(self.event_id, 2)
        event_before = self.db.get_event(self.event_id, 1)
        old_limit = event_before[5]
        query = self.make_query(f'open_event_{self.event_id}', user_id=123)  # создатель
        update = SimpleNamespace(callback_query=query)
        # Добавляем необходимые атрибуты для поиска события
        update.effective_user = SimpleNamespace(id=123)
        update.effective_chat = SimpleNamespace(id=1)
        context = MagicMock()
        import logging
        logging.info(f"TEST OPEN_EVENT: event_id={self.event_id}, user_id={update.effective_user.id}, chat_id={update.effective_chat.id}")
        import asyncio; asyncio.run(handle_event_selection(update, context))
        event_after = self.db.get_event(self.event_id, 1)
        new_limit = event_after[5]
        self.assertEqual(new_limit, old_limit + 1)

if __name__ == '__main__':
    unittest.main() 