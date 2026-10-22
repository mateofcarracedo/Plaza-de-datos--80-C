/* ============================================================
   Configuración del front-end de monitoreo de super freezers
   ============================================================

   CONTRATO MQTT (lo que el back-end Python debe publicar)
   -------------------------------------------------------
   <TOPIC_BASE> = "freezers" por defecto. <id> es un identificador único
   e interno del equipo (ej. "eq01"), distinto del "número de equipo".

   freezers/<id>/info         (retain)  {"numero": 60, "grupo": "Pérez", "piso": 3}
   freezers/<id>/estado       (retain)  "funcionando" | "no funcionando"
   freezers/<id>/temperatura            -79.8          (número)
                                        o {"temp": -79.8}
   freezers/config            (retain)  {"umbral": -70, "margen": 5}   (opcional)

   Recomendado publicar info/estado/config con retain=True para que el
   navegador los reciba apenas se conecta.

   HISTORIAL (HTTP)
   ----------------
   GET <API_HISTORIAL> con {id} reemplazado -> JSON:
   [{"t": "2026-10-22T10:00:00Z", "temp": -79.5}, ...]
   "t" puede ser ISO 8601, milisegundos o segundos epoch.
   El rango de tiempo lo decide el back-end.

   LISTA DE EQUIPOS (opcional, HTTP)
   ---------------------------------
   GET <API_EQUIPOS> -> [{"id":"eq01","numero":60,"grupo":"Pérez","piso":3,
                          "estado":"funcionando"}, ...]
   Si no se usa, los equipos se crean solos al llegar sus mensajes MQTT.

   NOTA: el navegador no habla MQTT por TCP (1883); necesita WebSocket.
   En Mosquitto: agregar un listener, por ejemplo
       listener 9001
       protocol websockets
*/
const CONFIG = {
  // true = datos simulados (sin broker). Poner false para usar MQTT real.
  DEMO: true,

  // Conexión MQTT sobre WebSocket
  MQTT_URL: "ws://localhost:9001",
  MQTT_USER: "",
  MQTT_PASS: "",
  TOPIC_BASE: "freezers",

  // Endpoints del back-end (rutas relativas o absolutas)
  API_EQUIPOS: "",                       // opcional, ej. "/api/equipos"
  API_HISTORIAL: "/api/historial/{id}",

  // Alarma: se activa cuando temp > UMBRAL_ALARMA (°C)
  UMBRAL_ALARMA: -70,
  // Amarillo: cuando temp > UMBRAL_ALARMA - MARGEN_AVISO (°C)
  MARGEN_AVISO: 5,

  // Si un equipo "funcionando" no envía datos en este tiempo (ms) se muestra
  // "Sin datos". 0 = desactivado.
  STALE_MS: 120000,
};
