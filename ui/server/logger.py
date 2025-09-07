import logging
import asyncio
from typing import Optional
import json 

class ChatLogger:
    _instance = None
    _loop: Optional[asyncio.AbstractEventLoop] = None
    _handler = None

    def __new__(cls, name):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, name):
        if self._initialized:
            return

        self._initialized = True
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)
        self._logger.addHandler(logging.NullHandler())

    @classmethod
    def setup(cls, loop: asyncio.AbstractEventLoop):
        """Инициализация с event loop"""
        if cls._instance is None:
            raise RuntimeError("Logger instance not created")

        cls._loop = loop

        from ui.server.handlers import WebSocketHandler
        cls._handler = WebSocketHandler(loop)
        cls._handler.setFormatter(logging.Formatter('%(message)s'))

        for handler in cls._instance._logger.handlers[:]:
            cls._instance._logger.removeHandler(handler)

        cls._instance._logger.addHandler(cls._handler)

    def _check_handler(self):
        """Проверяет, есть ли активный обработчик"""
        if not self._logger.handlers:
            return False
        return True

    def message(self, username: str, msg: str):
        """Специальные сообщения в чат"""
        if not self._check_handler():
            return

        record = self._logger.makeRecord(
            self._logger.name, logging.INFO,
            "(chat)", 0,
            f"{username}: {msg}",
            None, None, "(chat)"
        )
        self._logger.handle(record)

    def log_read_message(self, username: str, msg: str):
        """Специальные сообщения в чат — принимает AIMessage, dict или str"""
        if not self._check_handler():
            return
        record = self._logger.makeRecord(
            self._logger.name, logging.INFO,
            "(reason)", 0,
            f"{username}: {msg}",
            None, None, "(reason)"
        )
        self._logger.handle(record)

    def log_llm(self, username: str, msg):
        """Специальные сообщения в чат — принимает AIMessage, dict или str"""
        if not self._check_handler():
            return
        print(f"check \n\n {msg}")
        # Поддержка разных типов msg
        if isinstance(msg, str):
            try:
                msg_data = json.loads(msg)
                metadata = msg_data.get("response_metadata", {})
            except json.JSONDecodeError:
                metadata = {}
        elif hasattr(msg, "response_metadata"):  # Например, AIMessage
            metadata = getattr(msg, "response_metadata", {})
        elif isinstance(msg, dict):
            metadata = msg.get("response_metadata", {})
        else:
            metadata = {}

        token_usage = metadata.get('token_usage', {})
        token_data = {
            'model_name': metadata.get('model_name', 'unknown'),
            'prompt_tokens': token_usage.get('prompt_tokens', 0),
            'completion_tokens': token_usage.get('completion_tokens', 0),
            'total_tokens': token_usage.get('total_tokens', 0),
            'finish_reason': metadata.get('finish_reason', 'unknown')
        }

        formatted_msg = json.dumps(token_data, ensure_ascii=False, indent=2)

        record = self._logger.makeRecord(
            self._logger.name,
            logging.INFO,
            "(llm)", 0,
            f"{username}: (llm) {formatted_msg}",
            None, None, "(llm)"
        )
        self._logger.handle(record)

    def info(self, msg: str, *args, **kwargs):
        """Логирование информационных сообщений"""
        if not self._check_handler():
            return
        self._logger.info(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        if not self._check_handler():
            return
        self._logger.debug(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        if not self._check_handler():
            return
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        if not self._check_handler():
            return
        self._logger.error(msg, *args, **kwargs)