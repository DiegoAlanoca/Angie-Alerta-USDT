# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

import math
import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, MenuButtonCommands
import config
import database
import tiempo

bot = telebot.TeleBot(config.TOKEN)

# Minutos sin lectura nueva a partir de los cuales un dato se avisa como desactualizado
# (Binance se consulta cada 1 min; el BCB cada 5 min).
BINANCE_VENCE_MIN = 5
BCB_VENCE_MIN = 30

# Rangos aceptados para lo que escribe el usuario (evita valores absurdos o que rompan el motor)
PRECIO_MIN, PRECIO_MAX = 1, 1000     # BOB por USDT
UMBRAL_MIN, UMBRAL_MAX = 0.01, 100   # BOB (los promedios tienen 2 decimales: menos de 0.01 no tiene sentido)
DISPONIBLE_MAX = 1_000_000_000       # USDT

# Operación que sigue cada usuario en Binance P2P. BUY = compra USDT (anuncios de vendedores),
# SELL = vende USDT (anuncios de compradores).
NOMBRES_OPERACION = {"BUY": "Comprar USDT", "SELL": "Vender USDT"}
ICONOS_OPERACION = {"BUY": "🛒", "SELL": "💰"}
# Qué significa la cantidad ("disponible") de cada anuncio según el lado
ETIQUETA_CANTIDAD = {"BUY": "Disp.", "SELL": "Demanda"}
TEXTO_CANTIDAD = {"BUY": "disponible", "SELL": "demandado"}
LADO = {"BUY": "compra", "SELL": "venta"}

# Atribución exigida por NOTICE (AGPL-3.0, sección 7(b)): debe verse en la interfaz del bot.
REPO_URL = "https://github.com/DiegoAlanoca/Angie-Alerta-USDT"
ATRIBUCION = f'Basado en "Angie Alerta USDT" de Diego Ronald Alanoca Avircata\n{REPO_URL}'

# Comandos del botón "Menú" (abajo a la izquierda del campo de texto), como en @BotFather.
COMANDOS = [
    ("start", "Iniciar el bot y ver la bienvenida"),
    ("menu", "Abrir el panel principal"),
    ("precio", "Ver el promedio actual del USDT"),
    ("bcb", "Ver el tipo de cambio oficial del BCB"),
    ("ayuda", "Cómo funciona el bot"),
    ("acerca", "Acerca de este proyecto"),
]

def enviar_mensaje(chat_id, texto, parse_mode="Markdown"):
    bot.send_message(chat_id, texto, parse_mode=parse_mode)


# ======================================================================================
# Utilidades de formato y teclados
# ======================================================================================

def _num(valor):
    """Número sin ceros sobrantes: 0.05, 11.9, 500."""
    return f"{valor:.4f}".rstrip("0").rstrip(".")

def _boton(texto, dato):
    return InlineKeyboardButton(texto, callback_data=dato)

def _teclado(*filas):
    """Arma un teclado en línea; ignora las filas None (p. ej. el botón de donar si no está configurado)."""
    markup = InlineKeyboardMarkup()
    for fila in filas:
        if fila:
            markup.row(*fila)
    return markup

def _fila_volver():
    return [_boton("⬅️ Menú", "nav:menu")]

def _fila_donar():
    if config.DONATION_URL:
        return [InlineKeyboardButton("💖 Apoyar el proyecto", url=config.DONATION_URL)]
    return None

def _texto_comandos():
    return "\n".join(f"/{comando} - {descripcion}" for comando, descripcion in COMANDOS)

def _texto_antiguedad(hora, vence_min, aviso):
    """Línea 'Actualizado: fecha (hace X)', más un aviso si el dato superó `vence_min` minutos."""
    if hora is None:
        return "_Sin hora de actualización._"
    texto = f"_Actualizado: {tiempo.formatear(hora)} ({tiempo.hace(hora)})_"
    if tiempo.minutos_desde(hora) > vence_min:
        texto += f"\n⚠️ *Dato desactualizado.* {aviso}"
    return texto

