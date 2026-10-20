# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

from curl_cffi import requests
from bs4 import BeautifulSoup

# Rango razonable (BOB por USD). Si el BCB cambia su HTML y el scraping lee otro número, se descarta.
TC_MIN, TC_MAX = 1.0, 100.0

def obtener_tipo_cambio():
    url = "https://www.bcb.gob.bo/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15, impersonate="chrome110")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Localizamos la clase exacta según la estructura HTML del BCB
            elemento = soup.find('span', class_='bcb-tco-num')
            
            if elemento:
                # Extraemos el texto, quitamos espacios y cambiamos la coma por punto
                texto = elemento.text.strip().replace(',', '.')
                valor = float(texto)
                if TC_MIN <= valor <= TC_MAX:
                    return valor
                print(f"Error: valor del BCB fuera de rango ({texto!r}); se descarta.")
            else:
                print("Error: No se encontró la etiqueta 'bcb-tco-num' en el HTML.")
        else:
            print(f"Error BCB: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"Error conectando al BCB: {e}")
        
    return None