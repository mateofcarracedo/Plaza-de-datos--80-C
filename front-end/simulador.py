#!/usr/bin/env python3
"""
Simulador MQTT de super freezers (heladeras).

Publica una lectura por heladera cada N segundos en:
  ifibyne/heladeras/<id>/lectura        (ej: ifibyne/heladeras/heladera-01/lectura)

Mensaje JSON:
  {"temp_c": -79.4, "ts": 1792690530}   (ts = int(time.time()))
QoS 1, sin retained.

Comportamientos (heladeras 1 a 5; el resto funciona normal):
  1) normal
  2) excursion: anda normal un rato, sube hasta -50 °C y vuelve a la normalidad (se repite)
  3) defectuosa: la temperatura sube siempre
  4) intermitente: anda bien a ratos, se corta y sube, vuelve a andar y baja (se repite)
  5) outliers: estable, pero cada tanto emite un valor absurdamente alto (~45 °C)

Instalación en Windows (PowerShell):
  py -m pip install paho-mqtt

Ejecución:
  py simulador.py
  py simulador.py --host 192.168.1.50 --intervalo 5

Detener con Ctrl+C.
"""

import argparse
import json
import math
import random
import sys
import time

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
# Configuración
# ---------------------------------------------------------------------------
TOPIC_BASE = "ifibyne/heladeras"
CLIENT_ID = "simulador-super-freezers"
QOS = 1

TEMP_NORMAL = -79.5          # temperatura de trabajo habitual (°C)

# Qué comportamiento tiene cada heladera (las no listadas son "normal")
COMPORTAMIENTOS = {
    1: "normal",
    2: "excursion",
    3: "defectuosa",
    4: "intermitente",
    5: "outliers",
}

# 2) Excursión: duración de cada tramo del ciclo, en segundos
EXC_NORMAL = 240             # anda normal
EXC_SUBIDA = 150             # sube hasta el pico
EXC_PICO = 30                # se queda en el pico
EXC_BAJADA = 150             # vuelve a la normalidad
EXC_TEMP_PICO = -50.0

# 3) Defectuosa: sube de forma exponencial hacia la temperatura ambiente
DEF_AMBIENTE = 22.0
DEF_TAU = 1500.0             # segundos; con 1500 llega a ~-50 °C a los ~8 min

# 4) Intermitente
INT_SUBE_C_POR_S = 0.25      # velocidad de subida durante la falla (°C/s)
INT_BAJA_C_POR_S = 0.35      # velocidad de bajada al recuperarse (°C/s)
INT_TEMP_MAX = -45.0
INT_OK_SEG = (40, 100)       # duración aleatoria de los tramos "bien"
INT_FALLA_SEG = (50, 90)     # duración aleatoria de los tramos "cortada"

# 5) Outliers
OUT_PROBABILIDAD = 0.05      # probabilidad de valor raro en cada lectura
OUT_RANGO = (40.0, 50.0)

random.seed()


# ---------------------------------------------------------------------------
# Generación de temperaturas
# ---------------------------------------------------------------------------
def base_normal(numero, t):
    """Temperatura normal sin ruido: variación lenta alrededor de -79.5 °C."""
    return TEMP_NORMAL + 0.7 * math.sin(t / 18.0 + numero)


def ruido(amplitud=0.25):
    return random.uniform(-amplitud, amplitud)


def suavizar(x):
    """Interpolación suave (0 -> 1) para que las subidas/bajadas no sean lineales."""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class Heladera:
    def __init__(self, numero):
        self.numero = numero
        self.id = f"heladera-{numero:02d}"
        self.comportamiento = COMPORTAMIENTOS.get(numero, "normal")

        # Estado interno para el comportamiento intermitente
        self.fase = "ok"
        self.fase_hasta = random.uniform(*INT_OK_SEG)
        self.temp_interm = base_normal(numero, 0)

    def leer(self, t, dt):
        """Devuelve la temperatura (°C) en el instante t (segundos desde el inicio)."""
        metodo = getattr(self, "_" + self.comportamiento)
        return round(metodo(t, dt), 1)

    # 1) Normal -------------------------------------------------------------
    def _normal(self, t, dt):
        return base_normal(self.numero, t) + ruido()

    # 2) Excursión: normal -> sube a -50 -> vuelve -------------------------------
    def _excursion(self, t, dt):
        periodo = EXC_NORMAL + EXC_SUBIDA + EXC_PICO + EXC_BAJADA
        pos = t % periodo
        base = base_normal(self.numero, t)

        if pos < EXC_NORMAL:
            return base + ruido()

        pos -= EXC_NORMAL
        if pos < EXC_SUBIDA:
            s = suavizar(pos / EXC_SUBIDA)
            return base + (EXC_TEMP_PICO - base) * s + ruido(0.3)

        pos -= EXC_SUBIDA
        if pos < EXC_PICO:
            return EXC_TEMP_PICO + ruido(0.3)

        pos -= EXC_PICO
        s = suavizar(pos / EXC_BAJADA)
        return EXC_TEMP_PICO + (base - EXC_TEMP_PICO) * s + ruido(0.3)

    # 3) Defectuosa: siempre sube ---------------------------------------------
    def _defectuosa(self, t, dt):
        temp = DEF_AMBIENTE - (DEF_AMBIENTE - TEMP_NORMAL) * math.exp(-t / DEF_TAU)
        return temp + ruido(0.2)

    # 4) Intermitente: bien -> se corta y sube -> vuelve y baja ------------------
    def _intermitente(self, t, dt):
        base = base_normal(self.numero, t)

        if self.fase == "ok":
            self.temp_interm = base
            if t >= self.fase_hasta:
                self.fase = "falla"
                self.fase_hasta = t + random.uniform(*INT_FALLA_SEG)

        elif self.fase == "falla":
            self.temp_interm = min(
                self.temp_interm + INT_SUBE_C_POR_S * dt * random.uniform(0.7, 1.3),
                INT_TEMP_MAX,
            )
            if t >= self.fase_hasta:
                self.fase = "recupera"

        else:  # recupera
            self.temp_interm = max(
                self.temp_interm - INT_BAJA_C_POR_S * dt * random.uniform(0.8, 1.2),
                base,
            )
            if self.temp_interm <= base:
                self.fase = "ok"
                self.fase_hasta = t + random.uniform(*INT_OK_SEG)

        return self.temp_interm + ruido(0.2)

    # 5) Estable con valores atípicos ------------------------------------------
    def _outliers(self, t, dt):
        if random.random() < OUT_PROBABILIDAD:
            return random.uniform(*OUT_RANGO)
        return TEMP_NORMAL + ruido(0.2)


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------
def publicar(client, topic, payload):
    """Publica con QoS 1, sin retained. Avisa si no pudo encolarse."""
    info = client.publish(
        topic,
        payload=json.dumps(payload, ensure_ascii=False),
        qos=QOS,
        retain=False,
    )
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        print(f"[ERROR] No se pudo publicar en {topic}: código {info.rc}")
        return False
    return True


