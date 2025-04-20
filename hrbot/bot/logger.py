import logging
from logging.handlers import RotatingFileHandler

class BotLogger:
    @staticmethod
    def setup(root_level=logging.INFO, file_level=logging.DEBUG, log_file="hrbot.log"):
        root = logging.getLogger()
        root.setLevel(root_level)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(root_level)
        ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        root.addHandler(ch)

        # Rotating file handler
        fh = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
        fh.setLevel(file_level)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        root.addHandler(fh)