def leer_numero(message):
    """Convierte el texto del usuario en un float finito, o devuelve None si no es válido.

    Rechaza mensajes sin texto (fotos, stickers), 'nan', 'inf' y '1e999': SQLite guarda
    NaN como NULL y eso rompería el motor de alertas. Acepta coma decimal ("7,15").
    """
    texto = (message.text or "").strip().replace(",", ".")
    try:
        val = float(texto)
    except ValueError:
        return None
    return val if math.isfinite(val) else None

def _operacion(u):
    """'BUY' o 'SELL' del usuario; un valor guardado desconocido cuenta como la operación por defecto."""
    return u.get('operacion') if u.get('operacion') in NOMBRES_OPERACION else database.OPERACION_POR_DEFECTO

def _texto_operacion(u):
    op = _operacion(u)
    return f"{ICONOS_OPERACION[op]} {NOMBRES_OPERACION[op]}"

def _cargar_usuario(chat_id):
    """Fila del usuario (registrándolo si no existe) con sus alertas en u['alertas'].

    `u['alertas']` es {(operacion, tipo): {'limite', 'activa'}}; las vistas y los ajustes lo leen de ahí.
    """
    usuario = database.obtener_usuario(chat_id)
    if usuario is None:   # p. ej. fue eliminado por bloquear el bot y toca un botón viejo
        database.registrar_usuario(chat_id)
        usuario = database.obtener_usuario(chat_id)
    usuario['alertas'] = database.obtener_alertas(chat_id)
    return usuario

def _es_comando(message):
    return (message.text or "").startswith("/")


# ======================================================================================
# Ajustes que el usuario cambia escribiendo un número
# ======================================================================================
# Cada entrada describe una pantalla de "escribe el valor": a qué vista vuelve, cómo se valida,
# cómo se guarda y qué se le responde. Las alertas (clave "alerta" = (operación, tipo)) además se pueden desactivar.

def _validar_precio(v):
    return None if PRECIO_MIN <= v <= PRECIO_MAX else f"Precio fuera de rango ({PRECIO_MIN} a {PRECIO_MAX} BOB)."

# Alertas de precio: dos tipos por operación. `otra` es la alerta opuesta, para que no se contradigan.
_TIPOS_PRECIO = {
    "sup": {"icono": "📈", "etiqueta": "Mayor o igual", "simbolo": "≥", "otra": "inf"},
    "inf": {"icono": "📉", "etiqueta": "Menor o igual", "simbolo": "≤", "otra": "sup"},
}

def _clave_alerta(operacion, tipo):
    """Clave en AJUSTES (y en el callback `cfg:`/`off:`) de una alerta: 'sup_BUY', 'disp_SELL'..."""
    return f"{tipo}_{operacion}"

def _estado_alerta(u, operacion, tipo, simbolo, unidad, formato):
    alerta = u['alertas'].get((operacion, tipo))
    return f"✅ {simbolo} {formato(alerta['limite'])} {unidad}" if alerta and alerta['activa'] else "❌ desactivada"

