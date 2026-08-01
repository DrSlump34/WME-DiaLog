#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DiaLog / Phase 0 -- Inventaire des arretes permanents.

Objectif : decider s'il faut construire quelque chose. Aucun livrable, aucune
interface. Cinq chiffres, puis arret.

Source retenue : l'API JSON /api/regulations/search, et non l'export DATEX II.
Justification en fin de rapport (section ECARTS AU BRIEF).

Dependances : bibliotheque standard uniquement.
Usage :
    python phase0_inventaire.py                 # utilise le cache si present
    python phase0_inventaire.py --refresh       # force le retelechargement
"""

import argparse
import collections
import datetime as dt
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

API = "https://dialog.beta.gouv.fr/api"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_permanents.json")
UA = {"Accept": "application/json", "User-Agent": "dialog-phase0-inventaire/1.0"}
PAGE_SIZE = 100

# Departements francais : code -> nom. Sert a la ventilation et a la liste des absents.
DEPARTEMENTS = {
    "01": "Ain", "02": "Aisne", "03": "Allier", "04": "Alpes-de-Haute-Provence",
    "05": "Hautes-Alpes", "06": "Alpes-Maritimes", "07": "Ardeche", "08": "Ardennes",
    "09": "Ariege", "10": "Aube", "11": "Aude", "12": "Aveyron",
    "13": "Bouches-du-Rhone", "14": "Calvados", "15": "Cantal", "16": "Charente",
    "17": "Charente-Maritime", "18": "Cher", "19": "Correze", "21": "Cote-d'Or",
    "22": "Cotes-d'Armor", "23": "Creuse", "24": "Dordogne", "25": "Doubs",
    "26": "Drome", "27": "Eure", "28": "Eure-et-Loir", "29": "Finistere",
    "2A": "Corse-du-Sud", "2B": "Haute-Corse", "30": "Gard", "31": "Haute-Garonne",
    "32": "Gers", "33": "Gironde", "34": "Herault", "35": "Ille-et-Vilaine",
    "36": "Indre", "37": "Indre-et-Loire", "38": "Isere", "39": "Jura",
    "40": "Landes", "41": "Loir-et-Cher", "42": "Loire", "43": "Haute-Loire",
    "44": "Loire-Atlantique", "45": "Loiret", "46": "Lot", "47": "Lot-et-Garonne",
    "48": "Lozere", "49": "Maine-et-Loire", "50": "Manche", "51": "Marne",
    "52": "Haute-Marne", "53": "Mayenne", "54": "Meurthe-et-Moselle", "55": "Meuse",
    "56": "Morbihan", "57": "Moselle", "58": "Nievre", "59": "Nord",
    "60": "Oise", "61": "Orne", "62": "Pas-de-Calais", "63": "Puy-de-Dome",
    "64": "Pyrenees-Atlantiques", "65": "Hautes-Pyrenees", "66": "Pyrenees-Orientales",
    "67": "Bas-Rhin", "68": "Haut-Rhin", "69": "Rhone", "70": "Haute-Saone",
    "71": "Saone-et-Loire", "72": "Sarthe", "73": "Savoie", "74": "Haute-Savoie",
    "75": "Paris", "76": "Seine-Maritime", "77": "Seine-et-Marne", "78": "Yvelines",
    "79": "Deux-Sevres", "80": "Somme", "81": "Tarn", "82": "Tarn-et-Garonne",
    "83": "Var", "84": "Vaucluse", "85": "Vendee", "86": "Vienne",
    "87": "Haute-Vienne", "88": "Vosges", "89": "Yonne", "90": "Territoire de Belfort",
    "91": "Essonne", "92": "Hauts-de-Seine", "93": "Seine-Saint-Denis",
    "94": "Val-de-Marne", "95": "Val-d'Oise",
    "971": "Guadeloupe", "972": "Martinique", "973": "Guyane",
    "974": "La Reunion", "976": "Mayotte",
}

# Index nom normalise -> code, pour resoudre numberedRoad.administrator.
def _norm(s):
    """Minuscules sans accents ni ponctuation, pour comparer des noms."""
    if not s:
        return ""
    table = str.maketrans("aaaaaeeeeiiiioooouuuuyc", "aaaaaeeeeiiiioooouuuuyc")
    s = s.lower().translate(table)
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
                 ("à", "a"), ("â", "a"), ("ä", "a"),
                 ("î", "i"), ("ï", "i"), ("ô", "o"), ("ö", "o"),
                 ("ù", "u"), ("û", "u"), ("ü", "u"), ("ç", "c")):
        s = s.replace(a, b)
    return "".join(c for c in s if c.isalnum())

NOM2CODE = {_norm(v): k for k, v in DEPARTEMENTS.items()}


# --------------------------------------------------------------------------
# Collecte
# --------------------------------------------------------------------------

def _get(url, tries=4):
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if n == tries - 1:
                raise
            time.sleep(2 * (n + 1))
            print(f"    (reessai {n + 1} apres {e})", file=sys.stderr)


def collecter(refresh=False):
    """Recupere tous les arretes permanents, tous statuts. Cache sur disque."""
    if os.path.exists(CACHE) and not refresh:
        with open(CACHE, encoding="utf-8") as f:
            d = json.load(f)
        print(f"Cache : {len(d['regulations'])} arretes lus depuis {os.path.basename(CACHE)}")
        print(f"        (collecte du {d['collecte']}) -- --refresh pour reinterroger l'API\n")
        return d

    base = f"{API}/regulations/search?category=permanentRegulation&status=all&pageSize={PAGE_SIZE}"
    first = _get(base + "&page=1")
    meta = first.get("metadata", {})
    total, last = meta.get("totalItems", 0), meta.get("lastPage", 1)
    print(f"Collecte : {total} arretes permanents annonces sur {last} pages...")

    regs = list(first.get("regulations", []))
    for p in range(2, last + 1):
        regs.extend(_get(f"{base}&page={p}").get("regulations", []))
        if p % 10 == 0 or p == last:
            print(f"    page {p}/{last} -- {len(regs)} arretes")

    d = {"collecte": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
         "totalItems": total, "regulations": regs}
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    print(f"    -> cache ecrit ({len(regs)} arretes)\n")
    return d


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def uuid7_date(u):
    """Un UUIDv7 encode l'horodatage Unix (ms) de creation sur ses 48 premiers bits.

    L'API n'expose aucun createdAt ; c'est notre seul acces a la date de SAISIE,
    a distinguer de startDate qui est la date d'effet juridique de l'arrete.
    """
    if not u:
        return None
    h = u.replace("-", "")
    if len(h) != 32 or h[12] != "7":
        return None
    try:
        ms = int(h[:12], 16)
    except ValueError:
        return None
    if not (1_600_000_000_000 < ms < 2_000_000_000_000):
        return None
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)


def dept_depuis_cp(label):
    """'Maisse (91720)' -> '91'. Gere Corse et DOM."""
    if not label or "(" not in label:
        return None
    cp = label.rsplit("(", 1)[-1].strip(") ").strip()
    if len(cp) != 5 or not cp.isdigit():
        return None
    if cp.startswith("97") or cp.startswith("98"):
        return cp[:3] if cp[:3] in DEPARTEMENTS else None
    if cp.startswith("20"):
        # Corse : le code postal ne distingue pas 2A de 2B de facon fiable.
        return "2A" if int(cp) < 20200 else "2B"
    return cp[:2] if cp[:2] in DEPARTEMENTS else None


# Sieges d'EPCI/metropoles : le nom de l'organisation ne contient aucun nom de
# departement. Table limitee aux organisations reellement presentes dans la base.
EPCI2DEPT = {
    "brest": "29", "bordeaux": "33", "montpellier": "34", "aixmarseille": "13",
    "paris": "75", "bethune": "62", "angouleme": "16", "reims": "51",
    "annecy": "74", "toulouse": "31", "lille": "59", "mel": "59",
    "paysbasque": "64", "genevois": "74", "avignon": "84",
    "mandelieu": "06", "dunkerque": "59", "fougeres": "35", "lyon": "69",
    "nantes": "44", "rennes": "35", "strasbourg": "67", "grenoble": "38",
    "nice": "06", "rouen": "76", "metz": "57", "nancy": "54", "dijon": "21",
    "tours": "37", "orleans": "45", "clermont": "63", "limoges": "87",
    "besancon": "25", "amiens": "80", "poitiers": "86", "caen": "14",
}

# Les noms les plus longs d'abord : sinon 'Savoie' matcherait 'Haute-Savoie'.
_NOMS_TRIES = sorted(NOM2CODE.items(), key=lambda kv: -len(kv[0]))


def dept_depuis_administrator(admin):
    """Resout un code departement depuis un nom libre.

    Sert pour numberedRoad.administrator ('Loiret', 'Manche') et pour le nom
    d'organisation ('Sarthe (departement)', 'Brest Metropole').
    """
    if not admin:
        return None
    n = _norm(admin)
    if n in NOM2CODE:
        return NOM2CODE[n]
    for nom, code in _NOMS_TRIES:
        if nom and len(nom) > 5 and nom in n:
            return code
    for cle, code in EPCI2DEPT.items():
        if cle in n:
            return code
    return None


def parse_iso(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def normaliser(regs):
    """Aplati chaque arrete en un enregistrement d'analyse."""
    out = []
    for r in regs:
        org = r.get("organization") or {}
        mesures = r.get("measures") or []

        types, depts, localisable_txt, avec_geom, nb_loc = set(), set(), False, False, 0
        roadtypes = set()
        saisies = []

        for m in mesures:
            if m.get("type"):
                types.add(m["type"])
            d = uuid7_date(m.get("uuid"))
            if d:
                saisies.append(d)
            for loc in (m.get("locations") or []):
                nb_loc += 1
                rt = loc.get("roadType")
                roadtypes.add(rt)
                if loc.get("geometry"):
                    avec_geom = True

                ns = loc.get("namedStreet") or {}
                nr = loc.get("numberedRoad") or {}
                # Critere du brief : roadName + commune, OU route numerotee avec PR.
                if ns.get("roadName") and ns.get("cityLabel"):
                    localisable_txt = True
                    c = dept_depuis_cp(ns.get("cityLabel"))
                    if c:
                        depts.add(c)
                if nr.get("roadNumber") and nr.get("fromPointNumber") is not None:
                    localisable_txt = True
                    c = dept_depuis_administrator(nr.get("administrator"))
                    if c:
                        depts.add(c)

        # Date de saisie de l'arrete = la plus ancienne de ses mesures.
        saisie = min(saisies) if saisies else None
        # Repli : l'UUID de l'organisation est v7 mais date la creation du COMPTE,
        # pas de l'arrete -- on ne l'utilise pas comme date de saisie.

        out.append({
            "identifier": r.get("identifier"),
            "org_uuid": org.get("uuid"),
            "org_nom": org.get("name"),
            "cle": f"{r.get('identifier')}#{org.get('uuid')}",
            "status": r.get("status"),
            "titre": r.get("title"),
            "startDate": parse_iso(r.get("startDate")),
            "endDate": parse_iso(r.get("endDate")),
            "saisie": saisie,
            "types": types,
            "depts": depts,
            "roadtypes": roadtypes,
            "nb_mesures": len(mesures),
            "nb_loc": nb_loc,
            "localisable_txt": localisable_txt,
            "avec_geom": avec_geom,
        })
    return out


