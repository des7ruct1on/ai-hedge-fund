"""
Скрипт для запуска FastAPI веб-интерфейса мультиагентной системы
"""
import os
import sys
import uvicorn

# Добавляем текущую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    print("🚀 Запуск FastAPI веб-интерфейса мультиагентной системы анализа акций")
    print("📱 Откройте браузер и перейдите по адресу: http://localhost:8000")
    print("📊 API документация доступна по адресу: http://localhost:8000/docs")
    print("=" * 60)
    
    uvicorn.run(
        "web_interface_fastapi:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