def _alerta_precio(operacion, tipo):
    t = _TIPOS_PRECIO[tipo]
    otro = _TIPOS_PRECIO[t["otra"]]
    lado = LADO[operacion]
    nombre, nombre_otra = t["etiqueta"].lower(), otro["etiqueta"].lower()
    es_superior = tipo == "sup"

    def coherencia(v, u):
        # La superior debe quedar por encima de la inferior (del mismo lado); si no, saltarían las dos a la vez
        otra = u['alertas'].get((operacion, t["otra"]))
        if not otra or not otra['activa']:
            return None
        if es_superior and v <= otra['limite']:
            posicion, ayuda = "por encima", "más alto"
        elif not es_superior and v >= otra['limite']:
            posicion, ayuda = "por debajo", "más bajo"
        else:
            return None
        return (f"La alerta de {lado} «{nombre}» debe quedar *{posicion}* de tu alerta de {lado} «{nombre_otra}» "
                f"({otra['limite']:.2f} BOB); si no, saltarían a la vez. Elige un precio {ayuda} o desactiva la otra.")

    return {
        "coherencia": coherencia,
        "vista": "alertas", "alerta": (operacion, tipo),
        "etiqueta": f"{t['icono']} {t['etiqueta']}",
        "boton": f"{ICONOS_OPERACION[operacion]} {lado.capitalize()} · {t['icono']} {t['etiqueta']}",
        "titulo": f"{t['icono']} *Alerta de {lado} · {t['etiqueta']}*",
        "pregunta": (f"Escribe el precio en BOB (ej. 11.90). Te aviso una sola vez cuando el promedio de "
                     f"{lado} ({NOMBRES_OPERACION[operacion]}) sea {nombre} a ese precio."),
        "actual": lambda u: _estado_alerta(u, operacion, tipo, t["simbolo"], "BOB", lambda x: f"{x:.2f}"),
        "validar": _validar_precio,
        "guardar": lambda cid, v: database.guardar_alerta(cid, operacion, tipo, v),
        "exito": lambda v: f"✅ Alerta de {lado} {nombre} *activada* ({t['simbolo']} {v:.2f} BOB).",
        "exito_off": f"🚫 Alerta de {lado} {nombre} *desactivada*.",
    }

def _alerta_disponible(operacion):
    lado = LADO[operacion]
    cantidad = TEXTO_CANTIDAD[operacion]
    return {
        "vista": "alertas", "alerta": (operacion, "disp"),
        "etiqueta": f"📦 USDT {cantidad}",
        "boton": f"{ICONOS_OPERACION[operacion]} {lado.capitalize()} · 📦 USDT {cantidad}",
        "titulo": f"📦 *Alerta de USDT {cantidad} · {lado}*",
        "pregunta": (f"Escribe la cantidad mínima de USDT. Te aviso una sola vez cuando el promedio de USDT "
                     f"{cantidad} en {lado} ({NOMBRES_OPERACION[operacion]}) baje de ese valor."),
        "actual": lambda u: _estado_alerta(u, operacion, "disp", "≤", "USDT", _num),
        "validar": lambda v: None if 0 < v <= DISPONIBLE_MAX else f"Cantidad fuera de rango (máximo {DISPONIBLE_MAX:,} USDT).",
        "guardar": lambda cid, v: database.guardar_alerta(cid, operacion, "disp", v),
        "exito": lambda v: f"✅ Alerta de USDT {cantidad} en {lado} *activada* (≤ {_num(v)} USDT).",
        "exito_off": f"🚫 Alerta de USDT {cantidad} en {lado} *desactivada*.",
    }

AJUSTES = {
    "top": {
        "vista": "ajustes",
        "titulo": "🔢 *Cantidad de anuncios (Top)*",
        "pregunta": "¿Cuántos anuncios quieres promediar? Escribe un número entero del 1 al 15.",
        "actual": lambda u: f"Top {u['top_anuncios']}",
        "validar": lambda v: None if v.is_integer() and 1 <= v <= 15 else "Debe ser un número entero del 1 al 15.",
        # bot_iniciado=2: el motor fija el precio base nuevo sin enviar un aviso
        "guardar": lambda cid, v: database.actualizar_valores(cid, {'top_anuncios': int(v), 'bot_iniciado': 2}),
        "exito": lambda v: f"✅ Promedio configurado al Top *{int(v)}*.",
    },
    "umbral": {
        "vista": "ajustes",
        "titulo": "📏 *Umbral de cambio*",
        "pregunta": f"Escribe cuántos BOB debe moverse el promedio para avisarte (de {UMBRAL_MIN} a {UMBRAL_MAX}). Ej: 0.05",
        "actual": lambda u: f"{_num(u['umbral_diferencia'])} BOB",
        "validar": lambda v: None if UMBRAL_MIN <= v <= UMBRAL_MAX else f"Fuera de rango (de {UMBRAL_MIN} a {UMBRAL_MAX} BOB).",
        "guardar": lambda cid, v: database.actualizar_valor(cid, 'umbral_diferencia', v),
        "exito": lambda v: f"✅ Umbral actualizado a *{_num(v)} BOB*.",
    },
}

