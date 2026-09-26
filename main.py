from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

BASE_DE_DATOS_NFTS: List[Dict[str, Any]] = []
NFTS_POR_ID: Dict[int, Dict[str, Any]] = {}
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

ANALYSIS_URL = "https://analysis4nft.com:8080/api/v1/filter"

ANALYSIS_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "Origin": "https://www.analysis4nft.com",
    "Pragma": "no-cache",
    "Referer": "https://www.analysis4nft.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
    ),
}

ANALYSIS_BODY_BASE = {
    "legSpritCountMin": 0, "legSpritCountMax": 40,
    "legItemCountMin": 0, "legItemCountMax": 40,
    "legSkillCountMin": 0, "legSkillCountMax": 40,
    "tradeEquipmentCountMin": 0, "tradeEquipmentCountMax": 10,
    "powerScoreMin": 0, "powerScoreMax": 5000000,
    "priceMin": 0, "priceMax": 10000000,
    "lvlMin": 1, "lvlMax": 300,
    "sort": "DESC",
    "property": "sell_date",
    "codexMin": 0, "codexMax": 10000,
    "_classMin": 1, "_classMax": 7,
    "hasTradableItem": False,
    "tradeTypeNft": 0,
    "spiritFilter": [],
    "equipmentFilters": None,
    "regionFilter": "",
    "serverFilter": "",
    "allItemFilterRequestDto": [],
    "statFilterRequestDto": [],
    "farmingFilter": None,
    "ticketFilter": None,
    "skillFilterObj": None,
    "crystalFilterObj": None,
}

SLOT_NAMES = {
    1: "Weapon",
    2: "Necklace",
    3: "Bracelet",
    4: "Ring",
    5: "Armor Top",
    6: "Armor Pants",
    7: "Armor Gloves",
    8: "Armor Shoes",
    9: "Sub-weapon",
    10: "Earring",
}


def parsear_equipo(item_dto: Dict[str, Any]) -> List[Dict[str, Any]]:
    slots = []
    for i in range(1, 11):
        slots.append({
            "slot": i,
            "name": SLOT_NAMES.get(i, f"Slot {i}"),
            "tradeable": bool(item_dto.get(f"_{i}isTradeble", False)),
            "icon": item_dto.get(f"_{i}itemPath", ""),
            "enhance": item_dto.get(f"_{i}enhance"),
            "grade": item_dto.get(f"_{i}grade"),
            "tier": item_dto.get(f"_{i}tier"),
        })
    return slots


def parsear_nft(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    seq = raw.get("seq")
    if seq is None:
        return None

    item_dto = raw.get("itemDetailDto") or {}
    equipo = parsear_equipo(item_dto)
    equipo_trade = [e for e in equipo if e["tradeable"]]

    return {
        "id": seq,
        "name": raw.get("name") or "Desconocido",
        "class": raw.get("className") or "N/A",
        "level": raw.get("lv"),
        "power": raw.get("powerScoreLong"),
        "price_wemix": raw.get("price"),
        "server": raw.get("server"),
        "image": raw.get("imagePath") or "",
        "url": f"https://www.xdraco.com/nft/trade/{seq}",
        "tradable_item_count": raw.get("tradableItemCount", 0),
        "equipment": equipo,
        "tradeable_equipment": equipo_trade,
        "created_ago": raw.get("createdDateString"),
    }


async def obtener_nfts_reales(max_paginas: int = 40):
    global BASE_DE_DATOS_NFTS, NFTS_POR_ID, DIAGNOSTICO_ESTADO
    DIAGNOSTICO_ESTADO = "Consultando analysis4nft.com..."
    nfts_procesados: List[Dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            page = 1
            while page <= max_paginas:
                resp = await client.post(
                    f"{ANALYSIS_URL}?page={page}",
                    headers=ANALYSIS_HEADERS,
                    json=ANALYSIS_BODY_BASE,
                )
                resp.raise_for_status()
                items = resp.json()

                if not isinstance(items, list) or not items:
                    break

                for raw in items:
                    parsed = parsear_nft(raw)
                    if parsed is not None:
                        nfts_procesados.append(parsed)

                page += 1
                await asyncio.sleep(0.4)

        if nfts_procesados:
            BASE_DE_DATOS_NFTS = nfts_procesados
            NFTS_POR_ID = {nft["id"]: nft for nft in nfts_procesados}
            DIAGNOSTICO_ESTADO = f"✅ Éxito: {len(nfts_procesados)} NFTs reales cargados desde analysis4nft.com."
        else:
            DIAGNOSTICO_ESTADO = "⚠️ La API respondió pero sin items."

    except httpx.HTTPStatusError as e:
        DIAGNOSTICO_ESTADO = f"❌ Error HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        DIAGNOSTICO_ESTADO = f"❌ Error: {str(e)}"


async def planificador_background():
    while True:
        await obtener_nfts_reales()
        await asyncio.sleep(900)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(planificador_background())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "diagnostico": DIAGNOSTICO_ESTADO, "total_nfts": len(BASE_DE_DATOS_NFTS)}


@app.get("/api/nfts")
async def obtener_nfts():
    return {
        "status": "ok",
        "total": len(BASE_DE_DATOS_NFTS),
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS,
    }


@app.get("/api/nft/{nft_id}")
async def obtener_nft_detalle(nft_id: int):
    nft = NFTS_POR_ID.get(nft_id)
    if not nft:
        raise HTTPException(status_code=404, detail="NFT no encontrado")
    return {"status": "ok", "nft": nft}
