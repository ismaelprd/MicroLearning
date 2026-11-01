import os
import requests
from google import genai
from google.genai import types
import json

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_ID = "gemini-3.5-flash-lite"

def buscar_imagen_wikipedia(tema):
    """Busca una imagen en Wikipedia. Si falla, devuelve None."""
    try:
        headers = {'User-Agent': 'MiAppCultura/1.0 (test@example.com)'}
        url_busqueda = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={tema}&format=json&utf8=1&srlimit=1"
        res = requests.get(url_busqueda, headers=headers, timeout=5)
        data = res.json()
        
        if data.get('query', {}).get('search'):
            titulo = data['query']['search'][0]['title']
            url_imagen = f"https://es.wikipedia.org/w/api.php?action=query&titles={titulo}&prop=pageimages&format=json&pithumbsize=600"
            res_img = requests.get(url_imagen, headers=headers, timeout=5)
            data_img = res_img.json()
            
            pages = data_img.get('query', {}).get('pages', {})
            for page_id in pages:
                if 'thumbnail' in pages[page_id]:
                    return pages[page_id]['thumbnail']['source']
    except Exception as e:
        print(f"Error buscando imagen: {e}")
    return None

def generar_microaprendizaje(nivel):
    """Genera una píldora un poco más larga (aprox 350 palabras)."""
    prompt = f"""
    Eres un experto divulgador de cultura general. Genera un microaprendizaje para el nivel {nivel} de una app.
    Elige un tema fascinante (hecho histórico, científico, personaje, arte, etc.) que sea sorprendente.
    
    Requisitos:
    1. Escribe un texto ameno y narrativo de aproximadamente 350 palabras (unos 2 minutos y medio de lectura).
    2. Incluye un título llamativo.
    3. Al final, proporciona una palabra clave exacta (en español) para buscar una imagen representativa en Wikipedia.
    
    Devuelve la respuesta ÚNICAMENTE en formato JSON con las claves: "titulo", "texto", "palabra_clave_imagen".
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        datos = json.loads(response.text)
        imagen_url = buscar_imagen_wikipedia(datos.get("palabra_clave_imagen", ""))
        datos["imagen_url"] = imagen_url
        return datos
    except Exception as e:
        print(f"Error con Gemini: {e}")
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
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        return json.loads(response.text)
    except:
        return {"preguntas": []}