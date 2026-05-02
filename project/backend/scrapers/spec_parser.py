"""
GulfDeals — Spec Parser
Extracts and normalizes product specifications from titles, descriptions,
and structured tech-spec tables for GPUs, CPUs, and gaming laptops.
"""

import re
from typing import Optional


# ─── GPU ──────────────────────────────────────────────────────────────────────

# Ordered longest-match first so "RTX 4070 Ti Super" wins over "RTX 4070"
GPU_CHIPS = [
    # NVIDIA Ada Lovelace
    "RTX 4090", "RTX 4080 Super", "RTX 4080", "RTX 4070 Ti Super",
    "RTX 4070 Ti", "RTX 4070 Super", "RTX 4070", "RTX 4060 Ti", "RTX 4060",
    # NVIDIA Ampere
    "RTX 3090 Ti", "RTX 3090", "RTX 3080 Ti", "RTX 3080",
    "RTX 3070 Ti", "RTX 3070", "RTX 3060 Ti", "RTX 3060",
    # AMD RDNA 3
    "RX 7900 XTX", "RX 7900 XT", "RX 7900 GRE", "RX 7800 XT",
    "RX 7700 XT", "RX 7600 XT", "RX 7600",
    # AMD RDNA 2
    "RX 6950 XT", "RX 6900 XT", "RX 6800 XT", "RX 6800",
    "RX 6750 XT", "RX 6700 XT", "RX 6700", "RX 6650 XT",
    "RX 6600 XT", "RX 6600", "RX 6500 XT",
    # Intel Arc
    "Arc A770", "Arc A750", "Arc A580", "Arc A380",
]

GPU_VRAM_SIZES = {
    "RTX 4090": 24, "RTX 4080 Super": 16, "RTX 4080": 16,
    "RTX 4070 Ti Super": 16, "RTX 4070 Ti": 12, "RTX 4070 Super": 12,
    "RTX 4070": 12, "RTX 4060 Ti": 16, "RTX 4060": 8,
    "RTX 3090 Ti": 24, "RTX 3090": 24, "RTX 3080 Ti": 12, "RTX 3080": 10,
    "RTX 3070 Ti": 8, "RTX 3070": 8, "RTX 3060 Ti": 8, "RTX 3060": 12,
    "RX 7900 XTX": 24, "RX 7900 XT": 20, "RX 7900 GRE": 16,
    "RX 7800 XT": 16, "RX 7700 XT": 12, "RX 7600 XT": 16, "RX 7600": 8,
    "RX 6950 XT": 16, "RX 6900 XT": 16, "RX 6800 XT": 16, "RX 6800": 16,
    "RX 6750 XT": 12, "RX 6700 XT": 12, "RX 6700": 12,
    "RX 6650 XT": 8, "RX 6600 XT": 8, "RX 6600": 8,
    "Arc A770": 16, "Arc A750": 8, "Arc A580": 8, "Arc A380": 6,
}

GPU_VRAM_TYPES = {
    "RTX 4090": "GDDR6X", "RTX 4080 Super": "GDDR6X", "RTX 4080": "GDDR6X",
    "RTX 4070 Ti Super": "GDDR6X", "RTX 4070 Ti": "GDDR6X",
    "RTX 4070 Super": "GDDR6X", "RTX 4070": "GDDR6X",
    "RTX 4060 Ti": "GDDR6", "RTX 4060": "GDDR6",
    "RX 7900 XTX": "GDDR6", "RX 7900 XT": "GDDR6", "RX 7900 GRE": "GDDR6",
    "RX 7800 XT": "GDDR6", "RX 7700 XT": "GDDR6", "RX 7600": "GDDR6",
}

GPU_CUDA_CORES = {
    "RTX 4090": 16384, "RTX 4080 Super": 10240, "RTX 4080": 9728,
    "RTX 4070 Ti Super": 8448, "RTX 4070 Ti": 7680, "RTX 4070 Super": 7168,
    "RTX 4070": 5888, "RTX 4060 Ti": 4352, "RTX 4060": 3072,
    "RTX 3090 Ti": 10752, "RTX 3090": 10496, "RTX 3080 Ti": 10240,
    "RTX 3080": 8704, "RTX 3070 Ti": 6144, "RTX 3070": 5888,
    "RTX 3060 Ti": 4864, "RTX 3060": 3584,
}

GPU_STREAM_PROCESSORS = {
    "RX 7900 XTX": 12288, "RX 7900 XT": 10752, "RX 7900 GRE": 9728,
    "RX 7800 XT": 3840, "RX 7700 XT": 3456, "RX 7600 XT": 2048, "RX 7600": 2048,
    "RX 6950 XT": 4096, "RX 6900 XT": 4096, "RX 6800 XT": 4096, "RX 6800": 3840,
}

GPU_TDP = {
    "RTX 4090": 450, "RTX 4080 Super": 320, "RTX 4080": 320,
    "RTX 4070 Ti Super": 285, "RTX 4070 Ti": 285, "RTX 4070 Super": 220,
    "RTX 4070": 200, "RTX 4060 Ti": 165, "RTX 4060": 115,
    "RX 7900 XTX": 355, "RX 7900 XT": 315, "RX 7900 GRE": 260,
    "RX 7800 XT": 263, "RX 7700 XT": 190, "RX 7600": 165,
}

