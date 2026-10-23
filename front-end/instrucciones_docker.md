# Monitoreo de Super Freezers con Docker en Windows

## 1. Crear la estructura del proyecto

Crearemos una carpeta principal con los archivos del front-end, la configuración del broker y el simulador.

En PowerShell:

```powershell
New-Item -ItemType Directory -Force C:\freezers-docker
Set-Location C:\freezers-docker

New-Item -ItemType Directory -Force mosquitto
New-Item -ItemType Directory -Force frontend
New-Item -ItemType Directory -Force simulador
```

La estructura final será:

```text
C:\freezers-docker\
├── compose.yaml
├── mosquitto\
│   └── mosquitto.conf
├── frontend\
│   ├── index.html
│   ├── styles.css
│   ├── config.js
│   └── app.js
├── simulador\
│   ├── Dockerfile
│   ├── requirements.txt
│   └── simulador.py
└── backend\
    ├── Dockerfile
    ├── requirements.txt
    ├── ingesta.py
    └── api.py
```

Copia tus cuatro archivos actuales del front-end a `C:\freezers-docker\frontend\`. Conservaremos tu HTML, CSS y JavaScript, y modificaremos únicamente la configuración de conexión MQTT.

## 2. Configurar Mosquitto dentro de Docker

Crea el archivo:

```text
C:\freezers-docker\mosquitto\mosquitto.conf
```

Puedes abrirlo con:

```powershell
notepad C:\freezers-docker\mosquitto\mosquitto.conf
```

Pega esta configuración:

```properties
# MQTT para el simulador Python
listener 1883 0.0.0.0
protocol mqtt

# MQTT sobre WebSocket para el navegador
listener 9001 0.0.0.0
protocol websockets

# Solo para pruebas locales
allow_anonymous true

# Logs visibles mediante docker compose logs
log_dest stdout
log_type all

# Conservar mensajes retenidos y persistencia del broker
persistence true
persistence_location /mosquitto/data/
```

Dentro del contenedor utilizamos `0.0.0.0` para que Mosquitto acepte conexiones procedentes de otros contenedores y de los puertos publicados por Docker.

No debes ejecutar Mosquitto manualmente. Docker lo iniciará por ti.

> **Advertencia:** esta configuración permite conexiones sin autenticación. Es adecuada para pruebas locales, pero no debe utilizarse tal cual en una red de producción.

## 3. Crear el simulador Python

El simulador se ejecutará en su propio contenedor y se conectará a Mosquitto mediante el nombre de servicio `mosquitto`.

### 3.1. Archivo `simulador/requirements.txt`

```text
paho-mqtt>=2.1,<3
```

Este paquete permite que Python publique mensajes MQTT.

### 3.2. Archivo `simulador/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY simulador.py .

CMD ["python", "-u", "simulador.py"]
```

### 3.3. Archivo `simulador/simulador.py`

Este ejemplo genera 20 equipos, publica su identificación y estado como mensajes retenidos y actualiza las temperaturas cada dos segundos. También incluye dos equipos fuera de servicio, uno próximo al umbral y otro en alarma.

```python
import json
import os
import random
import time

import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_HOST", "mosquitto")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_BASE = os.getenv("TOPIC_BASE", "freezers")
INTERVALO = float(os.getenv("INTERVALO", "2"))

# Equipos identificados por un ID único.
# Los números visibles van de 50 a 60.
GRUPOS = [
    "Pérez", "Kukiernik", "Gómez", "López",
    "Fernández", "Rodríguez", "Sánchez",
]

EQUIPOS = []

for i in range(20):
    numero = 50 + (i % 11)

    EQUIPOS.append({
        "id": f"eq{i + 1:02d}",
        "numero": numero,
        "grupo": GRUPOS[i % len(GRUPOS)],
        "piso": (i % 5) - 1,
        "estado": (
            "no funcionando"
            if i in (4, 15)
            else "funcionando"
        ),
    })

# Dos equipos especiales:
# eq03 se aproxima a la alarma; eq04 la supera.
TEMPERATURAS_ESPECIALES = {
    "eq03": -73.5,
    "eq04": -69.0,
}


