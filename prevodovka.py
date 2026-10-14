#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
   SIMULACE A OPTIMALIZACE AUTOMATICKÉ PŘEVODOVKY PRO HRU 'SCREWDRIVERS'
   Model: Total Fitness Score, Koaxiální Base Modifier & Stacking planet
================================================================================
Tento skript provádí pokročilou simulaci a optimalizaci automatické převodovky
pro hru Screwdrivers s dynamickým počtem rychlostních stupňů (2 až 6).

KLÍČOVÉ MECHANIKY A PRINCIPY:
1. PROSTOROVÁ VÝHODA (KOAXIÁLNÍ USPOŘÁDÁNÍ = NEZABÍRÁ ŠÍŘKU):
   - Běžný převod vyžaduje přesun výkonu na novou paralelní předlohovou hřídel,
     což rozšiřuje podvozek auta (chassis width).
   - Planetární převodovka je koaxiální – umísťuje se přímo na stávající hřídel.
     Změní poměr, ale výkon zůstává na stejné ose a nepřidává novou hřídel.
   - Algoritmus masivně penalizuje každou novou hřídel (DEFAULT_WIDTH_PENALTY = 35.0),
     takže naskládat planetární moduly na stávající osu je prostorově i bodově
     absolutně nadřazené stavbě paralelních hřídelí.

2. FUNKČNÍ VÝHODA (OBOUSMĚRNOST - PŘEVOD DO RYCHLA I DO SÍLY):
   - Planetární modul lze fyzicky otočit:
     * Multiplikátor / Rychloběh: poměr 2.30x (1x) nebo 5.29x (2x)
     * Redukce do síly: poměr 1 / 2.30 = 0.4348x (1x) nebo 0.1890x (2x)
   - Obě varianty jsou aktivně testovány jak na jednotlivých stupních (stacking),
     tak jako předřazené mezičleny.

3. TAKTICKÁ VÝHODA (PŘEDŘAZENÝ MEZIČLEN PŘED POSUVEM - BASE MODIFIER):
   - Planetární převodovku lze umístit na hřídel ještě před samotný mechanismus
     posunu (před přehazovačku).
   - Funguje jako globální redukce/násobič pro celou danou hřídel, aniž by zabírala
     místo v posuvné dráze (Pozice 0, 1, 2 zůstávají plně volné pro řazení).
   - Změní základní otáčky osy pro všechny stupně na ní zapojené.

4. LOGICKÁ PROGRESE RYCHLOSTNÍCH STUPŇŮ (OD SÍLY K RYCHLOSTI):
   - 1. rychlostní stupeň (Pozice 0 v klidu s pružinou) musí poskytovat maximální
     točivý moment pro překonání odporu a rozjezd (striktně <= 1.05x).
   - Výstupní otáčky napříč rychlostními stupni (Pozice 0 -> 1 -> 2) musí VŽDY
     striktně stoupat: RPM_st1 < RPM_st2 < RPM_st3.
   - Jakákoliv sestava se zpomalením při přeřazení je okamžitě zahozena.
