# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

import sys
import time
import threading
import traceback
import config
import database
import binance_api
import telegram_bot
import tiempo
from telebot.apihelper import ApiTelegramException
import bcb_api


class Salud:
    """Cuenta los fallos seguidos de una fuente de datos y avisa al admin.

    Avisa una sola vez al llegar a `fallos_para_avisar` y otra al recuperarse,
    para no llenar el chat del admin mientras dure la caída.
    """
    def __init__(self, nombre, fallos_para_avisar, motivo=None):
        self.nombre = nombre
        self.fallos_para_avisar = fallos_para_avisar
        self.motivo = motivo   # función opcional que devuelve el último error (texto)
        self.fallos = 0
        self.avisado = False
        self.ultimo_ok = None

    @staticmethod
    def _avisar_admin(texto):
        # Un fallo al avisar (red, Telegram) nunca debe interrumpir el ciclo de alertas
        try:
            return _enviar(config.CHAT_ID, texto)
        except Exception as e:
            print(f"No se pudo avisar al admin: {e}")
            return False

    def registrar(self, ok):
        if ok:
            if self.avisado:
                self._avisar_admin(f"✅ *{self.nombre}* volvió a responder.")
            self.fallos = 0
            self.avisado = False
            self.ultimo_ok = tiempo.ahora()
            return

        self.fallos += 1
        if self.fallos >= self.fallos_para_avisar and not self.avisado:
            desde = f"Última lectura buena: {tiempo.formatear(self.ultimo_ok)}." if self.ultimo_ok else "Aún no hubo ninguna lectura buena."
            motivo = self.motivo() if self.motivo else ""
            # Va dentro de `código` para que guiones bajos o asteriscos del error no rompan el Markdown
            motivo = motivo.replace("`", "'")
            detalle = f"\nMotivo: `{motivo}`" if motivo else ""
            self.avisado = self._avisar_admin(
                f"🚨 *{self.nombre}* lleva {self.fallos} intentos fallidos seguidos.\n{desde}{detalle}\n"
                f"Los datos mostrados pueden estar desactualizados."
            )

# Binance se consulta cada 60 s (5 fallos = ~5 min); el BCB cada 300 s (3 fallos = ~15 min)
salud_binance = Salud("Binance P2P", 5, motivo=lambda: binance_api.ultimo_error)
salud_bcb = Salud("BCB", 3)


def _enviar(chat_id, texto):
    """Envía un mensaje. Devuelve True si salió; False si no (y ya se manejó el error).

    Si el usuario bloqueó el bot (403) se elimina de la base, salvo el admin.
    Si Telegram pide frenar (429) se espera lo indicado.
    """
    try:
        telegram_bot.enviar_mensaje(chat_id, texto)
        return True
    except ApiTelegramException as e:
        if e.error_code == 403 and chat_id != config.CHAT_ID:
            database.eliminar_usuario(chat_id)
            print(f"Usuario {chat_id} bloqueó el bot ({e.description}); eliminado.")
        elif e.error_code == 429:
            espera = e.result_json.get('parameters', {}).get('retry_after', 5)
            print(f"Telegram pide esperar {espera}s (429).")
            time.sleep(espera)
        else:
            print(f"No se pudo enviar a {chat_id}: {e}")
        return False


def _disparar_alerta(chat_id, operacion, tipo, limite, mensaje):
    """Desactiva la alerta de un solo disparo y avisa al usuario.

    Primero 'reclama' la alerta de forma atómica: si el usuario la cambió mientras
    tanto, no se dispara. Si el envío falla, se vuelve a armar para reintentar.
    Devuelve False si no se pudo enviar (hay que dejar de procesar a este usuario).
    """
    if not database.cambiar_alerta(chat_id, operacion, tipo, limite, 1, 0):
        return True
    if _enviar(chat_id, mensaje):
        return True
    database.cambiar_alerta(chat_id, operacion, tipo, limite, 0, 1)
    return False