def publicar(client, tema, valor, retain=False):
    if isinstance(valor, (dict, list)):
        payload = json.dumps(valor, ensure_ascii=False)
    else:
        payload = str(valor)

    info = client.publish(
        tema,
        payload=payload,
        qos=1,
        retain=retain,
    )

    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        print(f"Error al publicar en {tema}: {info.rc}")


def al_conectar(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"No se pudo conectar: {reason_code}")
        return

    print(f"Conectado a MQTT: {BROKER}:{PORT}")

    # La identificación y el estado quedan retenidos.
    for equipo in EQUIPOS:
        base = f"{TOPIC_BASE}/{equipo['id']}"

        publicar(
            client,
            f"{base}/info",
            {
                "numero": equipo["numero"],
                "grupo": equipo["grupo"],
                "piso": equipo["piso"],
            },
            retain=True,
        )

        publicar(
            client,
            f"{base}/estado",
            equipo["estado"],
            retain=True,
        )


def main():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="simulador-freezers",
        protocol=mqtt.MQTTv311,
    )

    client.on_connect = al_conectar
    client.reconnect_delay_set(min_delay=1, max_delay=15)

    while True:
        try:
            print(f"Conectando a {BROKER}:{PORT}...")
            client.connect(BROKER, PORT, keepalive=30)
            client.loop_start()

            try:
                while not client.is_connected():
                    time.sleep(0.2)

                while client.is_connected():
                    for equipo in EQUIPOS:
                        if equipo["estado"] != "funcionando":
                            # No publicar temperatura para equipos apagados.
                            continue

                        equipo_id = equipo["id"]

                        if equipo_id in TEMPERATURAS_ESPECIALES:
                            temp = TEMPERATURAS_ESPECIALES[equipo_id]
                        else:
                            temp = round(
                                random.uniform(-80.8, -79.2),
                                1,
                            )

                        publicar(
                            client,
                            f"{TOPIC_BASE}/{equipo_id}/temperatura",
                            temp,
                        )

                    print(
                        f"Actualización enviada: {time.strftime('%H:%M:%S')}"
                    )
                    time.sleep(INTERVALO)

            finally:
                client.loop_stop()
                client.disconnect()

        except (OSError, mqtt.MQTTException) as error:
            print(f"Broker no disponible: {error}. Reintento en 3 s.")
            time.sleep(3)


if __name__ == "__main__":
    main()
