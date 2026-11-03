import os
import json
import requests
import uuid
import re
import urllib3
from dotenv import load_dotenv
from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Загружаем ключ из .env
load_dotenv()
AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")


def get_access_token():
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = {'scope': 'GIGACHAT_API_PERS'}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': str(uuid.uuid4()),
        'Authorization': f'Basic {AUTH_KEY}'
    }
    response = requests.post(url, headers=headers, data=payload, verify=False)
    response.raise_for_status()
    return response.json().get('access_token')


def generate_card(access_token, product_data):
    url = "https://api.giga.chat/v1/chat/completions"

    # Формируем запрос к нейросети
    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                product_json=json.dumps(product_data, ensure_ascii=False, indent=2))}
        ],
        "temperature": 0.1,  # Делаем модель максимально точной
        "max_tokens": 1500
    }

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }

    try:
        response = requests.post(url, headers=headers, json=payload, verify=False)
        response.raise_for_status()
        data = response.json()

        content = data['choices'][0]['message']['content']

        # Очистка от возможных markdown-тегов ```json
        content = re.sub(r'^```json\s*', '', content, flags=re.MULTILINE)
        content = re.sub(r'```\s*$', '', content, flags=re.MULTILINE)

        return json.loads(content.strip())

    except requests.exceptions.RequestException as e:
        return {"error": f"Ошибка API: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"error": f"Ошибка парсинга JSON от нейросети: {str(e)}", "raw_content": content}


def validate_product(product, index):
    """Проверяет входные данные и возвращает ошибку, если чего-то не хватает"""
    if not isinstance(product, dict):
        return f"ОШИБКА ВАЛИДАЦИИ: Товар #{index} имеет неверный формат (ожидался JSON-объект)."

    missing_fields = []
    if not product.get("name"): missing_fields.append("название товара (name)")
    if not product.get("manufacturer"): missing_fields.append("производитель (manufacturer)")
    if not product.get("description"): missing_fields.append("описание (description)")
    if not product.get("specs"): missing_fields.append("характеристики (specs)")

    if missing_fields:
        return (
            f"ОШИБКА ВАЛИДАЦИИ: Генерация карточки для товара #{index} невозможна. "
            f"Для создания качественного текста не хватает следующих полей: {', '.join(missing_fields)}. "
            f"Пожалуйста, дополните входные данные и запустите скрипт снова."
        )

    return None


def main():
    if not AUTH_KEY:
        print("ОШИБКА: Ключ GIGACHAT_AUTH_KEY не найден в .env")
        return

    print("Получаем Access token...")
    try:
        token = get_access_token()
        print("Токен получен!")
    except Exception as e:
        print(f"Критическая ошибка при получении токена: {e}")
        return

    # Читаем товары
    try:
        with open("products.json", "r", encoding="utf-8") as f:
            products = json.load(f)
    except FileNotFoundError:
        print("ОШИБКА: Файл products.json не найден!")
        return
    except json.JSONDecodeError:
        print("ОШИБКА: Файл products.json содержит некорректный JSON!")
        return

    # Создаем папку output, если её нет
    os.makedirs("output", exist_ok=True)

    # Проходимся по каждому товару
    for i, product in enumerate(products, 1):
        # 1. Валидация входных данных
        error_msg = validate_product(product, i)
        if error_msg:
            print(f"[{i}/{len(products)}] {error_msg}")
            # Записываем ошибку в файл
            with open(f"output/product_{i}_error.json", "w", encoding="utf-8") as f:
                json.dump({"error": error_msg}, f, ensure_ascii=False, indent=2)
            continue

        name = product.get("name")
        print(f"\n[{i}/{len(products)}] Генерируем карточку для: {name}...")

        # 2. Генерация
        result = generate_card(token, product)

        # 3. Сохранение
        safe_filename = f"product_{i}.json"
        filepath = os.path.join("output", safe_filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        if "error" in result:
            print(f"Внимание! Ошибка при генерации: {result['error']}")
        else:
            print(f"Готово! Результат сохранен в {filepath}")


if __name__ == "__main__":
    main()