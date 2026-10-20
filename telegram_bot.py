# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
import database

bot = telebot.TeleBot(config.TOKEN)

def enviar_mensaje(chat_id, texto, parse_mode="Markdown"):
    bot.send_message(chat_id, texto, parse_mode=parse_mode)

@bot.message_handler(commands=['menu', 'start'])
def comando_menu(message):
    chat_id = message.chat.id
    database.registrar_usuario(chat_id)
    usuario = database.obtener_usuario(chat_id)
    n = usuario.get('top_anuncios', 6)
    
    markup = InlineKeyboardMarkup(row_width=1)
    
    markup.add(InlineKeyboardButton(f"⚙️ Configurar Top (Actual: {n})", callback_data="cmd_top"))
    markup.add(InlineKeyboardButton(f"💵 Ver Promedio Actual (Top {n})", callback_data="cmd_showprom"))
    markup.add(InlineKeyboardButton(f"🏦 Ver Cambio Oficial BCB", callback_data="cmd_bcb"))
    markup.add(InlineKeyboardButton(f"Cambiar Umbral (Actual: {usuario['umbral_diferencia']})", callback_data="cmd_umbral"))
    
    estado_sup = f"✅ >= {usuario['limite_superior']}" if usuario['alerta_sup_activada'] else "❌ Desactivado"
    markup.add(InlineKeyboardButton(f"Alerta Mayor o Igual: {estado_sup}", callback_data="cmd_sup"))
    
    estado_inf = f"✅ <= {usuario['limite_inferior']}" if usuario['alerta_inf_activada'] else "❌ Desactivado"
    markup.add(InlineKeyboardButton(f"Alerta Menor o Igual: {estado_inf}", callback_data="cmd_inf"))
    
    estado_disp = f"✅ <= {usuario.get('limite_disponible', 0)}" if usuario.get('alerta_disp_activada', 0) else "❌ Desactivado"
    markup.add(InlineKeyboardButton(f"Alerta USDT Disp.: {estado_disp}", callback_data="cmd_disp"))
    
    msj = "*Panel de Configuración*\nSelecciona qué deseas modificar:"
    bot.send_message(chat_id, msj, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["cmd_umbral", "cmd_sup", "cmd_inf", "cmd_disp", "cmd_top", "cmd_showprom", "cmd_bcb"])