GPU_AIB_BRANDS = [
    "ASUS", "MSI", "Gigabyte", "EVGA", "Sapphire", "PowerColor",
    "Zotac", "XFX", "PNY", "Colorful", "Gainward", "Palit", "Inno3D",
]

GPU_SERIES_NAMES = {
    "ASUS": ["ROG STRIX", "ROG Strix", "TUF Gaming", "Dual", "Phoenix", "ProArt"],
    "MSI": ["Gaming X Trio", "Gaming X", "Suprim X", "Suprim", "Ventus 3X", "Ventus 2X"],
    "Gigabyte": ["AORUS Master", "AORUS Elite", "Gaming OC", "Eagle OC", "Windforce"],
    "Zotac": ["Trinity OC", "Trinity", "Amp Extreme Airo", "Amp Airo", "Amp"],
    "Sapphire": ["Nitro+", "Pulse", "Pure"],
    "PowerColor": ["Red Devil", "Hellhound", "Fighter"],
}


# ─── CPU ──────────────────────────────────────────────────────────────────────

CPU_SOCKET_MAP = {
    # Intel
    "i9-14": "LGA1700", "i9-13": "LGA1700", "i9-12": "LGA1700",
    "i7-14": "LGA1700", "i7-13": "LGA1700", "i7-12": "LGA1700",
    "i5-14": "LGA1700", "i5-13": "LGA1700", "i5-12": "LGA1700",
    "i3-14": "LGA1700", "i3-13": "LGA1700",
    "i9-13900K": "LGA1700", "Core Ultra 9": "LGA1851",
    "Core Ultra 7": "LGA1851", "Core Ultra 5": "LGA1851",
    # AMD
    "Ryzen 9 7": "AM5", "Ryzen 9 9": "AM5",
    "Ryzen 7 7": "AM5", "Ryzen 7 9": "AM5",
    "Ryzen 5 7": "AM5", "Ryzen 5 9": "AM5",
    "Ryzen 9 5": "AM4", "Ryzen 7 5": "AM4",
    "Ryzen 5 5": "AM4", "Ryzen 3 5": "AM4",
    "Ryzen 9 3": "AM4", "Ryzen 7 3": "AM4",
    # Threadripper
    "Threadripper 7": "sTR5", "Threadripper 5": "sWRX8",
    "Threadripper 3": "sTRX4",
}

