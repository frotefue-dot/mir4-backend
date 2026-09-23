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
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

def actualizar_subastas_xdraco():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    print("🔄 Intentando conectar con xDRACO...")
    nfts_acumulados = []
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "es-ES,es;q=0.9,en;q=0.8",
        "referer": "https://www.xdraco.com/nft",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Probar diferentes firmas de navegador para evadir Cloudflare en Render
    versiones = ["chrome120", "chrome119", "safari15_5"]
    
    for version in versiones:
        if nfts_acumulados:
            break
            
        for page in range(1, 4):
            url = f"https://www.xdraco.com/api/nft/lists?listType=sale&languageCode=es&page={page}"
            try:
                res = requests.get(url, headers=headers, impersonate=version, timeout=12)
                
                if res.status_code == 200:
                    data = res.json()
                    items = data.get("data", {}).get("lists", [])
                    nfts_acumulados.extend(items)
                    DIAGNOSTICO_ESTADO = f"Éxito con {version}. Carga completada."
                else:
                    DIAGNOSTICO_ESTADO = f"Bloqueo Cloudflare: HTTP {res.status_code} al usar {version}"
                    print(f"⚠️ {DIAGNOSTICO_ESTADO}")
                    break
            except Exception as e:
                DIAGNOSTICO_ESTADO = f"Error de conexión: {str(e)}"
                print(f"❌ {DIAGNOSTICO_ESTADO}")
                break

    if nfts_acumulados:
        BASE_DE_DATOS_NFTS = nfts_acumulados

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
def obtener_nfts():
    return {"status": "ok", "total": len(BASE_DE_DATOS_NFTS), "items": BASE_DE_DATOS_NFTS}
