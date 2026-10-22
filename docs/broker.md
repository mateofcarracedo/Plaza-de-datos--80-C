# Cómo correr el broker MQTT

Guía rápida para levantar el broker Mosquitto del Desafío -80 °C en tu compu
y probar que anda. El formato de los mensajes está en
[contrato-mqtt.md](contrato-mqtt.md).

Todos los comandos son para PowerShell (Windows). En Linux/Mac son iguales.

## 1. Requisitos

- **Docker Desktop**: https://www.docker.com/products/docker-desktop/
  Después de instalarlo, reiniciá la compu, abrilo y esperá a que abajo a la
  izquierda diga *Engine running*.
- **Git**.

Para confirmar que Docker anda (tiene que devolver un número de versión):

```powershell
docker info --format "{{.ServerVersion}}"
```

## 2. Bajar el repo (una sola vez)

```powershell
git clone --branch MQTT https://github.com/mateofcarracedo/Plaza-de-datos--80-C.git
cd Plaza-de-datos--80-C
```

Si ya lo tenés clonado, actualizalo con `git pull`.

## 3. Levantar el broker

El compose levanta dos servicios: `mosquitto` (el broker) y `mysql` (la base
de datos de la ingesta). Siempre parado en la carpeta del repo, elegí una:

**Solo el broker** (alcanza para el simulador o para probar MQTT):

```powershell
docker compose up -d mosquitto
```

**Todo (broker + MySQL)**: la primera vez, creá tu archivo de contraseñas
copiando el modelo, y abrilo para poner contraseñas propias en lugar de
`cambiar`. Ese `.env` no se sube a Git.

```powershell
Copy-Item .env.example .env
notepad .env
docker compose up -d
```

Después, en ambos casos:

```powershell
docker compose ps
```

En `STATUS` tiene que decir `Up ... (healthy)`. Los primeros segundos dice
`(health: starting)`, es normal. MySQL tarda más la primera vez (unos 30 s).

El broker queda escuchando en el puerto `1883` y se vuelve a levantar solo
cuando arranca Docker.

## 4. Probar que anda

Abrí dos terminales en la carpeta del repo.

Terminal 1, escuchar todo lo que se publique en `prueba/...`:

```powershell
docker compose exec mosquitto mosquitto_sub -h localhost -t "prueba/#" -v
```

Terminal 2, publicar un mensaje:

```powershell
docker compose exec mosquitto mosquitto_pub -h localhost -t "prueba/hola" -m "anda"
```

En la terminal 1 tiene que aparecer `prueba/hola anda`. Se corta con Ctrl+C.

Para escuchar las lecturas reales del contrato:

```powershell
docker compose exec mosquitto mosquitto_sub -h localhost -t "ifibyne/#" -v
```

## 5. Conectarse desde otra compu o desde el simulador

- Desde la misma compu: host `localhost`, puerto `1883`.
- Desde otra compu de la misma red: host = IP de la compu que corre el broker,
  puerto `1883`. La IP se ve con `ipconfig` (línea *Dirección IPv4* del Wi-Fi)
  y puede cambiar cada vez que te conectás.

Para comprobar desde la otra compu que llega:

```powershell
Test-NetConnection <IP> -Port 1883
```

Tiene que decir `TcpTestSucceeded : True`.

Ojo: el broker no tiene contraseña. Cualquiera en la misma red puede publicar
y leer. No lo dejes prendido en redes públicas cuando no lo estés usando.

## 6. Ver logs, apagar, borrar

| Para | Comando |
|---|---|
| Ver los logs en vivo | `docker compose logs -f mosquitto` |
| Apagarlo (los datos quedan) | `docker compose stop` |
| Prenderlo de nuevo | `docker compose up -d` |
| Borrar el contenedor (los datos quedan) | `docker compose down` |
| **Borrar todo, incluidos los datos guardados** | `docker compose down -v` |

## 7. Si algo falla

| Error | Causa | Qué hacer |
|---|---|---|
| `no configuration file provided: not found` | No estás en la carpeta del repo. | `cd` a la carpeta donde está `docker-compose.yml`. |
| `failed to connect to the docker API` | Docker Desktop no está corriendo (o no está instalado, solo el comando `docker`). | Abrir Docker Desktop y esperar *Engine running*. |
| `The "MYSQL_ROOT_PASSWORD" variable is not set` y MySQL reiniciándose | Falta el archivo `.env`. | Crearlo desde `.env.example` (paso 3), o levantar solo el broker con `docker compose up -d mosquitto`. Si ya lo habías levantado sin `.env`, después de crearlo corré de nuevo `docker compose up -d`. |
| `Bind for 0.0.0.0:1883 failed: port is already allocated` | Otro programa usa el 1883 (por ejemplo, Mosquitto instalado en Windows como servicio). | Parar ese servicio o desinstalarlo. |
| Docker Desktop no arranca: `The file cannot be accessed by the system` (`dockerInference`, `engine.sock`) | Quedaron archivos de socket rotos de una ejecución anterior. | Pedir ayuda a Augusto: no se borran con `del`, hay que borrarlos de otra forma. *Reset to factory defaults* no lo arregla. |
| Desde otra compu `TcpTestSucceeded : False` | La red no deja que las compus se vean entre sí, o la IP cambió. | Revisar la IP con `ipconfig`. Si sigue, probar con el hotspot de un celular. |