def al_conectar(client, userdata, flags, reason_code, properties=None):
    """Callback compatible con paho-mqtt 2.x."""
    try:
        correcto = int(reason_code) == 0
    except (TypeError, ValueError):
        correcto = str(reason_code).lower() in ("success", "0")

    if correcto:
        print(f"[OK] Conectado a Mosquitto en {userdata['host']}:{userdata['port']}")
    else:
        print(f"[ERROR] No se pudo conectar a Mosquitto: {reason_code}")


def al_desconectar(client, userdata, disconnect_flags, reason_code, properties=None):
    try:
        codigo = int(reason_code)
    except (TypeError, ValueError):
        codigo = reason_code
    if codigo != 0:
        print(f"[AVISO] Se perdió la conexión con Mosquitto: {reason_code}")


def parsear_argumentos():
    p = argparse.ArgumentParser(description="Simulador MQTT de super freezers")
    p.add_argument("--host", default="localhost", help="host del broker (default: localhost)")
    p.add_argument("--puerto", type=int, default=1883, help="puerto del broker (default: 1883)")
    p.add_argument(
        "--intervalo", type=float, default=5.0,
        help="segundos entre lecturas de cada heladera (default: 5)",
    )
    p.add_argument("--cantidad", type=int, default=20, help="cantidad de heladeras (default: 20)")
    p.add_argument("--usuario", default="", help="usuario MQTT (opcional)")
    p.add_argument("--password", default="", help="contraseña MQTT (opcional)")
    args = p.parse_args()

    if args.intervalo <= 0:
        p.error("--intervalo debe ser mayor que 0")
    if args.cantidad < 1:
        p.error("--cantidad debe ser al menos 1")
    return args


def main():
    args = parsear_argumentos()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        protocol=mqtt.MQTTv311,
        userdata={"host": args.host, "port": args.puerto},
    )
    if args.usuario:
        client.username_pw_set(args.usuario, args.password)

    client.on_connect = al_conectar
    client.on_disconnect = al_desconectar
    client.reconnect_delay_set(min_delay=1, max_delay=10)

    heladeras = [Heladera(n) for n in range(1, args.cantidad + 1)]

    print("Simulador de super freezers")
    print(f"Broker: {args.host}:{args.puerto}")
    print(f"Temas: {TOPIC_BASE}/<id>/lectura  (QoS {QOS}, sin retained)")
    print("Comportamientos especiales:")
    for h in heladeras:
        if h.numero in COMPORTAMIENTOS:
            print(f"  {h.id}: {h.comportamiento}")
    print("Conectando...")

    try:
        client.connect(args.host, args.puerto, keepalive=30)
    except OSError as exc:
        print(f"[ERROR] No se pudo conectar a Mosquitto: {exc}")
        print(
            "Verificá que Mosquitto esté ejecutándose y escuchando "
            f"en {args.host}:{args.puerto}."
        )
        raise SystemExit(1)

    client.loop_start()

    try:
        while not client.is_connected():
            time.sleep(0.2)

        print(
            f"[OK] Enviando una lectura por heladera cada {args.intervalo:g} segundos. "
            "Presioná Ctrl+C para detener."
        )

        inicio = time.monotonic()
        proximo = inicio

        while True:
            t = time.monotonic() - inicio
            ts = int(time.time())

            for h in heladeras:
                temp = h.leer(t, args.intervalo)
                publicar(
                    client,
                    f"{TOPIC_BASE}/{h.id}/lectura",
                    {"temp_c": temp, "ts": ts},
                )
                etiqueta = f" ({h.comportamiento})" if h.numero in COMPORTAMIENTOS else ""
                print(
                    f"[{time.strftime('%H:%M:%S')}] "
                    f"{h.id}{etiqueta}  {temp:.1f} °C"
                )

            # Programar el próximo ciclo sin acumular deriva.
            proximo += args.intervalo
            time.sleep(max(0.0, proximo - time.monotonic()))

    except KeyboardInterrupt:
        print("\nDeteniendo simulador...")
    finally:
        client.loop_stop()
        client.disconnect()
        print("Simulador detenido.")


if __name__ == "__main__":
    main()