"""

import sys
import os
import argparse
from itertools import combinations
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional

# Zajištění bezpečného kódování výstupu na Windows (podpora UTF-8)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.widgets import RadioButtons
import numpy as np


# ==============================================================================
# 1. HLAVNÍ HODNOTÍCÍ KONSTANTY (SNADNO ZMĚNITELNÉ PRO LADĚNÍ)
# ==============================================================================

# Pevná penalizace za každé přeřazení (přesně +3.0 body za každé přeřazení)
DEFAULT_SHIFT_PENALTY_PER_GEAR: float = 3.0

# Masivní penalizace za šířku zástavby (paralelní hřídele nad rámec 1. hřídele)
# Zajišťuje, že naskládat planetární převody koaxiálně je bodově výrazně výhodnější než stavět novou hřídel
DEFAULT_WIDTH_PENALTY: float = 35.0

# Váha odečtu bodů za plynulost řazení (Smoothness Bonus)
DEFAULT_SMOOTHNESS_WEIGHT: float = 0.25

# Váha penalizace za odchylku od cílových otáček
DEFAULT_ERROR_PENALTY_WEIGHT: float = 1.5

# Základní parametry dynamické tolerance
DEFAULT_BASE_TOLERANCE: float = 0.05
DEFAULT_K_TOLERANCE: float = 0.20

# Striktní podmínka pro 1. rychlostní stupeň: musí poskytovat sílu/točivý moment pro rozjezd
DEFAULT_MAX_LAUNCH_RATIO: float = 1.05
DEFAULT_MIN_LAUNCH_RATIO: float = 0.15


# ==============================================================================
# 2. FYZIKÁLNÍ DEFINICE KOMPONENT A PARAMETRŮ PRO HRU 'SCREWDRIVERS'
# ==============================================================================

# Přesné poloměry ozubených kol v blocích (slouží VÝHRADNĚ pro rozteč hřídelí)
GEAR_RADII: Dict[str, float] = {
    "Small": 0.5,
    "Medium": 1.5,
    "Large": 2.5
}

# Skutečné počty zubů (slouží pro výpočet převodového poměru: Hnací / Hnaný)
GEAR_TEETH: Dict[str, Any] = {
    "Small": 8,
    "Medium": 16,
    "Large": 24,
    "Planetary": 18.4  # Poměrný počet zubů (18.4 / 8 = 2.30x)
}

# Fyzické hmotnosti komponent
GEAR_WEIGHTS: Dict[str, float] = {
    "Small": 1.0,
    "Medium": 3.0,
    "Large": 5.0,
    "Planetary": 12.0
}

# Možnosti řetězení (stacking) planetových převodovek na stejné ose pro každou pozici posuvu
PLANETARY_STACK_OPTIONS: List[Dict[str, Any]] = [
    {"count": 0, "mode": "none", "ratio": 1.0, "weight": 0.0, "desc": ""},
    {"count": 1, "mode": "1x_od", "ratio": 2.30, "weight": 12.0, "desc": "+ 1x Plan. (2.30x Rychloběh)"},
    {"count": 1, "mode": "1x_red", "ratio": 1.0 / 2.30, "weight": 12.0, "desc": "+ 1x Plan. (0.43x Redukce)"},
    {"count": 2, "mode": "2x_od", "ratio": 2.30 ** 2, "weight": 24.0, "desc": "+ 2x Plan. (5.29x Rychloběh)"},
    {"count": 2, "mode": "2x_red", "ratio": 1.0 / (2.30 ** 2), "weight": 24.0, "desc": "+ 2x Plan. (0.19x Redukce)"},
]

# Možnosti předřazeného mezičlenu (Base Modifier) na vstupu pevné části hřídele
BASE_MODIFIER_OPTIONS: List[Dict[str, Any]] = [
    {"count": 0, "mode": "none", "ratio": 1.0, "weight": 0.0, "desc": "Bez mezičlenu (1.00x přímý náhon)", "short": "Bez mezičlenu"},
    {"count": 1, "mode": "1x_red", "ratio": 1.0 / 2.30, "weight": 12.0, "desc": "1x Plan. Redukce do síly (0.43x)", "short": "1x Plan. Redukce (0.43x)"},
    {"count": 1, "mode": "1x_od", "ratio": 2.30, "weight": 12.0, "desc": "1x Plan. Rychloběh (2.30x)", "short": "1x Plan. Rychloběh (2.30x)"},
    {"count": 2, "mode": "2x_red", "ratio": 1.0 / (2.30 ** 2), "weight": 24.0, "desc": "2x Plan. Redukce do síly (0.19x)", "short": "2x Plan. Redukce (0.19x)"},
    {"count": 2, "mode": "2x_od", "ratio": 2.30 ** 2, "weight": 24.0, "desc": "2x Plan. Rychloběh (5.29x)", "short": "2x Plan. Rychloběh (5.29x)"},
]


# ==============================================================================
# 3. SESTAVENÍ ELEMENTŮ PŘEVODŮ PODLE ROZTEČE HŘÍDELÍ A STACKINGU
# ==============================================================================

def build_available_stage_elements() -> Dict[float, List[Dict[str, Any]]]:
    """
    Sestaví všechny fyzicky realizovatelné kombinace ozubených kol
    seskupené podle osové rozteče D = R_driving + R_driven a rozšířené
    o možnost axiálního připojení 0x, 1x nebo 2x planetové převodovky (stacking do rychla i síly).
    """
    elements_by_dist: Dict[float, List[Dict[str, Any]]] = defaultdict(list)
    for d_name, r_d in GEAR_RADII.items():
        for f_name, r_f in GEAR_RADII.items():
            dist = round(r_d + r_f, 2)
            t_d = GEAR_TEETH[d_name]
            t_f = GEAR_TEETH[f_name]
            base_r = t_d / t_f
            base_w = GEAR_WEIGHTS[d_name] + GEAR_WEIGHTS[f_name]
            
            for p_opt in PLANETARY_STACK_OPTIONS:
                tot_r = base_r * p_opt["ratio"]
                tot_w = base_w + p_opt["weight"]
                p_desc = f" {p_opt['desc']}" if p_opt["desc"] else ""
                desc = f"{d_name} ({t_d}z) -> {f_name} ({t_f}z){p_desc}"
                elements_by_dist[dist].append({
                    "driving": d_name,
                    "driven": f_name,
                    "d_radius": r_d,
                    "f_radius": r_f,
                    "d_teeth": t_d,
                    "f_teeth": t_f,
                    "distance": dist,
                    "p_count": p_opt["count"],
                    "p_mode": p_opt["mode"],
                    "p_ratio": p_opt["ratio"],
                    "base_ratio": base_r,
                    "ratio": tot_r,
                    "weight": tot_w,
                    "desc": desc
                })
    return elements_by_dist


# ==============================================================================
# 4. GENEROVÁNÍ HARDWAROVÝCH SESTAV S BASE MODIFIERY A STACKINGEM
# ==============================================================================

def generate_all_hardware_setups(elements_by_dist: Dict[float, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Vygeneruje hardwarové sestavy převodovek:
    A) 1-Stupeň řazení (2 hřídele celkem, posun až o 2 bloky = 2 až 3 pozice na hřídeli)
       Kombinuje předřazený mezičlen (Base Modifier) na vstupu a stacking na posuvné dráze.
    B) 2-Stupně řazení (3 hřídele celkem, 2 sady řazení za sebou).
    """
    hardware_setups: List[Dict[str, Any]] = []
    dist_keys = list(elements_by_dist.keys())

    # --------------------------------------------------------------------------
    # A) 1 SADA ŘAZENÍ (2 Hřídele, šířka = 2 hřídele)
    # --------------------------------------------------------------------------
    for b_mod in BASE_MODIFIER_OPTIONS:
        bm_r = b_mod["ratio"]
        bm_w = b_mod["weight"]
        for d, el_list in elements_by_dist.items():
            for k in (2, 3):
                for comb in combinations(el_list, k):
                    # Spočítat efektivní převodové poměry včetně mezičlenu
                    comb_sorted = sorted(comb, key=lambda c: c["ratio"] * bm_r)
                    ratios = [round(c["ratio"] * bm_r, 4) for c in comb_sorted]
                    # Podmínka unikátnosti a striktního růstu (Pozice 0 < Pozice 1 < Pozice 2)
                    if len(set(ratios)) != k or any(ratios[i+1] <= ratios[i] for i in range(k - 1)):
                        continue
                    
                    items = [{"pos": i, "pair": c, "stage_ratio": c["ratio"], "effective_ratio": ratios[i]}
                             for i, c in enumerate(comb_sorted)]
                    w = bm_w + sum(c["weight"] for c in comb_sorted)
                    hardware_setups.append({
                        "stages": 1,
                        "shaft_count": 2,
                        "base_modifier": b_mod,
                        "stages_setup": [{"d": d, "items": items}],
                        "weight": w
                    })

    # --------------------------------------------------------------------------
    # B) 2 SADY ŘAZENÍ (3 Hřídele, šířka = 3 hřídele)
    # --------------------------------------------------------------------------
    for b_mod in BASE_MODIFIER_OPTIONS[:3]:  # none, 1x_red, 1x_od
        bm_r = b_mod["ratio"]
        bm_w = b_mod["weight"]
        for d1 in dist_keys:
            el1 = [e for e in elements_by_dist[d1] if e["p_count"] <= 1]
            for d2 in dist_keys:
                el2 = [e for e in elements_by_dist[d2] if e["p_count"] <= 1]
                
                # Varianta 1: Sada 1 pevná (1 pozice), Sada 2 řadí (2 až 3 pozice)
                for c1 in el1:
                    for k2 in (2, 3):
                        for comb2 in combinations(el2, k2):
                            comb2_sorted = sorted(comb2, key=lambda c: c["ratio"])
                            r2 = [round(c1["ratio"] * c["ratio"] * bm_r, 4) for c in comb2_sorted]
                            if len(set(r2)) != k2 or any(r2[i+1] <= r2[i] for i in range(k2 - 1)):
                                continue
                            w = bm_w + c1["weight"] + sum(c["weight"] for c in comb2_sorted)
                            items1 = [{"pos": 0, "pair": c1, "stage_ratio": c1["ratio"], "effective_ratio": c1["ratio"] * bm_r}]
                            items2 = [{"pos": i, "pair": c, "stage_ratio": c["ratio"], "effective_ratio": r2[i]}
                                     for i, c in enumerate(comb2_sorted)]
                            hardware_setups.append({
                                "stages": 2,
                                "shaft_count": 3,
                                "base_modifier": b_mod,
                                "stages_setup": [{"d": d1, "items": items1}, {"d": d2, "items": items2}],
                                "weight": w
                            })

                # Varianta 2: Obě sady řadí (k1=2, k2=2 => 4 rychlostní stupně)
                for comb1 in combinations(el1, 2):
                    if round(comb1[0]["ratio"], 4) == round(comb1[1]["ratio"], 4):
                        continue
                    for comb2 in combinations(el2, 2):
                        if round(comb2[0]["ratio"], 4) == round(comb2[1]["ratio"], 4):
                            continue
                        tot_p = sum(c["p_count"] for c in comb1) + sum(c["p_count"] for c in comb2)
                        if tot_p > 2:
                            continue
                        
                        all_comb_r = []
                        for i1, c1 in enumerate(comb1):
                            for i2, c2 in enumerate(comb2):
                                r = c1["ratio"] * c2["ratio"] * bm_r
                                all_comb_r.append({
                                    "ratio": round(r, 4),
                                    "pos_path": [i1, i2],
                                    "stage_ratios": [c1["ratio"], c2["ratio"]],
                                    "pairs": [c1, c2]
                                })
                        all_comb_r.sort(key=lambda x: x["ratio"])
                        uniq = []
                        seen_r = set()
                        for x in all_comb_r:
                            if x["ratio"] not in seen_r:
                                seen_r.add(x["ratio"])
                                uniq.append(x)
                        if len(uniq) < 4:
                            continue
                        
                        w = bm_w + sum(c["weight"] for c in comb1) + sum(c["weight"] for c in comb2)
                        items1 = [{"pos": i, "pair": c, "stage_ratio": c["ratio"], "effective_ratio": c["ratio"] * bm_r}
                                 for i, c in enumerate(comb1)]
                        items2 = [{"pos": i, "pair": c, "stage_ratio": c["ratio"], "effective_ratio": c["ratio"]}
                                 for i, c in enumerate(comb2)]
                        hardware_setups.append({
                            "stages": 2,
                            "shaft_count": 3,
                            "base_modifier": b_mod,
                            "stages_setup": [{"d": d1, "items": items1}, {"d": d2, "items": items2}],
                            "weight": w,
                            "precomputed_gears": uniq[:4]
                        })

    return hardware_setups


# ==============================================================================
# 5. VÝPOČET PLYNULOSTI (SMOOTHNESS) A TOTAL FITNESS SCORE
# ==============================================================================

def evaluate_smoothness(ratios: List[float]) -> float:
    """
    Vypočítá index plynulosti řazení (Smoothness Score v rozsahu 0 až 100 bodů).
    - Hodnotí velikost skoků mezi převody i jejich rovnoměrnost.
    - Čím menší skoky a vyrovnanější odstupňování, tím vyšší hodnocení.
    """
    if len(ratios) < 2:
        return 0.0
    steps = [ratios[i + 1] / ratios[i] for i in range(len(ratios) - 1)]
    if any(s <= 1.0 for s in steps):
        return 0.0
    
    mean_step = float(np.mean(steps))
    max_step = float(np.max(steps))
    std_step = float(np.std(steps)) if len(steps) > 1 else 0.0
    
    penalty = 0.8 * ((mean_step - 1.0) ** 1.2) + 0.5 * ((max_step - 1.0) ** 1.2) + 1.5 * std_step
    base_score = 100.0 / (1.0 + penalty)
    
    speed_factor = 1.0 + 0.15 * (len(ratios) - 2)
    score = min(100.0, base_score * speed_factor)
    return score


