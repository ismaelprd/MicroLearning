import os
import requests
from google import genai
from google.genai import types
import json

# Configura tu API Key (en Render la pondrás como variable de entorno)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# Modelo que solicitaste
MODEL_ID = "gemini-3.5-flash-lite"

def buscar_imagen_wikipedia(tema):
    """Busca una imagen en Wikipedia relacionada con el tema."""
    try:
        # Buscamos el artículo
        url_busqueda = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={tema}&format=json&utf8=1&srlimit=1"
        headers = {'User-Agent': 'MiAppCultura/1.0'}
        res = requests.get(url_busqueda, headers=headers, timeout=5)
        data = res.json()
        
        if data['query']['search']:
            titulo = data['query']['search'][0]['title']
            # Buscamos la imagen principal de ese artículo
            url_imagen = f"https://es.wikipedia.org/w/api.php?action=query&titles={titulo}&prop=pageimages&format=json&pithumbsize=500"
            res_img = requests.get(url_imagen, headers=headers, timeout=5)
            data_img = res_img.json()
            
            pages = data_img['query']['pages']
            for page_id in pages:
                if 'thumbnail' in pages[page_id]:
                    return pages[page_id]['thumbnail']['source']
    except Exception as e:
        print(f"Error buscando imagen: {e}")
    return None

def generar_microaprendizaje(nivel):
    """Genera una píldora de conocimiento de 2 minutos sobre un tema."""
    prompt = f"""
    Eres un experto divulgador de cultura general. Genera un microaprendizaje para el nivel {nivel} de una app.
    Elige un tema interesante (hecho histórico, científico, personaje, etc.) que no se haya tratado antes.
    
    Requisitos:
    1. El texto debe ser ameno y durar máximo 2 minutos de lectura (aprox. 250-300 palabras).
    2. Incluye un título llamativo.
    3. Al final, proporciona una palabra clave exacta (en español) para buscar una imagen en Wikipedia sobre el tema.
    
    Devuelve la respuesta ÚNICAMENTE en formato JSON con las claves: "titulo", "texto", "palabra_clave_imagen".
    """
    
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        )
    )
    
    try:
        datos = json.loads(response.text)
        # Buscamos la imagen
        imagen_url = buscar_imagen_wikipedia(datos.get("palabra_clave_imagen", ""))
        datos["imagen_url"] = imagen_url
        return datos
    except:
        return {
            "titulo": "Error de conexión",
            "texto": "No se pudo generar el contenido. Inténtalo de nuevo.",
            "imagen_url": None
        }

def generar_quiz(temas_previos):
    """Genera un quiz variado basado en los temas aprendidos."""
    contexto = "Temas aprendidos previamente: " + ", ".join(temas_previos)
    
    prompt = f"""
    {contexto}
    
    Genera un quiz de 5 preguntas para evaluar el conocimiento sobre estos temas.
    Varía los tipos de pregunta:
    - 2 de opción múltiple (4 opciones).
    - 1 de completar el hueco (con una palabra).
    - 1 de redactar (respuesta corta).
    - 1 de verdadero/falso.
    
    Devuelve la respuesta ÚNICAMENTE en formato JSON con una lista llamada "preguntas".
    Cada pregunta debe tener: "tipo", "pregunta", "opciones" (si aplica), "respuesta_correcta".
    """
    
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        )
    )
    
    try:
        return json.loads(response.text)
    except:
        return {"preguntas": []}