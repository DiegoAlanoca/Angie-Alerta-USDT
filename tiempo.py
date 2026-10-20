# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

from datetime import datetime
from zoneinfo import ZoneInfo

# La VPS de Google Cloud usa UTC; el bot siempre muestra hora de Bolivia.
ZONA = ZoneInfo("America/La_Paz")

def ahora():
    return datetime.now(ZONA)

def formatear(momento):
    """'19/10/2026 20:50' en hora de Bolivia."""
    return momento.astimezone(ZONA).strftime("%d/%m/%Y %H:%M")

def minutos_desde(momento):
    return (ahora() - momento).total_seconds() / 60

def hace(momento):
    """Antigüedad legible: 'hace 30 s', 'hace 12 min', 'hace 3 h 5 min'."""
    segundos = max(0, int((ahora() - momento).total_seconds()))
    if segundos < 60:
        return f"hace {segundos} s"
    minutos = segundos // 60
    if minutos < 60:
        return f"hace {minutos} min"
    return f"hace {minutos // 60} h {minutos % 60} min"
