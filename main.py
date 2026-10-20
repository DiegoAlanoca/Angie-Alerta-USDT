# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

import time
import threading
import config
import database
import binance_api
import telegram_bot
from datetime import datetime
import bcb_api


def motor_de_alertas():
    while True:
        precios, disponibles = binance_api.obtener_datos_completos()
        
        if precios is not None and disponibles is not None:
            # Actualizar caché para que telegram_bot.py lo lea al instante
            database.cache_precios = precios
            database.cache_disponibles = disponibles
            
            usuarios = database.obtener_todos_los_usuarios()
            total_obtenidos = len(precios)
            
            for usuario in usuarios:
                chat_id = usuario['chat_id']
                
                # Definir cuántos promediar para este usuario específico
                n = min(usuario.get('top_anuncios', 6), total_obtenidos)
                if n == 0: continue
                
                # Matemática personalizada para el usuario
                precio_promedio = round(sum(precios[:n]) / n, 2)
                disponible_promedio = round(sum(disponibles[:n]) / n, 2)
                
                # --- A. Lógica Inicial y Umbral de Diferencia ---
                if usuario['bot_iniciado'] == 0:
                    database.actualizar_valor(chat_id, 'precio_anterior', precio_promedio)
                    database.actualizar_valor(chat_id, 'bot_iniciado', 1)
                    msj = f"🤖 *Bot Iniciado*\nPrecio base (Top {n}): `{precio_promedio:.2f} BOB`\nEscribe /menu para configurar tu bot."
                    telegram_bot.enviar_mensaje(chat_id, msj)
                
                # NUEVO: Lógica de reinicio silencioso
                elif usuario['bot_iniciado'] == 2:
                    database.actualizar_valor(chat_id, 'precio_anterior', precio_promedio)
                    database.actualizar_valor(chat_id, 'bot_iniciado', 1)
                
                elif abs(precio_promedio - usuario['precio_anterior']) >= usuario['umbral_diferencia']:
                    icono = "🔴 Subió" if precio_promedio > usuario['precio_anterior'] else "🟢 Bajó"
                    msj_alerta = f"⚠️ *(Top {n})*\nEl promedio {icono} a: `{precio_promedio:.2f} BOB`\nAnterior: `{usuario['precio_anterior']:.2f} BOB`"
                    telegram_bot.enviar_mensaje(chat_id, msj_alerta)
                    database.actualizar_valor(chat_id, 'precio_anterior', precio_promedio)

                if usuario['alerta_sup_activada'] == 1 and precio_promedio >= usuario['limite_superior']:
                    msj_sup = f"🚀 *¡ALERTA SUPERIOR ALCANZADA! (Top {n})*\nActual: `{precio_promedio:.2f} BOB`\nLímite: `{usuario['limite_superior']} BOB`\n\n_Alerta desactivada._"
                    telegram_bot.enviar_mensaje(chat_id, msj_sup)
                    database.actualizar_valor(chat_id, 'alerta_sup_activada', 0)

                if usuario['alerta_inf_activada'] == 1 and precio_promedio <= usuario['limite_inferior']:
                    msj_inf = f"📉 *¡ALERTA INFERIOR ALCANZADA! (Top {n})*\nActual: `{precio_promedio:.2f} BOB`\nLímite: `{usuario['limite_inferior']} BOB`\n\n_Alerta desactivada._"
                    telegram_bot.enviar_mensaje(chat_id, msj_inf)
                    database.actualizar_valor(chat_id, 'alerta_inf_activada', 0)
                
                if usuario.get('alerta_disp_activada', 0) == 1 and disponible_promedio <= usuario['limite_disponible']:
                    msj_disp = f"⚠️ *¡POCO USDT DISPONIBLE! (Top {n})*\nPromedio disponible: `{disponible_promedio:.2f} USDT`\nLímite: `{usuario['limite_disponible']} USDT`\n\n_Alerta desactivada._"
                    telegram_bot.enviar_mensaje(chat_id, msj_disp)
                    database.actualizar_valor(chat_id, 'alerta_disp_activada', 0)
                
        time.sleep(60)

def motor_bcb():
    while True:
        precio_bcb = bcb_api.obtener_tipo_cambio()
        
        if precio_bcb is not None:
            database.cache_bcb_venta = precio_bcb
            # Guardamos la hora exacta de la actualización
            database.cache_bcb_hora = datetime.now().strftime("%H:%M:%S")
            print(f"BCB Actualizado: {precio_bcb} BOB a las {database.cache_bcb_hora}")
            
        time.sleep(300) # Duerme 5 minutos (300 segundos)

if __name__ == '__main__':
    database.iniciar_base_datos()
    database.registrar_usuario(config.CHAT_ID)
    
    print("Iniciando sistema...")
    telegram_bot.enviar_mensaje(config.CHAT_ID, "🔧 Sistema en línea ADMIN 😎.\nEscribe /menu para configurar.")
    
    hilo_binance = threading.Thread(target=motor_de_alertas)
    hilo_binance.daemon = True
    hilo_binance.start()

    hilo_bcb = threading.Thread(target=motor_bcb)
    hilo_bcb.daemon = True
    hilo_bcb.start()
    
    telegram_bot.iniciar_bot()
    print("Servidor en correcto funcionamiento")