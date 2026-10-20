# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

import math
import statistics
import time
from curl_cffi import requests

# --- Calidad de los datos ---
# Se piden más anuncios de los que se usan para que, tras descartar los poco fiables,
# siga habiendo suficientes para el Top 15 del usuario.
ANUNCIOS_PEDIDOS = 20
ANUNCIOS_MAX = 15
# BUY = el usuario compra USDT (anuncios de vendedores); SELL = el usuario vende USDT (anuncios de
# compradores). Binance ordena ambos del mejor precio para el usuario al peor.
OPERACIONES = ("BUY", "SELL")
ANUNCIOS_MIN = 3           # con menos anuncios fiables el promedio no es confiable: se trata como fallo
MIN_USDT_OPERABLE = 20     # anuncios con menos USDT realmente operables son señuelos o inútiles
TOLERANCIA_MEDIANA = 0.03  # se descarta un precio que se aleje más de 3% de la mediana


def _leer_anuncio(anuncio):
    """Devuelve (precio, disponible) si el anuncio es operable de verdad, o None.

    'disponible' es `tradableQuantity` (lo que de verdad se puede operar ahora: en BUY lo que
    ofrece el vendedor, en SELL lo que aún quiere comprar el comprador); `surplusAmount`
    incluye saldo que el anunciante no puede ofrecer.
    """
    adv = anuncio["adv"]
    precio = float(adv["price"])
    operable = float(adv.get("tradableQuantity", adv["surplusAmount"]))
    minimo = float(adv["minSingleTransAmount"])           # en BOB
    maximo = float(adv.get("dynamicMaxSingleTransAmount") or adv["maxSingleTransAmount"])  # en BOB

    if not (math.isfinite(precio) and math.isfinite(operable)) or precio <= 0:
        return None
    if operable < MIN_USDT_OPERABLE:
        return None
    if operable * precio < minimo:   # la orden mínima supera lo que queda: nadie puede operar
        return None
    if maximo < minimo:
        return None
    return precio, operable


def filtrar_anuncios(anuncios):
    """De la lista cruda de Binance saca (precios, disponibles) solo de anuncios fiables.

    Conserva el orden de Binance (del mejor precio al peor). Descarta anuncios mal formados,
    inoperables y precios que se alejan de la mediana (típico de anuncios señuelo).
    """
    validos = []
    for anuncio in anuncios:
        try:
            leido = _leer_anuncio(anuncio)
        except (KeyError, TypeError, ValueError):
            continue   # un anuncio raro no debe invalidar a los demás
        if leido is not None:
            validos.append(leido)

    if validos:
        mediana = statistics.median(p for p, _ in validos)
        validos = [(p, d) for p, d in validos if abs(p - mediana) <= mediana * TOLERANCIA_MEDIANA]

    validos = validos[:ANUNCIOS_MAX]
    return [p for p, _ in validos], [d for _, d in validos]


class _Bloqueado(Exception):
    """Binance limitó o bloqueó las consultas (429/418/403). No se debe insistir."""
    def __init__(self, estado, espera=None):
        super().__init__(f"HTTP {estado}")
        self.estado = estado
        self.espera = espera   # segundos pedidos por Binance (Retry-After), si los dio


# --- Resistencia a fallos ---
# Errores pasajeros (red, timeout, 5xx, respuesta rara): se reintenta dentro del mismo ciclo.
REINTENTOS = 3
ESPERA_REINTENTOS = (2, 5)           # segundos antes del 2º y del 3º intento (el ciclo total es de 60 s)
# Límite/bloqueo (429, 418, 403): no se insiste. Se pausa con espera creciente para no empeorarlo.
ESTADOS_BLOQUEO = (429, 418, 403)
ESPERA_BLOQUEO_MIN = 60              # 1 min la primera vez, luego 2, 4, 8...
ESPERA_BLOQUEO_MAX = 900             # tope: 15 min

_bloqueos_seguidos = 0
_pausado_hasta = 0.0                 # time.monotonic() hasta el que no se consulta
ultimo_error = ""                    # motivo del último fallo, para el aviso al admin


def _consultar(url, headers, payload):
    """Una consulta a Binance. Devuelve el JSON, o lanza _Bloqueado / otra excepción si falla."""
    response = requests.post(url, headers=headers, json=payload, timeout=10, impersonate="chrome110")

    if response.status_code in ESTADOS_BLOQUEO:
        try:
            espera = float(response.headers.get("Retry-After"))
        except (TypeError, ValueError):
            espera = None
        raise _Bloqueado(response.status_code, espera)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")

    data = response.json()   # si Binance devolvió una página HTML (WAF), falla aquí y se reintenta
    if data.get("code") != "000000":
        raise RuntimeError(f"código de respuesta {data.get('code')!r} (se esperaba '000000')")
    return data


def _pausar_por_bloqueo(bloqueo):
    global _bloqueos_seguidos, _pausado_hasta, ultimo_error
    _bloqueos_seguidos += 1
    espera = bloqueo.espera or min(ESPERA_BLOQUEO_MIN * 2 ** (_bloqueos_seguidos - 1), ESPERA_BLOQUEO_MAX)
    espera = max(1, min(espera, 3600))
    _pausado_hasta = time.monotonic() + espera
    ultimo_error = f"Binance limitó las consultas ({bloqueo}); en pausa {espera / 60:.0f} min"
    print(f"Error: {ultimo_error}.")


def obtener_datos_completos(operacion="BUY"):
    """Devuelve (precios, disponibles) del lado `operacion` ("BUY" o "SELL"), o (None, None) si falla."""
    global _bloqueos_seguidos, ultimo_error

    if operacion not in OPERACIONES:
        raise ValueError(f"Operación inválida: {operacion!r}")

    if time.monotonic() < _pausado_hasta:
        return None, None   # en pausa por un bloqueo previo: no se vuelve a golpear a Binance

    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }
    payload = {
        "fiat": "BOB", "page": 1, "rows": ANUNCIOS_PEDIDOS, "tradeType": operacion,
        "asset": "USDT", "countries": [], "proMerchantAds": False,
        "shieldMerchantAds": False, "publisherType": None,
        "payTypes": [], "classifies": ["mass", "profession", "tier1", "tier2"]
    }

    data = None
    for intento in range(1, REINTENTOS + 1):
        try:
            data = _consultar(url, headers, payload)
            break
        except _Bloqueado as bloqueo:
            _pausar_por_bloqueo(bloqueo)
            return None, None
        except Exception as e:
            ultimo_error = f"{type(e).__name__}: {e}"
            print(f"Error consultando Binance (intento {intento}/{REINTENTOS}): {ultimo_error}")
            if intento < REINTENTOS:
                time.sleep(ESPERA_REINTENTOS[intento - 1])
    if data is None:
        return None, None

    _bloqueos_seguidos = 0   # Binance respondió bien: se reinicia la espera creciente

    anuncios = data.get("data") or []
    if len(anuncios) > 0:
        precios, disponibles = filtrar_anuncios(anuncios)
        if len(precios) >= ANUNCIOS_MIN:
            return precios, disponibles
        ultimo_error = f"solo {len(precios)} de {len(anuncios)} anuncios son fiables (mínimo {ANUNCIOS_MIN})"
    else:
        ultimo_error = "Binance no devolvió ningún anuncio"
    print(f"Error: {ultimo_error}.")
    return None, None
