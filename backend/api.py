from flask import Flask, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)
DB_PATH = "/datos/historial.db"

@app.route('/api/historial/<id>')
def get_historial(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT temperatura, fecha_ts FROM registros WHERE equipo_id=? ORDER BY fecha_ts ASC", (id,))
    rows = c.fetchall()
    conn.close()
    
    data = [{"t": row[1] * 1000, "temp": row[0]} for row in rows]
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)