# Las seis alertas (compra y venta a la vez): claves 'sup_BUY', 'inf_BUY', 'disp_BUY', 'sup_SELL'...
for _operacion_ in NOMBRES_OPERACION:
    for _tipo_ in database.TIPOS_ALERTA:
        AJUSTES[_clave_alerta(_operacion_, _tipo_)] = (
            _alerta_disponible(_operacion_) if _tipo_ == "disp" else _alerta_precio(_operacion_, _tipo_))
# Orden en pantalla: primero las de compra, luego las de venta
ORDEN_ALERTAS = tuple(_clave_alerta(op, tipo) for op in NOMBRES_OPERACION for tipo in database.TIPOS_ALERTA)


# ======================================================================================
# Vistas (cada una devuelve (texto, teclado) a partir de la fila del usuario)
# ======================================================================================

def _texto_bienvenida():
    return (
        "👋 *¡Bienvenido a Angie Alerta USDT!*\n\n"
        "Te aviso de los cambios del precio del *USDT* para *comprar o vender* en el mercado *P2P de Binance* "
        "(Bolivia, BOB) y te muestro el tipo de cambio oficial del *BCB*.\n\n"
        f"*Comandos*\n{_texto_comandos()}\n\n"
        "Puedes usar el botón *Menú* (abajo a la izquierda) o los botones de aquí abajo.\n\n"
        f"ℹ️ {ATRIBUCION}"
    )

def _teclado_menu():
    return _teclado(
        [_boton("💵 Precio ahora", "nav:precio"), _boton("🏦 Cambio BCB", "nav:bcb")],
        [_boton("🔔 Mis alertas", "nav:alertas"), _boton("⚙️ Ajustes", "nav:ajustes")],
        [_boton("❓ Ayuda", "nav:ayuda"), _boton("ℹ️ Acerca de", "nav:acerca")],
        _fila_donar(),
    )

def _vista_menu(u):
    activas = sum(1 for alerta in u['alertas'].values() if alerta['activa'])
    texto = (
        "🏠 *Panel principal*\n\n"
        f"Promedio del *Top {u['top_anuncios']}* · aviso de cambio de {_texto_operacion(u)} cada ±{_num(u['umbral_diferencia'])} BOB\n"
        f"🔔 Alertas activas: *{activas}* de {len(ORDEN_ALERTAS)}\n\n"
        "Elige una opción:"
    )
    return texto, _teclado_menu()

def _vista_alertas(u):
    def activa(clave):
        alerta = u['alertas'].get(AJUSTES[clave]["alerta"])
        return bool(alerta and alerta['activa'])

    secciones = []
    for operacion in NOMBRES_OPERACION:
        claves = [c for c in ORDEN_ALERTAS if AJUSTES[c]["alerta"][0] == operacion]
        lineas = "\n".join(f"{AJUSTES[c]['etiqueta']}: {AJUSTES[c]['actual'](u)}" for c in claves)
        secciones.append(f"*{ICONOS_OPERACION[operacion]} {NOMBRES_OPERACION[operacion]}*\n{lineas}")
    texto = (
        "🔔 *Mis alertas*\n"
        "Las de compra y las de venta funcionan a la vez. Cada una se dispara una sola vez y luego se desactiva.\n\n"
        + "\n\n".join(secciones) +
        "\n\nToca una para configurarla:"
    )
    filas = [[_boton(AJUSTES[c]["boton"] + (" ✅" if activa(c) else ""), f"cfg:{c}")] for c in ORDEN_ALERTAS]
    return texto, _teclado(*filas, _fila_volver())

