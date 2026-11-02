import os
import json
import random
import requests
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_ID = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Nivel de inglés de las historias (escala MCER). Se puede cambiar con la variable NIVEL_INGLES.
NIVEL_INGLES = os.environ.get("NIVEL_INGLES", "B2")

TEST_VOCAB_PREGUNTAS = 10
QUIZ_HISTORIAS_MUESTRA = 5

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


def _pedir_json(prompt):
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)


def buscar_imagen_wikipedia(tema):
    if not tema:
        return None
    try:
        headers = {"User-Agent": "MiAppCultura/1.0 (test@example.com)"}
        api = "https://en.wikipedia.org/w/api.php"
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
    """Genera una lección en inglés, única y de cultura general."""
    historial = ", ".join(temas_previos) if temas_previos else "Ninguno (es el primer nivel)"
    categoria_actual = categoria_de_nivel(nivel)

    prompt = f"""
    Eres un divulgador experto en cultura general. Genera una lección para una app con la que un
    hispanohablante aprende cultura general Y mejora su inglés leyendo.
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
    4. IDIOMA: TODO el texto y el título deben estar escritos en INGLÉS (nivel {NIVEL_INGLES} del MCER:
       vocabulario variado y preciso, frases claras, sin jerga innecesaria).
    5. Resalta los conceptos clave con negritas en Markdown (**así**). Usa 3 o 4 negritas. NO uses etiquetas HTML.
    6. Estructura: 3 o 4 párrafos cortos (línea en blanco entre ellos) y, al final, un párrafo que
       empiece exactamente por "**Key points to remember:**" con 2 o 3 ideas resumidas en una o dos frases.
    7. Extensión: 300 - 350 palabras. Tono claro, directo y amable, sin florituras.
    8. Título claro y descriptivo en inglés, sin clickbait (máx 6 palabras).
    9. Proporciona una palabra clave EN INGLÉS para buscar la imagen en Wikipedia.
    10. No uses efemérides ("On this day...").

    Devuelve la respuesta ÚNICAMENTE en formato JSON con las claves: "titulo", "texto", "palabra_clave_imagen".
    """

    try:
        datos = _pedir_json(prompt)
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


# ── Traducciones ─────────────────────────────────────────────────────────────
def traducir_en_contexto(palabra, frase):
    """Traduce una palabra inglesa al español según el sentido que tiene en esa frase.

    Devuelve {"traduccion": ..., "tipo": ...} o None si falla.
    """
    prompt = f"""
    Eres un diccionario inglés-español contextual.
    Frase en inglés: "{frase}"
    Palabra o expresión tocada por el alumno: "{palabra}"

    Dime qué significa "{palabra}" en español EN ESTA FRASE CONCRETA (no todas sus acepciones).
    - "traduccion": la traducción al español en ese contexto (1 a 4 palabras; si es un verbo, en infinitivo
      salvo que el contexto pida otra forma).
    - "tipo": categoría gramatical en español, muy breve (p. ej. "verbo", "sustantivo", "adjetivo", "expresión").

    Devuelve ÚNICAMENTE un JSON con las claves "traduccion" y "tipo".
    """
    try:
        datos = _pedir_json(prompt)
        traduccion = str(datos.get("traduccion", "")).strip()
        if not traduccion:
            return None
        return {"traduccion": traduccion, "tipo": str(datos.get("tipo", "")).strip()}
    except Exception as e:
        print(f"Error traduciendo palabra: {e}")
        return None


def traducir_frase(frase):
    """Traduce una frase inglesa al español. Devuelve el texto o None."""
    prompt = f"""
    Traduce al español, de forma natural y fiel, esta frase en inglés:
    "{frase}"
    Devuelve ÚNICAMENTE un JSON con la clave "traduccion".
    """
    try:
        t = str(_pedir_json(prompt).get("traduccion", "")).strip()
        return t or None
    except Exception as e:
        print(f"Error traduciendo frase: {e}")
        return None


def traducir_texto(texto):
    """Traduce una historia completa al español conservando párrafos y **negritas**."""
    prompt = f"""
    Traduce al español, de forma natural y fiel, el siguiente texto en inglés.
    Conserva EXACTAMENTE la estructura de párrafos (línea en blanco entre ellos) y las negritas en
    Markdown (**así**), colocadas sobre los conceptos equivalentes.

    TEXTO:
    {texto}

    Devuelve ÚNICAMENTE un JSON con la clave "traduccion".
    """
    try:
        t = str(_pedir_json(prompt).get("traduccion", "")).strip()
        return t or None
    except Exception as e:
        print(f"Error traduciendo texto: {e}")
        return None