def _operacion(usuario):
    """'BUY' o 'SELL' del usuario; cualquier otro valor guardado se trata como la operación por defecto."""
    operacion = usuario.get('operacion')
    return operacion if operacion in binance_api.OPERACIONES else database.OPERACION_POR_DEFECTO


def _promedios(datos, operacion, top):
    """(n, precio, disponible) promedio del Top `top` de `operacion`, o None si no hay anuncios."""
    precios, disponibles = datos[operacion]
    n = min(top, len(precios))
    if n == 0:
        return None
    return n, round(sum(precios[:n]) / n, 2), round(sum(disponibles[:n]) / n, 2)


def _alerta_cumplida(tipo, limite, precio, disponible):
    if tipo == 'sup':
        return precio >= limite
    if tipo == 'inf':
        return precio <= limite
    return disponible <= limite   # 'disp'


def _texto_alerta(tipo, operacion, n, precio, disponible, limite):
    nombre_op = telegram_bot.NOMBRES_OPERACION[operacion]
    if tipo == 'sup':
        titulo, cuerpo = "🚀 *¡ALERTA SUPERIOR ALCANZADA!", f"Actual: `{precio:.2f} BOB`\nLímite: `{limite:.2f} BOB`"
    elif tipo == 'inf':
        titulo, cuerpo = "📉 *¡ALERTA INFERIOR ALCANZADA!", f"Actual: `{precio:.2f} BOB`\nLímite: `{limite:.2f} BOB`"
    else:
        cantidad = telegram_bot.TEXTO_CANTIDAD[operacion]
        titulo = f"⚠️ *¡POCO USDT {cantidad.upper()}!"
        cuerpo = f"Promedio {cantidad}: `{disponible:.2f} USDT`\nLímite: `{limite:.2f} USDT`"
    return f"{titulo} ({nombre_op}, Top {n})*\n{cuerpo}\n\n_Alerta desactivada._"


def _avisar_cambio(chat_id, usuario, operacion, n, precio_promedio):
    """Bienvenida / aviso de cambio del precio de la operación elegida en Ajustes.

    Devuelve False si no se pudo enviar (hay que dejar de procesar a este usuario).
    """
    nombre_op = telegram_bot.NOMBRES_OPERACION[operacion]

    if usuario['bot_iniciado'] == 0:
        database.actualizar_valores(chat_id, {'precio_anterior': precio_promedio, 'bot_iniciado': 1})
        msj = f"🤖 *Bot Iniciado*\nPrecio base ({nombre_op}, Top {n}): `{precio_promedio:.2f} BOB`\nEscribe /menu para configurar tu bot."
        return _enviar(chat_id, msj)

    # Reinicio silencioso (cambio de Top N u operación)
    if usuario['bot_iniciado'] == 2:
        database.actualizar_valores(chat_id, {'precio_anterior': precio_promedio, 'bot_iniciado': 1})
        return True

    # round(): los promedios tienen 2 decimales, pero su resta en float no (7.15-7.14 != 0.01)
    if round(abs(precio_promedio - usuario['precio_anterior']), 2) >= usuario['umbral_diferencia']:
        subio = precio_promedio > usuario['precio_anterior']
        # 🟢 = favorable para quien opera: al comprar conviene que baje; al vender, que suba
        favorable = subio == (operacion == "SELL")
        icono = f"{'🟢' if favorable else '🔴'} {'Subió' if subio else 'Bajó'}"
        msj_alerta = f"⚠️ *({nombre_op}, Top {n})*\nEl promedio {icono} a: `{precio_promedio:.2f} BOB`\nAnterior: `{usuario['precio_anterior']:.2f} BOB`"
        # Si el envío falla no se mueve el precio base: se reintenta en el próximo ciclo
        if not _enviar(chat_id, msj_alerta):
            return False
        database.actualizar_valor(chat_id, 'precio_anterior', precio_promedio)
    return True