def rattacher_orgs(recs):
    """Attribue un departement aux arretes non resolus via leur organisation.

    Beaucoup d'arretes sont en rawGeoJSON (pas de commune texte). Si les AUTRES
    arretes de la meme organisation designent un departement unique, on l'etend.
    """
    par_org = collections.defaultdict(collections.Counter)
    for r in recs:
        if r["org_uuid"]:
            par_org[r["org_uuid"]].update(r["depts"])

    noms_org = {r["org_uuid"]: r["org_nom"] for r in recs if r["org_uuid"]}

    org2dept = {}
    par_nom = 0
    for org in par_org:
        c = par_org[org]
        if c:
            org2dept[org] = c.most_common(1)[0][0]
        else:
            # Aucune localisation textuelle : on tente le nom de l'organisation.
            d = dept_depuis_administrator(noms_org.get(org))
            if d:
                org2dept[org] = d
                par_nom += 1

    herite = 0
    for r in recs:
        if not r["depts"] and r["org_uuid"] in org2dept:
            r["depts"] = {org2dept[r["org_uuid"]]}
            r["dept_herite"] = True
            herite += 1
        else:
            r["dept_herite"] = False
    return org2dept, herite, par_nom


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------

def titre(n, s):
    print()
    print("=" * 78)
    print(f"{n}. {s}")
    print("=" * 78)


