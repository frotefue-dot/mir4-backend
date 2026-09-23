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
    print("🔄 Consultando xDRACO con huella TLS de Chrome...")
    nfts_acumulados = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.xdraco.com/nft",
        "Origin": "https://www.xdraco.com",
        "Accept": "application/json, text/plain, */*"
    }

    # Dominios principales válidos
    candidate_urls = [
        "https://www.xdraco.com/api/nft/lists",
        "https://xdraco.com/api/nft/lists"
    ]

    diagnosticos_intentos = []

    for page in range(1, 4):
        exito_pagina = False

        for base_url in candidate_urls:
            url_target = f"{base_url}?listType=sale&languageCode=es&page={page}"
            
            try:
                res = requests_cffi.get(url_target, headers=headers, impersonate="chrome", timeout=15)
                contenido = res.text.strip()

                if res.status_code == 200 and contenido.startswith("{"):
                    data = res.json()
                    items = data.get("data", {}).get("lists", []) or data.get("data", {}).get("list", [])
                    if isinstance(items, list) and len(items) > 0:
                        nfts_acumulados.extend(items)
                        exito_pagina = True
                        break
                    elif isinstance(items, list):
                        diagnosticos_intentos.append(f"{base_url}: Respuesta 200 pero 0 items")
                else:
                    preview = contenido[:60].replace("\n", " ")
                    diagnosticos_intentos.append(f"{base_url}: HTTP {res.status_code} ({preview})")
            except Exception as e:
                diagnosticos_intentos.append(f"{base_url}: Error {str(e)}")

        if not exito_pagina and not nfts_acumulados:
            DIAGNOSTICO_ESTADO = " | ".join(diagnosticos_intentos[:2])
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