def evaluate_fitness_score(
    ratios: List[float],
    weight: float,
    shaft_count: int,
    target_ratio: float,
    shift_penalty_per_gear: float = DEFAULT_SHIFT_PENALTY_PER_GEAR,
    width_penalty: float = DEFAULT_WIDTH_PENALTY,
    smoothness_weight: float = DEFAULT_SMOOTHNESS_WEIGHT,
    error_penalty_weight: float = DEFAULT_ERROR_PENALTY_WEIGHT
) -> Optional[Dict[str, Any]]:
    """
    Vypočítá Total Fitness Score:
      Total Fitness Score = Footprint Penalty + Shifting Penalty - Smoothness Bonus + Error Penalty
    
    Sestava s NEJNIŽŠÍM Total Fitness Score vyhrává.
    """
    N = len(ratios)
    if N < 2:
        return None
    
    # Striktní podmínka: převody musí striktně stoupat
    steps = [ratios[i + 1] / ratios[i] for i in range(N - 1)]
    if any(s <= 1.0 for s in steps):
        return None
    
    shift_count = N - 1
    
    # 1. Shifting Penalty: přesně +3.0 body za každé přeřazení
    shifting_penalty = shift_count * shift_penalty_per_gear
    
    # 2. Footprint Penalty: masivní penalizace za šířku (paralelní hřídele)
    footprint_penalty = weight + (shaft_count * width_penalty)
    
    # 3. Smoothness Bonus: odměna za rovnoměrné a menší skoky
    smoothness_raw = evaluate_smoothness(ratios)
    smoothness_bonus = smoothness_raw * smoothness_weight
    
    # 4. Target Error Penalty: odchylka koncového převodu od požadovaného cíle
    final_r = ratios[-1]
    err_pct = abs(final_r - target_ratio) / target_ratio * 100.0
    error_penalty = err_pct * error_penalty_weight
    
    total_score = footprint_penalty + shifting_penalty - smoothness_bonus + error_penalty
    
    return {
        "total_score": total_score,
        "footprint_penalty": footprint_penalty,
        "shifting_penalty": shifting_penalty,
        "smoothness_bonus": smoothness_bonus,
        "smoothness_raw": smoothness_raw,
        "error_penalty": error_penalty,
        "err_pct": err_pct,
        "weight": weight,
        "shaft_count": shaft_count,
        "shift_count": shift_count,
        "steps": steps
    }


# ==============================================================================
# 6. OPTIMALIZAČNÍ CYKLUS AUTOMATICKÉ PŘEVODOVKY
# ==============================================================================

def optimize_automatic_transmission(
    input_power: float = 1000.0,
    target_power: float = 4500.0,
    shift_penalty_per_gear: float = DEFAULT_SHIFT_PENALTY_PER_GEAR,
    width_penalty: float = DEFAULT_WIDTH_PENALTY,
    smoothness_weight: float = DEFAULT_SMOOTHNESS_WEIGHT,
    error_penalty_weight: float = DEFAULT_ERROR_PENALTY_WEIGHT,
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
    k_tolerance: float = DEFAULT_K_TOLERANCE,
    min_launch_ratio: float = DEFAULT_MIN_LAUNCH_RATIO,
    max_launch_ratio: float = DEFAULT_MAX_LAUNCH_RATIO
) -> Dict[str, Any]:
    """
    Kompletní simulace a optimalizace převodovky pro hru Screwdrivers.
    """
    target_ratio = target_power / input_power
    elements_by_dist = build_available_stage_elements()
    hardware_setups = generate_all_hardware_setups(elements_by_dist)

    all_candidates: List[Dict[str, Any]] = []

    for hw in hardware_setups:
        bm = hw["base_modifier"]
        bm_r = bm["ratio"]

        if "precomputed_gears" in hw:
            gear_options = hw["precomputed_gears"]
        elif hw["stages"] == 1:
            gear_options = []
            for it in hw["stages_setup"][0]["items"]:
                gear_options.append({
                    "ratio": round(it["effective_ratio"], 4),
                    "pos_path": [it["pos"]],
                    "stage_ratios": [it["stage_ratio"]],
                    "pairs": [it["pair"]]
                })
        else:
            gear_options = []
            it1 = hw["stages_setup"][0]["items"][0]
            for it2 in hw["stages_setup"][1]["items"]:
                r = it1["stage_ratio"] * it2["stage_ratio"] * bm_r
                gear_options.append({
                    "ratio": round(r, 4),
                    "pos_path": [it1["pos"], it2["pos"]],
                    "stage_ratios": [it1["stage_ratio"], it2["stage_ratio"]],
                    "pairs": [it1["pair"], it2["pair"]]
                })

        gear_options.sort(key=lambda x: x["ratio"])
        unique_options = []
        seen = set()
        for opt_item in gear_options:
            if opt_item["ratio"] not in seen:
                seen.add(opt_item["ratio"])
                unique_options.append(opt_item)

        dynamic_tol = base_tolerance + (k_tolerance / max(1.0, hw["weight"]))
        max_err_pct = dynamic_tol * 100.0

        for N in range(2, min(len(unique_options) + 1, 7)):
            subsets = [unique_options] if len(unique_options) == N else [list(sub) for sub in combinations(unique_options, N)]
            for g_list in subsets:
                # 1. Striktní progrese rychlostních stupňů: RPM musí napříč stupni striktně stoupat!
                ratios = [g["ratio"] for g in g_list]
                if any(ratios[i + 1] <= ratios[i] for i in range(N - 1)):
                    continue

                # 2. Striktní podmínka pro 1. rychlostní stupeň: síla / točivý moment pro rozjezd
                start_r = ratios[0]
                if not (min_launch_ratio <= start_r <= max_launch_ratio):
                    continue

                final_r = ratios[-1]
                err_pct = abs(final_r - target_ratio) / target_ratio * 100.0
                if err_pct > max_err_pct:
                    continue

                eval_res = evaluate_fitness_score(
                    ratios=ratios,
                    weight=hw["weight"],
                    shaft_count=hw["shaft_count"],
                    target_ratio=target_ratio,
                    shift_penalty_per_gear=shift_penalty_per_gear,
                    width_penalty=width_penalty,
                    smoothness_weight=smoothness_weight,
                    error_penalty_weight=error_penalty_weight
                )
                if eval_res is None:
                    continue

                all_candidates.append({
                    **eval_res,
                    "N": N,
                    "gears": g_list,
                    "ratios": ratios,
                    "rpms": [input_power * r for r in ratios],
                    "weight": hw["weight"],
                    "shaft_count": hw["shaft_count"],
                    "shift_count": N - 1,
                    "hw": hw
                })

    if not all_candidates:
        raise RuntimeError("Nebyla nalezena žádná platná konfigurace převodovky pro zadané parametry.")

    # Seřazení primárně podle Total Fitness Score vzestupně (nejnižší skóre vyhrává)
    all_candidates.sort(key=lambda x: x["total_score"])
    winner = all_candidates[0]

    best_by_speed: Dict[int, Dict[str, Any]] = {}
    for n in range(2, 7):
        cands = [c for c in all_candidates if c["N"] == n]
        if cands:
            best_by_speed[n] = cands[0]

    return {
        "input_power": input_power,
        "target_power": target_power,
        "target_ratio": target_ratio,
        "winner": winner,
        "best_by_speed": best_by_speed,
        "total_evaluated": len(all_candidates),
        "hardware_setups_count": len(hardware_setups),
        "shift_penalty_per_gear": shift_penalty_per_gear,
        "width_penalty": width_penalty,
        "smoothness_weight": smoothness_weight,
        "max_launch_ratio": max_launch_ratio
    }


# ==============================================================================
# 7. TEXTOVÝ VÝSTUP A REPORT DO KONZOLE
# ==============================================================================

