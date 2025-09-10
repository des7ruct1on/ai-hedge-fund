import json
import re
from openai import OpenAI


class NewsSentimentAnalyzer:
    def __init__(self, api_key, base_url="https://api.proxyapi.ru/openrouter/v1", model="mistralai/mistral-medium-3.1"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def analyze_sentiment(self, news_json):
        try:
            if not all(key in news_json for key in ['ticket', 'news', 'text']):
                print(f"Ошибка: news_json не содержит всех необходимых ключей: {news_json}")
                result = news_json.copy()
                result['sentiment'] = 'neutral'
                return result

            chat_completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": f"""
                    Инструкции:
                    - Сосредоточьтесь на финансовых последствиях для компании, а не на общем эмоциональном тоне.
                    - "Positive" — новость, которая, вероятно, повысит стоимость акций или улучшит финансовые перспективы.
                    - "Negative" — новость, которая, вероятно, снизит стоимость акций или ухудшит финансовые перспективы.
                    - "Neutral" — новость без явного или значительного финансового воздействия.
                    - Значимость (significance):
                      - Высокая (0.8–1.0): новости, связанные с политикой (например, санкции, регуляции), решениями центрального банка (ставки, монетарная политика), ключевыми финансовыми показателями компании (доходы, прибыль, долги) или макроэкономическими событиями (например, рецессия).
                      - Средняя (0.4–0.7): новости о партнерствах, продуктах, внутренних изменениях (например, смена руководства), которые могут повлиять на акции, но не имеют критического значения.
                      - Низкая (0.0–0.3): новости с минимальным финансовым воздействием (например, PR-кампании, незначительные события).
                    - Учитывайте заголовок и текст новости вместе.

                    Входные данные:
                    - Тикер: {news_json['ticket']}
                    - Заголовок: {news_json['news']}
                    - Текст: {news_json['text']}
                    Верните ТОЛЬКО словарь в формате JSON: {{"sentiment": "positive|negative|neutral", "significance": float}}. Не добавляйте пояснений, текста или других данных.
                    """}
                ],
            )
            response_content = chat_completion.choices[0].message.content
            print(f"API response: {response_content}")  # Логируем сырой ответ

            # Удаляем кодовые ограждения ```json
            cleaned_content = re.sub(r'^```json\s*|\s*```$', '', response_content, flags=re.MULTILINE).strip()
            print(f"Cleaned response: {cleaned_content}")  # Логируем очищенный ответ для отладки

            # Парсим очищенную строку как JSON
            sentiment_response = json.loads(cleaned_content)
            if not isinstance(sentiment_response, dict) or 'sentiment' not in sentiment_response or 'significance' not in sentiment_response:
                raise ValueError("Ответ не содержит ожидаемых ключей 'sentiment' и 'significance'")
            result = news_json.copy()
            result['sentiment'] = sentiment_response['sentiment']
            result['significance'] = sentiment_response['significance']
            return result

        except json.JSONDecodeError as e:
            print(f"Ошибка разбора JSON ответа: {e}, response: {response_content}")
            result = news_json.copy()
            result['sentiment'] = 'neutral'
            return result
        except Exception as e:
            print(f"Ошибка анализа сентимента: {e}")
            result = news_json.copy()
            result['sentiment'] = 'neutral'
            return result

    def process_file(self, input_file, output_file):
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list):
                results = [self.analyze_sentiment(news) for news in data]
            else:
                results = self.analyze_sentiment(data)

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                
            return results
        except json.JSONDecodeError as e:
            print(f"Ошибка чтения JSON из файла {input_file}: {e}")
            return None
        except Exception as e:
            print(f"Ошибка обработки файла: {e}")
            return None

if __name__ == "__main__":
    analyzer = NewsSentimentAnalyzer(api_key=api_key)
    result = analyzer.process_file("news_by_ticker.json", "output_with_sentiment.json")
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))