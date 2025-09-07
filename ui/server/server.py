from aiohttp import web
from ui.server.handlers import chat_websocket_handler, log_websocket_handler, login_websocket_handler, reasoning_websocket_handler
import os

def get_static_path():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend', 'static')

async def index(request):
    templates_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'frontend',
        'templates'
    )
    return web.FileResponse(os.path.join(templates_path, 'index.html'))

async def start_server(loop):
    app = web.Application()

    static_path = get_static_path()
    if not os.path.exists(static_path):
        os.makedirs(static_path, exist_ok=True)

    app.add_routes([
        web.get('/chat', chat_websocket_handler),
        web.get('/log', log_websocket_handler),
        web.get('/login', login_websocket_handler),
        web.get('/reasoning', reasoning_websocket_handler),
        web.get('/', index),
        web.static('/static', static_path)
    ])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    return site