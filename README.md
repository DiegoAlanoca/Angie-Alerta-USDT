<div align="center">

```
         .--.               .--.
        ( () )_____________( () )
         '--'               '--'
       /                         \
       |      o           o      |
       |    .---.   ^   .---.    |
       |   (     ) \_/ (     )   |
       \    '---'  |_|  '---'    /
        '.      .-------.      .'
          '-.___( $USDT )___.-'
                '-------'

    _    _   _  ____ ___ _____ 
   / \  | \ | |/ ___|_ _| ____|
  / _ \ |  \| | |  _ | ||  _|  
 / ___ \| |\  | |_| || || |___ 
/_/   \_\_| \_|\____|___|_____|
   _   _         _          _   _ ___ ___ _____ 
  /_\ | |___ _ _| |_ __ _  | | | / __|   \_   _|
 / _ \| / -_) '_|  _/ _` | | |_| \__ \ |) || |  
/_/ \_\_\___|_|  \__\__,_|  \___/|___/___/ |_|
```

</div>

# Angie Alerta USDT

Bot de Telegram **gratuito y de código abierto** que envía alertas del mercado **P2P de Binance** (USDT/BOB, Bolivia) y muestra el tipo de cambio oficial del **Banco Central de Bolivia (BCB)**.

> Basado en "Angie Alerta USDT" de Diego Ronald Alanoca Avircata
> https://github.com/DiegoAlanoca/Angie-Alerta-USDT
>
> Based on "Angie Alerta USDT" by Diego Ronald Alanoca Avircata
> https://github.com/DiegoAlanoca/Angie-Alerta-USDT

## Funciones

- Promedio del Top N de anuncios P2P (BUY, USDT/BOB), configurable por usuario (1 a 15).
- Alerta por variación (umbral de diferencia).
- Alerta de precio mayor o igual / menor o igual a un límite (un solo disparo).
- Alerta de USDT disponible bajo un mínimo.
- Consulta del tipo de cambio oficial del BCB.

## Requisitos

- Python 3.10 o superior (desarrollado con 3.14).
- Un bot de Telegram creado con [@BotFather](https://t.me/BotFather).

## Instalación

```
git clone https://github.com/DiegoAlanoca/Angie-Alerta-USDT.git
cd Angie-Alerta-USDT
pip install -r requirements.txt
```

Copia la plantilla de variables de entorno y complétala:

```
# Windows
copy .env.example .env
# Linux / macOS
cp .env.example .env
```

Edita `.env`:

- `TELEGRAM_TOKEN`: token que te da @BotFather.
- `ADMIN_CHAT_ID`: tu chat_id de Telegram.

Ejecuta:

```
python main.py
```

En Telegram escribe `/menu` para configurar tus alertas.

## Estructura

| Archivo | Función |
|---|---|
| `main.py` | Punto de entrada; hilos de alertas (60 s) y BCB (300 s) y polling de Telegram |
| `binance_api.py` | Consulta de anuncios P2P de Binance |
| `bcb_api.py` | Lectura del tipo de cambio del BCB |
| `telegram_bot.py` | Menú y comandos del bot |
| `database.py` | SQLite (`usuarios.db`) y caché en memoria |
| `config.py` | Carga de variables desde `.env` |

## Aviso

Este proyecto usa un endpoint **no oficial** de Binance P2P y lee la página pública del BCB. No tiene relación ni respaldo de Binance, del BCB ni de Telegram, y puede dejar de funcionar si cambian sus servicios. La información es solo referencial y **no constituye asesoría financiera**.

## Licencia

[GNU AGPL-3.0](LICENSE) © 2026 Diego Ronald Alanoca Avircata, con término adicional de atribución (sección 7(b)) descrito en [NOTICE](NOTICE).

Si ofreces una versión modificada del bot a otros usuarios por red, debes publicar su código fuente bajo la misma licencia y conservar la atribución de arriba en tu README y en la interfaz del bot.

## Contribuir y apoyar

Se aceptan issues y pull requests. El proyecto se mantiene con donaciones voluntarias vía Binance Pay (próximamente en el bot).
