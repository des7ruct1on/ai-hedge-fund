from aiohttp import web
import logging
import asyncio
from collections import deque

chat_websockets = set()
log_websockets = set()
log_llm_websockets = set()
login_websockets = set()
reasoning_websockets = set()

class WebInputHandler:
    def __init__(self):
        self.message_queue = deque(maxlen=100)
        self.new_message_event = asyncio.Event()
        self._shutdown = False

    async def get_input(self) -> str:
        """
        Ожидает ввод от пользователя через вебсокет
        """
        if self.message_queue:
            return self.message_queue.popleft()

    def add_message(self, message: str):
        """Добавляет сообщение в очередь (вызывается из websocket handler)"""
        self.message_queue.append(message)
        self.new_message_event.set()

    def shutdown(self):
        """Завершает ожидание ввода"""
        self._shutdown = True
        self.new_message_event.set()

web_input_handler = WebInputHandler()

class WebLoginHandler:
    def __init__(self):
        self.login_queue = deque(maxlen=100)
        self.new_login_event = asyncio.Event()
        self._shutdown = False

    async def get_login(self) -> str:
        """
        Ожидает ввод логина от пользователя через вебсокет
        """
        if self.login_queue:
            return self.login_queue.popleft()

    def add_login(self, login: str):
        """Добавляет логин в очередь (вызывается из websocket handler)"""
        self.login_queue.append(login)
        self.new_login_event.set()

    def shutdown(self):
        """Завершает ожидание ввода логина"""
        self._shutdown = True
        self.new_login_event.set()

web_login_handler = WebLoginHandler()

class WebSocketHandler(logging.Handler):
    def __init__(self, loop):
        super().__init__()
        self.loop = loop

    def emit(self, record):
        print(f"Trying to send log: {record.msg}")
        if record.module == "(chat)":
            asyncio.run_coroutine_threadsafe(
                self.broadcast_chat(record.msg),
                self.loop
            )
        elif record.module == "(llm)":
            asyncio.run_coroutine_threadsafe(
                self.broadcast_log(record.msg),
                self.loop
            )
        elif record.module == "(reason)":
            asyncio.run_coroutine_threadsafe(
                self.broadcast_reasoning(record.msg),
                self.loop
            )
        else:
            log_entry = self.format(record)
            asyncio.run_coroutine_threadsafe(
                self.broadcast_log(log_entry),
                self.loop
            )

    async def broadcast_log(self, message):
        print(f"MESSAGE LOG: {message}")
        print(list(log_websockets))
        for ws in list(log_websockets):
            try:
                await ws.send_str(message)
            except:
                log_websockets.remove(ws)

    async def broadcast_chat(self, message):
        print(f"MESSAGE CHAT: {message}")
        print(list(chat_websockets))
        for ws in list(chat_websockets):
            try:
                await ws.send_str(message)
            except:
                chat_websockets.remove(ws)

    async def broadcast_reasoning(self, message):
        print(f"MESSAGE REASONING: {message}")
        print(f"Reasoning websockets: {list(reasoning_websockets)}")
        if not reasoning_websockets:
            print("No reasoning websockets connected!")
            return
        for ws in list(reasoning_websockets):
            try:
                await ws.send_str(message)
                print(f"Reasoning message sent to websocket")
            except Exception as e:
                print(f"Error sending reasoning message: {e}")
                reasoning_websockets.remove(ws)

async def chat_websocket_handler(request):
    
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    chat_websockets.add(ws)

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                web_input_handler.add_message(msg.data)
                for client in list(chat_websockets):
                    try:
                        await asyncio.sleep(0.1)
                    except:
                        chat_websockets.remove(client)
    finally:
        chat_websockets.remove(ws)
        if ws.closed:
            web_input_handler.shutdown()
    return ws

async def log_websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    log_websockets.add(ws)

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                pass
    finally:
        log_websockets.remove(ws)
    return ws

async def login_websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    login_websockets.add(ws)

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                web_login_handler.add_login(msg.data)
                print(f"Получен логин через веб-сокет: {msg.data}")
    finally:
        login_websockets.remove(ws)
        if ws.closed:
            web_login_handler.shutdown()
    return ws

async def reasoning_websocket_handler(request):
    print("Reasoning WebSocket handler called")
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    reasoning_websockets.add(ws)
    print(f"Reasoning WebSocket connected. Total connections: {len(reasoning_websockets)}")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                pass  # Рассуждения только отправляются, не принимаются
    finally:
        reasoning_websockets.remove(ws)
        print(f"Reasoning WebSocket disconnected. Total connections: {len(reasoning_websockets)}")
    return ws