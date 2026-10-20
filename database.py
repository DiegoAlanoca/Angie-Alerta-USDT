# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

import os
import sqlite3
from collections import namedtuple

# Ruta absoluta junto al código: no depende del directorio desde el que se lance el bot
# (systemd, cron, etc.). Con una ruta relativa, otro directorio crearía una base vacía.
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usuarios.db")

# --- CACHÉ EN MEMORIA ---
# Cada caché es UNA sola tupla inmutable que los motores reemplazan de golpe: así quien la lee
# nunca ve precios de un ciclo con disponibles u hora de otro. Léela una vez en una variable local.
# `hora` es un datetime con zona de Bolivia. `None` = aún no hubo ninguna lectura exitosa.
LecturaBinance = namedtuple("LecturaBinance", "precios disponibles hora")
LecturaBCB = namedtuple("LecturaBCB", "venta hora")
# cache_binance guarda una lectura por operación ("BUY"/"SELL"); cada clave se reemplaza entera.
cache_binance = {"BUY": None, "SELL": None}
cache_bcb = None

OPERACION_POR_DEFECTO = "BUY"
# Tipos de alerta de un solo disparo: precio superior, precio inferior y USDT disponible
TIPOS_ALERTA = ("sup", "inf", "disp")

# Umbral (BOB) con el que nace cada usuario. Con 0.01 el promedio de unos pocos anuncios cambia
# casi cada minuto y el bot envía un mensaje por ciclo; 0.05 avisa solo de movimientos que importan.
UMBRAL_POR_DEFECTO = 0.05

def conectar():
    # timeout: si otro hilo está escribiendo, espera hasta 30 s en vez de fallar con "database is locked"
    conexion = sqlite3.connect(DB_NAME, timeout=30, check_same_thread=False)
    conexion.execute("PRAGMA synchronous = NORMAL")   # seguro con WAL y mucho menos fsync en el disco de la VPS
    return conexion

def iniciar_base_datos():
    conexion = conectar()
    # WAL: lectores y escritor no se bloquean entre sí (hilos del motor y del bot). Es persistente.
    conexion.execute("PRAGMA journal_mode = WAL")
    cursor = conexion.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            chat_id INTEGER PRIMARY KEY,
            umbral_diferencia REAL DEFAULT 0.05,
            precio_anterior REAL DEFAULT 0.0,
            bot_iniciado INTEGER DEFAULT 0,
            top_anuncios INTEGER DEFAULT 6,
            operacion TEXT DEFAULT 'BUY'
        )
    ''')
    # Una fila por alerta configurada: (usuario, operación, tipo). 'activa' = 0 conserva el límite
    # para mostrarlo, pero el motor la ignora. Hasta 6 por usuario: {BUY, SELL} x {sup, inf, disp}.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alertas (
            chat_id INTEGER NOT NULL,
            operacion TEXT NOT NULL CHECK (operacion IN ('BUY', 'SELL')),
            tipo TEXT NOT NULL CHECK (tipo IN ('sup', 'inf', 'disp')),
            limite REAL NOT NULL,
            activa INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (chat_id, operacion, tipo)
        )
    ''')
    # CREATE TABLE IF NOT EXISTS no altera bases ya creadas: columnas nuevas se añaden aquí
    columnas = {fila[1] for fila in cursor.execute("PRAGMA table_info(usuarios)")}
    if 'operacion' not in columnas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN operacion TEXT DEFAULT 'BUY'")
    conexion.commit()
    conexion.close()

def registrar_usuario(chat_id):
    conexion = conectar()
    cursor = conexion.cursor()
    # El umbral se pasa explícito: las bases creadas antes conservan el DEFAULT 0.01 en su esquema
    cursor.execute('INSERT OR IGNORE INTO usuarios (chat_id, umbral_diferencia) VALUES (?, ?)',
                   (chat_id, UMBRAL_POR_DEFECTO))
    conexion.commit()
    conexion.close()

def obtener_usuario(chat_id):
    conexion = conectar()
    conexion.row_factory = sqlite3.Row 
    cursor = conexion.cursor()
    cursor.execute('SELECT * FROM usuarios WHERE chat_id = ?', (chat_id,))
    fila = cursor.fetchone()
    conexion.close()
    return dict(fila) if fila else None

