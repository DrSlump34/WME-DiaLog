#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DiaLog / Phase 1 -- Diff incremental des arretes permanents.

Repose sur la cle stable verifiee en Phase 0 : 'identifier#organization.uuid'
(10 541 valeurs, 0 collision). 'identifier' seul n'est PAS unique.

Principe : chaque collecte produit un INSTANTANE compact (une empreinte par
arrete, pas les donnees completes). Comparer deux instantanes donne les
arretes apparus, disparus et modifies -- et, pour les modifies, la NATURE du
changement (valeur reglementaire, trace, localisation, intitule).

Les empreintes sont separees par nature, pour distinguer une correction de
trace d'un vrai changement de reglementation.

Dependances : bibliotheque standard uniquement.
Usage :
    python diff_dialog.py --instantane            # en creer un depuis le cache
    python diff_dialog.py --instantane --refresh  # collecte fraiche puis instantane
    python diff_dialog.py                         # comparer les 2 derniers
    python diff_dialog.py --depuis A.json --vers B.json
    python diff_dialog.py --tout                  # sans filtrer sur l'interet WME
"""

import argparse
import collections
import datetime as dt
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase0_inventaire import (CACHE, DEPARTEMENTS, collecter, normaliser,
                               rattacher_orgs)

INSTANTANES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instantanes")

TYPES_UTILES = {"speedLimitation", "noEntry"}


def _h(obj):
    """Empreinte stable d'une structure : JSON trie puis sha1 tronque."""
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def empreintes(reg):
    """Trois empreintes distinctes : reglementation, trace, localisation texte."""
    regl, geo, loc = [], [], []
    for m in reg.get("measures") or []:
        vs = m.get("vehicleSet") or {}
        regl.append({
            "type": m.get("type"),
            "maxSpeed": m.get("maxSpeed"),
            "restricted": sorted(
                (t.get("name") if isinstance(t, dict) else t) or ""
                for t in (vs.get("restrictedTypes") or [])),
            "exempted": sorted(
                (t.get("name") if isinstance(t, dict) else t) or ""
                for t in (vs.get("exemptedTypes") or [])),
            "carac": sorted((c.get("name"), c.get("value"))
                            for c in (vs.get("maxCharacteristics") or [])),
            "periodes": [
                {"r": p.get("recurrenceType"),
                 "ts": sorted((t.get("startTime"), t.get("endTime"))
                              for t in (p.get("timeSlots") or []))}
                for p in (m.get("periods") or [])],
        })
        for lo in (m.get("locations") or []):
            geo.append(lo.get("geometry"))
            ns = lo.get("namedStreet") or {}
            nr = lo.get("numberedRoad") or {}
            loc.append({
                "roadType": lo.get("roadType"),
                "city": ns.get("cityLabel"), "road": ns.get("roadName"),
                "num": nr.get("roadNumber"),
                "pr": (nr.get("fromPointNumber"), nr.get("toPointNumber")),
            })
    return _h(regl), _h(geo), _h(loc)


def construire_instantane(regs, norm, collecte):
    par_cle = {r["cle"]: r for r in norm}
    arretes = {}
    for r in regs:
        org = r.get("organization") or {}
        cle = f"{r.get('identifier')}#{org.get('uuid')}"
        hr, hg, hl = empreintes(r)
        n = par_cle.get(cle)
        types = sorted({m.get("type") for m in (r.get("measures") or [])
                        if m.get("type")})
        vitesses = sorted({m.get("maxSpeed") for m in (r.get("measures") or [])
                           if m.get("maxSpeed") is not None})
        arretes[cle] = {
            "titre": r.get("title"),
            "org": org.get("name"),
            "dept": (sorted(n["depts"])[0] if n and n["depts"] else None),
            "types": types,
            "vitesses": vitesses,
            "debut": r.get("startDate"),
            "hr": hr, "hg": hg, "hl": hl,
        }
    return {"collecte": collecte, "nb": len(arretes), "arretes": arretes}


def chemin_instantane(collecte):
    horo = collecte.replace(":", "").replace("-", "").replace("+0000", "")[:15]
    return os.path.join(INSTANTANES, f"instantane_{horo}.json")


def lister_instantanes():
    return sorted(glob.glob(os.path.join(INSTANTANES, "instantane_*.json")))


