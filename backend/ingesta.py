import paho.mqtt.client as mqtt
import sqlite3
import json
import os

BROKER = os.getenv("MQTT_HOST", "mosquitto")
PORT = 1883
TOPIC = "freezers/+/lectura"
DB_PATH = "/datos/historial.db"


#se conecta al archivo historial.db (si no existe, lo crea automáticamente). Arma la tabla
#registros con cuatro columnas: una clave primaria autoincremental, el identificador en 
#texto del equipo, la temperatura en formato decimal (REAL), y el tiempo en formato numérico
#(INTEGER) para almacenar el timestamp de Unix.
def start_baseDatos(): 
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS registros
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  equipo_id TEXT,
                  temperatura REAL,
                  fecha_ts INTEGER)''')
    conn.commit()
    conn.close()


#verifica que la conexión no haya sido rechazada (if not reason_code.is_failure) y 
#ejecuta client.subscribe(TOPIC) para que el script deje de estar inactivo y empiece a
# escuchar las transmisiones
def conexion_on(client, userdata, flags, reason_code, properties=None):
    if not reason_code.is_failure:
        print("Ingesta conectada a Mosquitto. Suscribiendo")
        client.subscribe(TOPIC)


def mensaje_on(client, userdata, msg):
    try:
        #identificar el origen: corta la ruta del mensaje y solo se queda con el ID
        equipo_id = msg.topic.split("/")[1] 
        #extrae los datos: decodifica el mensaje crudo y lo cinvierte en un diccionario y
        #de ahi rescata los valores de temperatura y fecha
        payload = json.loads(msg.payload.decode())
        temp = float(payload.get("temp_c", 0))
        ts = int(payload.get("ts", 0))
        #esto es para filtrar cortocircuitos de la sonda, fallas del modulo/sensor, etc
        # que devuelvan valores falopas (si es que no los queremos)
        if -150 <= temp <= 50:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO registros (equipo_id, temperatura, fecha_ts) VALUES (?, ?, ?)", (equipo_id, temp, ts))
            conn.commit()
            conn.close()
            print(f"Guardado: {equipo_id} -> {temp}°C")
    except Exception as e:
        print(f"Error procesando mensaje: {e}")

start_baseDatos()
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = conexion_on 
client.on_message = mensaje_on 


#ejecuta el intento de conexion inicial contra Mosquitto. Si pasan 60 segundos sin actividad,
#el cliente enviara un ping para mantener la conexion viva
client.connect(BROKER, PORT, 60)
#mantiene el script de Python corriendo indefinidamente, procesando el trafico de red en
#segundo plano y ejecutando los callbacks cuando haya que hacerlo
client.loop_forever()