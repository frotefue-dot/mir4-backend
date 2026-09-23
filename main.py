from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests as requests_cffi
import threading
import time
import json
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
)

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

def extraer_json_de_scripts(html_text):
    """Analiza todas las etiquetas <script> en búsqueda de datos de NFTs."""
    # 1. Buscar variables globales de estado comunes (window.__DATA__, window.__INITIAL_STATE__, etc.)
    var_patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        r'window\.__DATA__\s*=\s*(\{.*?\});',
        r'window\.__NUXT__\s*=\s*(\{.*?\});',
        r'let\s+data\s*=\s*(\{.*?\});',
        r'const\s+nfts\s*=\s*(\[.*?\]);'
    ]
    
    for pattern in var_patterns:
        match = re.search(pattern, html_text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, list) and len(parsed) > 0:
                    return parsed, "Variable global (lista)"
                elif isinstance(parsed, dict):
                    # Recorrer dict buscando listas de items
                    for k in ["nfts", "items", "lists", "characters", "data", "results"]:
                        val = parsed.get(k)
                        if isinstance(val, list) and len(val) > 0:
                            return val, f"Variable global ({k})"
            except Exception:
                continue

    # 2. Buscar cualquier estructura JSON tipo lista de objetos dentro de scripts
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html_text, re.DOTALL)
    for index, script in enumerate(scripts):
        if any(term in script.lower() for term in ["character", "price", "nft", "seller", "token"]):
            # Buscar arreglos JSON dentro del script
            json_arrays = re.findall(r'(\[\s*\{.*?\}\s*\])', script, re.DOTALL)
            for jm in json_arrays:
                try:
                    data = json.loads(jm)
                    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                        return data, f"Script #{index+1} (arreglo embebido)"
                except Exception:
                    continue

    return None, "No se encontraron datos estructurados en el HTML"

def actualizar_subastas_hofgamer():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    print("🔄 Consultando HofGamer MIR4...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html, application/xhtml+xml, */*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://nft.hofgamer.com/",
        "X-Requested-With": "XMLHttpRequest"
    }

    # Endpoints a probar en orden de prioridad
    urls_objetivo = [
        "https://nft.hofgamer.com/mir4/?limit=48&page=1",
        "https://nft.hofgamer.com/api/mir4?limit=48&page=1",
        "https://nft.hofgamer.com/api/v1/mir4?limit=48&page=1",
        "https://nft.hofgamer.com/api/nft/mir4?limit=48&page=1"
    ]

    diagnosticos = []
    exito = False

    for url in urls_objetivo:
        try:
            res = requests_cffi.get(url, headers=headers, impersonate="chrome", timeout=15)
            contenido = res.text.strip()

            if res.status_code == 200:
                # Caso A: Respuesta directa en JSON (API)
                if contenido.startswith("{") or contenido.startswith("["):
                    try:
                        data = res.json()
                        items = data if isinstance(data, list) else (
                            data.get("data") or data.get("items") or data.get("nfts") or data.get("lists")
                        )
                        if isinstance(items, list) and len(items) > 0:
                            BASE_DE_DATOS_NFTS = items
                            DIAGNOSTICO_ESTADO = f"✅ Éxito JSON desde {url}: {len(items)} items cargados."
                            exito = True
                            break
                    except Exception:
                        pass

                # Caso B: Respuesta en HTML
                elif contenido.startswith("<"):
                    items, detalle = extraer_json_de_scripts(contenido)
                    if items and len(items) > 0:
                        BASE_DE_DATOS_NFTS = items
                        DIAGNOSTICO_ESTADO = f"✅ Éxito extraído de HTML ({url}): {len(items)} items ({detalle})."
                        exito = True
                        break
                    else:
                        diagnosticos.append(f"{url.split('?')[0]}: {detalle}")
            else:
                diagnosticos.append(f"{url.split('?')[0]}: HTTP {res.status_code}")

        except Exception as e:
            diagnosticos.append(f"{url.split('?')[0]}: Error {str(e)}")

    if not exito:
        DIAGNOSTICO_ESTADO = "Intentos HofGamer: " + " | ".join(diagnosticos[:2])

def planificador_background():
    actualizar_subastas_hofgamer()
    while True:
        time.sleep(900)
        actualizar_subastas_hofgamer()

threading.Thread(target=planificador_background, daemon=True).start()

@app.get("/api/nfts")
def obtener_nfts():
    return {
        "status": "ok",
        "total": len(BASE_DE_DATOS_NFTS),
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS
    }