# ── Examen de historias (acumulativo) ────────────────────────────────────────
def generar_quiz(temas):
    """Quiz de 5 preguntas sobre una muestra aleatoria de TODAS las historias completadas.

    `temas` es la lista de dicts {"titulo", "texto", ...}.
    """
    muestra = random.sample(temas, min(QUIZ_HISTORIAS_MUESTRA, len(temas)))
    material = "\n\n".join(f"### {t['titulo']}\n{t['texto']}" for t in muestra)

    prompt = f"""
    Estas son lecciones que el alumno ya ha leído:

    {material}

    Genera un quiz de 5 preguntas para evaluar si entendió y recuerda estas lecciones.
    Reparte las preguntas entre lecciones distintas y pregunta por ideas importantes (causas, mecanismos,
    consecuencias), no por detalles triviales. Redacta TODAS las preguntas y respuestas en INGLÉS.
    Tipos de pregunta (usa EXACTAMENTE estos valores en "tipo"):
    - 2 de "opcion_multiple" (4 opciones; "respuesta_correcta" es el texto exacto de una opción).
    - 1 de "completar" (frase con un hueco "____"; "respuesta_correcta" es una sola palabra).
    - 1 de "redactar" (respuesta corta; "respuesta_correcta" es un ejemplo de buena respuesta).
    - 1 de "verdadero_falso" ("opciones" son ["Verdadero", "Falso"]; "respuesta_correcta" es una de ellas).

    Devuelve la respuesta ÚNICAMENTE en formato JSON con una lista llamada "preguntas".
    Cada pregunta debe tener: "tipo", "pregunta", "opciones" (lista; vacía si no aplica), "respuesta_correcta".
    """

    try:
        return _pedir_json(prompt)
    except Exception as e:
        print(f"Error generando quiz: {e}")
        return {"preguntas": []}


# ── Test de vocabulario ──────────────────────────────────────────────────────
def generar_test_vocabulario(palabras):
    """10 frases NUEVAS en inglés que contienen palabras/frases que el usuario tocó.

    `palabras` es la lista de dicts {"termino", "traduccion", ...} guardados en la base de datos.
    Devuelve {"preguntas": [{"termino", "frase", "traduccion_referencia"}]}.
    """
    muestra = random.sample(palabras, min(TEST_VOCAB_PREGUNTAS, len(palabras)))
    lineas = "\n".join(f'- "{p["termino"]}" (significa: {p["traduccion"]})' for p in muestra)

    prompt = f"""
    Eres profesor de inglés para hispanohablantes. El alumno ha consultado estas palabras o expresiones
    mientras leía:

    {lineas}

    Crea EXACTAMENTE {TEST_VOCAB_PREGUNTAS} ejercicios de traducción inglés → español.
    - Cada ejercicio es una frase NUEVA en inglés (8 a 18 palabras, nivel {NIVEL_INGLES}) que contenga el término.
      No copies frases de ninguna lección: invéntalas con un contexto distinto.
    - Si hay menos de {TEST_VOCAB_PREGUNTAS} términos, reutiliza términos en frases y contextos distintos.
    - Si el término es una frase entera, escribe una frase nueva que use esa misma expresión o idea.
    - Sin frases repetidas. Cada una debe tener sentido por sí sola.
    - "traduccion_referencia": una traducción natural de la frase al español.

    Devuelve ÚNICAMENTE un JSON con la lista "preguntas"; cada elemento con las claves
    "termino" (el término trabajado), "frase" (la frase en inglés) y "traduccion_referencia".
    """

    try:
        datos = _pedir_json(prompt)
        validas = [
            p for p in datos.get("preguntas", [])
            if p.get("frase") and p.get("traduccion_referencia")
        ]
        return {"preguntas": validas[:TEST_VOCAB_PREGUNTAS]}
    except Exception as e:
        print(f"Error generando test de vocabulario: {e}")
        return {"preguntas": []}


def corregir_traducciones(items):
    """Corrige traducciones inglés → español del alumno.

    `items`: lista de dicts {"termino", "frase", "referencia", "respuesta"}.
    Devuelve una lista [{"correcta": bool, "comentario": str}] en el mismo orden, o None si falla.
    """
    if not items:
        return []
    bloques = "\n\n".join(
        f'{i}. Frase: "{it["frase"]}"\n   Término clave: "{it["termino"]}"\n'
        f'   Traducción de referencia: "{it["referencia"]}"\n   Traducción del alumno: "{it["respuesta"]}"'
        for i, it in enumerate(items, start=1)
    )

    prompt = f"""
    Corrige estas traducciones inglés → español hechas por un alumno.

    {bloques}

    Para cada ejercicio decide si la traducción del alumno es correcta:
    - Acepta sinónimos, otro orden de palabras y pequeñas faltas de ortografía o de tildes.
    - Marca incorrecta si traduce mal el término clave o si cambia el sentido de la frase.
    - La traducción de referencia es solo UNA de las traducciones posibles.

    Devuelve ÚNICAMENTE un JSON con la lista "resultados": un objeto por ejercicio, EN EL MISMO ORDEN,
    con "correcta" (true/false) y "comentario" (una frase corta en español; si es incorrecta, explica el fallo).
    """

    try:
        resultados = _pedir_json(prompt).get("resultados", [])
        if len(resultados) != len(items):
            return None
        return [
            {"correcta": bool(r.get("correcta")), "comentario": str(r.get("comentario", "")).strip()}
            for r in resultados
        ]
    except Exception as e:
        print(f"Error corrigiendo traducciones: {e}")
        return None
