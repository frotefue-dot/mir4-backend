from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests
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

def actualizar_subastas_xdraco():
    global BASE_DE_DATOS_NFTS
    nfts_acumulados = []
    
    for page in range(1, 4):
        url = f"https://www.xdraco.com/api/nft/lists?listType=sale&languageCode=es&page={page}"
        try:
            response = requests.get(url, impersonate="chrome120", timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get("data", {}).get("lists", [])
                nfts_acumulados.extend(items)
        except Exception:
            pass
            
    if nfts_acumulados:
        BASE_DE_DATOS_NFTS = nfts_acumulados

def planificador_background():
    while True:
        actualizar_subastas_xdraco()
        time.sleep(120)

threading.Thread(target=planificador_background, daemon=True).start()

@app.get("/api/nfts")
def obtener_nfts():
    return {"status": "ok", "total": len(BASE_DE_DATOS_NFTS), "items": BASE_DE_DATOS_NFTS}
