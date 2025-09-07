from ui.server.run_server import WebSocketServerManager
from ui.server.logger import ChatLogger
from ui.server.handlers import web_input_handler, web_login_handler
from llm.cloudrugpt import CloudRuGPT
from simple_workflow import SimpleGraph, get_analysis_results
from utils.agent import Agent
from dotenv import load_dotenv
import time
import random
import threading
import asyncio
import os
import json

# Глобальная переменная для агента
agent_instance = None

def initialize_agent():
    """Инициализирует агента"""
    global agent_instance
    print("🔄 Инициализация агента...")
    
    load_dotenv()
    cloudru_api_key = os.getenv("CLOUDRU_API_KEY")
    
    if not cloudru_api_key:
        print("❌ Ошибка: CLOUDRU_API_KEY не найден в переменных окружения")
        return None
    
    try:
        llm = CloudRuGPT(api_key=cloudru_api_key)
        graph = SimpleGraph(llm)
        compiled_graph = graph.get_graph()
        agent_instance = Agent(llm, compiled_graph)
        
        print("✅ Агент успешно инициализирован")
        return agent_instance
    except Exception as e:
        print(f"❌ Ошибка инициализации агента: {e}")
        return None

def process_user_message(user_message: str, logger: ChatLogger) -> str:
    """Обрабатывает сообщение пользователя через агента"""
    global agent_instance
    
    if not agent_instance:
        return "❌ Агент не инициализирован. Проверьте настройки."
    
    try:
        logger.info(f"🤖 Обработка сообщения: {user_message}")
        
        
        # Обрабатываем сообщение агентом
        result = agent_instance.process_message(user_message)
        
        # Получаем результаты анализа
        web_results = get_analysis_results()
        
        # Формируем ответ
        response_parts = []
        
        if result:
            response_parts.append(f"\n{str(result)}")
        
        # Добавляем результаты анализа если есть
        if web_results and any(web_results.values()):
            if web_results.get("agent_opinions"):
                response_parts.append(f"👥 **Мнения агентов:** {len(web_results['agent_opinions'])} мнений получено")
            
            if web_results.get("aggregated_decisions"):
                response_parts.append(f"📊 **Агрегированные решения:** {len(web_results['aggregated_decisions'])} решений")
                
            if web_results.get("risk_assessments"):
                response_parts.append(f"⚠️ **Оценка рисков:** {len(web_results['risk_assessments'])} оценок")
                
            if web_results.get("final_recommendations"):
                response_parts.append(f"💡 **Итоговые рекомендации:**\n{web_results['final_recommendations']}")
        
        if not response_parts:
            response_parts.append("✅ Сообщение обработано. Анализ завершен.")
        
        return "\n\n".join(response_parts)
        
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        return f"❌ Ошибка обработки: {str(e)}"

def main() -> None:
    logger = ChatLogger('main')

    ws_manager = WebSocketServerManager()
    ws_manager.start()

    time.sleep(1)

    ChatLogger.setup(ws_manager.get_loop())

    # Инициализируем агента
    agent = initialize_agent()
    if not agent:
        logger.error("Не удалось инициализировать агента. Приложение завершается.")
        return

    try:
        logger.info("🚀 Мультиагентная система анализа акций запущена")
        logger.info("📱 Откройте http://localhost:8080 в браузере")
        logger.message("System", "🤖 Система готова к работе! Задайте вопрос о вашем портфеле.")
        
        # Основной цикл приложения
        while True:
            time.sleep(0.1)  # Уменьшаем задержку для более быстрого отклика
            
            # Проверяем входящие логины от пользователя через UI
            if web_login_handler.login_queue:
                user_login = web_login_handler.login_queue.popleft()
                logger.info(f"Пользователь вошел в систему: {user_login}")
                logger.message("System", f"👋 Добро пожаловать, {user_login}!")
            
            # Проверяем входящие сообщения от пользователя через UI
            if web_input_handler.message_queue:
                user_message = web_input_handler.message_queue.popleft()
                logger.info(f"📨 Получено сообщение: {user_message}")
                
                
                # Обрабатываем сообщение через агента
                response = process_user_message(user_message, logger)
                
                # Отправляем ответ в чат
                logger.message("Bot", response)

    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
    finally:
        try:
            logger.info("Завершение работы...")
            ws_manager.stop()
        except:
            pass

if __name__ == "__main__":
    main()

