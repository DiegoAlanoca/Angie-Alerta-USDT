# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

from curl_cffi import requests

def obtener_datos_completos():
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }
    payload = {
        "fiat": "BOB", "page": 1, "rows": 15, "tradeType": "BUY",
        "asset": "USDT", "countries": [], "proMerchantAds": False,
        "shieldMerchantAds": False, "publisherType": None,
        "payTypes": [], "classifies": ["mass", "profession", "tier1", "tier2"]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10, impersonate="chrome110")
        data = response.json()

        if data.get("code") == "000000":
            anuncios = data.get("data", [])
            if len(anuncios) > 0:
                precios = []
                disponibles = []
                
                for anuncio in anuncios:
                    precios.append(float(anuncio["adv"]["price"]))
                    disponibles.append(float(anuncio["adv"]["surplusAmount"]))
                
                return precios, disponibles
            else:
                print("Error: No se encontró ni un anuncio.")
        else:
            print("Error: Código de respuesta de Binance no fue 000000")
            
    except Exception as e:
        print(f"Error consultando Binance: {e}")
        
    return None, None