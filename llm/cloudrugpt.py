import os
import asyncio
import re
from typing import Optional, List, Dict
from openai import OpenAI
import json
from datetime import datetime

class CloudRuGPT:
    """Интеграция с Cloud.ru API через OpenAI клиент"""

    def __init__(self, api_key: str = None, model: str = "Qwen/Qwen3-Coder-480B-A35B-Instruct"):
        self.api_key = api_key or os.getenv('CLOUDRU_API_KEY')
        self.model = model
        self.base_url = "https://foundation-models.api.cloud.ru/v1"
        
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        else:
            self.client = None

    
    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 500) -> str:
        try:

            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=10000,
                temperature=temperature,
                presence_penalty=0,
                top_p=0.95,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            if response and response.choices:
                cleaned_text = response.choices[0].message.content
                # print(response)
                return cleaned_text

        except Exception as e:
            return f"❌ Ошибка анализа: {str(e)}"
