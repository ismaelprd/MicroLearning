"""Persistencia del progreso.

- Si existen TURSO_DATABASE_URL y TURSO_AUTH_TOKEN, usa Turso a través de su API HTTP
  (solo necesita `requests`, así no hay que compilar nada en el despliegue).
- Si no existen, usa un SQLite local (cultura_local.db) para poder probar en tu PC.
"""
import os
import sqlite3
import requests

TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "").strip().replace("libsql://", "https://")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
USAR_TURSO = bool(TURSO_URL and TURSO_TOKEN)
RUTA_LOCAL = os.environ.get("LOCAL_DB_PATH", "cultura_local.db")


def _arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def _valor(celda):
    t = celda.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(celda["value"])
    if t == "float":
        return float(celda["value"])
    return celda.get("value")


def _ejecutar(sql, args=()):
    """Ejecuta una sentencia y devuelve las filas como lista de tuplas."""
    if USAR_TURSO:
        cuerpo = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in args]}},
                {"type": "close"},
            ]
        }
        r = requests.post(
            f"{TURSO_URL}/v2/pipeline",
            json=cuerpo,
            headers={"Authorization": f"Bearer {TURSO_TOKEN}"},
            timeout=10,
        )
        r.raise_for_status()
        resultado = r.json()["results"][0]
        if resultado.get("type") == "error":
            raise RuntimeError(resultado["error"]["message"])
        filas = resultado["response"]["result"]["rows"]
        return [tuple(_valor(c) for c in fila) for fila in filas]

    con = sqlite3.connect(RUTA_LOCAL)
    try:
        cur = con.execute(sql, tuple(args))
        filas = cur.fetchall()
        con.commit()
        return filas
    finally:
        con.close()


def init_db():
    _ejecutar(
        """CREATE TABLE IF NOT EXISTS usuarios (
            nombre TEXT PRIMARY KEY,
            nivel INTEGER NOT NULL DEFAULT 1,
            estrellas INTEGER NOT NULL DEFAULT 0
        )"""
    )
    _ejecutar(
        """CREATE TABLE IF NOT EXISTS temas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            nivel INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            texto TEXT NOT NULL,
            imagen_url TEXT,
            creado TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    _ejecutar(
        """CREATE TABLE IF NOT EXISTS examenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            aciertos INTEGER NOT NULL,
            total INTEGER NOT NULL,
            creado TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )


def cargar_usuario(nombre):
    """Devuelve el progreso del usuario (lo crea si no existe)."""
    _ejecutar("INSERT OR IGNORE INTO usuarios (nombre) VALUES (?)", [nombre])
    fila = _ejecutar("SELECT nivel, estrellas FROM usuarios WHERE nombre = ?", [nombre])[0]
    temas = listar_temas(nombre)
    return {"nivel": fila[0], "estrellas": fila[1], "temas": temas}


def listar_temas(nombre):
    filas = _ejecutar(
        "SELECT titulo, texto, imagen_url, nivel FROM temas WHERE usuario = ? ORDER BY id",
        [nombre],
    )
    return [{"titulo": f[0], "texto": f[1], "imagen_url": f[2], "nivel": f[3]} for f in filas]


def guardar_tema_y_progreso(nombre, nivel_completado, titulo, texto, imagen_url, nuevo_nivel, estrellas):
    _ejecutar(
        "INSERT INTO temas (usuario, nivel, titulo, texto, imagen_url) VALUES (?, ?, ?, ?, ?)",
        [nombre, nivel_completado, titulo, texto, imagen_url],
    )
    _ejecutar(
        "UPDATE usuarios SET nivel = ?, estrellas = ? WHERE nombre = ?",
        [nuevo_nivel, estrellas, nombre],
    )


def guardar_examen(nombre, aciertos, total):
    _ejecutar(
        "INSERT INTO examenes (usuario, aciertos, total) VALUES (?, ?, ?)",
        [nombre, aciertos, total],
    )