def _vista_ajustes(u):
    texto = (
        "⚙️ *Ajustes*\n\n"
        f"🔢 Promedio: *Top {u['top_anuncios']}* anuncios\n"
        f"📏 Aviso de cambio: *{_num(u['umbral_diferencia'])} BOB* sobre *{_texto_operacion(u)}*\n\n"
        "El aviso de cambio sigue el precio de una sola operación; elígela abajo. "
        "Tus alertas de compra y de venta funcionan siempre, sin importar esta opción.\n\n"
        "Toca un ajuste para cambiarlo:"
    )
    actual = _operacion(u)
    return texto, _teclado(
        [_boton(f"{ICONOS_OPERACION[op]} {NOMBRES_OPERACION[op]}" + (" ✅" if op == actual else ""), f"op:{op}")
         for op in NOMBRES_OPERACION],
        [_boton(f"🔢 Cantidad de anuncios (Top {u['top_anuncios']})", "cfg:top")],
        [_boton(f"📏 Umbral de cambio ({_num(u['umbral_diferencia'])} BOB)", "cfg:umbral")],
        _fila_volver(),
    )

def _vista_precio(u):
    teclado = _teclado([_boton("🔄 Actualizar", "nav:precio"), _boton("⬅️ Menú", "nav:menu")])
    # Cada lado se lee de una sola vez: precios, disponibles y hora son del mismo ciclo
    lecturas = {op: database.cache_binance.get(op) for op in NOMBRES_OPERACION}
    lecturas = {op: l for op, l in lecturas.items() if l is not None and len(l.precios) > 0}
    if not lecturas:
        return "💵 *Promedio actual*\n\n⏳ Recolectando datos, intenta en unos segundos.", teclado

    secciones = []
    for operacion in NOMBRES_OPERACION:
        encabezado = f"*{ICONOS_OPERACION[operacion]} {NOMBRES_OPERACION[operacion]}*"
        lectura = lecturas.get(operacion)
        if lectura is None:
            secciones.append(f"{encabezado}\n⏳ Aún sin datos.")
            continue
        n_real = min(u['top_anuncios'], len(lectura.precios))
        promedio = sum(lectura.precios[:n_real]) / n_real
        disp_prom = sum(lectura.disponibles[:n_real]) / n_real
        secciones.append(
            f"{encabezado} (Top {n_real})\n"
            f"Precio: `{promedio:.2f} BOB`\n"
            f"{ETIQUETA_CANTIDAD[operacion]}: `{disp_prom:.2f} USDT`")

    texto = (
        "💵 *Promedio actual*\n\n" + "\n\n".join(secciones) + "\n\n"
        + _texto_antiguedad(
            min(l.hora for l in lecturas.values()), BINANCE_VENCE_MIN,
            "Binance no responde: estos precios pueden no ser reales y tus alertas están en pausa.")
    )
    return texto, teclado

def _vista_bcb(u):
    teclado = _teclado([_boton("🔄 Actualizar", "nav:bcb"), _boton("⬅️ Menú", "nav:menu")])
    lectura = database.cache_bcb
    if lectura is None:
        return "🏦 *Tipo de Cambio Oficial (BCB)*\n\n⏳ Conectando con el Banco Central. Intenta en unos segundos.", teclado
    texto = (
        f"🏦 *Tipo de Cambio Oficial (BCB)*\n\nVenta: `{lectura.venta} BOB`\n\n"
        + _texto_antiguedad(
            lectura.hora, BCB_VENCE_MIN,
            "No se pudo leer el BCB hace rato: este valor puede haber cambiado.")
    )
    return texto, teclado

