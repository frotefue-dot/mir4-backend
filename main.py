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
    print("🔄 Consultando subastas a xDRACO...")
    nfts_acumulados = []
    
    # Cabeceras requeridas para emular un navegador real
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.xdraco.com/nft",
        "Accept": "application/json, text/plain, */*"
    }
    
    for page in range(1, 5):
        url = f"https://www.xdraco.com/api/nft/lists?listType=sale&languageCode=es&page={page}"
        try:
            response = requests.get(url, headers=headers, impersonate="chrome120", timeout=15)
            if response.status_code == 200:
                data = response.json()
                items = data.get("data", {}).get("lists", [])
                nfts_acumulados.extend(items)
        except Exception as e:
            print(f"Error en página {page}: {e}")
            
    if nfts_acumulados:
        BASE_DE_DATOS_NFTS = nfts_acumulados
        print(f"✅ Descarga exitosa: {len(BASE_DE_DATOS_NFTS)} personajes guardados.")

def planificador_background():
    # Ejecutar una descarga inmediata al iniciar
    actualizar_subastas_xdraco()
    while True:
        time.sleep(120)
        actualizar_subastas_xdraco()

# Iniciar hilo secundario
threading.Thread(target=planificador_background, daemon=True).start()

@app.get("/api/nfts")
def obtener_nfts():
    return {"status": "ok", "total": len(BASE_DE_DATOS_NFTS), "items": BASE_DE_DATOS_NFTS}