def callback_botones(call):
    chat_id = call.message.chat.id
    
    if call.data == "cmd_showprom":
        bot.answer_callback_query(call.id)
        usuario = database.obtener_usuario(chat_id)
        n = usuario.get('top_anuncios', 6)
        
        if len(database.cache_precios) > 0:
            n_real = min(n, len(database.cache_precios))
            promedio = sum(database.cache_precios[:n_real]) / n_real
            disp_prom = sum(database.cache_disponibles[:n_real]) / n_real
            
            msj = f"💵 *Promedio Actual (Top {n_real})*\nPrecio: `{promedio:.2f} BOB`\nDisp.: `{disp_prom:.2f} USDT`"
            bot.send_message(chat_id, msj, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "⏳ Recolectando datos, intenta en 60 segundos.")
            
    elif call.data == "cmd_top":
        bot.answer_callback_query(call.id, "Configurando Top...")
        msg = bot.send_message(chat_id, "Escribe la cantidad de anuncios para promediar (1 a 15):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, procesar_top)
        
    elif call.data == "cmd_umbral":
        bot.answer_callback_query(call.id, "Configurando umbral...")
        msg = bot.send_message(chat_id, "Escribe el nuevo valor del *Umbral* (ej. 0.05):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, procesar_nuevo_umbral)
        
    elif call.data == "cmd_sup":
        bot.answer_callback_query(call.id, "Configurando límite superior...")
        msg = bot.send_message(chat_id, "Escribe el precio para la *ALERTA SUPERIOR* (ej. 7.15) o 0 para desactivar:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, procesar_limite_superior)
        
    elif call.data == "cmd_inf":
        bot.answer_callback_query(call.id, "Configurando límite inferior...")
        msg = bot.send_message(chat_id, "Escribe el precio para la *ALERTA INFERIOR* (ej. 7.05) o 0 para desactivar:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, procesar_limite_inferior)
        
    elif call.data == "cmd_disp":
        bot.answer_callback_query(call.id, "Configurando límite USDT...")
        msg = bot.send_message(chat_id, "Escribe la cantidad mínima de *USDT en promedio* para alertarte o 0 para desactivar:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, procesar_limite_disponible)

    elif call.data == "cmd_bcb":
        bot.answer_callback_query(call.id)
        
        if database.cache_bcb_venta > 0.0:
            msj = f"🏦 *Tipo de Cambio Oficial (BCB)*\n\nVenta: `{database.cache_bcb_venta} BOB`\n\n_Última actualización: {database.cache_bcb_hora}_"
            bot.send_message(chat_id, msj, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "⏳ Conectando con el Banco Central. Intenta en unos segundos.")

def procesar_top(message):
    chat_id = message.chat.id
    try:
        val = int(message.text)
        if 1 <= val <= 15:
            database.actualizar_valor(chat_id, 'top_anuncios', val)
            # Cambiamos a estado 2 para actualizar el precio base sin enviar spam
            database.actualizar_valor(chat_id, 'bot_iniciado', 2) 
            bot.send_message(chat_id, f"✅ Promedio configurado al Top *{val}*.", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "❌ Valor fuera de rango (1-15).")
    except ValueError:
        bot.send_message(chat_id, "❌ Formato numérico inválido.")

def procesar_nuevo_umbral(message):
    chat_id = message.chat.id
    try:
        nuevo_valor = float(message.text)
        if nuevo_valor > 0.0:
            database.actualizar_valor(chat_id, 'umbral_diferencia', nuevo_valor)
            bot.send_message(chat_id, f"✅ Umbral actualizado a: *{nuevo_valor} BOB*", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "❌ Valor inválido.")
    except ValueError:
        bot.send_message(chat_id, "❌ Formato inválido.")

def procesar_limite_superior(message):
    chat_id = message.chat.id
    try:
        val = float(message.text)
        if val <= 0:
            database.actualizar_valor(chat_id, 'alerta_sup_activada', 0)
            bot.send_message(chat_id, "❌ Alerta Superior *DESACTIVADA*.", parse_mode="Markdown")
        else:
            database.actualizar_valor(chat_id, 'limite_superior', val)
            database.actualizar_valor(chat_id, 'alerta_sup_activada', 1)
            bot.send_message(chat_id, f"✅ Alerta Superior *ACTIVADA* (>= {val} BOB)", parse_mode="Markdown")
    except ValueError:
        bot.send_message(chat_id, "❌ Formato inválido.")

def procesar_limite_inferior(message):
    chat_id = message.chat.id
    try:
        val = float(message.text)
        if val <= 0:
            database.actualizar_valor(chat_id, 'alerta_inf_activada', 0)
            bot.send_message(chat_id, "❌ Alerta Inferior *DESACTIVADA*.", parse_mode="Markdown")
        else:
            database.actualizar_valor(chat_id, 'limite_inferior', val)
            database.actualizar_valor(chat_id, 'alerta_inf_activada', 1)
            bot.send_message(chat_id, f"✅ Alerta Inferior *ACTIVADA* (<= {val} BOB)", parse_mode="Markdown")
    except ValueError:
        bot.send_message(chat_id, "❌ Formato inválido.")

def procesar_limite_disponible(message):
    chat_id = message.chat.id
    try:
        val = float(message.text)
        if val <= 0:
            database.actualizar_valor(chat_id, 'alerta_disp_activada', 0)
            bot.send_message(chat_id, "❌ Alerta USDT Disponible *DESACTIVADA*.", parse_mode="Markdown")
        else:
            database.actualizar_valor(chat_id, 'limite_disponible', val)
            database.actualizar_valor(chat_id, 'alerta_disp_activada', 1)
            bot.send_message(chat_id, f"✅ Alerta USDT *ACTIVADA* (<= {val} USDT)", parse_mode="Markdown")
    except ValueError:
        bot.send_message(chat_id, "❌ Formato inválido.")

def iniciar_bot():
    print("Conectado a Telegram. Escuchando mensajes...")
    bot.infinity_polling()