def procesar_usuario(chat_id, datos):
    """`datos` es {operacion: (precios, disponibles)} con los lados que se pudieron leer este ciclo."""
    # Lectura fresca: el usuario pudo cambiar su configuración desde que empezó el ciclo
    usuario = database.obtener_usuario(chat_id)
    if usuario is None:
        return
    top = usuario.get('top_anuncios') or 6

    # --- A. Aviso de cambio: sigue una sola operación, la elegida en Ajustes ---
    operacion = _operacion(usuario)
    if operacion in datos:
        resumen = _promedios(datos, operacion, top)
        if resumen and not _avisar_cambio(chat_id, usuario, operacion, resumen[0], resumen[1]):
            return

    # --- B. Alertas de un solo disparo: compra y venta a la vez, cada lado con su propio precio ---
    alertas = database.obtener_alertas(chat_id)
    for operacion in binance_api.OPERACIONES:
        if operacion not in datos:
            continue   # no se pudo leer este lado en este ciclo: sus alertas esperan al siguiente
        resumen = _promedios(datos, operacion, top)
        if resumen is None:
            continue
        n, precio, disponible = resumen
        for tipo in database.TIPOS_ALERTA:
            alerta = alertas.get((operacion, tipo))
            if not alerta or not alerta['activa']:
                continue
            if not _alerta_cumplida(tipo, alerta['limite'], precio, disponible):
                continue
            texto = _texto_alerta(tipo, operacion, n, precio, disponible, alerta['limite'])
            if not _disparar_alerta(chat_id, operacion, tipo, alerta['limite'], texto):
                return


def ciclo_de_alertas():
    # Siempre se leen los dos lados: las alertas de compra y de venta conviven en cada usuario
    datos = {}
    for operacion in binance_api.OPERACIONES:
        precios, disponibles = binance_api.obtener_datos_completos(operacion)
        if precios is None or disponibles is None:
            continue
        datos[operacion] = (precios, disponibles)
        # Actualizar caché para que telegram_bot.py lo lea al instante
        database.cache_binance[operacion] = database.LecturaBinance(tuple(precios), tuple(disponibles), tiempo.ahora())

    salud_binance.registrar(len(datos) == len(binance_api.OPERACIONES))
    if not datos:
        return

    for usuario in database.obtener_todos_los_usuarios():
        chat_id = usuario['chat_id']
        # Un usuario con datos corruptos o un error puntual no debe afectar a los demás
        try:
            procesar_usuario(chat_id, datos)
        except Exception:
            print(f"Error procesando al usuario {chat_id}:")
            traceback.print_exc()


def motor_de_alertas():
    while True:
        # Nada debe matar este hilo: si muere, el bot sigue "vivo" pero sin alertas
        try:
            ciclo_de_alertas()
        except Exception:
            print("Error en el ciclo del motor de alertas:")
            traceback.print_exc()
        time.sleep(60)

def motor_bcb():
    while True:
        try:
            precio_bcb = bcb_api.obtener_tipo_cambio()

            if precio_bcb is not None:
                # Valor y fecha/hora (Bolivia) de la lectura, juntos en una sola tupla
                database.cache_bcb = database.LecturaBCB(precio_bcb, tiempo.ahora())
                print(f"BCB Actualizado: {precio_bcb} BOB el {tiempo.formatear(database.cache_bcb.hora)}")
            salud_bcb.registrar(precio_bcb is not None)
        except Exception:
            print("Error en el ciclo del BCB:")
            traceback.print_exc()

        time.sleep(300) # Duerme 5 minutos (300 segundos)

if __name__ == '__main__':
    # Bajo systemd/nohup stdout no es una terminal y Python lo guarda en un búfer: los print()
    # aparecerían en el log con minutos de retraso (o nunca si el proceso cae). Se fuerza línea a línea.
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

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