def print_transmission_report(result: Dict[str, Any]) -> None:
    """
    Vypíše přehledný report založený na Total Fitness Score.
    """
    inp = result["input_power"]
    tgt = result["target_power"]
    tgt_r = result["target_ratio"]
    winner = result["winner"]
    hw = winner["hw"]
    bm = hw["base_modifier"]
    best_by_speed = result["best_by_speed"]

    print("\n" + "=" * 80)
    print("   SIMULACE A OPTIMALIZACE AUTOMATICKÉ PŘEVODOVKY (HRA SCREWDRIVERS)")
    print("   HODNOCENÍ: TOTAL FITNESS SCORE (FOOTPRINT + SHIFTING - SMOOTHNESS)")
    print("=" * 80)
    print(f" Vstupní otáčky (motor):   {inp:,.2f} RPM")
    print(f" Cílové otáčky (výstup):  {tgt:,.2f} RPM (požadovaný násobek: {tgt_r:.4f}x)")
    print(f" Shifting Penalty / stupeň: +{result['shift_penalty_per_gear']:.1f} bodů za každé přeřazení")
    print(f" Width Penalty / hřídel:   +{result['width_penalty']:.1f} bodů za paralelní hřídel (masivní penalizace šířky)")
    print(f" Max. převod 1. stupně:    <={result['max_launch_ratio']:.2f}x (striktní požadavek síly/točivého momentu na rozjezd)")
    print(f" Celkem prověřeno sestav:  {result['total_evaluated']} platných variant převodovek")
    print("-" * 80)

    print(f"\n🏆 ABSOLUTNÍ VÍTĚZ: {winner['N']}-STUPŇOVÁ AUTOMATICKÁ PŘEVODOVKA")
    print("-" * 80)
    print(f"  Celkové Total Fitness Score: {winner['total_score']:.2f} bodů (NEJLEPŠÍ HODNOCENÍ)")
    print(f"  Footprint Penalty:           {winner['footprint_penalty']:.1f} bodů (váha {winner['weight']:.1f} + {winner['shaft_count']}x hřídel @ {result['width_penalty']:.1f})")
    print(f"  Shifting Penalty ({winner['shift_count']}x):       +{winner['shifting_penalty']:.1f} bodů ({winner['shift_count']}x {result['shift_penalty_per_gear']:.1f})")
    print(f"  Smoothness Bonus:           -{winner['smoothness_bonus']:.2f} bodů (index plynulosti: {winner['smoothness_raw']:.1f}/100)")
    print(f"  Chyba vůči cíli:             +{winner['error_penalty']:.2f} bodů (odchylka: {winner['err_pct']:.2f} %)")
    print(f"  Fyzická hmotnost:            {winner['weight']:.1f} jednotek hmotnosti")
    print(f"  Počet paralelních hřídelí:   {winner['shaft_count']} hřídele (Koaxiální konstrukce šetří šířku vozidla)")
    print(f"  Předřazený mezičlen (Base):  {bm['desc']} (Váha: {bm['weight']:.1f})")
    print(f"  Výstupní otáčky (max):       {winner['rpms'][-1]:,.2f} RPM (Cíl: {tgt:,.2f} RPM)")

    print("\n  PŘESNÉ SLOŽENÍ NA KAŽDÉ POZICI POSUNU (0, 1, 2):")
    for s_idx, st in enumerate(hw["stages_setup"], 1):
        from_s = s_idx
        to_s = s_idx + 1
        print(f"   * Sada řazení {s_idx} (mezi Hřídelí {from_s} a Hřídelí {to_s}, osová rozteč D = {st['d']:.1f} bloků):")
        pos_names = ["Pozice 0 (výchozí s pružinou)", "Pozice 1 (posun o 1 blok)   ", "Pozice 2 (posun o 2 bloky)  "]
        for p_i in range(3):
            if p_i < len(st["items"]):
                it = st["items"][p_i]
                p = it["pair"]
                plan_str = f" + {p['p_count']}x Planetární ({p['p_ratio']:.2f}x)" if p['p_count'] > 0 else " (bez planetové na pozici)"
                bm_str = f" [x Base Mod {bm['ratio']:.2f}x]" if bm['count'] > 0 else ""
                print(f"     - {pos_names[p_i]}: Kolo {p['driving']} ({p['d_teeth']}z) -> {p['driven']} ({p['f_teeth']}z){plan_str}{bm_str} [Výsledný převod: {it['effective_ratio']:.3f}x, váha: {p['weight']:.1f}]")
            else:
                print(f"     - {pos_names[p_i]}: [Neobsazeno / volná dráha posunu]")

    print("\n  DETAILNÍ PRŮBĚH ŘAZENÍ PŘI JÍZDĚ (OD SÍLY K RYCHLOSTI):")
    for g_i, g_info in enumerate(winner["gears"]):
        rpm_val = winner["rpms"][g_i]
        r_val = g_info["ratio"]
        pos_str = " | ".join(f"Sada {s_i+1} na Pozici {pos}" for s_i, pos in enumerate(g_info["pos_path"]))
        if g_i == 0:
            role_desc = "[START Z MÍSTA - MAXIMÁLNÍ SÍLA / ROZJEZDOVÝ PŘEVOD]"
            print(f"   * {g_i+1}. Rychlostní stupeň:    {rpm_val:,.2f} RPM [Převod: {r_val:.4f}x] | {pos_str} {role_desc}")
        elif g_i == len(winner["gears"]) - 1:
            step_jump = r_val / winner["gears"][g_i-1]["ratio"]
            role_desc = f"[MAXIMÁLNÍ RYCHLOST (přeřazení ze {g_i}. st.: skok {step_jump:.2f}x, penalizace +{result['shift_penalty_per_gear']:.1f})]"
            print(f"   * {g_i+1}. Rychlostní stupeň:    {rpm_val:,.2f} RPM [Převod: {r_val:.4f}x] | {pos_str} {role_desc}")
        else:
            step_jump = r_val / winner["gears"][g_i-1]["ratio"]
            role_desc = f"[PŘECHODOVÝ STUPEŇ (skok {step_jump:.2f}x, penalizace +{result['shift_penalty_per_gear']:.1f})]"
            print(f"   * {g_i+1}. Rychlostní stupeň:    {rpm_val:,.2f} RPM [Převod: {r_val:.4f}x] | {pos_str} {role_desc}")

    print("\n" + "-" * 80)
    print(" SROVNÁNÍ NEJLEPŠÍCH VARIANT DLE POČTU STUPŇŮ (2 AŽ 6 STUPŇŮ):")
    print("-" * 80)
    for n in sorted(best_by_speed.keys()):
        cand = best_by_speed[n]
        c_bm = cand["hw"]["base_modifier"]["short"]
        tag = "[🏆 VÍTĚZ  ]" if n == winner["N"] else f"[{n} stupňů ]"
        print(f" {tag} Score: {cand['total_score']:5.2f} | Footprint: {cand['footprint_penalty']:4.1f} | Shift: +{cand['shifting_penalty']:4.1f} | Smooth: -{cand['smoothness_bonus']:4.1f} | Váha: {cand['weight']:4.1f} | Hřídelí: {cand['shaft_count']} | BaseMod: {c_bm} | Max otáčky: {cand['rpms'][-1]:,.0f} RPM")
    print("=" * 80)


# ==============================================================================
# 8. KINEMATICKÝ BLUEPRINT S BASE MODIFIEREM A GHOST BLOKY
# ==============================================================================

