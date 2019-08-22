 
import logging, sys
from pathlib import Path

def init_log():
	log_root = logging.getLogger(__name__)
	log_root.setLevel(logging.INFO)

	Path('./logs').mkdir(exist_ok=True)
	
	handlers = [
		logging.StreamHandler(sys.stdout),
		logging.handlers.RotatingFileHandler('logs/watchdog.log', maxBytes=1024*1024, backupCount=7),
	]

	formatter = logging.Formatter(style='{asctime} | {name} {levelname} | {message}')

	for handler in handlers:
		handler.setFormatter(formatter)
		log_root.addHandler(handler)

init_log()
