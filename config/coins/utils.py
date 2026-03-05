import os
import requests
from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI

# .env 파일을 명시적으로 로드
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(env_path)

def get_ai_response(prompt, system_prompt="Answer in Korean"):
    """SSAFY GMS API를 사용하여 AI의 답변을 가져옵니다."""
    api_key = os.getenv("GMS_KEY")
    if not api_key:
        return "GMS_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요."

    client = OpenAI(
        api_key=api_key,
        base_url="https://gms.ssafy.io/gmsapi/api.openai.com/v1"
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "developer", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            timeout=60
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI API Error: {e}")
        return f"AI 분석을 가져오는 중 오류가 발생했습니다: {e}"

def get_coin_market_chart(coin_id, days=7):
    """코인게코에서 최근 N일간의 가격 데이터를 가져옵니다."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days,
        "interval": "daily"
    }
    
    headers = {}
    api_key = os.getenv("COINGECKO_API_KEY")
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
        
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"CoinGecko API Error: {e}")
        return None

def get_coin_ohlc(coin_id, days=1):
    """코인게코에서 OHLC(캔들) 데이터를 가져옵니다."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {
        "vs_currency": "usd",
        "days": days
    }
    
    headers = {}
    api_key = os.getenv("COINGECKO_API_KEY")
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
        
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"CoinGecko OHLC API Error: {e}")
        return None

def get_coins_markets_data(coin_ids, vs_currency="usd"):
    """여러 코인의 실시간 마켓 데이터(가격, 등락률 등)를 가져옵니다."""
    if not coin_ids:
        return []
        
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": vs_currency,
        "ids": ",".join(coin_ids),
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "24h"
    }
    
    headers = {}
    api_key = os.getenv("COINGECKO_API_KEY")
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
        
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"CoinGecko Markets API Error: {e}")
        return []
