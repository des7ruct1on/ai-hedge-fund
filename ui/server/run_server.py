import asyncio
import threading
from typing import Optional

class WebSocketServerManager:
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server_thread: Optional[threading.Thread] = None
        self._running = False

    async def _run_server(self):
        """Основная корутина для запуска сервера"""
        from ui.server.server import start_server
        from ui.server.handlers import WebSocketHandler
        await start_server(self._loop)

        while self._running:
            await asyncio.sleep(1)

    def _thread_target(self):
        """Целевая функция для потока сервера"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._running = True
        try:
            self._loop.run_until_complete(self._run_server())
        finally:
            if self._loop.is_running():
                self._loop.stop()
            self._loop.close()

    def start(self):
        """Запуск сервера в отдельном потоке"""
        if self._server_thread is None:
            self._server_thread = threading.Thread(
                target=self._thread_target,
                daemon=True
            )
            self._server_thread.start()

    def stop(self):
        """Остановка сервера"""
        self._running = False
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._server_thread is not None:
            self._server_thread.join(timeout=1)
            self._server_thread = None

    def get_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Возвращает текущий event loop сервера, если он доступен.
        """
        return self._loop