# Monitoreo de Super Freezers: configuración de MQTT en Windows

## Introducción

Para probar el front-end con un simulador MQTT, utilizaremos **Mosquitto como broker** y un publicador en Python que simule las temperaturas de los 20 super freezers.

De esta manera, podremos comprobar las temperaturas en tiempo real, los cambios de color, las alarmas y los estados de los equipos sin necesidad de sensores físicos.

> [!IMPORTANT]
> En los archivos actuales, `config.js` tiene `DEMO: true`. En ese modo, el front-end genera sus propias temperaturas ficticias y no se conecta a Mosquitto. Para utilizar el broker, debemos cambiarlo a `false` y configurar MQTT sobre WebSocket.

## 1. Arquitectura

La comunicación entre los componentes será la siguiente:

```text
Simulador Python
    |
    | MQTT TCP (1883)
    v
Mosquitto Broker
    |
    | MQTT sobre WebSocket (9001)
    v
Front-end web
HTML + CSS + JavaScript
```

Los puertos tienen funciones distintas:

| Puerto | Función |
|---|---|
| `1883` | Comunicación MQTT entre Python y Mosquitto. |
| `9001` | Conexión del navegador al broker mediante WebSocket. |
| `8000` | Servidor HTTP para visualizar el front-end durante las pruebas. |

El puerto HTTP es independiente de MQTT.

## 2. Requisitos e instalaciones

### Mosquitto

Es el broker MQTT que recibirá los datos del simulador y los distribuirá al navegador.