def draw_gearbox_blueprint(ax: plt.Axes, candidate: Dict[str, Any], input_power: float = 1000.0) -> None:
    """
    Vykreslí montážní stavební plánek (Blueprint) s Base Modifierem a kinematikou
    s inteligentním odsazením prvků bez jakýchkoliv kolizí (Zero-Collision Layout):
    - Dynamické rozestupy stanic na ose X (STATION_SPACING = 6.8, SHIFT_DELTA = 1.6)
    - Vertikální odsazení popisků: spodní kola pod hřídel (-r_d - 0.45), horní kola nad hřídel (+r_f + 0.45)
    - Čitelný z-order (12+) a podkladové rámečky (bbox) pro všechny texty
    - Šrafované a čárkované Ghost bloky (hatch='//', alpha=0.45, edgecolor='#27ae60')
    """
    hw = candidate["hw"]
    bm = hw["base_modifier"]
    stages_setup = hw["stages_setup"]
    stages = hw["stages"]

    gear_colors = {
        "Small":  {"face": "#3498db", "edge": "#1f618d"},
        "Medium": {"face": "#f39c12", "edge": "#d35400"},
        "Large":  {"face": "#e74c3c", "edge": "#922b21"},
    }

    y_shafts = [0.0, 2.0] if stages == 1 else [0.0, 2.0, 4.0]
    D1 = stages_setup[0]["d"]
    D2 = stages_setup[1]["d"] if stages == 2 else None

    # Bezpečné rozestupy bez kolizí podél osy X
    STATION_SPACING = 6.8
    SHIFT_DELTA = 1.6
    has_bm = bm["count"] > 0

    x_motor_in = 0.0
    x_bm_center = 2.4
    x_divider = 4.8

    x_s1_start = 6.8
    x_positions_s1 = [x_s1_start + i * STATION_SPACING for i in range(len(stages_setup[0]["items"]))]
    dim_x1 = x_s1_start - 1.2

    if stages == 2:
        x_s2_start = x_positions_s1[-1] + STATION_SPACING + 2.5
        x_positions_s2 = [x_s2_start + i * STATION_SPACING for i in range(len(stages_setup[1]["items"]))]
        x_shaft_end = x_positions_s2[-1] + 3.8
        divider_x = (x_positions_s1[-1] + x_s2_start) / 2
        dim_x2 = divider_x + 0.9
    else:
        x_shaft_end = x_positions_s1[-1] + 3.8
        divider_x = None
        dim_x2 = None

    # Vykreslení hřídelí
    for s_idx, y_s in enumerate(y_shafts, 1):
        if s_idx == 1:
            ax.hlines(y_s, x_motor_in, x_shaft_end, colors="#2c3e50", linewidth=7, zorder=2)
            ax.annotate(
                "HŘÍDEL 1\n[PEVNÁ HNACÍ OSA - MOTOR]",
                xy=(x_motor_in - 0.2, y_s), xytext=(-10, 0), textcoords="offset points",
                ha="right", va="center", fontsize=8.6, fontweight="bold", color="#1a252f",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#eaeded", edgecolor="#7f8c8d", lw=1.5),
                zorder=12
            )
        elif s_idx == 2:
            slide_track = patches.Rectangle(
                (x_divider + 0.2, y_s - 0.30), x_shaft_end - (x_divider + 0.2), 0.60,
                facecolor="#d5f5e3", edgecolor="#27ae60", linestyle="--", linewidth=1.2, zorder=1
            )
            ax.add_patch(slide_track)
            ax.hlines(y_s, x_divider + 0.2, x_shaft_end, colors="#1e8449", linewidth=6, zorder=2)
            s_title = "POSUVNÁ PŘEDLOHOVÁ HŘÍDEL" if stages == 2 else "POSUVNÁ VÝSTUPNÍ HŘÍDEL"
            ax.annotate(
                f"HŘÍDEL 2\n[{s_title}\nLINEÁRNÍ VEDENÍ ŘAZENÍ]",
                xy=(x_motor_in - 0.2, y_s), xytext=(-10, 0), textcoords="offset points",
                ha="right", va="center", fontsize=8.6, fontweight="bold", color="#145a32",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#e8f8f5", edgecolor="#27ae60", lw=1.5),
                zorder=12
            )
        else:
            slide_track3 = patches.Rectangle(
                (x_divider + 0.2, y_s - 0.30), x_shaft_end - (x_divider + 0.2), 0.60,
                facecolor="#ebf5fb", edgecolor="#2980b9", linestyle="--", linewidth=1.2, zorder=1
            )
            ax.add_patch(slide_track3)
            ax.hlines(y_s, x_divider + 0.2, x_shaft_end, colors="#2471a3", linewidth=6, zorder=2)
            ax.annotate(
                "HŘÍDEL 3\n[POSUVNÁ VÝSTUPNÍ HŘÍDEL\nLINEÁRNÍ VEDENÍ 2]",
                xy=(x_motor_in - 0.2, y_s), xytext=(-10, 0), textcoords="offset points",
                ha="right", va="center", fontsize=8.6, fontweight="bold", color="#1b4f72",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#ebf5fb", edgecolor="#2980b9", lw=1.5),
                zorder=12
            )

    # ZÓNA 1: Předřazený mezičlen (Base Modifier)
    ax.axvline(x_divider, color="#7f8c8d", linestyle="--", linewidth=1.6, alpha=0.8, zorder=1)

    if has_bm:
        bm_w, bm_h = 2.4, 1.3
        bm_rect = patches.FancyBboxPatch(
            (x_bm_center - bm_w/2, y_shafts[0] - bm_h/2), bm_w, bm_h,
            boxstyle="round,pad=0.08", facecolor="#8e44ad", edgecolor="#5b2c6f", lw=2.2, zorder=5
        )
        ax.add_patch(bm_rect)
        p_mode_str = "REDUKCE DO SÍLY" if "red" in bm["mode"] else "RYCHLOBĚH"
        ax.text(x_bm_center, y_shafts[0] + 0.22, "BASE MODIFIER", ha="center", va="center",
                fontsize=7.4, fontweight="bold", color="#fcf3cf", zorder=6)
        ax.text(x_bm_center, y_shafts[0] - 0.05, f"{bm['count']}x PLAN. ({bm['ratio']:.2f}x)", ha="center", va="center",
                fontsize=7.2, fontweight="bold", color="white", zorder=6)
        ax.text(x_bm_center, y_shafts[0] - 0.32, f"[{p_mode_str}]", ha="center", va="center",
                fontsize=6.2, fontweight="bold", color="#f5b7b1" if "red" in bm["mode"] else "#d4efdf", zorder=6)

        eff_rpm = input_power * bm["ratio"]
        ax.text(x_bm_center, y_shafts[0] + 1.25,
                f"PŘEDŘAZENÝ MEZIČLEN (KOAXIÁLNÍ)\nZměna otáček osy: {input_power:,.0f} -> {eff_rpm:,.0f} RPM\nVáha: {bm['weight']:.1f} | Šířka auta: +0 hřídelí",
                ha="center", va="bottom", fontsize=7.4, fontweight="bold", color="#5b2c6f",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#f5eef8", edgecolor="#8e44ad", lw=1.2),
                zorder=12)
    else:
        ax.text(x_bm_center, y_shafts[0] + 0.8,
                "PŘÍMÝ NÁHON (1.00x)\n[Bez předřazeného mezičlenu]",
                ha="center", va="bottom", fontsize=7.2, fontweight="bold", color="#7f8c8d",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="#f8f9f9", edgecolor="#bdc3c7", lw=1.0, linestyle=":"),
                zorder=12)

    ax.text((x_motor_in + x_divider) / 2, max(y_shafts) + 3.0,
            "ZÓNA 1: PŘEDŘAZENÝ MEZIČLEN\n[KOAXIÁLNÍ PLANETOVÝ MODUL]",
            ha="center", va="bottom", fontsize=8.0, fontweight="bold", color="#6c3483",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#f5eef8", edgecolor="#8e44ad", lw=1.1),
            zorder=12)

    # Kótování rozteče D1
    ax.annotate('', xy=(dim_x1, y_shafts[0]), xytext=(dim_x1, y_shafts[1]),
                arrowprops=dict(arrowstyle='<->', color='#c0392b', lw=2.2))
    ax.annotate(
        f"ROZTEČ HŘÍDELÍ\nD = {D1:.1f} bloky",
        xy=(dim_x1, (y_shafts[0] + y_shafts[1]) / 2),
        ha="center", va="center", fontsize=8.0, fontweight="bold", color="#900c3f",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#fadbd8", edgecolor="#c0392b", lw=1.1),
        zorder=12
    )

    if stages == 2 and dim_x2 is not None:
        ax.annotate('', xy=(dim_x2, y_shafts[1]), xytext=(dim_x2, y_shafts[2]),
                    arrowprops=dict(arrowstyle='<->', color='#c0392b', lw=2.2))
        ax.annotate(
            f"ROZTEČ HŘÍDELÍ\nD = {D2:.1f} bloky",
            xy=(dim_x2, (y_shafts[1] + y_shafts[2]) / 2),
            ha="center", va="center", fontsize=8.0, fontweight="bold", color="#900c3f",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#fadbd8", edgecolor="#c0392b", lw=1.1),
            zorder=12
        )

    # ZÓNA 2: Vykreslení převodových sad
    def draw_stage_gears(st_info, x_positions, y_driver, y_driven, is_driven_sliding=True, stage_title="SADA 1", banner_color="#145a32"):
        items = st_info["items"]
        w = 0.65

        if is_driven_sliding and len(items) > 1:
            x_min_banner = x_positions[0] - 0.5
            x_max_banner = x_positions[len(items) - 1] + 1.4
            banner_y = max(y_shafts) + 3.0
            ax.annotate('', xy=(x_max_banner, banner_y), xytext=(x_min_banner, banner_y),
                        arrowprops=dict(arrowstyle='->', color=banner_color, lw=2.2))
            ax.text((x_min_banner + x_max_banner) / 2, banner_y + 0.22,
                    f"{stage_title}: AXIÁLNÍ POSUV (Pozice 0: klid  --->  +1 blok  --->  +2 bloky)",
                    ha="center", va="bottom", fontsize=8.0, fontweight="bold", color=banner_color,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#eafaf1", edgecolor=banner_color, lw=0.9),
                    zorder=12)

        for p_idx, it in enumerate(items):
            pair = it["pair"]
            d_name, f_name = pair["driving"], pair["driven"]
            r_d, r_f = pair["d_radius"], pair["f_radius"]
            t_d, t_f = pair["d_teeth"], pair["f_teeth"]
            p_count = pair["p_count"]
            p_mode = pair["p_mode"]
            eff_r = it["effective_ratio"]

            x_mesh = x_positions[p_idx]
            x_rest = x_mesh - p_idx * SHIFT_DELTA if is_driven_sliding else x_mesh
            mesh_y = y_driver + r_d

            # 1. Hnací kolo na pevné hřídeli
            rect_d = patches.Rectangle(
                (x_mesh - w/2, y_driver - r_d), w, 2 * r_d,
                facecolor=gear_colors[d_name]["face"], edgecolor=gear_colors[d_name]["edge"], lw=1.8, zorder=5
            )
            ax.add_patch(rect_d)

            # Popisek hnacího kola pod kolem
            lbl_y_d = y_driver - r_d - 0.45
            ax.text(x_mesh, lbl_y_d, f"{d_name} ({t_d}z)", ha="center", va="top",
                    fontsize=7.2, fontweight="bold", color=gear_colors[d_name]["edge"],
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#ffffff", edgecolor=gear_colors[d_name]["edge"], lw=0.9),
                    zorder=12)

            # 2. Hnané kolo na posuvné hřídeli
            if p_idx == 0:
                rect_f = patches.Rectangle(
                    (x_mesh - w/2, y_driven - r_f), w, 2 * r_f,
                    facecolor=gear_colors[f_name]["face"], edgecolor=gear_colors[f_name]["edge"], lw=1.8, zorder=5
                )
                ax.add_patch(rect_f)

                # Popisek hnaného kola nad kolem
                lbl_y_f = y_driven + r_f + 0.45
                ax.text(x_mesh, lbl_y_f, f"{f_name} ({t_f}z)\n[1. STUPEŇ - VÝCHOZÍ KLID]",
                        ha="center", va="bottom", fontsize=7.2, fontweight="bold", color=gear_colors[f_name]["edge"],
                        bbox=dict(boxstyle="round,pad=0.25", facecolor="#ffffff", edgecolor=gear_colors[f_name]["edge"], lw=0.9),
                        zorder=12)

                # Kontaktní linie záběru
                ax.plot([x_mesh - w/2 - 0.35, x_mesh + w/2 + 0.35], [mesh_y, mesh_y],
                        color="#e74c3c", linewidth=3.5, linestyle="-", zorder=8)
                ax.text(x_mesh, mesh_y + 0.28, "◀ AKTIVNÍ ZÁBĚR ▶",
                        ha="center", va="bottom", fontsize=6.8, fontweight="bold", color="#c0392b",
                        bbox=dict(boxstyle="round,pad=0.15", facecolor="#fef9e7", edgecolor="#e74c3c", lw=0.8),
                        zorder=12)

                if is_driven_sliding and len(items) > 1:
                    x_rest_ghost = x_mesh + SHIFT_DELTA
                    ghost_f0 = patches.Rectangle(
                        (x_rest_ghost - w/2, y_driven - r_f), w, 2 * r_f,
                        facecolor="#fef9e7", edgecolor="#f39c12",
                        lw=1.2, linestyle="--", alpha=0.35, hatch="..", zorder=3
                    )
                    ax.add_patch(ghost_f0)
                    ax.text(x_rest_ghost, y_driven, "odsun\n+1b", ha="center", va="center", fontsize=6.2, color="#7f8c8d", zorder=6)
            else:
                rect_f_rest = patches.Rectangle(
                    (x_rest - w/2, y_driven - r_f), w, 2 * r_f,
                    facecolor=gear_colors[f_name]["face"], edgecolor=gear_colors[f_name]["edge"], lw=1.8, zorder=5
                )
                ax.add_patch(rect_f_rest)

                lbl_y_rest = y_driven + r_f + 0.45
                ax.text(x_rest, lbl_y_rest, f"{f_name} ({t_f}z)\n[Klid mimo záběr]", ha="center", va="bottom",
                        fontsize=6.8, fontweight="bold", color=gear_colors[f_name]["edge"],
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="#ffffff", edgecolor=gear_colors[f_name]["edge"], lw=0.8),
                        zorder=12)

                ghost_f_active = patches.Rectangle(
                    (x_mesh - w/2, y_driven - r_f), w, 2 * r_f,
                    facecolor="#a9dfbf", edgecolor="#27ae60",
                    lw=2.2, linestyle="--", alpha=0.45, hatch="//", zorder=6
                )
                ax.add_patch(ghost_f_active)

                lbl_y_ghost = y_driven + r_f + 0.45
                ax.text(x_mesh, lbl_y_ghost, f"GHOST (+{p_idx}b)\n[{p_idx+1}. STUPEŇ ZÁBĚR]", ha="center", va="bottom",
                        fontsize=6.8, fontweight="bold", color="#145a32",
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="#eafaf1", edgecolor="#27ae60", lw=0.9),
                        zorder=12)

                arrow_y = y_driven + r_f + 1.25
                ax.annotate('', xy=(x_mesh, arrow_y), xytext=(x_rest, arrow_y),
                            arrowprops=dict(arrowstyle='->', color='#2980b9' if p_idx == 1 else '#8e44ad', lw=2.2))
                ax.text((x_rest + x_mesh) / 2, arrow_y + 0.18, f"POHYB +{p_idx}b (POZICE {p_idx})",
                        ha="center", va="bottom", fontsize=6.8, fontweight="bold",
                        color='#2980b9' if p_idx == 1 else '#8e44ad', zorder=12)

                ax.plot([x_mesh - w/2 - 0.25, x_mesh + w/2 + 0.25], [mesh_y, mesh_y],
                        color="#27ae60", linewidth=2.4, linestyle="--", zorder=7)

            # Planetový modul koaxiálně na hřídeli
            if p_count > 0:
                p_w, p_h = (1.2 if p_count == 2 else 0.95), 1.1
                px_mesh = x_mesh + w/2 + p_w/2 + 0.22
                p_rect = patches.FancyBboxPatch(
                    (px_mesh - p_w/2, y_driven - p_h/2), p_w, p_h,
                    boxstyle="round,pad=0.06", facecolor="#9b59b6", edgecolor="#6c3483", lw=1.6, zorder=7
                )
                ax.add_patch(p_rect)
                p_lbl = f"+{p_count}x PLANET.\n" + ("(5.29x)" if p_count == 2 and "od" in p_mode else ("(2.30x)" if "od" in p_mode else "(0.43x)"))
                ax.text(px_mesh, y_driven, p_lbl, ha="center", va="center",
                        fontsize=6.4, fontweight="bold", color="white", zorder=8)
                ax.plot([x_mesh + w/2, px_mesh - p_w/2], [y_driven, y_driven], color="#8e44ad", lw=3.0, zorder=4)

            # Spodní informační karta
            plan_desc = f" + {p_count}x Plan." if p_count > 0 else ""
            bm_note = f" (x Base {bm['ratio']:.2f}x)" if has_bm else ""
            role_desc = "[Síla / Rozjezd]" if eff_r < 1.0 else ("[Přímý náhon]" if abs(eff_r - 1.0) < 0.05 else "[Rychlost]")
            card_text = (
                f"POZICE {p_idx} " + ("(VÝCHOZÍ KLID)" if p_idx == 0 else f"(POSUN +{p_idx} BLOK)") + "\n"
                f"{d_name} ({t_d}z) -> {f_name} ({t_f}z){plan_desc}{bm_note}\n"
                f"Převod: {eff_r:.3f}x {role_desc} | Váha: {pair['weight']:.1f}"
            )
            card_color = "#27ae60" if p_idx == 0 else ("#2980b9" if p_idx == 1 else "#8e44ad")
            card_bg = "#eafaf1" if p_idx == 0 else ("#ebf5fb" if p_idx == 1 else "#f5eef8")
            card_y = -3.2
            ax.text(x_mesh, card_y, card_text, ha="center", va="top", fontsize=7.2, color="#1a252f",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor=card_bg, edgecolor=card_color, lw=1.2),
                    zorder=12)

    # Vykreslení Sady 1
    draw_stage_gears(stages_setup[0], x_positions_s1, y_shafts[0], y_shafts[1], is_driven_sliding=True, stage_title="SADA 1", banner_color="#145a32")

    # Vykreslení Sady 2 (pokud existuje)
    if stages == 2 and divider_x is not None:
        ax.axvline(divider_x, linestyle="-.", color="#7f8c8d", linewidth=1.6, alpha=0.7)
        draw_stage_gears(stages_setup[1], x_positions_s2, y_shafts[1], y_shafts[2], is_driven_sliding=True, stage_title="SADA 2", banner_color="#1b4f72")

    # Legenda Blueprintu
    legend_handles = [
        patches.Patch(facecolor="#3498db", edgecolor="#1f618d", label="Small Gear (8 zubů, r = 0.5)"),
        patches.Patch(facecolor="#f39c12", edgecolor="#d35400", label="Medium Gear (16 zubů, r = 1.5)"),
        patches.Patch(facecolor="#e74c3c", edgecolor="#922b21", label="Large Gear (24 zubů, r = 2.5)"),
        patches.Patch(facecolor="#8e44ad", edgecolor="#5b2c6f", label="Base Modifier / Planetární modul"),
        patches.Patch(facecolor="#d5f5e3", edgecolor="#27ae60", label="Posuvná hřídel (lineární vedení posuvu)"),
        patches.Patch(facecolor="#a9dfbf", edgecolor="#27ae60", alpha=0.55, linestyle="--", hatch="//", label="Ghost Block (záběr po přeřazení)")
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8.0, framealpha=0.95)

    ax.set_xlim(x_motor_in - 5.5, x_shaft_end + 1.5)
    ax.set_ylim(-4.8, max(y_shafts) + 5.5)
    ax.set_xticks([])
    ax.set_title(
        f"STAVEBNÍ PLÁNEK (BLUEPRINT) – {candidate['N']}-STUPŇOVÁ AUTOMATICKÁ PŘEVODOVKA "
        f"[HŘÍDELÍ: {candidate['shaft_count']}, VÁHA: {candidate['weight']:.1f}, SCORE: {candidate['total_score']:.1f}]",
        fontsize=11.5, fontweight="bold", color="#1a5276", pad=12
    )
    ax.set_xlabel("Axiální souřadnice podél hřídelí ve hře Screwdrivers [bloky]", fontsize=9.5, fontweight="bold")
    ax.set_ylabel("Fyzické bloky ve hře", fontsize=9.5)
    ax.grid(True, linestyle=":", alpha=0.35)