def barre(n, total, largeur=40):
    if not total:
        return ""
    return "#" * max(1, round(n / total * largeur)) if n else ""


def rapport(recs, meta, org2dept, herite, par_nom=0):
    maintenant = dt.datetime.now(dt.timezone.utc)
    total = len(recs)
    noms_org = {r["org_uuid"]: r["org_nom"] for r in recs if r["org_uuid"]}

    print()
    print("#" * 78)
    print("#  DiaLog -- PHASE 0 : INVENTAIRE DES ARRETES PERMANENTS")
    print(f"#  Collecte : {meta.get('collecte', '?')}")
    print(f"#  Source   : {API}/regulations/search"
          "?category=permanentRegulation&status=all")
    print("#" * 78)

    # ---------------------------------------------------------------- Q1
    titre(1, "COUVERTURE -- organisations et departements")
    orgs = {r["org_uuid"]: r["org_nom"] for r in recs if r["org_uuid"]}
    print(f"Organisations distinctes ayant au moins un arrete permanent : {len(orgs)}")

    par_dept = collections.Counter()
    orgs_par_dept = collections.defaultdict(set)
    for r in recs:
        for d in r["depts"]:
            par_dept[d] += 1
            orgs_par_dept[d].add(r["org_uuid"])
    sans_dept = sum(1 for r in recs if not r["depts"])

    print(f"Departements couverts : {len(par_dept)} / {len(DEPARTEMENTS)}")
    print(f"Arretes sans departement resolu : {sans_dept} ({sans_dept / total:.1%})")
    print(f"  Rattachements indirects : {herite} arretes heritent du departement de")
    print(f"  leur organisation ({par_nom} organisations resolues par leur seul nom,")
    print("  faute de toute localisation textuelle dans leurs arretes).")

    print("\nVentilation par departement (arretes) :")
    print(f"  {'dep':<4} {'nom':<26} {'arretes':>8} {'orgs':>5}")
    for d, n in par_dept.most_common():
        print(f"  {d:<4} {DEPARTEMENTS.get(d, '?'):<26} {n:>8} "
              f"{len(orgs_par_dept[d]):>5}  {barre(n, par_dept.most_common(1)[0][1], 24)}")

    absents = sorted(set(DEPARTEMENTS) - set(par_dept))
    print(f"\nDepartements ABSENTS : {len(absents)} / {len(DEPARTEMENTS)}")
    for i in range(0, len(absents), 6):
        print("  " + "   ".join(
            f"{d} {DEPARTEMENTS[d][:16]}" for d in absents[i:i + 6]))

    # ---------------------------------------------------------------- Q2
    titre(2, "VOLUME -- arretes permanents et types de mesure")
    print(f"Arretes permanents (tous statuts)   : {total}")
    par_statut = collections.Counter(r["status"] for r in recs)
    for s, n in par_statut.most_common():
        print(f"    {s:<12} {n:>6}  ({n / total:.1%})")

    en_vigueur = [r for r in recs
                  if not r["endDate"] or r["endDate"] > maintenant]
    print(f"Arretes non expires a ce jour       : {len(en_vigueur)} "
          f"({len(en_vigueur) / total:.1%})")

    print("\nVentilation par type de mesure (un arrete peut en porter plusieurs) :")
    par_type = collections.Counter()
    for r in recs:
        par_type.update(r["types"])
    mx = par_type.most_common(1)[0][1] if par_type else 1
    for t, n in par_type.most_common():
        print(f"  {t:<20} {n:>6}  ({n / total:>5.1%})  {barre(n, mx, 30)}")

    print("\nInteret pour Waze (types directement exploitables en edition WME) :")
    utiles = {"speedLimitation": "vitesse / zone 30",
              "noEntry": "interdiction (dont sauf riverains, tonnage, gabarit)"}
    n_utiles = sum(1 for r in recs if r["types"] & set(utiles))
    for t, lib in utiles.items():
        print(f"  {t:<20} {par_type.get(t, 0):>6}   {lib}")
    print(f"  -> arretes portant au moins un type utile : {n_utiles} "
          f"({n_utiles / total:.1%})")
    hors = {"parkingProhibited", "alternateRoad", "noOvertaking"}
    n_hors = sum(1 for r in recs if r["types"] and not (r["types"] - hors))
    print(f"  -> arretes uniquement hors perimetre Waze : {n_hors} "
          f"({n_hors / total:.1%})")

    # ---------------------------------------------------------------- Q3
    titre(3, "FRAICHEUR -- la base est-elle encore alimentee ?")
    print("ATTENTION : l'API n'expose aucun champ createdAt. Deux dates distinctes")
    print("sont analysees, et elles ne disent PAS la meme chose :")
    print("  - startDate : date d'effet JURIDIQUE de l'arrete (souvent tres ancienne)")
    print("  - saisie    : date de creation dans DiaLog, reconstruite depuis")
    print("                l'horodatage des UUIDv7 de mesure. C'est la metrique")
    print("                decisive : elle mesure l'ALIMENTATION de la base.")

    for libelle, champ in (("startDate (effet juridique)", "startDate"),
                           ("saisie (alimentation reelle)", "saisie")):
        vals = sorted(r[champ] for r in recs if r[champ])
        print(f"\n--- {libelle} --- {len(vals)}/{total} arretes dates "
              f"({len(vals) / total:.1%})")
        if not vals:
            print("    aucune donnee")
            continue

        aberr = [v for v in vals if v.year < 1950]
        futur = [v for v in vals if v > maintenant]
        if aberr or futur:
            print(f"    QUALITE : {len(aberr)} date(s) aberrante(s) (annee < 1950, "
                  f"ex. {aberr[0]:%Y-%m-%d})" if aberr else "", end="")
            print(f" ; {len(futur)} date(s) dans le futur" if futur else "")

        med = vals[len(vals) // 2]
        print(f"    plus ancien : {vals[0]:%Y-%m-%d}")
        print(f"    MEDIANE     : {med:%Y-%m-%d}")
        print(f"    plus recent : {vals[-1]:%Y-%m-%d}")

        trim = collections.Counter(f"{v.year}-T{(v.month - 1) // 3 + 1}" for v in vals)
        recents = [k for k in sorted(trim) if k >= "2023"]
        mxt = max((trim[k] for k in recents), default=1)
        print(f"    Distribution par trimestre (depuis 2023 ; "
              f"{sum(trim[k] for k in trim if k < '2023')} anterieurs) :")
        for k in recents:
            print(f"      {k:<9} {trim[k]:>6}  {barre(trim[k], mxt, 34)}")

        six = maintenant - dt.timedelta(days=182)
        douze = maintenant - dt.timedelta(days=365)
        n6 = sum(1 for v in vals if v >= six)
        n12 = sum(1 for v in vals if v >= douze)
        print(f"    Sur les 6 derniers mois  : {n6:>6}  ({n6 / 182 * 30:.1f}/mois)")
        print(f"    Sur les 12 derniers mois : {n12:>6}  ({n12 / 365 * 30:.1f}/mois)")

    # ------------------------------------------- Q3 bis : regime d'alimentation
    titre("3bis", "REGIME D'ALIMENTATION -- flux continu ou versement de stock ?")
    print("Un import massif unique gonfle le volume recent sans qu'aucun arrete")
    print("nouveau ne soit reellement suivi. On separe donc les deux regimes.")
    print("Convention : une organisation qui saisit plus de 50 arretes dans la")
    print("meme journee est en VERSEMENT DE STOCK ce jour-la, pas en flux courant.")

    SEUIL = 50
    par_org_jour = collections.defaultdict(list)
    for r in recs:
        if r["saisie"] and r["org_uuid"]:
            par_org_jour[(r["org_uuid"], r["saisie"].date())].append(r)

    jours_stock = {k for k, v in par_org_jour.items() if len(v) > SEUIL}
    n_stock = sum(len(par_org_jour[k]) for k in jours_stock)
    print(f"\nJournees de versement massif detectees : {len(jours_stock)}")
    print(f"Arretes verses lors de ces journees     : {n_stock} "
          f"({n_stock / total:.1%} du stock total)")
    if jours_stock:
        print(f"\n  {'organisation':<40} {'jour':<12} {'arretes':>8}")
        for k in sorted(jours_stock, key=lambda x: -len(par_org_jour[x]))[:12]:
            o, j = k
            print(f"  {(noms_org.get(o) or '?')[:40]:<40} {str(j):<12} "
                  f"{len(par_org_jour[k]):>8}")

    flux = [r for r in recs
            if r["saisie"] and (r["org_uuid"], r["saisie"].date()) not in jours_stock]
    print(f"\nArretes hors versement de stock (flux courant) : {len(flux)} "
          f"({len(flux) / total:.1%})")

    six = maintenant - dt.timedelta(days=182)
    douze = maintenant - dt.timedelta(days=365)
    f6 = [r for r in flux if r["saisie"] >= six]
    f12 = [r for r in flux if r["saisie"] >= douze]
    print(f"  flux courant sur 6 mois  : {len(f6):>5}  ({len(f6) / 182 * 30:.1f}/mois)")
    print(f"  flux courant sur 12 mois : {len(f12):>5}  ({len(f12) / 365 * 30:.1f}/mois)")

    # Regularite : combien d'organisations saisissent mois apres mois ?
    mois_par_org = collections.defaultdict(set)
    for r in recs:
        if r["saisie"] and r["saisie"] >= douze and r["org_uuid"]:
            mois_par_org[r["org_uuid"]].add(f"{r['saisie']:%Y-%m}")
    reguliers = {o: m for o, m in mois_par_org.items() if len(m) >= 6}
    print(f"\nOrganisations ayant saisi sur >= 6 mois distincts des 12 derniers : "
          f"{len(reguliers)}")
    for o, m in sorted(reguliers.items(), key=lambda x: -len(x[1]))[:10]:
        n = sum(1 for r in recs if r["org_uuid"] == o
                and r["saisie"] and r["saisie"] >= douze)
        print(f"    {(noms_org.get(o) or '?')[:42]:<42} {len(m):>2} mois, {n:>4} arretes")
    if not reguliers:
        print("    AUCUNE. Il n'existe pas d'alimentation reguliere.")

    # ---------------------------------------------------------------- Q4
    titre(4, "CONCENTRATION -- le volume est-il porte par quelques acteurs ?")
    par_org = collections.Counter()
    noms = {}
    for r in recs:
        if r["org_uuid"]:
            par_org[r["org_uuid"]] += 1
            noms[r["org_uuid"]] = r["org_nom"]
    top = par_org.most_common()
    print(f"{'rang':>4}  {'organisation':<44} {'arretes':>8} {'part':>7} {'cumul':>7}")
    cum = 0
    for i, (o, n) in enumerate(top[:15], 1):
        cum += n
        print(f"{i:>4}  {(noms.get(o) or '?')[:44]:<44} {n:>8} "
              f"{n / total:>6.1%} {cum / total:>6.1%}")
    for k in (5, 10, 20):
        if len(top) >= k:
            p = sum(n for _, n in top[:k]) / total
            print(f"\n  Part des {k:>2} organisations les plus actives : {p:.1%}")
    mediane_org = statistics.median([n for _, n in top]) if top else 0
    print(f"  Mediane d'arretes par organisation : {mediane_org:.0f}")
    solo = sum(1 for _, n in top if n == 1)
    print(f"  Organisations n'ayant publie qu'UN seul arrete : {solo} "
          f"({solo / len(top):.1%} des organisations)")

    # ---------------------------------------------------------------- Q5
    titre(5, "LOCALISABILITE -- les arretes sont-ils exploitables sur la carte ?")
    n_txt = sum(1 for r in recs if r["localisable_txt"])
    n_geo = sum(1 for r in recs if r["avec_geom"])
    n_les_2 = sum(1 for r in recs if r["localisable_txt"] and r["avec_geom"])
    n_rien = sum(1 for r in recs if not r["localisable_txt"] and not r["avec_geom"])
    print("Critere du brief (roadName + commune, OU route numerotee avec PR) :")
    print(f"    {n_txt:>6} / {total}  ({n_txt / total:.1%})")
    print("Critere operationnel pour WME (geometrie GeoJSON fournie par l'API) :")
    print(f"    {n_geo:>6} / {total}  ({n_geo / total:.1%})")
    print(f"    dont les deux a la fois : {n_les_2} ({n_les_2 / total:.1%})")
    print(f"    ni l'un ni l'autre      : {n_rien} ({n_rien / total:.1%})  <- dechet")

    print("\nVentilation par roadType (au niveau localisation) :")
    rt = collections.Counter()
    for r in recs:
        rt.update(r["roadtypes"])
    mxr = rt.most_common(1)[0][1] if rt else 1
    aide = {"lane": "voie nommee + commune",
            "departmentalRoad": "route departementale + PR",
            "nationalRoad": "route nationale + PR",
            "rawGeoJSON": "geometrie brute, sans libelle de voie",
            "wholeCity": "commune entiere -- non exploitable au segment",
            None: "aucune localisation"}
    for t, n in rt.most_common():
        print(f"  {str(t):<18} {n:>6}  {barre(n, mxr, 26)}  {aide.get(t, '')}")

    # ------------------------------------------------- Vigilance : identifiants
    titre("*", "STABILITE DES IDENTIFIANTS (prealable a tout diff incremental)")
    ids = collections.Counter(r["identifier"] for r in recs)
    cles = collections.Counter(r["cle"] for r in recs)
    col_id = {k: v for k, v in ids.items() if v > 1}
    col_cle = {k: v for k, v in cles.items() if v > 1}
    print(f"Arretes                                  : {total}")
    print(f"Valeurs distinctes de 'identifier'       : {len(ids)}")
    print(f"  -> identifiants en collision           : {len(col_id)}")
    if col_id:
        ex = sorted(col_id.items(), key=lambda x: -x[1])[:3]
        print(f"     exemples : {ex}")
        print("     'identifier' est une reference INTERNE a chaque organisation.")
        print("     Il n'est PAS unique au niveau national : inutilisable seul.")
    print(f"Cles composites 'identifier#organisation' : {len(cles)}")
    print(f"  -> collisions restantes                 : {len(col_cle)}")
    if not col_cle:
        print("     => CLE STABLE DISPONIBLE. Un diff incremental est realisable")
        print("        sur 'identifier#organization.uuid' (c'est aussi la valeur")
        print("        exposee par le champ regulationId de l'export DATEX II).")

    # ---------------------------------------------------------- Porte de decision
    titre("*", "PORTE DE DECISION")
    six = maintenant - dt.timedelta(days=182)
    frais = [r for r in recs if r["saisie"] and r["saisie"] >= six]
    frais_utiles = [r for r in frais
                    if r["types"] & {"speedLimitation", "noEntry"}
                    and (r["localisable_txt"] or r["avec_geom"])]
    print("Critere indicatif du brief : > ~20 arretes permanents LOCALISABLES par")
    print("mois sur les departements ou la communaute est active.")
    print()
    print("  -- Lecture BRUTE (trompeuse : elle inclut les versements de stock) --")
    print(f"  Arretes saisis sur les 6 derniers mois          : {len(frais)}")
    print(f"    dont type utile a Waze ET localisables       : {len(frais_utiles)}")
    print(f"    soit un rythme apparent de                   : "
          f"{len(frais_utiles) / 182 * 30:.1f} arretes/mois (national)")
    print()
    print("  -- Lecture CORRIGEE (hors journees de versement massif) --")
    fu = [r for r in frais_utiles
          if (r["org_uuid"], r["saisie"].date()) not in jours_stock]
    print(f"  Arretes utiles, localisables, en flux courant  : {len(fu)}")
    print(f"    soit un rythme REEL de                       : "
          f"{len(fu) / 182 * 30:.1f} arretes/mois (national)")
    print()
    d_frais = collections.Counter()
    for r in fu:
        for d in r["depts"]:
            d_frais[d] += 1
    print("  Repartition du flux REEL (hors versement) par departement :")
    if d_frais:
        for d, n in d_frais.most_common(15):
            print(f"    {d} {DEPARTEMENTS.get(d, '?'):<24} {n:>4}  "
                  f"({n / 182 * 30:.1f}/mois)")
    else:
        print("    aucun")
    print(f"  Departements concernes par le flux recent : {len(d_frais)}")

    # ---------------------------------------------------------- Ecarts au brief
    titre("*", "ECARTS AU BRIEF (schema reel constate)")
    print("1. createdAt n'existe pas dans l'API. La fraicheur a ete reconstruite")
    print("   depuis l'horodatage des UUIDv7 (48 bits de poids fort = ms Unix).")
    print("   Mesurer la fraicheur sur startDate seul aurait donne un faux resultat :")
    print("   des arretes saisis en 2023 portent un startDate de 2004.")
    print()
    print("2. MeasureTypeEnum compte 5 valeurs, pas 4 : le brief omettait")
    print("   'noOvertaking'.")
    print()
    print("3. /api/stats ne contient AUCUN departmentCode : c'est une couche de")
    print("   158 polygones de couverture, dont la seule propriete est clusterName")
    print("   (une liste de noms d'organisations concatenee). La ventilation")
    print("   departementale a donc ete reconstruite depuis le code postal de")
    print("   namedStreet.cityLabel et depuis numberedRoad.administrator.")
    print("   /api/organization/identifiers repond 401 : non public.")
    print()
    print("4. Il n'y a pas de cityCode INSEE dans les reponses : le champ rendu est")
    print("   cityLabel, au format 'Commune (CodePostal)'. Le code postal n'est pas")
    print("   un code departemental fiable a 100% (Corse notamment).")
    print()
    print("5. Source retenue : l'API JSON /api/regulations/search et non l'export")
    print("   DATEX II. Le XML pese 93 Mo, encode la meme information sous forme de")
    print("   ConditionSet imbriques, et n'apporte aucun champ supplementaire utile")
    print("   a un inventaire. Conformement au point de vigilance du brief, c'est le")
    print("   schema REELLEMENT recu qui a guide l'analyse.")
    print()


def main():
    ap = argparse.ArgumentParser(description="DiaLog Phase 0 -- inventaire")
    ap.add_argument("--refresh", action="store_true",
                    help="force le retelechargement au lieu du cache")
    a = ap.parse_args()

    d = collecter(refresh=a.refresh)
    recs = normaliser(d["regulations"])
    org2dept, herite, par_nom = rattacher_orgs(recs)
    rapport(recs, d, org2dept, herite, par_nom)


if __name__ == "__main__":
    main()