def _vista_ayuda(u):
    texto = (
        "❓ *Ayuda*\n\n"
        "*¿Qué hace este bot?*\n"
        "Revisa cada minuto el mercado P2P de Binance (USDT/BOB) y te avisa por Telegram.\n\n"
        "*Comprar y vender*\n"
        "• 🛒 Comprar USDT: precios de quienes venden USDT (lo que pagarías tú). Conviene que baje.\n"
        "• 💰 Vender USDT: precios de quienes compran USDT (lo que recibirías tú). Conviene que suba.\n"
        "Puedes tener alertas de compra y de venta a la vez; el bot vigila los dos precios.\n\n"
        "*Promedio (Top N)*\n"
        "Todo se calcula con el promedio de los primeros N anuncios (de 1 a 15). Los anuncios dudosos "
        "(con muy poco USDT o precios fuera de lo normal) se descartan.\n\n"
        "*Aviso de cambio*\n"
        "Te escribo cuando el promedio se mueve al menos el umbral que elijas respecto al último aviso. "
        "Sigue el precio de una sola operación (compra o venta), que eliges en Ajustes.\n\n"
        "*Alertas* (para compra y para venta)\n"
        "• Mayor o igual: cuando el promedio llega a tu precio o lo supera.\n"
        "• Menor o igual: cuando baja a tu precio o menos.\n"
        "• USDT disponible: cuando el USDT promedio baja de tu cantidad "
        "(al vender, es el USDT que piden los compradores).\n"
        "Cada alerta se dispara una sola vez y luego se desactiva. En cada operación, la de «mayor o igual» "
        "debe quedar por encima de la de «menor o igual».\n\n"
        f"*Comandos*\n{_texto_comandos()}"
    )
    return texto, _teclado(_fila_volver())

def _vista_acerca(u):
    texto = (
        "ℹ️ *Acerca de*\n\n"
        "*Angie Alerta USDT* es un bot gratuito y de código abierto (licencia AGPL-3.0).\n\n"
        "Los datos vienen del mercado P2P de Binance y de la página del BCB. Son solo referenciales "
        "y no constituyen asesoría financiera.\n\n"
        f"{ATRIBUCION}"
    )
    return texto, _teclado(
        _fila_donar(),
        [InlineKeyboardButton("💻 Código fuente", url=REPO_URL)],
        _fila_volver(),
    )

_VISTAS = {
    "menu": _vista_menu, "alertas": _vista_alertas, "ajustes": _vista_ajustes,
    "precio": _vista_precio, "bcb": _vista_bcb, "ayuda": _vista_ayuda, "acerca": _vista_acerca,
}

def _construir_vista(nombre, chat_id, aviso=""):
    usuario = _cargar_usuario(chat_id)
    texto, teclado = _VISTAS.get(nombre, _vista_menu)(usuario)
    return (f"{aviso}\n\n{texto}" if aviso else texto), teclado


# ======================================================================================
# Envío: editar el mismo mensaje al navegar (como @BotFather) en vez de llenar el chat
# ======================================================================================

def _mostrar(chat_id, texto, teclado, message_id=None):
    """Edita el mensaje `message_id`; si no se puede, envía uno nuevo. Devuelve el id del mensaje mostrado."""
    if message_id:
        try:
            bot.edit_message_text(texto, chat_id, message_id, reply_markup=teclado, parse_mode="Markdown")
            return message_id
        except ApiTelegramException as e:
            if "message is not modified" in str(e):
                return message_id   # nada que cambiar (p. ej. "Actualizar" sin datos nuevos)
            # mensaje borrado o muy viejo: se envía uno nuevo
    return bot.send_message(chat_id, texto, reply_markup=teclado, parse_mode="Markdown").message_id

def _ir_a(nombre, chat_id, message_id=None, aviso=""):
    texto, teclado = _construir_vista(nombre, chat_id, aviso)
    return _mostrar(chat_id, texto, teclado, message_id)


# ======================================================================================
# Comandos
# ======================================================================================