# ==============================================================================
# 9. VIZUALIZACE GRAFŮ V MATPLOTLIB (3-ÚROVŇOVÝ LAYOUT + WIDGET SWITCHER)
# ==============================================================================

def plot_transmission_simulation(
    result: Dict[str, Any],
    save_path: Optional[str] = "prevodovka_vysledky.png",
    show_gui: bool = True
) -> None:
    """
    Vykreslí komplexní vizualizaci simulace automatické převodovky s interaktivním přepínáním blueprintů:
    - Řádek 1 (ax1, ax2):
      * ax1: Srovnání průběhu otáček na hřídelích pro 2, 3 a 4-stupňovou převodovku.
      * ax2: Rozklad Total Fitness Score (Footprint, Shifting Penalty, Smoothness Bonus).
    - Řádek 2 (ax_info):
      * Detailní přehled použitých kol, počtu zubů, pozic, Base Modifieru a otáček.
    - Ovládací widget (ax_radio):
      * Klikací menu RadioButtons pro interaktivní přepínání stavebního plánku mezi kandidáty.
    - Řádek 3 (ax3):
      * Stavební plánek (Blueprint) – montážní nákres s Base Modifierem a Ghost bloky vybrané převodovky.
    """
    winner = result["winner"]
    inp = result["input_power"]
    tgt = result["target_power"]
    best_by_speed = result["best_by_speed"]
    bm = winner["hw"]["base_modifier"]

    fig = plt.figure(figsize=(22, 16))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.0, 0.36, 1.45], hspace=0.48, wspace=0.20)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax_info = fig.add_subplot(gs[1, :])
    ax3 = fig.add_subplot(gs[2, :])

    bm_title_str = f" | Base Mod: {bm['short']}" if bm['count'] > 0 else " | Bez mezičlenu"
    fig.suptitle(
        f"Simulace automatické převodovky Screwdrivers – Optimalizace Total Fitness Score, Base Modifier & Stacking planet\n"
        f"Vstup: {inp:g} RPM | Cíl: {tgt:g} RPM | Vítěz: {winner['N']}-stupňová (Score: {winner['total_score']:.1f} | Váha: {winner['weight']:.1f}{bm_title_str})",
        fontsize=13, fontweight="bold", y=0.988
    )

    # --------------------------------------------------------------------------
    # Panel 1: Průběh otáček pro nejlepší 2-, 3- a 4-stupňovou převodovku
    # --------------------------------------------------------------------------
    compare_speeds = [n for n in [2, 3, 4] if n in best_by_speed]
    max_shafts = max((best_by_speed[n]["shaft_count"] for n in compare_speeds), default=winner["shaft_count"])

    shaft_indices = list(range(1, max_shafts + 1))
    shaft_labels = []
    for s in shaft_indices:
        if s == 1:
            shaft_labels.append("Hřídel 1\n(Vstup / Motor)")
        elif s == max_shafts:
            shaft_labels.append(f"Hřídel {s}\n(Výstup)")
        else:
            shaft_labels.append(f"Hřídel {s}\n(Předloha)")

    for s in shaft_indices:
        ax1.axvline(s, color="#bdc3c7", linestyle=":", linewidth=1.2, alpha=0.7, zorder=1)

    t_min, t_max = tgt * 0.95, tgt * 1.05
    ax1.axhspan(t_min, t_max, color="#2ecc71", alpha=0.18, label=f"Cílové pásmo ±5 % ({t_min:,.0f}–{t_max:,.0f} RPM)", zorder=1)
    ax1.axhline(tgt, color="#27ae60", linestyle="--", linewidth=1.8, label=f"Cílové otáčky ({tgt:g} RPM)", zorder=2)

    cand_styles = {
        2: {"name": "2-stupňová", "ls": "--", "m": "s", "colors": ["#2980b9", "#1f618d"]},
        3: {"name": "3-stupňová", "ls": "-.", "m": "^", "colors": ["#e67e22", "#d35400", "#b9770e"]},
        4: {"name": "4-stupňová", "ls": "-",  "m": "o", "colors": ["#8e44ad", "#27ae60", "#16a085", "#2c3e50"]}
    }

    all_y_vals = [inp, tgt]

    for n in compare_speeds:
        cand = best_by_speed[n]
        c_hw = cand["hw"]
        c_bm = c_hw["base_modifier"]
        is_win = (n == winner["N"])
        c_cfg = cand_styles.get(n, {"name": f"{n}-stupňová", "ls": "-", "m": "o", "colors": ["#34495e"] * n})

        for g_idx, g_info in enumerate(cand["gears"]):
            c_color = c_cfg["colors"][g_idx % len(c_cfg["colors"])]
            r_val = g_info["ratio"]
            rpm_val = inp * r_val
            all_y_vals.append(rpm_val)

            xs = [1.0]
            ys = [inp]
            curr_val = inp * c_bm["ratio"]

            if c_hw["stages"] == 2:
                xs.append(2.0)
                curr_val *= g_info["stage_ratios"][0]
                ys.append(curr_val)
                all_y_vals.append(curr_val)
                xs.append(3.0)
                curr_val *= g_info["stage_ratios"][1]
                ys.append(curr_val)
                all_y_vals.append(curr_val)
            else:
                xs.append(2.0)
                curr_val *= g_info["stage_ratios"][0]
                ys.append(curr_val)
                all_y_vals.append(curr_val)

            win_str = " [VÍTĚZ]" if is_win and g_idx == 0 else ""
            lbl = f"{c_cfg['name']}: {g_idx+1}. st ({rpm_val:,.0f} RPM){win_str}"
            lw = 2.4 if is_win else 1.6
            ms = 7 if is_win else 5.5
            ax1.plot(xs, ys, marker=c_cfg["m"], markersize=ms, linestyle=c_cfg["ls"],
                     linewidth=lw, label=lbl, color=c_color, zorder=5)

    ax1.set_xticks(shaft_indices)
    ax1.set_xticklabels(shaft_labels, fontsize=9.5, fontweight="bold")
    ax1.set_xlim(0.7, max_shafts + 0.45)
    ax1.set_ylim(min(all_y_vals) * 0.85, max(all_y_vals) * 1.15)
    ax1.set_title("Srovnání průběhu otáček na hřídelích (2, 3 a 4-stupňová)", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Fyzické hřídele (Šířka sestavy)", fontsize=9.5, fontweight="bold")
    ax1.set_ylabel("Otáčky [RPM]", fontsize=9.5)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left", fontsize=7.5, framealpha=0.92, ncol=2)

    # --------------------------------------------------------------------------
    # Panel 2: Rozklad Total Fitness Score (Footprint, Shifting, Smoothness)
    # --------------------------------------------------------------------------
    speeds_avail = sorted(best_by_speed.keys())
    n_labels = [f"{n}-stupňová\n(Score: {best_by_speed[n]['total_score']:.1f})" for n in speeds_avail]
    scores = [best_by_speed[n]["total_score"] for n in speeds_avail]
    footprints = [best_by_speed[n]["footprint_penalty"] for n in speeds_avail]
    shiftings = [best_by_speed[n]["shifting_penalty"] for n in speeds_avail]
    smoothnesses = [best_by_speed[n]["smoothness_bonus"] for n in speeds_avail]

    x_bars = np.arange(len(n_labels))
    width = 0.20

    r1 = ax2.bar(x_bars - 1.5 * width, scores, width, label="Total Fitness Score (nižší = lepší)", color="#2c3e50")
    r2 = ax2.bar(x_bars - 0.5 * width, footprints, width, label=f"Footprint Penalty (váha + hřídele @ {result['width_penalty']:.0f})", color="#2980b9")
    r3 = ax2.bar(x_bars + 0.5 * width, shiftings, width, label=f"Shifting Penalty (+{result['shift_penalty_per_gear']:.1f}/st.)", color="#e74c3c")
    r4 = ax2.bar(x_bars + 1.5 * width, smoothnesses, width, label="Smoothness Bonus (odečet bodů)", color="#27ae60")

    ax2.set_xticks(x_bars)
    ax2.set_xticklabels(n_labels, fontsize=9, fontweight="bold")
    ax2.set_title("Rozklad Total Fitness Score (Footprint, Shifting & Smoothness)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Hodnotící body [Score]", fontsize=9.5)
    ax2.grid(True, linestyle=":", alpha=0.6, axis="y")
    ax2.legend(loc="upper left", fontsize=7.5)

    max_bar = max(max(scores), max(footprints), max(shiftings), max(smoothnesses), 1)
    ax2.set_ylim(0, max_bar * 1.25)

    for rect in r1:
        h = rect.get_height()
        ax2.annotate(f"{h:.1f}", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=7.5, fontweight="bold")
    for rect in r2:
        h = rect.get_height()
        ax2.annotate(f"{h:.0f}", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=7.0, color="#1b4f72")
    for rect in r3:
        h = rect.get_height()
        ax2.annotate(f"{h:.1f}", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=7.0, color="#922b21")
    for rect in r4:
        h = rect.get_height()
        ax2.annotate(f"-{h:.1f}", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=7.0, color="#145a32")

    # --------------------------------------------------------------------------
    # Panel Info: Detailní karty pro 2, 3 a 4-stupňovou převodovku
    # --------------------------------------------------------------------------
    ax_info.axis("off")
    col_speeds = [n for n in [2, 3, 4] if n in best_by_speed]
    n_cols = max(len(col_speeds), 1)

    for c_i, n in enumerate(col_speeds):
        cand = best_by_speed[n]
        is_win = (n == winner["N"])
        c_hw = cand["hw"]
        c_bm = c_hw["base_modifier"]
        x_left = 0.02 + c_i * (0.96 / n_cols)
        col_w = 0.96 / n_cols - 0.02

        bg_col = "#eafaf1" if is_win else "#fdfefe"
        bd_col = "#27ae60" if is_win else "#bdc3c7"
        lw_box = 2.0 if is_win else 1.0

        title_str = f"{n}-STUPŇOVÁ PŘEVODOVKA" + (" [ABSOLUTNÍ VÍTĚZ]" if is_win else "")
        info_lines = [
            f"{title_str}",
            f"Score: {cand['total_score']:.1f} | Hřídelí: {cand['shaft_count']} | Váha: {cand['weight']:.1f} | Shift: +{cand['shifting_penalty']:.1f}",
            f"Předřazený mezičlen: {c_bm['desc']}",
            ""
        ]

        for g_idx, g in enumerate(cand["gears"]):
            r_val = g["ratio"]
            rpm_val = inp * r_val
            role = "[Rozjezd/Síla]" if g_idx == 0 else ("[Max. rychlost]" if g_idx == len(cand["gears"]) - 1 else "[Přechod]")
            if c_hw["stages"] == 1:
                p = g["pairs"][0]
                p_desc = f"+{p['p_count']}xP" if p['p_count'] > 0 else ""
                comb_str = f"P{g['pos_path'][0]}: {p['driving']}->{p['driven']}{p_desc}"
                info_lines.append(f" • {g_idx+1}. st: {comb_str} [{r_val:.2f}x -> {rpm_val:,.0f} RPM] {role}")
            else:
                pairs_str = " | ".join(f"P{pos}: {p['driving']}->{p['driven']}" for pos, p in zip(g["pos_path"], g["pairs"]))
                info_lines.append(f" • {g_idx+1}. st: {pairs_str} [{r_val:.2f}x -> {rpm_val:,.0f} RPM] {role}")

        text_block = "\n".join(info_lines)
        ax_info.text(
            x_left + col_w / 2, 0.50, text_block,
            ha="center", va="center", fontsize=7.6, color="#1a252f",
            bbox=dict(boxstyle="round,pad=0.5", facecolor=bg_col, edgecolor=bd_col, lw=lw_box)
        )

    # --------------------------------------------------------------------------
    # Interaktivní widget (RadioButtons) pro přepínání blueprintu
    # --------------------------------------------------------------------------
    bbox_3 = ax3.get_position()
    y_radio = bbox_3.y1 + 0.022
    h_radio = 0.052
    w_radio = 0.22
    ax_radio = fig.add_axes([bbox_3.x0, y_radio, w_radio, h_radio], facecolor="#eaf2f8")
    ax_radio.set_title("INTERAKTIVNÍ VÝBĚR BLUEPRINTU:", fontsize=8.5, fontweight="bold", loc="left", pad=4, color="#1b4f72")

    radio_labels = []
    label_map = {}
    for n in speeds_avail:
        lbl = f"{n}-stupňová (VÍTĚZ)" if n == winner["N"] else f"{n}-stupňová"
        radio_labels.append(lbl)
        label_map[lbl] = n

    active_idx = speeds_avail.index(winner["N"])
    radio_widget = RadioButtons(ax_radio, radio_labels, active=active_idx, activecolor="#1b4f72")

    for lbl in radio_widget.labels:
        lbl.set_fontsize(8.5)
        lbl.set_fontweight("bold")
        lbl.set_color("#1a252f")

    def on_select_blueprint(label: str) -> None:
        n_sel = label_map[label]
        cand_sel = best_by_speed[n_sel]
        ax3.clear()
        draw_gearbox_blueprint(ax3, cand_sel, input_power=inp)
        fig.canvas.draw_idle()

    radio_widget.on_clicked(on_select_blueprint)
    fig._radio_widget = radio_widget  # Trvalá reference pro udržení widgetu aktivního v paměti

    # --------------------------------------------------------------------------
    # Panel 3: Výchozí stavební plánek (Blueprint) vítězné převodovky
    # --------------------------------------------------------------------------
    draw_gearbox_blueprint(ax3, winner, input_power=inp)

    if save_path:
        abs_save = os.path.abspath(save_path)
        plt.savefig(abs_save, dpi=160, bbox_inches="tight")
        print(f"\n[OK] Graf byl úspěšně uložen do souboru: {abs_save}")

    if show_gui:
        try:
            plt.show()
        except Exception:
            pass


# ==============================================================================
# 10. SPOUŠTĚCÍ BOD A CLI PARAMETRY
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Simulace a optimalizace automatické převodovky pro hru Screwdrivers (Total Fitness Score & Base Modifiers)."
    )
    parser.add_argument("-i", "--input-power", type=float, default=1000.0, help="Vstupní otáčky motoru [RPM] (výchozí: 1000.0)")
    parser.add_argument("-t", "--target-power", type=float, default=4500.0, help="Cílové výstupní otáčky [RPM] (výchozí: 4500.0)")
    parser.add_argument("-s", "--shift-penalty", type=float, default=DEFAULT_SHIFT_PENALTY_PER_GEAR, help=f"Penalizace za každé přeřazení (výchozí: {DEFAULT_SHIFT_PENALTY_PER_GEAR})")
    parser.add_argument("-w", "--width-penalty", type=float, default=DEFAULT_WIDTH_PENALTY, help=f"Masivní penalizace za každou paralelní hřídel (výchozí: {DEFAULT_WIDTH_PENALTY})")
    parser.add_argument("--smoothness-weight", type=float, default=DEFAULT_SMOOTHNESS_WEIGHT, help=f"Váha bonusu za plynulost řazení (výchozí: {DEFAULT_SMOOTHNESS_WEIGHT})")
    parser.add_argument("--max-launch", type=float, default=DEFAULT_MAX_LAUNCH_RATIO, help=f"Maximální převodový poměr 1. stupně pro rozjezdovou sílu (výchozí: {DEFAULT_MAX_LAUNCH_RATIO})")
    parser.add_argument("--save", type=str, default="prevodovka_vysledky.png", help="Cesta pro uložení výsledného grafu (PNG)")
    parser.add_argument("--no-gui", action="store_true", help="Vypnout zobrazení GUI okna Matplotlib")

    args = parser.parse_args()

    result = optimize_automatic_transmission(
        input_power=args.input_power,
        target_power=args.target_power,
        shift_penalty_per_gear=args.shift_penalty,
        width_penalty=args.width_penalty,
        smoothness_weight=args.smoothness_weight,
        max_launch_ratio=args.max_launch
    )

    print_transmission_report(result)

    plot_transmission_simulation(
        result=result,
        save_path=args.save,
        show_gui=not args.no_gui
    )


if __name__ == "__main__":
    main()
