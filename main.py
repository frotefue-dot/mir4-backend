from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests as requests_cffi
import threading
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

def actualizar_subastas_xdraco():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    print("🔄 Consultando xDRACO...")
    nfts_acumulados = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.xdraco.com/",
        "Origin": "https://www.xdraco.com",
        "Accept": "application/json, text/plain, */*"
    }

    # Rutas API conocidas de xDRACO
    base_urls = [
        "https://api.xdraco.com/nft/lists",
        "https://api.xdraco.com/api/nft/lists"
    ]

    for page in range(1, 4):
        exito_pagina = False
        
        for base_url in base_urls:
            url_target = f"{base_url}?listType=sale&languageCode=es&page={page}"
            
            try:
                res = requests_cffi.get(url_target, headers=headers, impersonate="chrome", timeout=15)
                contenido = res.text.strip()
                
                if res.status_code == 200 and contenido.startswith("{"):
                    data = res.json()
                    items = data.get("data", {}).get("lists", []) or data.get("data", {}).get("list", [])
                    if isinstance(items, list):
                        nfts_acumulados.extend(items)
                        exito_pagina = True
                        break
                else:
                    DIAGNOSTICO_ESTADO = f"Página {page} en {base_url}: HTTP {res.status_code} - Respuesta: {contenido[:80]}"
            except Exception as e:
                DIAGNOSTICO_ESTADO = f"Error en página {page} con {base_url}: {str(e)}"

        if not exito_pagina and not nfts_acumulados:
            break

    if nfts_acumulados:
        BASE_DE_DATOS_NFTS = nfts_acumulados
        DIAGNOSTICO_ESTADO = f"✅ Éxito total: {len(nfts_acumulados)} personajes cargados desde xDRACO."

def planificador_background():
    actualizar_subastas_xdraco()
    while True:
        time.sleep(900)
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