```

### Comportamiento esperado

- `eq01` a `eq20` identifican los 20 equipos sin duplicar sus identificadores MQTT.
- Los números visibles van de 50 a 60.
- `eq05` y `eq16` están fuera de servicio.
- `eq03` publica `-73,5 °C`, para probar el aviso previo.
- `eq04` publica `-69,0 °C`, para probar la alarma.
- Los demás equipos varían entre `-80,8 °C` y `-79,2 °C`.

El simulador publica temperaturas sin retenerlas, pero sí retiene identificación y estado. Si el front-end requiere una temperatura inicial inmediatamente después de conectarse, el siguiente ciclo de dos segundos la enviará.

## 4. Crear `compose.yaml`

Este archivo permite iniciar y administrar todos los servicios juntos.

Crea:

```text
C:\freezers-docker\compose.yaml
```

Contenido:

```yaml
services:
  mosquitto:
    image: eclipse-mosquitto:2
    container_name: freezers-mosquitto
    restart: unless-stopped
    ports:
      - "127.0.0.1:1883:1883"
      - "127.0.0.1:9001:9001"
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - mosquitto_data:/mosquitto/data
    healthcheck:
      test: ["CMD", "mosquitto_sub", "-h", "127.0.0.1", "-p", "1883", "-t", "$$SYS/broker/version", "-C", "1", "-W", "3"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 5s

  simulador:
    build:
      context: ./simulador
    container_name: freezers-simulador
    restart: unless-stopped
    environment:
      MQTT_HOST: mosquitto
      MQTT_PORT: "1883"
      TOPIC_BASE: freezers
      INTERVALO: "2"
    depends_on:
      mosquitto:
        condition: service_healthy

  frontend:
    image: nginx:alpine
    container_name: freezers-frontend
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:80"
    volumes:
      - ./frontend:/usr/share/nginx/html:ro
    depends_on:
      - mosquitto

  ingesta:
    build:
      context: ./backend
    container_name: freezers-ingesta
    command: python -u ingesta.py
    restart: unless-stopped
    environment:
      MQTT_HOST: mosquitto
    depends_on:
      mosquitto:
        condition: service_healthy
    volumes:
      - db_data:/datos

  api:
    build:
      context: ./backend
    container_name: freezers-api
    command: python -u api.py
    restart: unless-stopped
    ports:
      - "127.0.0.1:5000:5000"
    volumes:
      - db_data:/datos

volumes:
  mosquitto_data:
  db_data:
```

### ¿Qué hace cada servicio?

- **mosquitto:** recibe los mensajes MQTT y los distribuye al simulador y al navegador.
- **simulador:** construye la imagen de Python e inicia el script automáticamente.
- **frontend:** publica tus cuatro archivos web mediante Nginx.
- **mosquitto_data:** conserva los datos persistentes del broker cuando el contenedor se reinicia.
- **ingesta:** se suscribe al broker MQTT, ataja las temperaturas y las guarda en una base de datos SQLite.
- **api:** levanta un servidor Flask en el puerto 5000 para proveer el historial de temperaturas al front-end.

Los puertos publicados están limitados a `127.0.0.1`, para que estos servicios de prueba no queden expuestos directamente a otras máquinas de la red.

## 5. Modificar `config.js`

Abre:

```text
C:\freezers-docker\frontend\config.js
```

Asegúrate de que los parámetros relevantes queden así, conservando cualquier otra configuración que necesite tu aplicación:

```javascript
const CONFIG = {
  DEMO: false,

  MQTT_URL: "ws://localhost:9001",
  MQTT_USER: "",
  MQTT_PASS: "",
  TOPIC_BASE: "freezers",

  API_EQUIPOS: "",
  API_HISTORIAL: "/api/historial/{id}",

  UMBRAL_ALARMA: -70,
  MARGEN_AVISO: 5,
  STALE_MS: 120000,
};
```

La dirección `localhost` es correcta porque `config.js` se ejecuta en el navegador de Windows, no dentro del contenedor frontend.

No cambies `MQTT_URL` a `ws://mosquitto:9001`: ese nombre solo es resoluble por los contenedores conectados a la red de Docker.

## 6. Iniciar todo el proyecto

Abre PowerShell y ejecuta:

```powershell
Set-Location C:\freezers-docker

docker compose config
```

Este comando valida la sintaxis de la configuración. Si no muestra errores, construye el simulador e inicia los tres servicios:

```powershell
docker compose up -d --build
```

La primera ejecución descargará las imágenes necesarias. Puede tardar unos minutos.

Comprueba el estado:

```powershell
docker compose ps
```

Deberías encontrar los servicios `mosquitto`, `simulador` y `frontend` ejecutándose. El simulador esperará a que el broker esté disponible antes de arrancar.

Para ver los mensajes del simulador:

```powershell
docker compose logs -f simulador
```

Para ver los registros de Mosquitto:

```powershell
docker compose logs -f mosquitto
```

Pulsa `Ctrl+C` para salir de los registros; esto no detiene los contenedores.

## 7. Comprobar que todo funciona

### 7.1. Abrir la página

Entra desde el navegador de Windows en:

[http://localhost:8000](http://localhost:8000)

La página debería cargarse y, si `app.js` está configurado para conectarse a MQTT con la estructura de temas indicada, el estado de conexión debería cambiar a **Conectado**.

### 7.2. Comprobar los mensajes del broker

Abre otra ventana de PowerShell y ejecuta:

```powershell
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "freezers/#" -v
```

Deberías ver mensajes similares a estos:

```text
freezers/eq01/info {"numero": 50, "grupo": "Pérez", "piso": -1}
freezers/eq01/estado funcionando
freezers/eq01/temperatura -80.1
freezers/eq02/temperatura -79.7
freezers/eq04/temperatura -69.0
```

Los valores de temperatura normales cambiarán con cada actualización.

### 7.3. Probar una alarma manualmente

Para modificar temporalmente la temperatura de un equipo, ejecuta:

```powershell
docker compose exec mosquitto mosquitto_pub -h 127.0.0.1 -p 1883 -t "freezers/eq01/temperatura" -m "-69"
```

Para devolverlo a una temperatura normal:

```powershell
docker compose exec mosquitto mosquitto_pub -h 127.0.0.1 -p 1883 -t "freezers/eq01/temperatura" -m "-80"
```

Ten en cuenta que el simulador seguirá publicando temperaturas para `eq01` cada dos segundos, por lo que puede sobrescribir enseguida tu prueba manual.

Para probar alarmas sin interferencias, detén temporalmente el simulador:

```powershell
docker compose stop simulador
```

Cuando termines, vuelve a iniciarlo:

```powershell
docker compose start simulador
```

En la página, activa el sonido mediante su botón. La reproducción de audio puede requerir una interacción del usuario con el navegador.

## 8. Solución de problemas

### El navegador no se conecta a MQTT

- Comprueba que `DEMO: false`.
- Verifica que `MQTT_URL` sea `ws://localhost:9001`.
- Ejecuta `docker compose logs mosquitto`.
- Comprueba que el puerto 9001 no esté ocupado por otra aplicación.

### La página abre, pero no aparecen los equipos

- Comprueba que los archivos estén en `frontend`.
- Ejecuta `docker compose logs simulador`.
- Revisa la consola del navegador con `F12`.
- Verifica que `app.js` interprete los temas `freezers/{id}/info`, `freezers/{id}/estado` y `freezers/{id}/temperatura`, además del formato JSON de identificación.

### Las temperaturas no cambian o las alarmas no se activan

- Verifica que el simulador esté en ejecución.
- Confirma que `UMBRAL_ALARMA` sea `-70` y `MARGEN_AVISO` sea `5`.
- Comprueba que el front-end considere alarma una temperatura superior al umbral numérico, por ejemplo `-69 °C`.

## 9. Historial de temperaturas

Con esta configuración tendremos el monitoreo en tiempo real, pero el historial aún no estará implementado.

La ruta `API_HISTORIAL: "/api/historial/{id}"` no funcionará por sí sola. Necesitamos un backend Python adicional que:

1. Reciba las temperaturas publicadas en MQTT.
2. Guarde cada medición con el identificador del equipo y su fecha y hora.
3. Exponga una API HTTP para consultar el historial.
4. Devuelva los datos en el formato que espera `app.js`.

Podemos incorporar ese backend como un cuarto servicio de Docker, junto con una base de datos SQLite para empezar. Así, podremos conservar el historial aunque se reinicie el simulador.

## 10. Comandos útiles de Docker

| Acción | Comando |
|---|---|
| Iniciar todos los servicios | `docker compose up -d` |
| Reconstruir y arrancar | `docker compose up -d --build` |
| Ver el estado | `docker compose ps` |
| Ver los registros | `docker compose logs -f` |
| Detener los servicios | `docker compose stop` |
| Reiniciar los servicios | `docker compose restart` |
| Detener y eliminar contenedores | `docker compose down` |

`docker compose down` no elimina el volumen de datos. Si ejecutas `docker compose down -v`, también eliminarás el volumen persistente de Mosquitto.

## Resultado final

Al terminar estos pasos tendrás una instalación reproducible de tu proyecto, gestionada desde Docker Desktop:

- Mosquitto con MQTT TCP y WebSocket.
- Simulador Python con 20 equipos.
- Publicación automática de temperaturas cada dos segundos.
- Dos equipos fuera de servicio y dos equipos para probar avisos y alarmas.
- Front-end accesible desde Windows.
- Sin necesidad de instalar Python ni Mosquitto directamente en Windows.

**Consideración final:** el simulador genera los datos, pero los colores, el parpadeo, el sonido y la presentación de los equipos dependen de la lógica existente en `app.js` y `styles.css`. Si alguno de esos comportamientos no funciona, habrá que revisar los cuatro archivos para adaptar el simulador exactamente al código actual.