Descarga oficial: [Mosquitto para Windows](https://mosquitto.org/download/)

### Python

Se utilizará para ejecutar un simulador que publique temperaturas automáticamente.

Descarga oficial: [Python para Windows](https://www.python.org/downloads/windows/)

No es necesario instalar Node.js ni implementar todavía el backend completo. El archivo `app.js` ya carga MQTT.js desde una CDN y puede comunicarse directamente con Mosquitto mediante WebSocket.

## 3. Instalar Mosquitto en Windows

1. Descarga el instalador de Windows desde el sitio oficial de Mosquitto.
2. Ejecuta el instalador y, si ofrece la opción, incluye los componentes de cliente `mosquitto_pub` y `mosquitto_sub`.
3. Si solicita instalar dependencias adicionales, sigue las indicaciones del instalador.
4. Comprueba dónde quedó instalado. La ubicación habitual es:

```text
C:\Program Files\mosquitto\
```

### Comprobar la instalación

Abre PowerShell y ejecuta:

```powershell
Test-Path "C:\Program Files\mosquitto\mosquitto.exe"
```

Si devuelve `True`, el ejecutable está en esa ubicación. Si devuelve `False`, localiza la carpeta en la que lo instalaste.

También puedes comprobar la versión y las opciones disponibles:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -h
```

## 4. Configurar los puertos MQTT y WebSocket

El navegador necesita el puerto `9001` para conectarse mediante WebSocket. Crearemos una configuración específica para las pruebas locales.

### Crear la carpeta de configuración

Ejecuta en PowerShell:

```powershell
New-Item -ItemType Directory -Force C:\freezers-mqtt
notepad C:\freezers-mqtt\mosquitto.conf
```

Se abrirá el Bloc de notas. Pega el siguiente contenido:

```conf
# Broker MQTT local para pruebas
listener 1883 127.0.0.1
protocol mqtt

# WebSocket para el navegador
listener 9001 127.0.0.1
protocol websockets

# Solo para pruebas locales
allow_anonymous true

# Logs en la consola
log_dest stdout
log_type all
```

Guarda el archivo como:

```text
C:\freezers-mqtt\mosquitto.conf
```

Asegúrate de que el nombre sea `mosquitto.conf` y no `mosquitto.conf.txt`.

> [!WARNING]
> Esta configuración permite conexiones sin autenticación y está limitada a la máquina local. Es adecuada para pruebas, pero no debe utilizarse tal cual en una red de producción.

### Iniciar el broker

En PowerShell, ejecuta:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c "C:\freezers-mqtt\mosquitto.conf" -v
```

Deja esta ventana abierta.

Si la configuración es correcta y los puertos están libres, Mosquitto debería indicar que está escuchando en los puertos `1883` y `9001`.

Si aparece un error de puerto ocupado, es posible que el servicio de Mosquitto instalado en Windows ya esté ejecutándose. En ese caso:

1. Abre `services.msc`.
2. Localiza el servicio de Mosquitto.
3. Detén temporalmente el servicio si corresponde.
4. Vuelve a iniciar el broker con el comando anterior.

## 5. Comprobar que MQTT funciona

Antes de conectar el front-end, comprobaremos que Mosquitto puede recibir y distribuir mensajes.

### Suscribirse a los mensajes

Abre una segunda ventana de PowerShell y ejecuta:

```powershell
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -p 1883 -t "freezers/#" -v
```

Este comando escucha todos los temas que comienzan con `freezers/`.

### Publicar una temperatura de prueba

Abre una tercera ventana de PowerShell y ejecuta:

```powershell
& "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -p 1883 -t "freezers/eq01/temperatura" -m "-79.5"
```

En la segunda ventana debería aparecer:

```text
freezers/eq01/temperatura -79.5
```

Si aparece el mensaje, la comunicación MQTT básica está funcionando.

## 6. Adaptar `config.js`

En la carpeta que contiene los cuatro archivos del front-end, abre `config.js` y modifica los valores de configuración para que coincidan con los siguientes:

```javascript
const CONFIG = {
  DEMO: false,

  MQTT_URL: "ws://127.0.0.1:9001",
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

Puedes conservar el resto de los comentarios que ya contiene el archivo.

Los parámetros principales son:

| Parámetro | Descripción |
|---|---|
| `DEMO` | Debe ser `false` para utilizar MQTT. |
| `MQTT_URL` | Dirección del broker mediante WebSocket. |
| `MQTT_USER` y `MQTT_PASS` | Credenciales MQTT, vacías en esta prueba local. |
| `TOPIC_BASE` | Prefijo de los temas MQTT. |
| `UMBRAL_ALARMA` | Umbral de alarma: `-70 °C`. |
| `MARGEN_AVISO` | Margen de aviso previo: `5 °C`. |
| `STALE_MS` | Tiempo máximo sin actualizaciones antes de considerar los datos desactualizados: 120 segundos. |

Por ahora, no es necesario modificar `app.js` ni `styles.css`.

## 7. Abrir el front-end en Windows

Supongamos que los cuatro archivos están guardados en:

```text
C:\freezers-web\
├── index.html
├── styles.css
├── config.js
└── app.js
```

### Iniciar el servidor HTTP

Abre PowerShell y ejecuta:

```powershell
cd C:\freezers-web
py -m http.server 8000
```

Deja esa ventana abierta.

Si el comando `py` no se reconoce, comprueba la instalación de Python y que esté disponible desde PowerShell.

### Abrir la página

En el navegador, visita:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

No abras `index.html` directamente haciendo doble clic. Para esta prueba, es preferible servirlo mediante HTTP.

Si Mosquitto está escuchando en el puerto `9001` y la conexión WebSocket funciona, el estado de conexión de la barra superior debería cambiar a **Conectado**.

## 8. Enviar los datos de un equipo de prueba

Con el broker y la página abiertos, ejecuta los siguientes comandos en PowerShell, uno por uno.

### Publicar la información del equipo

```powershell
& "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -p 1883 -t "freezers/eq01/info" -m '{"numero":60,"grupo":"Pérez","piso":3}' -r
```

Este mensaje identifica al equipo número 60, perteneciente al grupo Pérez y ubicado en el piso 3.

La opción `-r` hace que el mensaje quede retenido en el broker para que los nuevos suscriptores reciban la información más reciente.

### Publicar el estado

```powershell
& "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -p 1883 -t "freezers/eq01/estado" -m "funcionando" -r
```

### Publicar la temperatura

```powershell
& "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -p 1883 -t "freezers/eq01/temperatura" -m "-79.5"
```

En el front-end debería aparecer el equipo 60, del grupo Pérez, en el piso 3, con una temperatura de `-79,5 °C`.

### Probar una alarma

Publica una temperatura superior al umbral de alarma:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe"
```

El comando anterior solo muestra la ayuda del broker; para publicar la temperatura de alarma, utiliza este comando:

```powershell
& "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -p 1883 -t "freezers/eq01/temperatura" -m "-69"
```

La fila debería ponerse roja e intermitente.

Para comprobar el sonido:

1. Pulsa el botón de sonido en la página.
2. Verifica que el navegador no esté silenciado.
3. Comprueba que el equipo permanezca en estado de alarma mientras su temperatura supere el umbral.

### Solucionar problemas

Si el broker se conecta, pero el equipo no aparece:

1. Abre las herramientas de desarrollador del navegador con `F12`.
2. Entra en la pestaña **Console**.
3. Revisa si hay errores de JavaScript o de recepción de mensajes MQTT.
4. Comprueba que los temas publicados coincidan exactamente con los que espera `app.js`.

Si el navegador no se conecta, revisa primero los mensajes de la terminal donde ejecutaste Mosquitto y confirma que el puerto `9001` esté escuchando.

## 9. Simulación automática de los 20 equipos

Los pasos anteriores permiten probar manualmente un equipo. Para completar la simulación, el siguiente paso será crear un script Python que publique automáticamente:

- Los 20 equipos con sus datos identificativos.
- Temperaturas nuevas cada dos segundos.
- Dos equipos con estado `no funcionando`.
- Un equipo que se acerque al umbral de alarma.
- Otro equipo que supere el umbral y active la alarma.
- Mensajes retenidos para la información y el estado de cada equipo.

El simulador deberá respetar los temas MQTT que utiliza el front-end:

```text
freezers/<id>/info
freezers/<id>/estado
freezers/<id>/temperatura
```

Los mensajes de información tendrán un formato JSON similar al siguiente:

```json
{
  "numero": 60,
  "grupo": "Pérez",
  "piso": 3
}
```

Los estados posibles serán:

```text
funcionando
no funcionando
```

Las temperaturas podrán publicarse como números, por ejemplo:

```text
-79.5
```

También se puede utilizar un objeto JSON si el código del front-end está preparado para recibirlo:

```json
{
  "temp": -79.5
}
```

## 10. Historial de temperaturas: trabajo pendiente

El historial todavía necesita un backend Python con almacenamiento y una ruta HTTP que permita recuperar las mediciones anteriores.

La ruta configurada actualmente es:

```text
/api/historial/{id}
```

El backend deberá guardar las temperaturas con sus marcas de tiempo y devolver una respuesta similar a esta:

```json
[
  {
    "t": "2026-10-22T10:00:00Z",
    "temp": -79.5
  },
  {
    "t": "2026-10-22T10:00:02Z",
    "temp": -79.4
  }
]
```

Con esa información, la sección **Historial** podrá mostrar la evolución de la temperatura de cada equipo en el intervalo solicitado.

---

## Resultado esperado

Al finalizar esta primera etapa, tendremos:

- Mosquitto funcionando como broker MQTT local.
- MQTT TCP en el puerto `1883`.
- MQTT sobre WebSocket en el puerto `9001`.
- El front-end ejecutándose mediante HTTP en el puerto `8000`.
- La recepción de temperaturas en tiempo real.
- La posibilidad de probar manualmente los cambios de estado y las alarmas.

El siguiente paso será implementar `simulador.py` para generar automáticamente los datos de los 20 super freezers y, posteriormente, desarrollar el backend de historial.
