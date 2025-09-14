import os
import asyncio
import re
from typing import Optional, List, Dict, Any, Iterator
from openai import OpenAI
import json
from datetime import datetime
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.messages import BaseMessage, AIMessage
from pydantic import Field

class CloudRuGPT(BaseChatModel):
    """Интеграция с Cloud.ru API через OpenAI клиент"""

    api_key: Optional[str] = Field(default=None)
    model: str = Field(default="Qwen/Qwen3-Coder-480B-A35B-Instruct")
    base_url: str = Field(default="https://foundation-models.api.cloud.ru/v1")
    client: Optional[OpenAI] = Field(default=None)

    def __init__(self, api_key: str = None, model: str = "Qwen/Qwen3-Coder-480B-A35B-Instruct", **kwargs):
        # Устанавливаем значения по умолчанию
        api_key = api_key or os.getenv('CLOUDRU_API_KEY')
        
        super().__init__(
            api_key=api_key,
            model=model,
            **kwargs
        )
        
        # Инициализируем клиент после создания объекта
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
    
    @property
    def _llm_type(self) -> str:
        """Возвращает тип LLM для LangChain"""
        return "cloudrugpt"
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Генерация ответа с метриками"""
        # Преобразуем сообщения в промпт
        prompt = "\n".join([msg.content for msg in messages])
        
        result = self.complete_with_metrics(prompt, **kwargs)
        
        # Создаем AIMessage с дополнительными метаданными
        message = AIMessage(
            content=result["text"],
            additional_kwargs={
                "model": result["model"],
                "usage": result["usage"],
                "processing_time_seconds": result["processing_time_seconds"],
                "timestamp": result["timestamp"],
                "parameters": result["parameters"],
                "status": result["status"]
            }
        )
        
        # Создаем ChatGeneration и ChatResult
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])
    
    def complete_with_metrics(self, prompt: str, temperature: float = 0.3, max_tokens: int = 30000) -> Dict[str, Any]:
        """Полный вызов с метриками"""
        try:
            start_time = datetime.now()
            
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                presence_penalty=0,
                top_p=0.7,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # print(f"Response:\n\n {response}")

            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()

            if response and response.choices:
                result = {
                    "text": response.choices[0].message.content,
                    "model": self.model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0
                    },
                    "processing_time_seconds": round(processing_time, 2),
                    "timestamp": start_time.isoformat(),
                    "parameters": {
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "top_p": 0.7,
                        "presence_penalty": 0
                    },
                    "status": "success"
                }
                return result
            else:
                return {
                    "text": "❌ Пустой ответ от API",
                    "status": "error",
                    "timestamp": start_time.isoformat()
                }

        except Exception as e:
            return {
                "text": f"❌ Ошибка анализа: {str(e)}",
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "model": self.model
            }
    
    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 30000) -> str:
        """Простой вызов без метрик (для обратной совместимости)"""
        result = self.complete_with_metrics(prompt, temperature, max_tokens)
        return result["text"]
