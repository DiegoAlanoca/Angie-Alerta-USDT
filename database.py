# Angie Alerta USDT
# Copyright (C) 2026 Diego Ronald Alanoca Avircata
# SPDX-License-Identifier: AGPL-3.0-only
# Ver LICENSE y NOTICE (incluye término adicional de atribución).

import sqlite3

DB_NAME = "usuarios.db"

# --- CACHÉ EN MEMORIA ---
cache_precios = []
cache_disponibles = []
# NUEVO: Caché para BCB
cache_bcb_venta = 0.0
cache_bcb_hora = ""

def conectar():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def iniciar_base_datos():
    conexion = conectar()
    cursor = conexion.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            chat_id INTEGER PRIMARY KEY,
            umbral_diferencia REAL DEFAULT 0.01,
            precio_anterior REAL DEFAULT 0.0,
            bot_iniciado INTEGER DEFAULT 0,
            limite_superior REAL DEFAULT 0.0,
            limite_inferior REAL DEFAULT 0.0,
            alerta_sup_activada INTEGER DEFAULT 0,
            alerta_inf_activada INTEGER DEFAULT 0,
            limite_disponible REAL DEFAULT 0.0,
            alerta_disp_activada INTEGER DEFAULT 0,
            top_anuncios INTEGER DEFAULT 6
        )
    ''')
    conexion.commit()
    conexion.close()

def registrar_usuario(chat_id):
    conexion = conectar()
    cursor = conexion.cursor()
    cursor.execute('INSERT OR IGNORE INTO usuarios (chat_id) VALUES (?)', (chat_id,))
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