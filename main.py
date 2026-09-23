from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests
import threading
import time
import urllib.parse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

def obtener_json_seguro(url_original):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.xdraco.com/nft",
        "Accept": "application/json, text/plain, */*"
    }

    # Intento 1: Conexión directa emulando Chrome 120
    try:
        res = requests.get(url_original, headers=headers, impersonate="chrome120", timeout=8)
        if res.status_code == 200 and res.text.strip().startswith("{"):
            return res.json(), "Directo (Chrome120)"
    except Exception:
        pass

    # Intento 2: Pasarela / Proxy Alternativo 1
    try:
        url_proxy = f"https://api.allorigins.win/raw?url={urllib.parse.quote(url_original)}"
        res = requests.get(url_proxy, headers=headers, impersonate="chrome120", timeout=10)
        if res.status_code == 200 and res.text.strip().startswith("{"):
            return res.json(), "Pasarela AllOrigins"
    except Exception:
        pass

    # Intento 3: Pasarela / Proxy Alternativo 2
    try:
        url_proxy = f"https://corsproxy.io/?{urllib.parse.quote(url_original)}"
        res = requests.get(url_proxy, headers=headers, impersonate="chrome120", timeout=10)
        if res.status_code == 200 and res.text.strip().startswith("{"):
            return res.json(), "Pasarela CorsProxy"
    except Exception:
        pass

    return None, "Bloqueado en todas las rutas"

def actualizar_subastas_xdraco():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    print("🔄 Obteniendo subastas...")
    nfts_acumulados = []
    metodo_usado = ""

    for page in range(1, 5):
        url = f"https://www.xdraco.com/api/nft/lists?listType=sale&languageCode=es&page={page}"
        data, metodo = obtener_json_seguro(url)
        
        if data and "data" in data and "lists" in data["data"]:
            items = data["data"]["lists"]
            nfts_acumulados.extend(items)
            metodo_usado = metodo
        else:
            DIAGNOSTICO_ESTADO = f"Error en página {page}: {metodo}"
            break

    if nfts_acumulados:
        BASE_DE_DATOS_NFTS = nfts_acumulados
        DIAGNOSTICO_ESTADO = f"✅ Éxito usando {metodo_usado}. ({len(nfts_acumulados)} personajes cargados)"

def planificador_background():
    actualizar_subastas_xdraco()
    while True:
        time.sleep(120)
        actualizar_subastas_xdraco()

threading.Thread(target=planificador_background, daemon=True).start()

@app.get("/api/nfts")
def obtener_nfts():
    return {
        "status": "ok", 
        "total": len(BASE_DE_DATOS_NFTS), 
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS
    }
