import os
import json
import requests
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_ID = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

GUIA_CATEGORIAS = {
    "Historia": (
        "Un acontecimiento, proceso o periodo que toda persona culta debería entender: causas, "
        "desarrollo y consecuencias. Ejemplos: la Revolución Francesa, la Guerra Fría, la caída del "
        "Imperio Romano, la Revolución Industrial, la Reconquista, la Transición española."
    ),
    "Ciencia": (
        "Un concepto científico fundamental explicado con rigor y NIVEL TÉCNICO ALTO (universitario): "
        "usa terminología correcta, mecanismos y datos precisos, sin simplificar en exceso. Prioriza "
        "biología, genética, bioquímica, biotecnología, medicina o física y química básicas. Ejemplos: "
        "selección natural y deriva genética, fotosíntesis, replicación y expresión del ADN, CRISPR, "
        "cómo actúan las vacunas, termodinámica."
    ),
    "Economía y sociedad": (
        "Un concepto de economía, política o derecho que ayude a entender el mundo. Ejemplos: inflación, "
        "PIB, oferta y demanda, separación de poderes, Unión Europea, qué es un banco central, "
        "Estado del bienestar."
    ),
    "Arte y pensamiento": (
        "Un movimiento artístico, una obra clave o una idea filosófica fundamental. Ejemplos: "
        "Renacimiento, Barroco frente a Romanticismo, la alegoría de la caverna, el empirismo, "
        "la Ilustración, el Impresionismo."
    ),
    "Geografía y mundo actual": (
        "Un concepto de geografía, geopolítica o del mundo actual que se da por sabido. Ejemplos: "
        "por qué existen las estaciones, qué es la OTAN, tectónica de placas, cómo funcionan "
        "los monzones, qué son los BRICS."
    ),
}

CATEGORIAS = list(GUIA_CATEGORIAS)


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
    Eres un divulgador experto en cultura general. Genera una lección para una app de aprendizaje.
    El objetivo es que el lector aprenda algo que una persona culta debería saber y que le sirva
    para entender el mundo. NO son curiosidades ni datos anecdóticos.

    Temas ya aprendidos (PROHIBIDO REPETIRLOS O SOLAPARLOS): {historial}

    REQUISITOS ESTRICTOS:
    1. Categoría de este nivel: {categoria_actual}.
       Qué buscar: {GUIA_CATEGORIAS[categoria_actual]}
    2. Elige un tema FUNDAMENTAL y conocido, de los que aparecen en una buena formación general.
       PROHIBIDO: curiosidades, récords, anécdotas sueltas, "sabías que..." o datos que no ayuden a comprender nada.
    3. Explica el PORQUÉ: causas, mecanismo o razonamiento, y qué consecuencias o aplicaciones tiene.
       El lector debe poder explicárselo a otra persona después.
    4. Resalta los conceptos clave con negritas en Markdown (**así**). Usa 3 o 4 negritas. NO uses etiquetas HTML.
    5. Estructura: 3 o 4 párrafos cortos (línea en blanco entre ellos) y, al final, un párrafo que
       empiece exactamente por "**Lo que debes recordar:**" con 2 o 3 ideas resumidas en una o dos frases.
    6. Extensión: 300 - 350 palabras. Tono claro, directo y amable, sin florituras.
    7. Título claro y descriptivo, sin clickbait (máx 6 palabras).
    8. Proporciona una palabra clave en español para buscar la imagen en Wikipedia.
    9. No uses efemérides ("Un día como hoy...").

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