def obtener_todos_los_usuarios():
    conexion = conectar()
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    cursor.execute('SELECT * FROM usuarios')
    filas = cursor.fetchall()
    conexion.close()
    return [dict(fila) for fila in filas]

def actualizar_valor(chat_id, columna, valor):
    conexion = conectar()
    cursor = conexion.cursor()
    consulta = f"UPDATE usuarios SET {columna} = ? WHERE chat_id = ?"
    cursor.execute(consulta, (valor, chat_id))
    conexion.commit()
    conexion.close()

def actualizar_valores(chat_id, valores):
    """Actualiza varias columnas de un usuario en UN solo UPDATE (atómico, un solo commit).

    `valores` es un dict {columna: valor}. Igual que actualizar_valor(): solo nombres de
    columna internos, nunca texto que venga del usuario.
    """
    if not valores or not all(columna.isidentifier() for columna in valores):
        raise ValueError(f"Columnas inválidas: {list(valores)}")
    asignaciones = ", ".join(f"{columna} = ?" for columna in valores)
    conexion = conectar()
    try:
        conexion.execute(
            f"UPDATE usuarios SET {asignaciones} WHERE chat_id = ?",
            (*valores.values(), chat_id)
        )
        conexion.commit()
    finally:
        conexion.close()

# --- ALERTAS (tabla `alertas`) ---
# `operacion` es "BUY" o "SELL" y `tipo` es "sup", "inf" o "disp". Los valores se pasan como
# parámetros de la consulta (la tabla además los restringe con CHECK).

def obtener_alertas(chat_id):
    """Alertas del usuario como {(operacion, tipo): {'limite': float, 'activa': bool}}."""
    conexion = conectar()
    try:
        filas = conexion.execute(
            'SELECT operacion, tipo, limite, activa FROM alertas WHERE chat_id = ?', (chat_id,)
        ).fetchall()
    finally:
        conexion.close()
    return {(op, tipo): {'limite': limite, 'activa': bool(activa)} for op, tipo, limite, activa in filas}

def guardar_alerta(chat_id, operacion, tipo, limite):
    """Crea o reconfigura una alerta y la deja activa (un solo UPSERT atómico)."""
    conexion = conectar()
    try:
        conexion.execute(
            'INSERT INTO alertas (chat_id, operacion, tipo, limite, activa) VALUES (?, ?, ?, ?, 1) '
            'ON CONFLICT (chat_id, operacion, tipo) DO UPDATE SET limite = excluded.limite, activa = 1',
            (chat_id, operacion, tipo, limite)
        )
        conexion.commit()
    finally:
        conexion.close()

def desactivar_alerta(chat_id, operacion, tipo):
    conexion = conectar()
    try:
        conexion.execute(
            'UPDATE alertas SET activa = 0 WHERE chat_id = ? AND operacion = ? AND tipo = ?',
            (chat_id, operacion, tipo)
        )
        conexion.commit()
    finally:
        conexion.close()

def cambiar_alerta(chat_id, operacion, tipo, limite, de, a):
    """Cambia `activa` de `de` a `a` solo si la alerta sigue en ese estado Y con ese mismo límite.

    Es atómico: si el usuario la modificó mientras el motor la evaluaba, no toca nada
    y devuelve False.
    """
    conexion = conectar()
    try:
        cursor = conexion.execute(
            'UPDATE alertas SET activa = ? '
            'WHERE chat_id = ? AND operacion = ? AND tipo = ? AND activa = ? AND limite = ?',
            (a, chat_id, operacion, tipo, de, limite)
        )
        conexion.commit()
        return cursor.rowcount == 1
    finally:
        conexion.close()

def eliminar_usuario(chat_id):
    conexion = conectar()
    try:
        conexion.execute('DELETE FROM alertas WHERE chat_id = ?', (chat_id,))
        conexion.execute('DELETE FROM usuarios WHERE chat_id = ?', (chat_id,))
        conexion.commit()
    finally:
        conexion.close()