CPU_SPECS = {
    # Intel 14th Gen
    "i9-14900KS": {"cores": 24, "threads": 32, "base_ghz": 3.2, "boost_ghz": 6.2, "tdp": 150, "l3_mb": 36, "igpu": "Intel UHD 770"},
    "i9-14900K":  {"cores": 24, "threads": 32, "base_ghz": 3.2, "boost_ghz": 6.0, "tdp": 125, "l3_mb": 36, "igpu": "Intel UHD 770"},
    "i9-14900F":  {"cores": 24, "threads": 32, "base_ghz": 2.0, "boost_ghz": 5.8, "tdp": 65, "l3_mb": 36, "igpu": None},
    "i7-14700K":  {"cores": 20, "threads": 28, "base_ghz": 3.4, "boost_ghz": 5.6, "tdp": 125, "l3_mb": 33, "igpu": "Intel UHD 770"},
    "i7-14700KF": {"cores": 20, "threads": 28, "base_ghz": 3.4, "boost_ghz": 5.6, "tdp": 125, "l3_mb": 33, "igpu": None},
    "i7-14700F":  {"cores": 20, "threads": 28, "base_ghz": 2.1, "boost_ghz": 5.4, "tdp": 65, "l3_mb": 33, "igpu": None},
    "i5-14600K":  {"cores": 14, "threads": 20, "base_ghz": 3.5, "boost_ghz": 5.3, "tdp": 125, "l3_mb": 24, "igpu": "Intel UHD 770"},
    "i5-14600KF": {"cores": 14, "threads": 20, "base_ghz": 3.5, "boost_ghz": 5.3, "tdp": 125, "l3_mb": 24, "igpu": None},
    "i5-14400F":  {"cores": 10, "threads": 16, "base_ghz": 2.5, "boost_ghz": 4.7, "tdp": 65, "l3_mb": 20, "igpu": None},
    # Intel 13th Gen
    "i9-13900KS": {"cores": 24, "threads": 32, "base_ghz": 3.2, "boost_ghz": 6.0, "tdp": 150, "l3_mb": 36, "igpu": "Intel UHD 770"},
    "i9-13900K":  {"cores": 24, "threads": 32, "base_ghz": 3.0, "boost_ghz": 5.8, "tdp": 125, "l3_mb": 36, "igpu": "Intel UHD 770"},
    "i7-13700K":  {"cores": 16, "threads": 24, "base_ghz": 3.4, "boost_ghz": 5.4, "tdp": 125, "l3_mb": 30, "igpu": "Intel UHD 770"},
    "i5-13600K":  {"cores": 14, "threads": 20, "base_ghz": 3.5, "boost_ghz": 5.1, "tdp": 125, "l3_mb": 24, "igpu": "Intel UHD 770"},
    # AMD Ryzen 9000 (Zen 5)
    "Ryzen 9 9950X":  {"cores": 16, "threads": 32, "base_ghz": 4.3, "boost_ghz": 5.7, "tdp": 170, "l3_mb": 64, "igpu": None},
    "Ryzen 9 9900X":  {"cores": 12, "threads": 24, "base_ghz": 4.4, "boost_ghz": 5.6, "tdp": 120, "l3_mb": 64, "igpu": None},
    "Ryzen 7 9700X":  {"cores": 8,  "threads": 16, "base_ghz": 3.8, "boost_ghz": 5.5, "tdp": 65, "l3_mb": 32, "igpu": None},
    "Ryzen 5 9600X":  {"cores": 6,  "threads": 12, "base_ghz": 3.9, "boost_ghz": 5.4, "tdp": 65, "l3_mb": 32, "igpu": None},
    # AMD Ryzen 7000 (Zen 4)
    "Ryzen 9 7950X3D": {"cores": 16, "threads": 32, "base_ghz": 4.2, "boost_ghz": 5.7, "tdp": 120, "l3_mb": 128, "igpu": "Radeon Graphics"},
    "Ryzen 9 7950X":   {"cores": 16, "threads": 32, "base_ghz": 4.5, "boost_ghz": 5.7, "tdp": 170, "l3_mb": 64, "igpu": "Radeon Graphics"},
    "Ryzen 9 7900X3D": {"cores": 12, "threads": 24, "base_ghz": 4.4, "boost_ghz": 5.6, "tdp": 120, "l3_mb": 128, "igpu": "Radeon Graphics"},
    "Ryzen 9 7900X":   {"cores": 12, "threads": 24, "base_ghz": 4.7, "boost_ghz": 5.6, "tdp": 170, "l3_mb": 64, "igpu": "Radeon Graphics"},
    "Ryzen 9 7900":    {"cores": 12, "threads": 24, "base_ghz": 3.7, "boost_ghz": 5.4, "tdp": 65,  "l3_mb": 64, "igpu": "Radeon Graphics"},
    "Ryzen 7 7800X3D": {"cores": 8,  "threads": 16, "base_ghz": 4.5, "boost_ghz": 5.0, "tdp": 120, "l3_mb": 96, "igpu": "Radeon Graphics"},
    "Ryzen 7 7700X":   {"cores": 8,  "threads": 16, "base_ghz": 4.5, "boost_ghz": 5.4, "tdp": 105, "l3_mb": 32, "igpu": "Radeon Graphics"},
    "Ryzen 7 7700":    {"cores": 8,  "threads": 16, "base_ghz": 3.8, "boost_ghz": 5.3, "tdp": 65,  "l3_mb": 32, "igpu": "Radeon Graphics"},
    "Ryzen 5 7600X":   {"cores": 6,  "threads": 12, "base_ghz": 4.7, "boost_ghz": 5.3, "tdp": 105, "l3_mb": 32, "igpu": "Radeon Graphics"},
    "Ryzen 5 7600":    {"cores": 6,  "threads": 12, "base_ghz": 3.8, "boost_ghz": 5.1, "tdp": 65,  "l3_mb": 32, "igpu": "Radeon Graphics"},
    # AMD Ryzen 5000 (Zen 3)
    "Ryzen 9 5950X": {"cores": 16, "threads": 32, "base_ghz": 3.4, "boost_ghz": 4.9, "tdp": 105, "l3_mb": 64, "igpu": None},
    "Ryzen 9 5900X": {"cores": 12, "threads": 24, "base_ghz": 3.7, "boost_ghz": 4.8, "tdp": 105, "l3_mb": 64, "igpu": None},
    "Ryzen 7 5800X3D":{"cores": 8, "threads": 16, "base_ghz": 3.4, "boost_ghz": 4.5, "tdp": 105, "l3_mb": 96, "igpu": None},
    "Ryzen 7 5800X":  {"cores": 8, "threads": 16, "base_ghz": 3.8, "boost_ghz": 4.7, "tdp": 105, "l3_mb": 32, "igpu": None},
    "Ryzen 5 5600X":  {"cores": 6, "threads": 12, "base_ghz": 3.7, "boost_ghz": 4.6, "tdp": 65,  "l3_mb": 32, "igpu": None},
}


# ─── Parsing helpers ──────────────────────────────────────────────────────────

