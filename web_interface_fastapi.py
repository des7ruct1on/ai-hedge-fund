"""
FastAPI веб-интерфейс для мультиагентной системы анализа акций
"""
import os
import json
import asyncio
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import asyncio
import json
from llm.yandexgpt import YandexGPT
from llm.cloudrugpt import CloudRuGPT
from web_workflow import WebGraph, get_web_analysis_results
from agent import Agent
from models import AgentOpinion, AggregatedDecision, RiskAssessment
from utils import aggregate_agent_opinions
from backtest import BacktestEngine
from dotenv import load_dotenv
app = FastAPI(title="Мультиагентная система анализа акций", version="1.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

analysis_results = {
    "status": "ready",
    "portfolio": {},
    "news": [],
    "agent_opinions": [],
    "aggregated_decisions": [],
    "risk_assessments": [],
    "final_recommendations": "",
    "error": None
}

agent_instance = None

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                self.active_connections.remove(connection)

manager = ConnectionManager()

class AnalysisRequest(BaseModel):
    message: str = "Проанализируй мой портфель и дай рекомендации"

class AnalysisResponse(BaseModel):
    status: str
    message: Optional[str] = None
    error: Optional[str] = None

load_dotenv()

async def initialize_agent():
    """Инициализирует агента при запуске приложения"""
    global agent_instance
    
    try:
        folder_id = os.getenv("YANDEX_FOLDER_ID")
        api_key = os.getenv("YANDEX_API_KEY")
        cloudru_api_key = os.getenv("CLOUDRU_API_KEY")
        if not folder_id or not api_key:
            print("⚠️ Переменные окружения YANDEX_FOLDER_ID и YANDEX_API_KEY не установлены")
            print("📝 Используется мок-версия для демонстрации")
            from mock_llm import MockYandexGPT
            llm = MockYandexGPT(folder_id="demo", api_key="demo")
        else:
            # llm = YandexGPT(folder_id=folder_id, api_key=api_key)
            llm = CloudRuGPT(api_key=cloudru_api_key)
        
        graph = WebGraph(llm)
        compiled_graph = graph.get_graph()
        agent_instance = Agent(llm, compiled_graph)
        
        print("✅ Агент успешно инициализирован")
        
    except Exception as e:
        print(f"❌ Ошибка инициализации агента: {e}")
        from mock_llm import MockYandexGPT
        llm = MockYandexGPT(folder_id="demo", api_key="demo")
        graph = WebGraph(llm)
        compiled_graph = graph.get_graph()
        agent_instance = Agent(llm, compiled_graph)

async def run_analysis_background():
    """Запускает анализ портфеля в фоновом режиме"""
    global analysis_results, agent_instance
    
    try:
        analysis_results["status"] = "analyzing"
        analysis_results["error"] = None
        
        await manager.broadcast(json.dumps({
            "type": "status",
            "message": "🚀 Начинаем анализ портфеля...",
            "status": "analyzing"
        }))
        
        await manager.broadcast(json.dumps({
            "type": "status", 
            "message": "📊 Загружаем данные портфеля и новости...",
            "status": "loading_data"
        }))
        
        with open("user_portfolio.json", "r", encoding="utf-8") as f:
            analysis_results["portfolio"] = json.load(f)
        
        with open("sample_news.json", "r", encoding="utf-8") as f:
            analysis_results["news"] = json.load(f)
        
        if not agent_instance:
            raise Exception("Агент не инициализирован")
        
        await manager.broadcast(json.dumps({
            "type": "status",
            "message": "🤖 Агенты начинают обсуждение...",
            "status": "agents_discussing"
        }))
        
        result = agent_instance.process_message("Проанализируй мой портфель и дай рекомендации")
        
        web_results = get_web_analysis_results()
        
        for opinion in web_results["agent_opinions"]:
            await manager.broadcast(json.dumps({
                "type": "agent_opinion",
                "data": {
                    "agent_name": opinion.agent_name,
                    "ticker": opinion.ticker,
                    "action": opinion.action,
                    "confidence": opinion.confidence,
                    "reasoning": opinion.reasoning
                }
            }))
            await asyncio.sleep(0.5)  
        
        await manager.broadcast(json.dumps({
            "type": "status",
            "message": "🔄 Агрегируем решения агентов...",
            "status": "aggregating"
        }))
        
        for decision in web_results["aggregated_decisions"]:
            await manager.broadcast(json.dumps({
                "type": "aggregated_decision",
                "data": {
                    "ticker": decision.ticker,
                    "final_action": decision.final_action,
                    "confidence_score": decision.confidence_score,
                    "consensus_strength": decision.consensus_strength
                }
            }))
            await asyncio.sleep(0.3)
        
        await manager.broadcast(json.dumps({
            "type": "status",
            "message": "⚠️ Оцениваем риски...",
            "status": "risk_assessment"
        }))
        
        for risk in web_results["risk_assessments"]:
            await manager.broadcast(json.dumps({
                "type": "risk_assessment",
                "data": {
                    "ticker": risk.ticker,
                    "risk_level": risk.risk_level,
                    "risk_factors": risk.risk_factors,
                    "recommendations": risk.recommendations
                }
            }))
            await asyncio.sleep(0.3)
        
        await manager.broadcast(json.dumps({
            "type": "status",
            "message": "📋 Формируем итоговые рекомендации...",
            "status": "finalizing"
        }))
        
        await manager.broadcast(json.dumps({
            "type": "final_recommendations",
            "data": {
                "recommendations": web_results["final_recommendations"]
            }
        }))
        
        analysis_results["agent_opinions"] = web_results["agent_opinions"]
        analysis_results["aggregated_decisions"] = web_results["aggregated_decisions"]
        analysis_results["risk_assessments"] = web_results["risk_assessments"]
        analysis_results["final_recommendations"] = web_results["final_recommendations"]
        analysis_results["status"] = "completed"
        
        await manager.broadcast(json.dumps({
            "type": "status",
            "message": "✅ Анализ завершен!",
            "status": "completed"
        }))
        
        print("✅ Анализ завершен успешно")
        
    except Exception as e:
        analysis_results["status"] = "error"
        analysis_results["error"] = str(e)
        await manager.broadcast(json.dumps({
            "type": "error",
            "message": f"❌ Ошибка анализа: {e}",
            "status": "error"
        }))
        print(f"❌ Ошибка анализа: {e}")

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске приложения"""
    await initialize_agent()

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Главная страница"""
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/start_analysis", response_model=AnalysisResponse)
async def start_analysis(background_tasks: BackgroundTasks):
    """Запускает анализ портфеля"""
    if analysis_results["status"] == "analyzing":
        raise HTTPException(status_code=400, detail="Анализ уже выполняется")
    
    analysis_results["status"] = "ready"
    analysis_results["agent_opinions"] = []
    analysis_results["aggregated_decisions"] = []
    analysis_results["risk_assessments"] = []
    analysis_results["final_recommendations"] = ""
    analysis_results["error"] = None
    
    background_tasks.add_task(run_analysis_background)
    
    return AnalysisResponse(
        status="started",
        message="Анализ запущен"
    )

@app.get("/api/status")
async def get_status():
    """Возвращает статус анализа"""
    return analysis_results

@app.get("/api/portfolio")
async def get_portfolio():
    """Возвращает данные портфеля"""
    try:
        with open("user_portfolio.json", "r", encoding="utf-8") as f:
            portfolio = json.load(f)
        return portfolio
    except Exception as e:
        print(f"Ошибка загрузки портфеля: {e}")
        return {}

@app.get("/api/news")
async def get_news():
    """Возвращает новости"""
    try:
        with open("sample_news.json", "r", encoding="utf-8") as f:
            news = json.load(f)
        return news
    except Exception as e:
        print(f"Ошибка загрузки новостей: {e}")
        return []

@app.get("/api/agent_opinions")
async def get_agent_opinions():
    """Возвращает мнения агентов"""
    return analysis_results.get("agent_opinions", [])

@app.get("/api/risk_assessments")
async def get_risk_assessments():
    """Возвращает оценки рисков"""
    return analysis_results.get("risk_assessments", [])

@app.get("/api/recommendations")
async def get_recommendations():
    """Возвращает итоговые рекомендации"""
    return {
        "recommendations": analysis_results.get("final_recommendations", "")
    }

@app.get("/api/health")
async def health_check():
    """Проверка состояния системы"""
    return {
        "status": "healthy",
        "agent_initialized": agent_instance is not None,
        "analysis_status": analysis_results["status"]
    }

@app.get("/api/backtest")
async def run_backtest(days: int = 7):
    """
    Запускает бэктест на указанное количество дней
    
    Args:
        days: количество дней для бэктеста (по умолчанию 7)
    
    Returns:
        Результаты бэктеста
    """
    if not agent_instance:
        raise HTTPException(status_code=500, detail="Агент не инициализирован")
    
    if days < 1 or days > 30:
        raise HTTPException(status_code=400, detail="Количество дней должно быть от 1 до 30")
    
    try:
        # Загружаем данные портфеля и новостей
        with open("user_portfolio.json", "r", encoding="utf-8") as f:
            user_portfolio = json.load(f)
        
        with open("sample_news.json", "r", encoding="utf-8") as f:
            news_data = json.load(f)
        
        # Создаем движок бэктеста
        backtest_engine = BacktestEngine(agent_instance.llm)
        
        # Запускаем бэктест
        result = backtest_engine.run_backtest(days, user_portfolio, news_data)
        
        # Преобразуем результат в JSON-сериализуемый формат
        backtest_result = {
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "initial_portfolio_value": result.initial_portfolio_value,
            "final_portfolio_value": result.final_portfolio_value,
            "total_pnl": result.total_pnl,
            "total_return_pct": result.total_return_pct,
            "ticker_performance": result.ticker_performance,
            "daily_results": [
                {
                    "date": day.date.isoformat(),
                    "ticker": day.ticker,
                    "open_price": day.open_price,
                    "close_price": day.close_price,
                    "high_price": day.high_price,
                    "low_price": day.low_price,
                    "volume": day.volume,
                    "signal": day.signal,
                    "confidence": day.confidence,
                    "daily_pnl": day.daily_pnl,
                    "cumulative_pnl": day.cumulative_pnl
                }
                for day in result.daily_results
            ]
        }
        
        return {
            "status": "completed",
            "message": f"Бэктест завершен за {days} дней",
            "result": backtest_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка бэктеста: {str(e)}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для real-time обновлений"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_personal_message(json.dumps({
                "type": "pong",
                "message": "Соединение активно"
            }), websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
