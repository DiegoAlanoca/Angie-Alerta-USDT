# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

import os
from dotenv import load_dotenv

# Los secretos se leen del archivo .env (ver .env.example). Nunca escribirlos aquí.
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not TOKEN or not CHAT_ID:
    raise SystemExit("Falta TELEGRAM_TOKEN o ADMIN_CHAT_ID. Copia .env.example a .env y completa los valores.")

CHAT_ID = int(CHAT_ID)  # ID del SuperUsuario (admin)
