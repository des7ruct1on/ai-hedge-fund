"""
FastAPI веб-интерфейс для мультиагентной системы анализа акций
"""
import os
import json
import asyncio
from typing import Optional, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from llm.cloudrugpt import CloudRuGPT
from web_workflow import WebGraph, get_web_analysis_results
from utils.agent import Agent
from utils.agent_logger import agent_logger
from dotenv import load_dotenv
import logging

logging.basicConfig(
    filename='web_workflow.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
app = FastAPI(title="Мультиагентная система анализа акций", version="1.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

agent_instance = None

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except:
            self.disconnect(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except:
                self.disconnect(connection)
    
    def broadcast_sync(self, message: str):
        """Синхронная версия broadcast для использования из синхронного кода"""
        import asyncio
        
        if not self.active_connections:
            return  # Нет подключений
        
        try:
            # Получаем текущий event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если loop уже запущен, создаем задачу
                asyncio.create_task(self.broadcast(message))
            else:
                # Если loop не запущен, запускаем его
                loop.run_until_complete(self.broadcast(message))
        except RuntimeError:
            # Если нет event loop, создаем новый
            asyncio.run(self.broadcast(message))

manager = ConnectionManager()

class AgentLogger:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.current_reasoning = ""
        
    async def log_reasoning(self, text: str, is_final: bool = False):
        """Логирует рассуждения агента через WebSocket"""
        self.current_reasoning += text
        
        message = {
            "type": "agent_reasoning",
            "agent_name": self.agent_name,
            "text": text,
            "full_reasoning": self.current_reasoning,
            "is_final": is_final
        }
        
        await manager.broadcast(json.dumps(message))
        
        if is_final:
            self.current_reasoning = ""
    
    async def log_decision(self, decision: str, confidence: float):
        """Логирует решение агента"""
        message = {
            "type": "agent_decision",
            "agent_name": self.agent_name,
            "decision": decision,
            "confidence": confidence
        }
        
        await manager.broadcast(json.dumps(message))
    
    async def log_start_thinking(self):
        """Начинает процесс рассуждения"""
        message = {
            "type": "agent_start_thinking",
            "agent_name": self.agent_name
        }
        
        await manager.broadcast(json.dumps(message))


class InvokeRequest(BaseModel):
    message: str

class InvokeResponse(BaseModel):
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None

load_dotenv()

def initialize_agent():
    """Инициализирует агента при запуске приложения"""
    global agent_instance
    
    cloudru_api_key = os.getenv("CLOUDRU_API_KEY")
       
    llm = CloudRuGPT(api_key=cloudru_api_key)
        
    graph = WebGraph(llm)
    compiled_graph = graph.get_graph()
    agent_instance = Agent(llm, compiled_graph)
        
    print("✅ Агент успешно инициализирован")

@app.on_event("startup")
def startup_event():
    """Инициализация при запуске приложения"""
    initialize_agent()
    # Устанавливаем WebSocket менеджер в глобальный логгер
    agent_logger.set_manager(manager)
    print("✅ WebSocket менеджер установлен в глобальный логгер")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Главная страница"""
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(request: InvokeRequest):
    """Отправляет сообщение агенту и возвращает результат"""
    if not agent_instance:
        raise HTTPException(status_code=500, detail="Агент не инициализирован")
    
    try:
        # Обрабатываем сообщение агентом
        result = agent_instance.process_message(request.message)
        print(f"Agent result: {result}")
        
        # Получаем результаты анализа
        web_results = get_web_analysis_results()
        print(f"Web results: {web_results}")
        
        # Формируем простой ответ для начала
        response_data = {
            "message": request.message,
            "agent_response": str(result) if result else "Агент обработал сообщение",
            "agent_opinions": [],
            "aggregated_decisions": [],
            "risk_assessments": [],
            "final_recommendations": "Анализ завершен. Результаты будут доступны после полной настройки системы."
        }
        
        # Если есть результаты анализа, добавляем их
        if web_results and isinstance(web_results, dict):
            if "agent_opinions" in web_results and web_results["agent_opinions"]:
                response_data["agent_opinions"] = [
                    {
                        "agent_name": opinion.agent_name,
                        "ticker": opinion.ticker,
                        "action": opinion.action,
                        "confidence": opinion.confidence,
                        "reasoning": opinion.reasoning
                    }
                    for opinion in web_results["agent_opinions"]
                ]
            
            if "aggregated_decisions" in web_results and web_results["aggregated_decisions"]:
                response_data["aggregated_decisions"] = [
                    {
                        "ticker": decision.ticker,
                        "final_action": decision.final_action,
                        "confidence_score": decision.confidence_score,
                        "consensus_strength": decision.consensus_strength
                    }
                    for decision in web_results["aggregated_decisions"]
                ]
            
            if "risk_assessments" in web_results and web_results["risk_assessments"]:
                response_data["risk_assessments"] = [
                    {
                        "ticker": risk.ticker,
                        "risk_level": risk.risk_level,
                        "risk_factors": risk.risk_factors,
                        "recommendations": risk.recommendations
                    }
                    for risk in web_results["risk_assessments"]
                ]
            
            if "final_recommendations" in web_results and web_results["final_recommendations"]:
                response_data["final_recommendations"] = web_results["final_recommendations"]
        
        print(f"Response data: {response_data}")
        
        return InvokeResponse(
            status="success",
            result=response_data
        )
        
    except Exception as e:
        return InvokeResponse(
            status="error",
            error=str(e)
        )

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для real-time обновлений"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Отправляем pong обратно
            await manager.send_personal_message(json.dumps({
                "type": "pong",
                "message": "Соединение активно"
            }), websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)