def _find_in_text(text: str, patterns: list) -> Optional[str]:
    """Return first regex match from list of patterns."""
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _clean_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _clean_int(s: Optional[str]) -> Optional[int]:
    if s is None:
        return None
    try:
        return int(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


# ─── GPU spec parser ─────────────────────────────────────────────────────────

def parse_gpu_specs(title: str, description: str = "", tech_specs: dict | None = None) -> dict:
    """
    Extract GPU specs from product title, description, and tech specs table.
    Returns a normalized dict suitable for the `specs` JSONB column.
    """
    text = f"{title} {description}"
    text_lower = text.lower()
    specs: dict = {}

    # 1. Identify GPU chip
    gpu_chip = None
    for chip in GPU_CHIPS:
        if chip.lower() in text_lower:
            gpu_chip = chip
            break
    if gpu_chip:
        specs["gpu_chip"] = gpu_chip

    # 2. VRAM — from text first, fall back to lookup
    vram_match = re.search(
        r"(\d{1,2})\s*GB\s*(?:GDDR\d+X?|HBM\d?|VRAM|video\s+memory|graphics\s+memory)",
        text, re.IGNORECASE
    )
    if vram_match:
        specs["vram_gb"] = int(vram_match.group(1))
    elif gpu_chip and gpu_chip in GPU_VRAM_SIZES:
        specs["vram_gb"] = GPU_VRAM_SIZES[gpu_chip]

    # 3. VRAM type
    vram_type_m = re.search(r"(GDDR6X|GDDR6|GDDR5X|GDDR5|HBM\d?)", text, re.IGNORECASE)
    if vram_type_m:
        specs["vram_type"] = vram_type_m.group(1).upper()
    elif gpu_chip and gpu_chip in GPU_VRAM_TYPES:
        specs["vram_type"] = GPU_VRAM_TYPES[gpu_chip]

    # 4. CUDA / Stream cores
    cuda_m = re.search(
        r"(\d{3,5})\s*(?:CUDA|Shader|Stream|SP)\s*(?:Core|Processor)s?",
        text, re.IGNORECASE
    )
    if cuda_m:
        specs["compute_units"] = int(cuda_m.group(1))
    elif gpu_chip:
        if gpu_chip in GPU_CUDA_CORES:
            specs["cuda_cores"] = GPU_CUDA_CORES[gpu_chip]
        elif gpu_chip in GPU_STREAM_PROCESSORS:
            specs["stream_processors"] = GPU_STREAM_PROCESSORS[gpu_chip]

    # 5. Boost/base clock
    boost_patterns = [
        r"boost\s+clock\s*:?\s*([\d,]+)\s*MHz",
        r"([\d,]+)\s*MHz\s*(?:boost|max\s*clock)",
        r"GPU\s+boost\s+clock\s*[:\-]\s*([\d,]+)\s*MHz",
    ]
    base_patterns = [
        r"base\s+clock\s*:?\s*([\d,]+)\s*MHz",
        r"([\d,]+)\s*MHz\s*base",
        r"GPU\s+base\s+clock\s*[:\-]\s*([\d,]+)\s*MHz",
    ]
    boost = _clean_int(_find_in_text(text, boost_patterns))
    base = _clean_int(_find_in_text(text, base_patterns))
    if boost: specs["boost_clock_mhz"] = boost
    if base:  specs["base_clock_mhz"] = base

    # 6. Memory bandwidth
    bw_m = re.search(r"([\d,]+)\s*GB/s\s*(?:memory\s+bandwidth|bandwidth)", text, re.IGNORECASE)
    if bw_m:
        specs["memory_bandwidth_gbps"] = _clean_float(bw_m.group(1))

    # 7. Memory bus width
    bus_m = re.search(r"(\d{2,4})[- ]?bit\s*(?:memory\s+)?(?:interface|bus)", text, re.IGNORECASE)
    if bus_m:
        specs["memory_bus_bits"] = int(bus_m.group(1))

    # 8. TDP
    tdp_m = re.search(
        r"(\d{2,3})\s*W(?:atts?)?\s*(?:TDP|TBP|Total\s+Graphics\s+Power|Max\s+TDP)",
        text, re.IGNORECASE
    )
    if tdp_m:
        specs["tdp_watts"] = int(tdp_m.group(1))
    elif gpu_chip and gpu_chip in GPU_TDP:
        specs["tdp_watts"] = GPU_TDP[gpu_chip]

    # 9. PCIe interface
    pcie_m = re.search(r"PCIe\s*(\d\.\d)\s*x(\d{2})", text, re.IGNORECASE)
    if pcie_m:
        specs["interface"] = f"PCIe {pcie_m.group(1)} x{pcie_m.group(2)}"

    # 10. AIB brand (card manufacturer)
    for brand in GPU_AIB_BRANDS:
        if brand.lower() in text_lower:
            specs["aib_brand"] = brand
            break

    # 11. Card series / model name
    if "aib_brand" in specs:
        brand = specs["aib_brand"]
        for series in GPU_SERIES_NAMES.get(brand, []):
            if series.lower() in text_lower:
                specs["card_series"] = series
                break

    # 12. Card length
    len_m = re.search(r"(\d{3})\s*mm\s*(?:card\s+length|length|size)", text, re.IGNORECASE)
    if len_m:
        specs["length_mm"] = int(len_m.group(1))

    # 13. Slot width
    slot_m = re.search(r"(\d(?:\.\d)?)\s*[-–]?\s*Slot", text, re.IGNORECASE)
    if slot_m:
        specs["slot_width"] = slot_m.group(1)

    # 14. Display outputs (capture raw description)
    dp_m = re.search(
        r"(\d+\s*[xX×]\s*DisplayPort[^,;.\n]*(?:[,;]\s*\d+\s*[xX×]\s*HDMI[^,;.\n]*)?)",
        text, re.IGNORECASE
    )
    if dp_m:
        specs["display_outputs"] = dp_m.group(1).strip()

    # 15. Merge structured tech_specs table if provided
    if tech_specs:
        for key, val in tech_specs.items():
            k = key.lower().strip()
            v = val.strip() if isinstance(val, str) else val
            if "boost clock" in k and "boost_clock_mhz" not in specs:
                mhz = re.search(r"(\d{3,4})", str(v))
                if mhz: specs["boost_clock_mhz"] = int(mhz.group(1))
            elif "base clock" in k and "base_clock_mhz" not in specs:
                mhz = re.search(r"(\d{3,4})", str(v))
                if mhz: specs["base_clock_mhz"] = int(mhz.group(1))
            elif "memory size" in k or "vram" in k:
                gb = re.search(r"(\d{1,2})", str(v))
                if gb and "vram_gb" not in specs: specs["vram_gb"] = int(gb.group(1))
            elif "memory type" in k and "vram_type" not in specs:
                specs["vram_type"] = str(v).upper()
            elif "memory bandwidth" in k:
                bw = re.search(r"(\d+)", str(v))
                if bw and "memory_bandwidth_gbps" not in specs:
                    specs["memory_bandwidth_gbps"] = int(bw.group(1))
            elif "tdp" in k or "total graphics power" in k:
                w = re.search(r"(\d{2,3})", str(v))
                if w and "tdp_watts" not in specs: specs["tdp_watts"] = int(w.group(1))
            elif "cuda core" in k:
                n = re.search(r"(\d{3,5})", str(v))
                if n and "cuda_cores" not in specs: specs["cuda_cores"] = int(n.group(1))
            elif "stream processor" in k:
                n = re.search(r"(\d{3,5})", str(v))
                if n and "stream_processors" not in specs: specs["stream_processors"] = int(n.group(1))
            elif "interface" in k and "interface" not in specs:
                specs["interface"] = str(v)

    return specs


# ─── CPU spec parser ─────────────────────────────────────────────────────────

def parse_cpu_specs(title: str, description: str = "", tech_specs: dict | None = None) -> dict:
    """
    Extract CPU specs from product text.
    Returns normalized dict suitable for the `specs` JSONB column.
    """
    text = f"{title} {description}"
    text_lower = text.lower()
    specs: dict = {}

    # 1. Brand
    if "intel" in text_lower:
        specs["cpu_brand"] = "Intel"
    elif "amd" in text_lower:
        specs["cpu_brand"] = "AMD"

    # 2. Model number
    model_patterns = [
        r"(Core\s+(?:Ultra\s+)?i[3579][- ]?\d{4,5}[A-Z]{0,3})",   # Core i9-14900K
        r"(Ryzen\s+[3579]\s+\d{4}[A-Z0-9]{0,4})",                  # Ryzen 9 7950X3D
        r"(Threadripper\s+(?:PRO\s+)?\d{4}[A-Z]{0,2})",            # Threadripper PRO 7985WX
        r"(Core\s+Ultra\s+[579]\s+\d{3}[A-Z]?)",                   # Core Ultra 9 285K
    ]
    model = _find_in_text(text, model_patterns)
    if model:
        # Normalize spacing
        model = re.sub(r"\s+", " ", model).strip()
        specs["cpu_model"] = model

        # Lookup known specs
        for key, data in CPU_SPECS.items():
            if key.lower() in model.lower():
                specs.setdefault("cores", data["cores"])
                specs.setdefault("threads", data["threads"])
                specs.setdefault("base_clock_ghz", data["base_ghz"])
                specs.setdefault("boost_clock_ghz", data["boost_ghz"])
                specs.setdefault("tdp_watts", data["tdp"])
                specs.setdefault("l3_cache_mb", data["l3_mb"])
                if data.get("igpu"):
                    specs.setdefault("integrated_gpu", data["igpu"])
                break

    # 3. Core/thread counts from text
    core_m = re.search(
        r"(\d{1,2})[- ]?(?:Physical\s+)?Core(?:s|\s+Processor)?(?:\s+\d)", text, re.IGNORECASE
    )
    if core_m and "cores" not in specs:
        specs["cores"] = int(core_m.group(1))

    thread_m = re.search(r"(\d{1,2})\s*Thread", text, re.IGNORECASE)
    if thread_m and "threads" not in specs:
        specs["threads"] = int(thread_m.group(1))

    # 4. Clock speeds
    base_m = re.search(
        r"(?:Base\s+(?:Processor\s+)?|P-Core\s+Base\s+)Frequency\s*:?\s*([\d.]+)\s*GHz",
        text, re.IGNORECASE
    )
    if base_m and "base_clock_ghz" not in specs:
        specs["base_clock_ghz"] = float(base_m.group(1))

    boost_m = re.search(
        r"(?:Max\s+Turbo|Boost|P-Core\s+Max)\s*(?:Frequency)?\s*:?\s*([\d.]+)\s*GHz",
        text, re.IGNORECASE
    )
    if boost_m and "boost_clock_ghz" not in specs:
        specs["boost_clock_ghz"] = float(boost_m.group(1))

    # 5. TDP
    tdp_m = re.search(
        r"(\d{2,3})\s*W(?:atts?)?\s*(?:TDP|PBP|Base\s+Power|Processor\s+TDP)", text, re.IGNORECASE
    )
    if tdp_m and "tdp_watts" not in specs:
        specs["tdp_watts"] = int(tdp_m.group(1))

    # 6. Socket
    socket_m = re.search(r"(LGA\s*\d{3,4}|AM[345]|sTR[X45]|sWRX\d|BGA\d+)", text, re.IGNORECASE)
    if socket_m:
        specs["socket"] = socket_m.group(1).replace(" ", "").upper()
    elif "cpu_model" in specs:
        model_val = specs["cpu_model"]
        for prefix, socket in CPU_SOCKET_MAP.items():
            if prefix.lower() in model_val.lower():
                specs["socket"] = socket
                break

    # 7. Cache
    l3_m = re.search(r"(\d{1,3})\s*MB\s*(?:Smart\s+)?(?:L3\s+)?Cache", text, re.IGNORECASE)
    if l3_m and "l3_cache_mb" not in specs:
        specs["l3_cache_mb"] = int(l3_m.group(1))

    l2_m = re.search(r"(\d{1,3})\s*MB\s*L2\s*Cache", text, re.IGNORECASE)
    if l2_m:
        specs["l2_cache_mb"] = int(l2_m.group(1))

    # 8. Memory type support
    mem_m = re.search(r"(DDR5[\-–]\d+|DDR4[\-–]\d+|LPDDR5[\-–]\d+)", text, re.IGNORECASE)
    if mem_m:
        specs["memory_support"] = mem_m.group(1).upper()

    # 9. PCIe version
    pcie_m = re.search(r"PCIe\s*([\d.]+)", text, re.IGNORECASE)
    if pcie_m:
        specs["pcie_version"] = pcie_m.group(1)

    # 10. Integrated GPU
    igpu_m = re.search(
        r"(Intel\s+UHD\s+\d{3}|Intel\s+Iris\s+Xe|Intel\s+Arc|AMD\s+Radeon\s+\d{3}[MG]|Radeon\s+Graphics)",
        text, re.IGNORECASE
    )
    if igpu_m and "integrated_gpu" not in specs:
        specs["integrated_gpu"] = igpu_m.group(1)

    # 11. 3D V-Cache marker
    if "3d v-cache" in text_lower or "x3d" in text_lower:
        specs["has_3d_vcache"] = True

    # 12. Merge structured tech specs
    if tech_specs:
        for key, val in tech_specs.items():
            k = key.lower().strip()
            v = str(val).strip()
            if "# of cores" in k or "total cores" in k:
                n = re.search(r"(\d+)", v)
                if n and "cores" not in specs: specs["cores"] = int(n.group(1))
            elif "# of threads" in k or "total threads" in k:
                n = re.search(r"(\d+)", v)
                if n and "threads" not in specs: specs["threads"] = int(n.group(1))
            elif "base freq" in k or "base clock" in k:
                f = re.search(r"([\d.]+)", v)
                if f and "base_clock_ghz" not in specs: specs["base_clock_ghz"] = float(f.group(1))
            elif "max turbo" in k or "boost" in k:
                f = re.search(r"([\d.]+)", v)
                if f and "boost_clock_ghz" not in specs: specs["boost_clock_ghz"] = float(f.group(1))
            elif "tdp" in k or "processor base power" in k:
                w = re.search(r"(\d+)", v)
                if w and "tdp_watts" not in specs: specs["tdp_watts"] = int(w.group(1))
            elif "cache" in k and "l3" in k:
                mb = re.search(r"(\d+)", v)
                if mb and "l3_cache_mb" not in specs: specs["l3_cache_mb"] = int(mb.group(1))
            elif "socket" in k and "socket" not in specs:
                specs["socket"] = v.replace("FCLGA", "LGA").upper()
            elif "lithography" in k or "process" in k:
                nm_m = re.search(r"(\d+)\s*nm", v)
                if nm_m: specs["process_nm"] = int(nm_m.group(1))

    return specs


# ─── Laptop spec parser ───────────────────────────────────────────────────────

def parse_laptop_specs(title: str, description: str = "", tech_specs: dict | None = None) -> dict:
    """
    Extract gaming laptop specs from product text.
    Returns normalized dict suitable for the `specs` JSONB column.
    """
    text = f"{title} {description}"
    text_lower = text.lower()
    specs: dict = {}

    # 1. Screen size
    screen_m = re.search(
        r"(\d{1,2}(?:\.\d)?)\s*[\"'′]?\s*(?:inch|\"|\bFHD\b|\bQHD\b|\bOLED\b|\bIPS\b)",
        text, re.IGNORECASE
    )
    if not screen_m:
        screen_m = re.search(r'(\d{1,2}(?:\.\d)?)["\']', text)
    if screen_m:
        size = float(screen_m.group(1))
        if 10 <= size <= 20:  # sanity check
            specs["screen_size_inch"] = size

    # 2. Screen resolution
    res_m = re.search(r"(\d{3,4})\s*[xX×]\s*(\d{3,4})", text)
    if res_m:
        w, h = int(res_m.group(1)), int(res_m.group(2))
        # Ensure landscape
        if w < h:
            w, h = h, w
        specs["screen_resolution"] = f"{w}x{h}"

    # 3. Refresh rate
    hz_m = re.search(r"(\d{2,3})\s*Hz", text, re.IGNORECASE)
    if hz_m:
        hz = int(hz_m.group(1))
        if hz >= 60:  # Ignore non-display Hz values
            specs["refresh_rate_hz"] = hz

    # 4. Panel type
    for panel in ["OLED", "Mini-LED", "IPS", "VA", "TN", "QD-OLED"]:
        if panel.lower() in text_lower:
            specs["panel_type"] = panel
            break

    # 5. CPU model
    cpu_patterns = [
        r"(Intel\s+Core\s+(?:Ultra\s+)?i[3579][- ]?\d{4,5}[A-Z]{0,3}[HX]?[KS]?)",
        r"(AMD\s+Ryzen\s+[3579]\s+\d{4}[A-Z0-9]{0,4})",
        r"(Core\s+(?:Ultra\s+)?i[3579][- ]?\d{4,5}[A-Z]{0,3}[HX]?)",
        r"(Ryzen\s+[3579]\s+\d{4}[A-Z0-9]{0,4})",
    ]
    cpu = _find_in_text(text, cpu_patterns)
    if cpu:
        cpu = re.sub(r"\s+", " ", cpu).strip()
        specs["cpu_model"] = cpu
        if "intel" in cpu.lower():
            specs["cpu_brand"] = "Intel"
        elif "amd" in cpu.lower() or "ryzen" in cpu.lower():
            specs["cpu_brand"] = "AMD"

    # 6. GPU model
    gpu_chip = None
    for chip in GPU_CHIPS:
        if chip.lower() in text_lower:
            gpu_chip = chip
            break

    # Laptop GPU variants
    if not gpu_chip:
        for chip in ["RTX 4090", "RTX 4080", "RTX 4070", "RTX 4060",
                     "RTX 3080", "RTX 3070", "RTX 3060",
                     "RX 6800M", "RX 6700M", "RX 6600M",
                     "Arc A770M", "Arc A730M", "Arc A550M"]:
            if chip.lower() in text_lower:
                gpu_chip = chip
                break

    if gpu_chip:
        # Check for laptop-specific suffix
        suffix_m = re.search(
            rf"{re.escape(gpu_chip)}\s*(Laptop GPU|Mobile|Max-Q)?",
            text, re.IGNORECASE
        )
        if suffix_m and suffix_m.group(1):
            specs["gpu_model"] = f"{gpu_chip} {suffix_m.group(1)}"
        else:
            specs["gpu_model"] = gpu_chip

    # 7. GPU VRAM for laptop
    vram_m = re.search(
        r"(\d{1,2})\s*GB\s*(?:GDDR\d+X?|VRAM|dedicated\s+video|graphics\s+memory)",
        text, re.IGNORECASE
    )
    if vram_m:
        specs["gpu_vram_gb"] = int(vram_m.group(1))
    elif gpu_chip and gpu_chip in GPU_VRAM_SIZES:
        specs["gpu_vram_gb"] = GPU_VRAM_SIZES[gpu_chip]

    # 8. RAM
    ram_patterns = [
        r"(\d{1,3})\s*GB\s*(?:DDR5|DDR4|LPDDR5X?|LPDDR4X?|SO-DIMM|RAM\b|SDRAM|Memory)",
        r"(\d{1,3})\s*GB\s*RAM",
    ]
    ram = _find_in_text(text, ram_patterns)
    if ram:
        specs["ram_gb"] = int(ram)

    # RAM type
    for rtype in ["LPDDR5X", "LPDDR5", "LPDDR4X", "LPDDR4", "DDR5", "DDR4"]:
        if rtype.lower() in text_lower:
            specs["ram_type"] = rtype
            break

    # 9. Storage
    storage_patterns = [
        r"(\d+)\s*TB\s*(?:NVMe|PCIe|SSD|M\.2)",
        r"(\d+)\s*GB\s*(?:NVMe|PCIe|SSD|M\.2)",
        r"(\d+)\s*TB\s*(?:HDD|SATA)",
    ]
    for i, p in enumerate(storage_patterns):
        m = re.search(p, text, re.IGNORECASE)
        if m:
            size = int(m.group(1))
            if i == 0:  # TB
                specs["storage_gb"] = size * 1024
            elif i == 1:  # GB
                specs["storage_gb"] = size
            elif i == 2:  # HDD TB
                specs["storage_gb"] = size * 1024
                specs["storage_type"] = "HDD"
            break

    # Storage type
    for stype in ["PCIe 5.0", "PCIe 4.0", "NVMe", "M.2"]:
        if stype.lower() in text_lower:
            specs["storage_type"] = stype
            break

    # 10. Weight
    weight_m = re.search(r"([\d.]+)\s*kg(?:\s*/\s*[\d.]+\s*lb)?", text, re.IGNORECASE)
    if weight_m:
        w = float(weight_m.group(1))
        if 1.0 <= w <= 6.0:
            specs["weight_kg"] = w

    # 11. Battery
    batt_m = re.search(r"(\d{2,3})\s*W[Hh]\b", text)
    if batt_m:
        specs["battery_wh"] = int(batt_m.group(1))

    # 12. Operating system
    for os in ["Windows 11 Pro", "Windows 11 Home", "Windows 11", "Windows 10", "FreeDOS", "No OS"]:
        if os.lower() in text_lower:
            specs["os"] = os
            break

    # 13. Keyboard (RGB, backlit etc.)
    if "per-key rgb" in text_lower:
        specs["keyboard"] = "Per-Key RGB"
    elif "rgb" in text_lower:
        specs["keyboard"] = "RGB Backlit"
    elif "backlit" in text_lower:
        specs["keyboard"] = "Backlit"

    # 14. Ports (basic)
    ports = []
    if "thunderbolt" in text_lower:
        tb_m = re.search(r"Thunderbolt\s*(\d)", text, re.IGNORECASE)
        ports.append(f"Thunderbolt {tb_m.group(1)}" if tb_m else "Thunderbolt")
    if "usb-c" in text_lower or "usb type-c" in text_lower:
        ports.append("USB-C")
    if "hdmi" in text_lower:
        hdmi_m = re.search(r"HDMI\s*([\d.]+)?", text, re.IGNORECASE)
        ports.append(f"HDMI {hdmi_m.group(1)}" if hdmi_m and hdmi_m.group(1) else "HDMI")
    if ports:
        specs["ports"] = ", ".join(ports)

    # 15. Merge structured tech specs
    if tech_specs:
        for key, val in tech_specs.items():
            k = key.lower().strip()
            v = str(val).strip()
            if ("processor" in k or "cpu" in k) and "cpu_model" not in specs:
                specs["cpu_model"] = v[:100]
            elif ("graphics" in k or "gpu" in k) and "gpu_model" not in specs:
                specs["gpu_model"] = v[:100]
            elif "display" in k and "screen_resolution" not in specs:
                res_m = re.search(r"(\d{3,4})\s*[xX×]\s*(\d{3,4})", v)
                if res_m: specs["screen_resolution"] = f"{res_m.group(1)}x{res_m.group(2)}"
            elif "memory" in k and "ram" in k and "ram_gb" not in specs:
                gb_m = re.search(r"(\d+)", v)
                if gb_m: specs["ram_gb"] = int(gb_m.group(1))
            elif "storage" in k and "storage_gb" not in specs:
                tb_m = re.search(r"(\d+)\s*TB", v)
                gb_m = re.search(r"(\d+)\s*GB", v)
                if tb_m: specs["storage_gb"] = int(tb_m.group(1)) * 1024
                elif gb_m: specs["storage_gb"] = int(gb_m.group(1))
            elif "weight" in k and "weight_kg" not in specs:
                kg_m = re.search(r"([\d.]+)\s*kg", v, re.IGNORECASE)
                if kg_m: specs["weight_kg"] = float(kg_m.group(1))
            elif "battery" in k and "battery_wh" not in specs:
                wh_m = re.search(r"(\d+)", v)
                if wh_m: specs["battery_wh"] = int(wh_m.group(1))
            elif "operating system" in k and "os" not in specs:
                specs["os"] = v[:50]

    return specs


# ─── Router ───────────────────────────────────────────────────────────────────

def parse_specs(category: str, title: str, description: str = "", tech_specs: dict | None = None) -> dict:
    """Route to the appropriate parser based on category."""
    parsers = {
        "gpu": parse_gpu_specs,
        "cpu": parse_cpu_specs,
        "laptop": parse_laptop_specs,
    }
    parser = parsers.get(category)
    if parser:
        return parser(title, description, tech_specs)
    return {}


def infer_tags(category: str, specs: dict, title: str = "") -> list:
    """Generate searchable/filterable tags from product specs."""
    tags = []
    title_lower = title.lower()

    if category == "gpu":
        chip = specs.get("gpu_chip", "")
        if chip:
            tags.append(chip)
            if "RTX" in chip:
                tags.append("NVIDIA")
                tags.append("RTX")
            elif "RX" in chip:
                tags.append("AMD")
                tags.append("Radeon")
            elif "Arc" in chip:
                tags.append("Intel")
                tags.append("Arc")
        vram = specs.get("vram_gb")
        if vram:
            tags.append(f"{vram}GB VRAM")
        tdp = specs.get("tdp_watts")
        if tdp and tdp >= 300:
            tags.append("High Power")

    elif category == "cpu":
        model = specs.get("cpu_model", "")
        brand = specs.get("cpu_brand", "")
        if brand:
            tags.append(brand)
        if "x3d" in model.lower() or "3d v-cache" in title_lower:
            tags.append("3D V-Cache")
            tags.append("Gaming")
        cores = specs.get("cores", 0)
        if cores >= 16:
            tags.append(f"{cores}-Core")
        boost = specs.get("boost_clock_ghz", 0)
        if boost >= 5.5:
            tags.append("High Frequency")
        socket = specs.get("socket", "")
        if socket:
            tags.append(socket)

    elif category == "laptop":
        gpu = specs.get("gpu_model", "")
        if gpu:
            tags.append(gpu)
        size = specs.get("screen_size_inch")
        if size:
            tags.append(f'{size}"')
        hz = specs.get("refresh_rate_hz", 0)
        if hz >= 240:
            tags.append("240Hz+")
        elif hz >= 144:
            tags.append("144Hz+")
        panel = specs.get("panel_type", "")
        if panel == "OLED":
            tags.append("OLED")
        ram = specs.get("ram_gb", 0)
        if ram >= 32:
            tags.append(f"{ram}GB RAM")

    # Universal
    for brand in ["ASUS", "MSI", "Lenovo", "Razer", "HP", "Dell", "Acer",
                  "Gigabyte", "Samsung", "Zotac", "Sapphire", "EVGA", "Intel", "AMD", "NVIDIA"]:
        if brand.lower() in title_lower:
            if brand not in tags:
                tags.append(brand)
            break

    return list(dict.fromkeys(tags))  # deduplicate preserving order
