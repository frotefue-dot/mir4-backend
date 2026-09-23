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
    allow_headers=["*"],
)

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

def extraer_json_de_html(html_text):
    """Extrae objetos o arreglos JSON incrustados en páginas HTML (Next.js, Nuxt, React)."""
    # 1. Buscar en __NEXT_DATA__ (estándar de Next.js usado por HofGamer)
    match_next = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.DOTALL)
    if match_next:
        try:
            data = json.loads(match_next.group(1))
            props = data.get("props", {}).get("pageProps", {})
            for key in ["nfts", "items", "lists", "characters", "data", "list", "results"]:
                if key in props and isinstance(props[key], list) and len(props[key]) > 0:
                    return props[key]
                if isinstance(props.get(key), dict):
                    sub = props[key].get("items") or props[key].get("lists") or props[key].get("data")
                    if isinstance(sub, list) and len(sub) > 0:
                        return sub
        except Exception:
            pass

    # 2. Búsqueda de respaldos en scripts con arreglos JSON
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html_text, re.DOTALL)
    for s in scripts:
        if "character" in s.lower() or "price" in s.lower() or "nft" in s.lower():
            json_matches = re.findall(r'(\[\s*\{.*?\}\s*\])', s, re.DOTALL)
            for jm in json_matches:
                try:
                    parsed = json.loads(jm)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        return parsed
                except Exception:
                    continue
    return None

def actualizar_subastas():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    print("🔄 Consultando HofGamer / xDRACO...")
    nfts_acumulados = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html, application/xhtml+xml, */*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://nft.hofgamer.com/",
    }

    # Fuentes objetivo: HofGamer principal + endpoints API de respaldo
    sources = [
        "https://nft.hofgamer.com/mir4/?limit=48&page=1",
        "https://nft.hofgamer.com/api/mir4?limit=48&page=1",
        "https://nft.hofgamer.com/api/nft?limit=48&page=1",
        "https://gate.xdraco.com/nft/lists?listType=sale&languageCode=es&page=1",
        "https://nftmanager.xdraco.com/api/nft/lists?listType=sale&languageCode=es&page=1"
    ]

    diagnosticos_log = []
    fuente_exitosa = None

    for url in sources:
        try:
            res = requests_cffi.get(url, headers=headers, impersonate="chrome", timeout=12)
            contenido = res.text.strip()

            # Opción A: La URL respondió directamente con JSON
            if res.status_code == 200 and (contenido.startswith("{") or contenido.startswith("[")):
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    nfts_acumulados = data
                    fuente_exitosa = url
                    break
                elif isinstance(data, dict):
                    items = (
                        data.get("data", {}).get("lists") or 
                        data.get("data", {}).get("list") or 
                        data.get("items") or 
                        data.get("data") or 
                        data.get("nfts")
                    )
                    if isinstance(items, list) and len(items) > 0:
                        nfts_acumulados = items
                        fuente_exitosa = url
                        break

            # Opción B: Es HTML (página SSR de HofGamer) -> extraemos el JSON embebido
            elif res.status_code == 200 and contenido.startswith("<"):
                extracted = extraer_json_de_html(contenido)
                if extracted and isinstance(extracted, list) and len(extracted) > 0:
                    nfts_acumulados = extracted
                    fuente_exitosa = f"{url} (extraído de HTML)"
                    break
                else:
                    diagnosticos_log.append(f"{url.split('/')[2]}: HTML recibido sin JSON reconocible")
            else:
                diagnosticos_log.append(f"{url.split('/')[2]}: HTTP {res.status_code}")

        except Exception as e:
            diagnosticos_log.append(f"{url.split('/')[2]}: Error {str(e)}")

    if nfts_acumulados:
        BASE_DE_DATOS_NFTS = nfts_acumulados
        DIAGNOSTICO_ESTADO = f"✅ Éxito total desde {fuente_exitosa}: {len(nfts_acumulados)} personajes cargados."
    else:
        DIAGNOSTICO_ESTADO = "Detalle de intentos: " + " | ".join(diagnosticos_log[:3])

def planificador_background():
    actualizar_subastas()
    while True:
        time.sleep(900)
        actualizar_subastas()

threading.Thread(target=planificador_background, daemon=True).start()

@app.get("/api/nfts")
def obtener_nfts():
    return {
        "status": "ok",
        "total": len(BASE_DE_DATOS_NFTS),
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS
    }
