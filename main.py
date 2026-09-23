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

# Lista de servidores backend conocidos de WeMade / xDRACO para NFT
CANDIDATE_ENDPOINTS = [
    "https://draco-nft.wemade.games/api/v1/nft/lists",
    "https://draco-nft.wemade.games/api/nft/lists",
    "https://nft-api.xdraco.com/api/v1/nft/lists",
    "https://nft-api.xdraco.com/api/nft/lists",
    "https://www.xdraco.com/api/v1/nft/lists"
]

def actualizar_subastas_xdraco():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    print("🔄 Escaneando endpoints backend de xDRACO...")
    nfts_acumulados = []
    endpoint_activo = None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.xdraco.com",
        "Referer": "https://www.xdraco.com/nft",
        "X-Requested-With": "XMLHttpRequest"
    }

    # 1. Identificar cuál endpoint responde JSON
    diagnosticos_log = []
    for base_url in CANDIDATE_ENDPOINTS:
        test_url = f"{base_url}?listType=sale&languageCode=es&page=1"
        try:
            res = requests_cffi.get(test_url, headers=headers, impersonate="chrome", timeout=10)
            contenido = res.text.strip()
            
            if res.status_code == 200 and contenido.startswith("{"):
                endpoint_activo = base_url
                break
            else:
                tipo = "HTML" if contenido.startswith("<") else f"HTTP {res.status_code}"
                diagnosticos_log.append(f"{base_url.split('/')[2]}: {tipo}")
        except Exception as e:
            diagnosticos_log.append(f"{base_url.split('/')[2]}: Error de red")

    if not endpoint_activo:
        DIAGNOSTICO_ESTADO = "Ningún endpoint respondió JSON. Intentos: " + " | ".join(diagnosticos_log[:3])
        return

    # 2. Descargar páginas del endpoint activo
    for page in range(1, 4):
        url_target = f"{endpoint_activo}?listType=sale&languageCode=es&page={page}"
        try:
            res = requests_cffi.get(url_target, headers=headers, impersonate="chrome", timeout=15)
            if res.status_code == 200 and res.text.strip().startswith("{"):
                data = res.json()
                items = data.get("data", {}).get("lists", []) or data.get("data", {}).get("list", [])
                if isinstance(items, list):
                    nfts_acumulados.extend(items)
        except Exception as e:
            break

    if nfts_acumulados:
        BASE_DE_DATOS_NFTS = nfts_acumulados
        DIAGNOSTICO_ESTADO = f"✅ Éxito ({endpoint_activo.split('/')[2]}): {len(nfts_acumulados)} personajes cargados."
    else:
        DIAGNOSTICO_ESTADO = f"Conectado a {endpoint_activo} pero no se encontraron items."

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