@bot.message_handler(commands=['start'])
def comando_start(message):
    database.registrar_usuario(message.chat.id)
    bot.send_message(message.chat.id, _texto_bienvenida(), reply_markup=_teclado_menu(), parse_mode="Markdown")

def _comando_vista(nombre):
    def manejador(message):
        database.registrar_usuario(message.chat.id)
        _ir_a(nombre, message.chat.id)
    return manejador

for _comando, _vista in (("menu", "menu"), ("precio", "precio"), ("bcb", "bcb"), ("ayuda", "ayuda"), ("acerca", "acerca")):
    bot.message_handler(commands=[_comando])(_comando_vista(_vista))


# ======================================================================================
# Botones
# ======================================================================================

# Botones de mensajes antiguos (antes de este diseño) que siguen en los chats de los usuarios.
_BOTONES_ANTIGUOS = {
    "cmd_top": "cfg:top", "cmd_umbral": "cfg:umbral", "cmd_sup": "cfg:sup_BUY", "cmd_inf": "cfg:inf_BUY",
    "cmd_disp": "cfg:disp_BUY", "cmd_showprom": "nav:precio", "cmd_bcb": "nav:bcb",
    # Botones de la versión con una sola operación (antes de las alertas de compra y venta a la vez)
    "cfg:sup": "cfg:sup_BUY", "cfg:inf": "cfg:inf_BUY", "cfg:disp": "cfg:disp_BUY",
    "off:sup": "off:sup_BUY", "off:inf": "off:inf_BUY", "off:disp": "off:disp_BUY",
}

@bot.callback_query_handler(func=lambda call: True)
def callback_botones(call):
    try:
        bot.answer_callback_query(call.id)   # quita el relojito del botón
    except ApiTelegramException:
        pass   # botón muy viejo: igual se atiende
    if call.message is None:
        return

    chat_id = call.message.chat.id
    message_id = call.message.message_id
    dato = _BOTONES_ANTIGUOS.get(call.data, call.data or "")
    accion, _, clave = dato.partition(":")

    if accion == "nav" and clave in _VISTAS:
        bot.clear_step_handler_by_chat_id(chat_id)   # navegar cancela cualquier "escribe el valor" pendiente
        _ir_a(clave, chat_id, message_id)
    elif accion == "cfg" and clave in AJUSTES:
        _pedir_valor(chat_id, message_id, clave)
    elif accion == "op" and clave in NOMBRES_OPERACION:
        bot.clear_step_handler_by_chat_id(chat_id)
        _cambiar_operacion(chat_id, message_id, clave)
    elif accion == "off" and clave in AJUSTES and "alerta" in AJUSTES[clave]:
        bot.clear_step_handler_by_chat_id(chat_id)
        database.desactivar_alerta(chat_id, *AJUSTES[clave]["alerta"])
        _ir_a(AJUSTES[clave]["vista"], chat_id, message_id, AJUSTES[clave]["exito_off"])


def _cambiar_operacion(chat_id, message_id, operacion):
    """Elige sobre qué operación (compra o venta) va el aviso de cambio. Las alertas no se tocan."""
    usuario = _cargar_usuario(chat_id)

    if usuario.get('operacion') == operacion:
        _ir_a("ajustes", chat_id, message_id)
        return

    valores = {'operacion': operacion}
    if usuario['bot_iniciado'] == 1:
        valores['bot_iniciado'] = 2   # el motor fija el precio base del nuevo lado sin enviar un aviso
    database.actualizar_valores(chat_id, valores)
    _ir_a("ajustes", chat_id, message_id,
          f"✅ El aviso de cambio ahora sigue: *{ICONOS_OPERACION[operacion]} {NOMBRES_OPERACION[operacion]}*.")


# ======================================================================================
# Pantallas de "escribe el valor"
# ======================================================================================

