"""Ingesta de juguete: MQTT -> MySQL.

Se suscribe a las lecturas de las heladeras (ver docs/contrato-mqtt.md) y
guarda cada una, tal cual llega, en la tabla `lecturas`.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import pymysql
from dotenv import load_dotenv

# --- Configuración ---
# Las contraseñas salen del mismo .env que usa docker compose.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TEMA = "ifibyne/heladeras/+/lectura"

def conectar_db():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user="ingesta",
        password=os.environ["MYSQL_PASSWORD"],
        database="desafio80",
        autocommit=True,
    )


db = conectar_db()


def guardar(heladera_id, temp_c, ts):
    global db
    try:
        db.ping()
    except pymysql.Error:  # MySQL se reinició: abrir una conexión nueva
        db = conectar_db()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO lecturas (heladera_id, temp_c, ts) VALUES (%s, %s, %s)",
            (heladera_id, temp_c, ts),
        )


def interpretar(msg):
    """Devuelve (heladera_id, temp_c, ts) o lanza una excepción si el mensaje está mal."""
    heladera_id = msg.topic.split("/")[2]
    datos = json.loads(msg.payload)
    temp_c = datos["temp_c"]
    if temp_c is not None:
        temp_c = float(temp_c)
    if datos.get("ts") is not None:
        ts = datetime.fromtimestamp(datos["ts"], timezone.utc)
    else:
        ts = datetime.now(timezone.utc)
    return heladera_id, temp_c, ts.replace(tzinfo=None)  # MySQL guarda UTC sin zona


# --- MQTT ---
def al_conectar(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"El broker rechazó la conexión: {reason_code}")
        return
    # Suscribirse acá (y no una sola vez al arrancar) hace que al reconectar
    # se vuelva a suscribir solo.
    client.subscribe(TEMA, qos=1)
    print(f"Conectado a {MQTT_HOST}:{MQTT_PORT}, escuchando {TEMA}")


def al_recibir(client, userdata, msg):
    # Un mensaje malo nunca tiene que tirar abajo la ingesta: se avisa y se sigue.
    try:
        heladera_id, temp_c, ts = interpretar(msg)
    except (ValueError, KeyError, TypeError, IndexError, OverflowError, OSError) as e:
        print(f"IGNORADO {msg.topic}: {e!r} -> {msg.payload[:80]!r}")
        return
    try:
        guardar(heladera_id, temp_c, ts)
    except pymysql.MySQLError as e:
        print(f"ERROR al guardar {heladera_id}: {e}")
        return
    temp = "null" if temp_c is None else f"{temp_c:.2f}"
    print(f"{heladera_id:<12} {temp:>8}  {ts:%Y-%m-%d %H:%M:%S}")


# Nombre fijo + clean_session=False = sesión persistente: si la ingesta se cae,
# el broker guarda en cola los mensajes QoS 1 y los entrega al volver.
cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ingesta", clean_session=False)
cliente.on_connect = al_conectar
cliente.on_message = al_recibir
cliente.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

try:
    cliente.loop_forever()  # atiende mensajes y reconecta solo si se corta
except KeyboardInterrupt:
    print("Cortando la ingesta.")
finally:
    cliente.disconnect()
    db.close()
