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
        """CREATE TABLE IF NOT EXISTS pendientes (
            usuario TEXT NOT NULL,
            nivel INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            texto TEXT NOT NULL,
            imagen_url TEXT,
            categoria TEXT,
            PRIMARY KEY (usuario, nivel)
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
    # Palabras/frases que el usuario toca mientras lee (para el test de vocabulario).
    _ejecutar(
        """CREATE TABLE IF NOT EXISTS palabras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            termino TEXT NOT NULL,
            traduccion TEXT NOT NULL,
            frase TEXT,
            nivel INTEGER,
            es_frase INTEGER NOT NULL DEFAULT 0,
            veces INTEGER NOT NULL DEFAULT 1,
            creado TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (usuario, termino)
        )"""
    )
    # Migración: distinguir examen de historias y test de vocabulario.
    try:
        _ejecutar("ALTER TABLE examenes ADD COLUMN tipo TEXT DEFAULT 'historias'")
    except Exception:
        pass  # la columna ya existe

    _reparar_temas()


def _reparar_temas():
    """Limpia historias duplicadas de versiones anteriores y blinda la tabla.

    Es idempotente: si no hay duplicados, no cambia nada.
    """
    # 1) Mismo usuario + mismo título = la misma historia guardada dos veces.
    _ejecutar("DELETE FROM temas WHERE id NOT IN (SELECT MIN(id) FROM temas GROUP BY usuario, titulo)")
    # 2) Niveles consecutivos 1, 2, 3... según el orden en que se completaron.
    _ejecutar(
        "UPDATE temas SET nivel = "
        "(SELECT COUNT(*) FROM temas t2 WHERE t2.usuario = temas.usuario AND t2.id <= temas.id)"
    )
    # 3) Nivel y estrellas coherentes con las historias realmente guardadas.
    _ejecutar(
        "UPDATE usuarios SET "
        "nivel = (SELECT COUNT(*) FROM temas t WHERE t.usuario = usuarios.nombre) + 1, "
        "estrellas = (SELECT COUNT(*) FROM temas t WHERE t.usuario = usuarios.nombre)"
    )
    # 4) Historias pendientes de niveles que ya están completados.
    _ejecutar(
        "DELETE FROM pendientes WHERE nivel <= "
        "(SELECT COUNT(*) FROM temas t WHERE t.usuario = pendientes.usuario)"
    )
    # 5) A partir de ahora la base de datos no admite dos veces el mismo nivel.
    _ejecutar("CREATE UNIQUE INDEX IF NOT EXISTS idx_temas_usuario_nivel ON temas (usuario, nivel)")


def cargar_usuario(nombre):
    """Devuelve el progreso del usuario (lo crea si no existe)."""
    _ejecutar("INSERT OR IGNORE INTO usuarios (nombre) VALUES (?)", [nombre])
    fila = _ejecutar("SELECT nivel, estrellas FROM usuarios WHERE nombre = ?", [nombre])[0]
    temas = listar_temas(nombre)
    palabras = {p["termino"]: p for p in listar_palabras(nombre)}
    return {"nivel": fila[0], "estrellas": fila[1], "temas": temas, "palabras": palabras}


def listar_temas(nombre):
    filas = _ejecutar(
        "SELECT titulo, texto, imagen_url, nivel FROM temas WHERE usuario = ? ORDER BY id",
        [nombre],
    )
    return [{"titulo": f[0], "texto": f[1], "imagen_url": f[2], "nivel": f[3]} for f in filas]


def guardar_pendiente(nombre, nivel, titulo, texto, imagen_url, categoria):
    """Guarda la historia generada para un nivel aún sin completar."""
    _ejecutar(
        "INSERT OR REPLACE INTO pendientes (usuario, nivel, titulo, texto, imagen_url, categoria) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [nombre, nivel, titulo, texto, imagen_url, categoria],
    )


def cargar_pendiente(nombre, nivel):
    """Devuelve la historia ya generada para ese nivel, o None si no hay."""
    filas = _ejecutar(
        "SELECT titulo, texto, imagen_url, categoria FROM pendientes WHERE usuario = ? AND nivel = ?",
        [nombre, nivel],
    )
    if not filas:
        return None
    f = filas[0]
    return {"titulo": f[0], "texto": f[1], "imagen_url": f[2], "categoria": f[3]}


def guardar_tema_y_progreso(nombre, nivel_completado, titulo, texto, imagen_url):
    """Guarda la historia completada y devuelve (nuevo_nivel, estrellas).

    Es idempotente: si ese nivel ya estaba guardado no se duplica, y el nivel/estrellas
    se calculan a partir de las historias realmente guardadas (no se suman a ciegas).
    """
    _ejecutar(
        "INSERT OR IGNORE INTO temas (usuario, nivel, titulo, texto, imagen_url) VALUES (?, ?, ?, ?, ?)",
        [nombre, nivel_completado, titulo, texto, imagen_url],
    )
    _ejecutar("DELETE FROM pendientes WHERE usuario = ? AND nivel = ?", [nombre, nivel_completado])
    total = _ejecutar("SELECT COUNT(*) FROM temas WHERE usuario = ?", [nombre])[0][0]
    _ejecutar(
        "UPDATE usuarios SET nivel = ?, estrellas = ? WHERE nombre = ?",
        [total + 1, total, nombre],
    )
    return total + 1, total


def guardar_examen(nombre, aciertos, total, tipo="historias"):
    _ejecutar(
        "INSERT INTO examenes (usuario, aciertos, total, tipo) VALUES (?, ?, ?, ?)",
        [nombre, aciertos, total, tipo],
    )


# ── Vocabulario ──────────────────────────────────────────────────────────────
def guardar_palabra(nombre, termino, traduccion, frase, nivel, es_frase=False):
    """Guarda una palabra/frase tocada. Si ya existía, suma una consulta y actualiza el contexto."""
    _ejecutar(
        "INSERT INTO palabras (usuario, termino, traduccion, frase, nivel, es_frase) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (usuario, termino) DO UPDATE SET "
        "veces = veces + 1, traduccion = excluded.traduccion, frase = excluded.frase",
        [nombre, termino, traduccion, frase, nivel, 1 if es_frase else 0],
    )


def listar_palabras(nombre):
    filas = _ejecutar(
        "SELECT termino, traduccion, frase, nivel, es_frase, veces FROM palabras "
        "WHERE usuario = ? ORDER BY veces DESC, id DESC",
        [nombre],
    )
    return [
        {"termino": f[0], "traduccion": f[1], "frase": f[2], "nivel": f[3],
         "es_frase": bool(f[4]), "veces": f[5]}
        for f in filas
    ]
