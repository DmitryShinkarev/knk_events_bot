import logging
import os
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../log'))
LOG_PATH = os.path.join(LOG_DIR, 'test_bot_buttons.log')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(LOG_PATH, encoding='utf-8'), logging.StreamHandler()]
) 