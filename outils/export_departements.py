#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DiaLog — Export départemental destiné au userscript WME DiaLog.

Distinct de export_wme.py (qui alimente le listing et garde tout) : ici on
produit des fichiers LEGERS, destines a etre telecharges dans le navigateur.

Trois differences :
  1. la regle metier de l'auteur est appliquee -- seuls les vehicules de
     tourisme, taxis et motos concernent Waze, donc tout gabarit (poids,
     hauteur, largeur, longueur) et toute categorie etrangere sont ecartes ;
  2. les proprietes sont reduites au strict necessaire a l'affichage ;
  3. les coordonnees sont arrondies a 6 decimales (~10 cm) et le JSON est
     ecrit sans espaces.

Produit aussi index.json : la bbox reelle de chaque departement, calculee sur
les donnees. C'est ce qui permet au userscript de savoir quel fichier charger
SANS dependance a un service de geocodage.

Usage : python export_departements.py
"""

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase0_inventaire import CACHE, DEPARTEMENTS, normaliser, rattacher_orgs

RACINE = os.path.dirname(os.path.abspath(__file__))
SORTIE = os.path.join(RACINE, "departements")

TYPES = {"speedLimitation": "V", "noEntry": "I"}

# Meme regle que le userscript (WME-DiaLog.user.js).
RE_HORS_TOURISME = re.compile(
    r"heavygoods|poids\s*lourd|\btonne|camion|grumier|autocar|\bbus\b|"
    r"semi.?remorque|agricol|agyicol|agricio|tracteur|hazardous|mati[eè]re|"
    r"caravan|camping.?car|convoi|\bengin|remorque|\d\s*[,.]?\d*\s*t\b|"
    r"transport\s+de\s+d[ée]chets", re.I)

RE_RIVERAIN = re.compile(r"riverain|desserte?\s+locale|\bdeserte\b|localresident", re.I)
RE_LIVRAISON = re.compile(r"livrais|citylogistic|demenag", re.I)
RE_AGRICOLE = re.compile(r"agricol|agyicol|agricio", re.I)

VITESSES = {20, 30, 50, 70, 80, 90, 110, 130}


def libelles(l):
    return " | ".join(str((x.get("name") if isinstance(x, dict) else x) or "")
                      for x in (l or []))


def concerne_tourisme(carac, restrictions):
    if any(k in carac for k in ("weight", "height", "width", "length")):
        return False
    return not RE_HORS_TOURISME.search(restrictions)


def periodes(ps):
    if not ps:
        return True, "permanent"
    creneaux, tous = [], True
    for p in ps:
        if p.get("recurrenceType") != "everyDay":
            tous = False
        for t in (p.get("timeSlots") or []):
            d = (t.get("startTime") or "")[11:16]
            f = (t.get("endTime") or "")[11:16]
            if d or f:
                creneaux.append(d + "-" + f)
    if not creneaux and tous:
        return True, "permanent"
    b = []
    if creneaux:
        b.append(" / ".join(sorted(set(creneaux))))
    if not tous:
        b.append("certains jours")
    return False, ", ".join(b) or "récurrent"


def lineaires(geo):
    if not geo:
        return []
    if geo.get("type") == "GeometryCollection":
        out = []
        for g in geo.get("geometries") or []:
            out.extend(lineaires(g))
        return out
    return [geo] if geo.get("coordinates") else []


def arrondir(c):
    """Arrondit toutes les coordonnees a 6 decimales, en place."""
    if isinstance(c, list):
        if len(c) == 2 and all(isinstance(v, (int, float)) for v in c):
            return [round(c[0], 6), round(c[1], 6)]
        return [arrondir(x) for x in c]
    return c


def bbox_et_centre(geo):
    pts = []
    pile = [geo.get("coordinates")]
    while pile:
        x = pile.pop()
        if isinstance(x, list) and len(x) == 2 and all(isinstance(v, (int, float)) for v in x):
            pts.append(x)
        elif isinstance(x, list):
            pile.extend(x)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return ([round(min(xs), 6), round(min(ys), 6), round(max(xs), 6), round(max(ys), 6)],
            round(sum(xs) / len(xs), 6), round(sum(ys) / len(ys), 6))


def main():
    if not os.path.exists(CACHE):
        sys.exit("Cache absent. Lancer : python phase0_inventaire.py --refresh")
    with open(CACHE, encoding="utf-8") as f:
        d = json.load(f)
    norm = normaliser(d["regulations"])
    rattacher_orgs(norm)
    par_cle = {r["cle"]: r for r in norm}

    par_dept = collections.defaultdict(list)
    total = ecartes = 0

    for r in d["regulations"]:
        org = r.get("organization") or {}
        cle = f"{r.get('identifier')}#{org.get('uuid')}"
        n = par_cle.get(cle)
        dept = (sorted(n["depts"])[0] if n and n["depts"] else None)

        for m in r.get("measures") or []:
            if m.get("type") not in TYPES:
                continue
            total += 1
            vs = m.get("vehicleSet") or {}
            carac = {c.get("name"): c.get("value")
                     for c in (vs.get("maxCharacteristics") or []) if c.get("name")}
            restrictions = libelles(vs.get("restrictedTypes"))
            exemptions = libelles(vs.get("exemptedTypes"))
            if not concerne_tourisme(carac, restrictions):
                ecartes += 1
                continue

            perm, appli = periodes(m.get("periods"))
            alertes = []
            if m["type"] == "speedLimitation":
                v = m.get("maxSpeed")
                if v is None:
                    alertes.append("vitesse absente")
                elif v not in VITESSES:
                    alertes.append(f"vitesse inhabituelle ({v})")
            if not perm:
                alertes.append("restriction horaire")

            sauf = []
            if RE_RIVERAIN.search(exemptions):
                sauf.append("riverains")
            if RE_LIVRAISON.search(exemptions):
                sauf.append("livraisons")
            if RE_AGRICOLE.search(exemptions):
                sauf.append("agricole")

            if m["type"] == "speedLimitation":
                valeur = (f"{m.get('maxSpeed')} km/h" if m.get("maxSpeed") is not None
                          else "vitesse non précisée")
            else:
                valeur = "Interdit" + (" sauf " + ", ".join(sauf) if sauf else "")

            for loc in (m.get("locations") or []):
                if not loc.get("geometry"):
                    continue
                try:
                    geo = json.loads(loc["geometry"])
                except (ValueError, TypeError):
                    continue
                ns = loc.get("namedStreet") or {}
                nr = loc.get("numberedRoad") or {}
                voie = ns.get("roadName") or ""
                if not voie and nr.get("roadNumber"):
                    voie = nr["roadNumber"]
                    if nr.get("fromPointNumber") is not None:
                        voie += f" PR {nr['fromPointNumber']}"
                commune = ns.get("cityLabel") or ""
                if commune.endswith(")") and "(" in commune:
                    commune = commune.rsplit("(", 1)[0].strip()

                for g in lineaires(geo):
                    bc = bbox_et_centre(g)
                    if not bc:
                        continue
                    bbox, cx, cy = bc
                    ponctuel = g.get("type") in ("Point", "MultiPoint")
                    g = {"type": g["type"], "coordinates": arrondir(g["coordinates"])}
                    par_dept[dept or "00"].append({
                        "t": TYPES[m["type"]],
                        "v": valeur,
                        "r": voie,
                        "c": commune,
                        "a": appli,
                        "p": 1 if perm else 0,
                        "rv": 1 if RE_RIVERAIN.search(exemptions) else 0,
                        "al": " ; ".join(alertes + (["géométrie ponctuelle"] if ponctuel else [])),
                        "ti": (r.get("title") or "")[:120],
                        "o": org.get("name") or "",
                        "b": bbox, "x": cx, "y": cy,
                        "g": g,
                    })

    os.makedirs(SORTIE, exist_ok=True)
    index = {}
    print(f"Mesures utiles   : {total}")
    print(f"Ecartees (regle tourisme/taxi/moto) : {ecartes} ({ecartes/total:.1%})")
    print(f"Conservees       : {total - ecartes}\n")
    print(f"{'dep':<5}{'nom':<26}{'lignes':>8}{'Ko':>8}")

    total_ko = 0
    for dep in sorted(par_dept):
        # '00' = arretes dont le departement n'a pas pu etre resolu. Ils ne sont
        # rattachables a aucune vue : ni fichier, ni entree d'index.
        if dep == "00":
            print(f"{'--':<5}{'(departement non resolu)':<26}"
                  f"{len(par_dept[dep]):>8}{'ignore':>8}")
            continue
        lignes = par_dept[dep]
        chemin = os.path.join(SORTIE, f"dept_{dep}.json")
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(lignes, f, ensure_ascii=False, separators=(",", ":"))
        ko = os.path.getsize(chemin) / 1024
        total_ko += ko
        xs = [l["b"] for l in lignes]
        index[dep] = {
            "nom": DEPARTEMENTS.get(dep, "?"),
            "n": len(lignes),
            "ko": round(ko),
            "bbox": [round(min(b[0] for b in xs), 4), round(min(b[1] for b in xs), 4),
                     round(max(b[2] for b in xs), 4), round(max(b[3] for b in xs), 4)],
        }
        print(f"{dep:<5}{DEPARTEMENTS.get(dep, '?'):<26}{len(lignes):>8}{ko:>8.0f}")

    with open(os.path.join(SORTIE, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n{len(index)} fichiers, {total_ko/1024:.1f} Mo au total")
    gros = sorted(index.items(), key=lambda kv: -kv[1]["ko"])[:5]
    print("Les plus lourds :")
    for dep, i in gros:
        print(f"  {dep} {i['nom']:<24} {i['ko']:>6} Ko  ({i['n']} lignes)")
    print(f"\nindex.json : {os.path.getsize(os.path.join(SORTIE, 'index.json'))/1024:.0f} Ko")


if __name__ == "__main__":
    main()
