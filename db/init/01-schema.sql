-- Base de juguete para probar la cadena MQTT -> ingesta -> MySQL.
-- Se ejecuta sola solo la primera vez que arranca MySQL (volumen vacío).

CREATE TABLE IF NOT EXISTS lecturas (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  heladera_id  VARCHAR(64)   NOT NULL,
  temp_c       DECIMAL(5,2)  NULL,
  -- UTC: el ts del mensaje si viene, si no la hora de recepción
  ts           DATETIME(3)   NOT NULL,
  KEY ix_heladera_ts (heladera_id, ts)
);
