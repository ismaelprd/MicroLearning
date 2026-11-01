import os
import json
import requests
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_ID = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

CATEGORIAS = [
    "Ciencia asombrosa",
    "Historia oculta",
    "Arte y símbolos",
    "Filosofía y mente",
    "Tecnología y futuro",
    "Anatomía de la cultura",
]


def categoria_de_nivel(nivel):
    return CATEGORIAS[(nivel - 1) % len(CATEGORIAS)]


def buscar_imagen_wikipedia(tema):
    if not tema:
        return None
    try:
        headers = {"User-Agent": "MiAppCultura/1.0 (test@example.com)"}
        api = "https://es.wikipedia.org/w/api.php"
        res = requests.get(
            api,
            params={"action": "query", "list": "search", "srsearch": tema,
                    "format": "json", "utf8": 1, "srlimit": 1},
            headers=headers, timeout=5,
        )
        resultados = res.json().get("query", {}).get("search", [])
        if not resultados:
            return None
        titulo = resultados[0]["title"]
        res_img = requests.get(
            api,
            params={"action": "query", "titles": titulo, "prop": "pageimages",
                    "format": "json", "pithumbsize": 600},
            headers=headers, timeout=5,
        )
        pages = res_img.json().get("query", {}).get("pages", {})
        for page in pages.values():
            if "thumbnail" in page:
                return page["thumbnail"]["source"]
    except Exception as e:
        print(f"Error buscando imagen: {e}")
    return None


def generar_microaprendizaje(nivel, temas_previos):
    """Genera una píldora única, sorprendente y dinámica."""
    historial = ", ".join(temas_previos) if temas_previos else "Ninguno (es el primer nivel)"
    categoria_actual = categoria_de_nivel(nivel)

    prompt = f"""
    Eres un experto divulgador de cultura general. Genera una píldora de conocimiento para una app.

    Temas ya aprendidos (PROHIBIDO HABLAR DE ELLOS O REPETIRLOS): {historial}

    REQUISITOS ESTRICTOS:
    1. Categoría de este nivel: {categoria_actual}.
    2. NO uses efemérides (prohibido empezar con "El día que...", "Un día como hoy..." o "En 1492...").
    3. Busca un dato CONTRATINTUITIVO, un misterio, un error histórico famoso o un concepto que haga decir "No tenía ni idea".
    4. Resalta el concepto clave con negritas en Markdown (**así**). Usa 2 o 3 negritas por texto. NO uses etiquetas HTML.
    5. Separa el texto en 3 o 4 párrafos cortos (deja una línea en blanco entre ellos).
    6. Extensión: 300 - 350 palabras. Tono: ameno, casi como un podcast o un buen hilo de Twitter.
    7. Título corto, magnético y sin clickbait barato (máx 6 palabras).
    8. Proporciona una palabra clave en español para buscar la imagen en Wikipedia.

    Devuelve la respuesta ÚNICAMENTE en formato JSON con las claves: "titulo", "texto", "palabra_clave_imagen".
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        datos = json.loads(response.text)
        datos["categoria"] = categoria_actual
        datos["imagen_url"] = buscar_imagen_wikipedia(datos.get("palabra_clave_imagen", ""))
        return datos
    except Exception as e:
        print(f"Error con Gemini: {e}")
        return {
            "error": True,
            "titulo": "No se pudo generar la historia",
            "texto": "Revisa tu conexión y la clave de Gemini, y vuelve a intentarlo.",
            "imagen_url": None,
        }


def generar_quiz(temas_previos):
    contexto = "Temas aprendidos previamente: " + ", ".join(temas_previos)

    prompt = f"""
    {contexto}

    Genera un quiz de 5 preguntas para evaluar el conocimiento sobre estos temas.
    Tipos de pregunta (usa EXACTAMENTE estos valores en "tipo"):
    - 2 de "opcion_multiple" (4 opciones; "respuesta_correcta" es el texto exacto de una opción).
    - 1 de "completar" (frase con un hueco "____"; "respuesta_correcta" es una sola palabra).
    - 1 de "redactar" (respuesta corta; "respuesta_correcta" es un ejemplo de buena respuesta).
    - 1 de "verdadero_falso" ("opciones" son ["Verdadero", "Falso"]; "respuesta_correcta" es una de ellas).

    Devuelve la respuesta ÚNICAMENTE en formato JSON con una lista llamada "preguntas".
    Cada pregunta debe tener: "tipo", "pregunta", "opciones" (lista; vacía si no aplica), "respuesta_correcta".
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error generando quiz: {e}")
        return {"preguntas": []}
