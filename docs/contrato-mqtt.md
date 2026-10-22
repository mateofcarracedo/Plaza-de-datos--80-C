# Contrato MQTT — Desafío -80 °C

Formato de los mensajes entre las placas (ESP32) y el resto del sistema.
Estado: **propuesta v1** (bloque MQTT, 2026-10-22). Si algo no les cierra a
backend o panel, lo charlamos y lo ajustamos acá.

## Broker

- Host: Mosquitto 2.0.22 (ver `docker-compose.yml`), puerto `1883`.
- Por ahora sin usuario/contraseña ni TLS: solo para pruebas en red de confianza.

## Temas

| Tema | Quién publica | Contenido | QoS | Retained |
|---|---|---|---|---|
| `ifibyne/heladeras/<id>/lectura` | Placa | JSON con una medición | 1 | No |
| `ifibyne/heladeras/<id>/estado` | Placa (y el broker como Last Will) | `online` / `offline` | 1 | Sí |

`<id>` es el nombre de la heladera, configurado en cada placa: minúsculas,
números y guiones, sin espacios. Ejemplo: `heladera-01`. Nunca `/`, `+` ni `#`
(son caracteres especiales de MQTT).

Para escuchar todas las lecturas: `ifibyne/heladeras/+/lectura`.

## Lectura

```json
{"temp_c": -79.4, "ts": 1792690530}
```

| Campo | Tipo | Significado |
|---|---|---|
| `temp_c` | número o `null` | Temperatura en °C. `null` si el sensor falló (tratarlo como alarma). |
| `ts` | entero o `null` | Momento de la medición, en segundos desde 1970 (UTC), obtenido por NTP. `null` si la placa no tiene hora. |

- Frecuencia: una lectura por minuto.
- Se pueden agregar campos nuevos (batería, señal Wi-Fi, etc.); quien lee
  tiene que ignorar los campos que no conoce.
- La ingesta guarda también la hora de recepción. Si `ts` es `null`, se usa esa.
- QoS 1 garantiza que el mensaje llega **al menos una vez**: puede llegar
  duplicado. Quien lo guarde tiene que descartar duplicados
  (misma heladera y mismo `ts`).

## Estado (online / offline)

Al conectarse, la placa:

1. Se conecta con client ID `placa-<id>` (único por placa: si dos clientes
   usan el mismo ID, el broker desconecta al anterior).
2. Registra como Last Will: tema `ifibyne/heladeras/<id>/estado`, mensaje
   `offline`, QoS 1, retained.
3. Publica `online` en ese mismo tema, QoS 1, retained.

Si la placa se apaga de forma prolija, publica `offline` (retained) antes de
desconectarse, porque en una desconexión limpia el broker descarta el Last Will.

Si la placa se corta de golpe, el broker publica el `offline`:
- de inmediato, si la conexión se cerró (por ejemplo, se reinició la placa);
- o tras 1,5 × keepalive sin noticias, si se cortó la luz o el Wi-Fi.
  Con keepalive de 60 s (el valor recomendado), eso es hasta 90 s.
