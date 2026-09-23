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

def extraer_datos_nextjs(html_text):
    """Extrae y busca recursivamente arreglos de NFTs dentro de __NEXT_DATA__ de HofGamer."""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.DOTALL)
    if not match:
        return None, "No se encontró la etiqueta __NEXT_DATA__"

    try:
        payload = json.loads(match.group(1))
        page_props = payload.get("props", {}).get("pageProps", {})

        # Función recursiva para ubicar listas de objetos en pageProps
        def buscar_arreglos(obj, path=""):
            resultados = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_path = f"{path}.{k}" if path else k
                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                        resultados.append((new_path, v))
                    elif isinstance(v, (dict, list)):
                        resultados.extend(buscar_arreglos(v, new_path))
            elif isinstance(obj, list):
                for i, elem in enumerate(obj):
                    if isinstance(elem, (dict, list)):
                        resultados.extend(buscar_arreglos(elem, f"{path}[{i}]"))
            return resultados

        encontrados = buscar_arreglos(page_props)
        if encontrados:
            # Selecciona el arreglo con mayor cantidad de elementos
            encontrados.sort(key=lambda x: len(x[1]), reverse=True)
            path, items = encontrados[0]
            return items, f"Extraído de __NEXT_DATA__ ({path}, {len(items)} items)"
        
        keys = list(page_props.keys())
        return None, f"__NEXT_DATA__ detectado. Claves disponibles: {keys}"

    except Exception as e:
        return None, f"Error al procesar JSON de __NEXT_DATA__: {str(e)}"

def actualizar_subastas_hofgamer():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    print("🔄 Escaneando HofGamer NFT...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://nft.hofgamer.com/",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    # Rutas principales de HofGamer
    urls_hofgamer = [
        "https://nft.hofgamer.com/",
        "https://nft.hofgamer.com/nft",
        "https://nft.hofgamer.com/market",
        "https://nft.hofgamer.com/api/nfts",
        "https://nft.hofgamer.com/api/nft",
        "https://nft.hofgamer.com/api/market"
    ]

    diagnosticos = []
    exito = False

    for url in urls_hofgamer:
        try:
            res = requests_cffi.get(url, headers=headers, impersonate="chrome", timeout=15)
            contenido = res.text.strip()

            if res.status_code == 200:
                # Opción 1: La URL responde JSON directamente
                if contenido.startswith("{") or contenido.startswith("["):
                    try:
                        data = res.json()
                        items = data if isinstance(data, list) else data.get("data") or data.get("items") or data.get("nfts")
                        if isinstance(items, list) and len(items) > 0:
                            BASE_DE_DATOS_NFTS = items
                            DIAGNOSTICO_ESTADO = f"✅ Éxito directo JSON desde {url}: {len(items)} items cargados."
                            exito = True
                            break
                    except Exception:
                        pass
                
                # Opción 2: Responde HTML (página SSR Next.js)
                elif contenido.startswith("<"):
                    items, msg = extraer_datos_nextjs(contenido)
                    if items and len(items) > 0:
                        BASE_DE_DATOS_NFTS = items
                        DIAGNOSTICO_ESTADO = f"✅ Éxito desde {url}: {msg}"
                        exito = True
                        break
                    else:
                        diagnosticos.append(f"{url.split('/')[-1] or 'root'}: {msg}")
            else:
                diagnosticos.append(f"{url.split('/')[-1] or 'root'}: HTTP {res.status_code}")

        except Exception as e:
            diagnosticos.append(f"{url.split('/')[-1] or 'root'}: Error {str(e)}")

    if not exito:
        DIAGNOSTICO_ESTADO = "Diagnóstico HofGamer: " + " | ".join(diagnosticos[:2])

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
