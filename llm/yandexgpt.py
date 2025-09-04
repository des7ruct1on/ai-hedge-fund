from yandex_cloud_ml_sdk import YCloudML
from typing import Optional

class YandexGPT:
    def __init__(self, folder_id: str, api_key: str, model: str = "yandexgpt", version: str = "rc"):
        self.folder_id = folder_id
        self.api_key = api_key
        self.sdk = YCloudML(folder_id=folder_id, auth=api_key)
        self.model = self.sdk.models.completions(model, model_version=version)

    def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int = 500) -> str:
        try:
            response = self.model.run(prompt)
            return response.text 
        except Exception as e:
            raise RuntimeError(f"YandexGPT request failed: {e}")