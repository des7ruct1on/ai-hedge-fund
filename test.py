from llm.cloudrugpt import CloudRuGPT
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("CLOUDRU_API_KEY")
llm = CloudRuGPT(api_key=api_key)

prompt_1 = """
Ответь на вопрос: {question}
"""

prompt = ChatPromptTemplate.from_template(prompt_1)

chain = prompt | llm

response = chain.invoke({"question": "Как дела?"})

# Получаем AIMessage из ChatResult
message = response

print("🤖 Ответ:", message)
print("\n📊 Метрики:")
print(f"  Тип сообщения: {type(message).__name__}")
print(f"  Модель: {message.additional_kwargs['model']}")
print(f"  Статус: {message.additional_kwargs['status']}")
print(f"  Время обработки: {message.additional_kwargs['processing_time_seconds']} сек")
print(f"  Токены в промпте: {message.additional_kwargs['usage']['prompt_tokens']}")
print(f"  Токены в ответе: {message.additional_kwargs['usage']['completion_tokens']}")
print(f"  Всего токенов: {message.additional_kwargs['usage']['total_tokens']}")
print(f"  Время запроса: {message.additional_kwargs['timestamp']}")
print(f"  Параметры: {message.additional_kwargs['parameters']}")