def charger(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def utile(info):
    return bool(set(info.get("types") or []) & TYPES_UTILES)


def comparer(av, ap, filtrer=True):
    a, b = av["arretes"], ap["arretes"]
    ca, cb = set(a), set(b)

    nouveaux = [(k, b[k]) for k in cb - ca]
    disparus = [(k, a[k]) for k in ca - cb]

    modifies = []
    for k in ca & cb:
        x, y = a[k], b[k]
        natures = []
        if x["hr"] != y["hr"]:
            natures.append("reglementation")
        if x["hg"] != y["hg"]:
            natures.append("trace")
        if x["hl"] != y["hl"]:
            natures.append("localisation")
        if (x.get("titre") or "") != (y.get("titre") or ""):
            natures.append("intitule")
        if natures:
            modifies.append((k, x, y, natures))

    if filtrer:
        nouveaux = [t for t in nouveaux if utile(t[1])]
        disparus = [t for t in disparus if utile(t[1])]
        modifies = [t for t in modifies if utile(t[2]) or utile(t[1])]

    return nouveaux, disparus, modifies


def resume(info):
    d = info.get("dept")
    lieu = f"{d} {DEPARTEMENTS.get(d, '')}" if d else "dept inconnu"
    t = ",".join(info.get("types") or []) or "?"
    v = info.get("vitesses") or []
    vit = f" {v[0]} km/h" if len(v) == 1 else (f" {v}" if v else "")
    return f"[{lieu}] {t}{vit} -- {(info.get('org') or '?')[:28]} -- {(info.get('titre') or '')[:52]}"


def rapport(av, ap, nouveaux, disparus, modifies, filtrer):
    print()
    print("#" * 78)
    print("#  DiaLog -- DIFF INCREMENTAL")
    print(f"#  avant : {av['collecte']}  ({av['nb']} arretes)")
    print(f"#  apres : {ap['collecte']}  ({ap['nb']} arretes)")
    if filtrer:
        print("#  filtre : uniquement speedLimitation et noEntry "
              "(--tout pour lever)")
    print("#" * 78)

    print(f"\nApparus   : {len(nouveaux)}")
    print(f"Disparus  : {len(disparus)}")
    print(f"Modifies  : {len(modifies)}")

    if not (nouveaux or disparus or modifies):
        print("\nAucun changement.")
        return

    # Organisations qui entrent dans la base
    orgs_av = {i.get("org") for i in av["arretes"].values()}
    orgs_ap = {i.get("org") for i in ap["arretes"].values()}
    entrants = sorted(o for o in orgs_ap - orgs_av if o)
    if entrants:
        print(f"\nNOUVELLES ORGANISATIONS ({len(entrants)}) :")
        for o in entrants[:20]:
            n = sum(1 for i in ap["arretes"].values() if i.get("org") == o)
            print(f"  {o[:52]:<52} {n:>5} arretes")

    if nouveaux:
        par_dept = collections.Counter(i.get("dept") or "?" for _, i in nouveaux)
        print(f"\nAPPARUS par departement :")
        for d, n in par_dept.most_common(15):
            print(f"  {d:<5} {DEPARTEMENTS.get(d, ''):<26} {n:>5}")
        print(f"\nDetail des apparus ({min(len(nouveaux), 25)} sur {len(nouveaux)}) :")
        for k, i in sorted(nouveaux, key=lambda x: (x[1].get("dept") or "zz"))[:25]:
            print(f"  + {resume(i)}")

    if disparus:
        print(f"\nDISPARUS ({min(len(disparus), 15)} sur {len(disparus)}) :")
        for k, i in disparus[:15]:
            print(f"  - {resume(i)}")

    if modifies:
        par_nature = collections.Counter()
        for _, _, _, nat in modifies:
            par_nature[" + ".join(nat)] += 1
        print(f"\nMODIFIES par nature :")
        for n, c in par_nature.most_common():
            print(f"  {n:<40} {c:>5}")

        # Le changement de reglementation est le seul qui impose une reedition.
        regl = [m for m in modifies if "reglementation" in m[3]]
        print(f"\n  Dont changement de REGLEMENTATION : {len(regl)} "
              "(les seuls imposant une reedition)")
        for k, x, y, nat in regl[:20]:
            print(f"    ~ {resume(y)}")
            if x.get("vitesses") != y.get("vitesses"):
                print(f"        vitesse : {x.get('vitesses')} -> {y.get('vitesses')}")
            if x.get("types") != y.get("types"):
                print(f"        types   : {x.get('types')} -> {y.get('types')}")

        trace = [m for m in modifies if nat_only(m[3], "trace")]
        if trace:
            print(f"\n  Trace corrige sans changement de fond : {len(trace)} "
                  "(pas de reedition necessaire)")


def nat_only(natures, seule):
    return natures == [seule]


def main():
    ap_ = argparse.ArgumentParser(description="DiaLog -- diff incremental")
    ap_.add_argument("--instantane", action="store_true",
                     help="creer un instantane et sortir")
    ap_.add_argument("--refresh", action="store_true",
                     help="avec --instantane : recollecter depuis l'API")
    ap_.add_argument("--depuis", help="fichier instantane de depart")
    ap_.add_argument("--vers", help="fichier instantane d'arrivee")
    ap_.add_argument("--tout", action="store_true",
                     help="ne pas filtrer sur les types utiles a WME")
    a = ap_.parse_args()

    os.makedirs(INSTANTANES, exist_ok=True)

    if a.instantane:
        if a.refresh:
            d = collecter(refresh=True)
        else:
            if not os.path.exists(CACHE):
                sys.exit("Cache absent. Lancer : python phase0_inventaire.py --refresh")
            with open(CACHE, encoding="utf-8") as f:
                d = json.load(f)
        norm = normaliser(d["regulations"])
        rattacher_orgs(norm)
        inst = construire_instantane(d["regulations"], norm, d["collecte"])
        p = chemin_instantane(d["collecte"])
        with open(p, "w", encoding="utf-8") as f:
            json.dump(inst, f, ensure_ascii=False)
        print(f"Instantane ecrit : {p}")
        print(f"  {inst['nb']} arretes empreintes "
              f"({os.path.getsize(p) / 1024 / 1024:.1f} Mo)")
        return

    if a.depuis and a.vers:
        pav, pap = a.depuis, a.vers
    else:
        liste = lister_instantanes()
        if len(liste) < 2:
            print(f"Il faut au moins 2 instantanes ({len(liste)} trouve(s)).")
            print("Creer le premier :  python diff_dialog.py --instantane")
            print("Puis, plus tard  :  python diff_dialog.py --instantane --refresh")
            return
        pav, pap = liste[-2], liste[-1]

    av, apres = charger(pav), charger(pap)
    n, d, m = comparer(av, apres, filtrer=not a.tout)
    rapport(av, apres, n, d, m, filtrer=not a.tout)


if __name__ == "__main__":
    main()
