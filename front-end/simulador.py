#!/usr/bin/env python3
"""
Simulador MQTT para el panel web de super freezers.

Publica en Mosquitto:
  freezers/config
  freezers/<id>/info
  freezers/<id>/estado
  freezers/<id>/temperatura

Configuración por defecto:
  Broker: 127.0.0.1:1883
  Prefijo de temas: freezers
  20 equipos: eq01 ... eq20

Instalación en Windows (PowerShell):
  py -m pip install paho-mqtt

Ejecución:
  py simulador.py

Detener con Ctrl+C.
"""

import json
import random
import signal
import sys
import time
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print(
        "Falta la biblioteca paho-mqtt. Instalala con:\n"
        "  py -m pip install paho-mqtt",
        file=sys.stderr,
    )
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Configuración: debe coincidir con Mosquitto y config.js del panel web.
# ---------------------------------------------------------------------------
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_USERNAME = ""  # Dejar vacío si Mosquitto permite acceso anónimo local.
MQTT_PASSWORD = ""

TOPIC_BASE = "freezers"
NUM_EQUIPOS = 20
INTERVALO_SEGUNDOS = 2
UMBRAL_ALARMA = -60.0
MARGEN_AVISO = 5.0
CLIENT_ID = "simulador-super-freezers"

# Dos equipos fuera de servicio, uno en aviso y uno en alarma para poder
# comprobar visualmente los distintos estados del panel.
EQUIPOS_FUERA_SERVICIO = {19, 20}
EQUIPO_AVISO = 2
EQUIPO_ALARMA = 1

random.seed()


def publicar(client, topic, payload, retain=False):
    """Publica un mensaje MQTT y avisa si no pudo encolarse."""
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False)

    info = client.publish(topic, payload=payload, qos=0, retain=retain)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        print(f"[ERROR] No se pudo publicar en {topic}: código {info.rc}")
        return False
    return True


def nombre_grupo(numero):
    """Asigna grupos ficticios para identificar los equipos en la demo."""
    grupos = ["Pérez", "Gómez", "Laboratorio A", "Laboratorio B"]
    return grupos[(numero - 1) % len(grupos)]


def publicar_datos_iniciales(client):
    """Publica configuración, metadatos y estado inicial de cada equipo."""
    publicar(
        client,
        f"{TOPIC_BASE}/config",
        {"umbral": UMBRAL_ALARMA, "margen": MARGEN_AVISO},
        retain=True,
    )

    for numero in range(1, NUM_EQUIPOS + 1):
        equipo_id = f"eq{numero:02d}"

        # El panel espera info como JSON: numero, grupo y piso.
        publicar(
            client,
            f"{TOPIC_BASE}/{equipo_id}/info",
            {
                "numero": 59 + numero,
                "grupo": nombre_grupo(numero),
                "piso": 1 + ((numero - 1) % 4),
            },
            retain=True,
        )

        estado = (
            "no funcionando"
            if numero in EQUIPOS_FUERA_SERVICIO
            else "funcionando"
        )
        publicar(
            client,
            f"{TOPIC_BASE}/{equipo_id}/estado",
            estado,
            retain=True,
        )

    print(f"[OK] Metadatos publicados para {NUM_EQUIPOS} equipos.")
    print(f"[OK] Umbral de alarma: {UMBRAL_ALARMA:.1f} °C")
    print(f"[OK] Margen de aviso: {MARGEN_AVISO:.1f} °C")


def temperatura_simulada(numero, tiempo):
    """
    Genera una temperatura ficticia en °C.
    Equipo 1: alarma, por encima de -70 °C.
    Equipo 2: aviso, dentro del margen configurable.
    Equipos 19 y 20: fuera de servicio; no se publican temperaturas nuevas.
    Resto: temperaturas normales próximas a -80 °C.
    """
    if numero == EQUIPO_ALARMA:
        # Mantiene una temperatura insegura para que la alarma sea visible.
        return round(-68.5 + random.uniform(-0.5, 0.5), 1)

    if numero == EQUIPO_AVISO:
        # Entre el umbral y el límite de aviso, según la lógica del panel.
        return round(-73.0 + random.uniform(-0.5, 0.5), 1)

    # Temperaturas normales con una variación lenta y ruido pequeño.
    base = -79.5 + 0.7 * __import__("math").sin(tiempo / 18.0 + numero)
    return round(base + random.uniform(-0.25, 0.25), 1)


def al_conectar(client, userdata, flags, reason_code, properties=None):
    """Callback compatible con paho-mqtt 2.x."""
    try:
        correcto = int(reason_code) == 0
    except (TypeError, ValueError):
        correcto = str(reason_code).lower() in ("success", "0")

    if correcto:
        print(f"[OK] Conectado a Mosquitto en {MQTT_HOST}:{MQTT_PORT}")
        publicar_datos_iniciales(client)
    else:
        print(f"[ERROR] No se pudo conectar a Mosquitto: {reason_code}")


def al_desconectar(client, userdata, disconnect_flags, reason_code, properties=None):
    try:
        codigo = int(reason_code)
    except (TypeError, ValueError):
        codigo = reason_code
    if codigo != 0:
        print(f"[AVISO] Se perdió la conexión con Mosquitto: {reason_code}")


def main():
    # Callback API VERSION2 funciona con paho-mqtt 2.x.
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        protocol=mqtt.MQTTv311,
    )

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = al_conectar
    client.on_disconnect = al_desconectar
    client.reconnect_delay_set(min_delay=1, max_delay=10)

    print("Simulador de super freezers")
    print(f"Broker: {MQTT_HOST}:{MQTT_PORT}")
    print(f"Temas: {TOPIC_BASE}/...")
    print("Conectando...")

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    except OSError as exc:
        print(f"[ERROR] No se pudo conectar a Mosquitto: {exc}")
        print(
            "Verificá que Mosquitto esté ejecutándose y escuchando "
            f"en {MQTT_HOST}:{MQTT_PORT}."
        )
        raise SystemExit(1)

    client.loop_start()

    try:
        # Espera a que el callback de conexión publique los datos iniciales.
        while not client.is_connected():
            time.sleep(0.2)

        print(
            f"[OK] Enviando temperaturas cada {INTERVALO_SEGUNDOS} segundos. "
            "Presioná Ctrl+C para detener."
        )

        inicio = time.monotonic()
        while True:
            ahora = time.monotonic()
            segundos = ahora - inicio

            for numero in range(1, NUM_EQUIPOS + 1):
                if numero in EQUIPOS_FUERA_SERVICIO:
                    # No enviar temperatura nueva: el panel debe mostrar
                    # el estado "no funcionando" publicado como retained.
                    continue

                equipo_id = f"eq{numero:02d}"
                temp = temperatura_simulada(numero, segundos)
                publicar(
                    client,
                    f"{TOPIC_BASE}/{equipo_id}/temperatura",
                    f"{temp:.1f}",
                    retain=False,
                )
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"{equipo_id}  {temp:.1f} °C"
                )

            time.sleep(INTERVALO_SEGUNDOS)

    except KeyboardInterrupt:
        print("\nDeteniendo simulador...")
    finally:
        client.loop_stop()
        client.disconnect()
        print("Simulador detenido.")


if __name__ == "__main__":
    main()