def _pedir_valor(chat_id, message_id, clave):
    cfg = AJUSTES[clave]
    usuario = _cargar_usuario(chat_id)

    texto = f"{cfg['titulo']}\n\n{cfg['pregunta']}\n\n_Actual: {cfg['actual'](usuario)}_"
    fila = []
    if "alerta" in cfg:
        fila.append(_boton("🚫 Desactivar", f"off:{clave}"))
    fila.append(_boton("✖️ Cancelar", f"nav:{cfg['vista']}"))
    id_pantalla = _mostrar(chat_id, texto, _teclado(fila), message_id)
    bot.register_next_step_handler_by_chat_id(chat_id, _recibir_valor, id_pantalla, clave)

def _recibir_valor(message, id_pantalla, clave):
    chat_id = message.chat.id
    cfg = AJUSTES[clave]

    if _es_comando(message):
        # El usuario cambió de idea y escribió un comando: se atiende en vez de tomarlo como valor
        bot.process_new_messages([message])
        return

    val = leer_numero(message)
    if val is not None and "alerta" in cfg and val <= 0:   # escribir 0 también desactiva
        database.desactivar_alerta(chat_id, *cfg["alerta"])
        _terminar(chat_id, id_pantalla, cfg, cfg["exito_off"])
        return

    error = "Escribe solo un número (ej. 11.90)." if val is None else cfg["validar"](val)
    if val is not None and not error and "coherencia" in cfg:
        error = cfg["coherencia"](val, _cargar_usuario(chat_id))
    if error:
        bot.send_message(
            chat_id, f"❌ {error}\nIntenta de nuevo o pulsa *Cancelar*.",
            reply_markup=_teclado([_boton("✖️ Cancelar", f"nav:{cfg['vista']}")]), parse_mode="Markdown")
        bot.register_next_step_handler_by_chat_id(chat_id, _recibir_valor, id_pantalla, clave)
        return

    cfg["guardar"](chat_id, val)
    _terminar(chat_id, id_pantalla, cfg, cfg["exito"](val))

def _terminar(chat_id, id_pantalla, cfg, aviso):
    """Muestra el resultado debajo del mensaje del usuario y retira la pantalla de 'escribe el valor'."""
    _ir_a(cfg["vista"], chat_id, aviso=aviso)
    try:
        bot.delete_message(chat_id, id_pantalla)
    except ApiTelegramException:
        pass


# ======================================================================================
# Texto libre sin sentido (solo en chats privados, para no molestar en grupos)
# ======================================================================================

@bot.message_handler(func=lambda m: m.chat.type == "private", content_types=['text'])
def mensaje_no_entendido(message):
    bot.send_message(
        message.chat.id, "🤔 No entendí ese mensaje. Usa /menu o el botón *Menú* (abajo a la izquierda).",
        parse_mode="Markdown")


# ======================================================================================
# Arranque
# ======================================================================================

def configurar_perfil():
    """Registra los comandos del botón Menú y los textos del perfil del bot. Un fallo no impide arrancar."""
    try:
        bot.set_my_commands([BotCommand(comando, descripcion) for comando, descripcion in COMANDOS])
        bot.set_chat_menu_button(menu_button=MenuButtonCommands())   # botón "Menú" con la lista de comandos
        bot.set_my_short_description("Alertas del USDT en Binance P2P (Bolivia) y cambio oficial del BCB. Gratis y de código abierto.")
        bot.set_my_description(
            "Te aviso de los cambios del precio del USDT en el mercado P2P de Binance (Bolivia) "
            "y te muestro el tipo de cambio oficial del BCB.\n\nToca INICIAR para empezar.")
    except Exception as e:
        print(f"No se pudo configurar el perfil del bot: {e}")

def iniciar_bot():
    configurar_perfil()
    print("Conectado a Telegram. Escuchando mensajes...")
    # skip_pending: al arrancar se ignoran los mensajes/botones acumulados mientras el bot estaba apagado
    # (se ejecutarían de golpe y fuera de contexto). Solo afecta al arranque, no a las reconexiones.
    bot.infinity_polling(skip_pending=True)
