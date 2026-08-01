// ==UserScript==
// @name         WME DiaLog
// @namespace    https://github.com/DrSlump34
// @version      0.04.00
// @description  Affiche dans WME les arrêtés de circulation permanents de DiaLog (vitesse, interdictions) avec leur géométrie réelle. Chargement par département avec progression autour du bouton, compteur sur la vue élargie.
// @author       DrSlump34
// @match        https://www.waze.com/*editor*
// @exclude      https://www.waze.com/*user/*editor*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      raw.githubusercontent.com
// @connect      github.io
// @run-at       document-idle
// @license      MIT
// ==/UserScript==

/* global getWmeSdk, indexedDB */

(function () {
    'use strict';

    const ID = 'wme-dialog';
    const NOM = 'WME DiaLog';
    const VERSION = '0.04.00';

    // ------------------------------------------------------------------
    // SOURCE DES DONNEES
    // ------------------------------------------------------------------
    // ⚠️ L'API DiaLog ne sait pas livrer un departement : son seul filtre
    // geographique (inseeCode) est INOPERANT -- mesure du 01/08/2026, il
    // renvoie 0 quelle que soit sa valeur. Et un chargement integral prend
    // plus de 10 minutes (pageSize plafonne a 100, ~17 s/page, parallelisme
    // au-dela de 4 coupe par le serveur).
    // Les fichiers sont donc pre-generes par export_departements.py, un par
    // departement. 54 sur 55 pesent moins de 722 Ko ; seul l'Aveyron atteint
    // 14,5 Mo, d'ou l'indicateur de progression.
    //
    // Servi par GitHub Pages depuis la branche main, dossier /docs.
    // Le bouton « Charger un fichier » reste disponible en repli hors ligne.
    const BASE = 'https://drslump34.github.io/WME-DiaLog';

    const CACHE_JOURS = 7;
    const BDD = 'wme-dialog', MAGASIN = 'departements';

    // Marge autour de la vue : le compteur et le chargement portent sur la vue
    // elargie de 10 km, comme demande.
    const MARGE_KM = 10;

    const ZOOM_MINI = 14;
    const DELAI = 250;
    const PLAFOND_AFFICHE = 400;

    const COULEURS = { V: '#0b6bcb', I: '#d73027', A: '#f5a623' };

    // Bbox REELLE des donnees de chaque departement (pas le contour
    // administratif), produite par export_departements.py. Permet de savoir
    // quel fichier charger sans aucune requete ni service de geocodage.
    const INDEX = {"02":{"n":"Aisne","c":4,"k":5,"b":[3.184,49.7556,3.2864,49.8124]},"03":{"n":"Allier","c":3,"k":3,"b":[2.4458,46.2403,2.9317,46.4255]},"06":{"n":"Alpes-Maritimes","c":13,"k":10,"b":[6.8509,43.5233,7.2811,43.7162]},"09":{"n":"Ariege","c":30,"k":29,"b":[1.1823,42.7197,1.8439,42.9062]},"10":{"n":"Aube","c":176,"k":126,"b":[3.4714,48.4833,3.521,48.5129]},"12":{"n":"Aveyron","c":5134,"k":14561,"b":[1.8445,43.693,3.4059,44.9352]},"13":{"n":"Bouches-du-Rhone","c":8,"k":5,"b":[4.9828,43.5652,5.3582,43.7368]},"16":{"n":"Charente","c":1,"k":1,"b":[0.268,45.6796,0.2701,45.6805]},"17":{"n":"Charente-Maritime","c":1,"k":1,"b":[-0.5919,45.7713,-0.5903,45.7729]},"19":{"n":"Correze","c":69,"k":120,"b":[1.3175,44.9895,2.4589,45.6981]},"22":{"n":"Cotes-d'Armor","c":17,"k":20,"b":[-3.3416,48.2381,-2.0622,48.776]},"24":{"n":"Dordogne","c":11,"k":23,"b":[1.1562,45.0607,1.1771,45.0816]},"25":{"n":"Doubs","c":3,"k":6,"b":[6.3153,46.9107,6.3248,46.9145]},"26":{"n":"Drome","c":20,"k":22,"b":[4.7886,44.6198,5.0955,45.0897]},"27":{"n":"Eure","c":1,"k":3,"b":[1.7871,49.2834,1.7977,49.287]},"29":{"n":"Finistere","c":878,"k":446,"b":[-4.6348,48.1574,-4.2467,48.4603]},"30":{"n":"Gard","c":8,"k":5,"b":[4.3221,43.936,4.3497,43.9537]},"31":{"n":"Haute-Garonne","c":4,"k":5,"b":[1.3068,43.3212,1.4348,43.6743]},"32":{"n":"Gers","c":2,"k":1,"b":[0.0711,43.8525,0.4946,43.927]},"33":{"n":"Gironde","c":127,"k":97,"b":[-0.775,44.7283,-0.3362,44.9909]},"34":{"n":"Herault","c":277,"k":178,"b":[3.8138,43.5789,3.9374,43.6502]},"35":{"n":"Ille-et-Vilaine","c":16,"k":314,"b":[-1.6954,48.1531,-1.1856,48.3638]},"38":{"n":"Isere","c":42,"k":25,"b":[4.8736,44.9013,5.7898,45.5902]},"40":{"n":"Landes","c":7,"k":4,"b":[-1.3908,43.6614,-1.3723,43.6679]},"42":{"n":"Loire","c":6,"k":4,"b":[4.382,45.6343,4.3984,45.6404]},"44":{"n":"Loire-Atlantique","c":93,"k":100,"b":[-1.8659,47.4218,-1.6929,47.4912]},"47":{"n":"Lot-et-Garonne","c":21,"k":9,"b":[0.6508,44.3912,0.6836,44.4205]},"49":{"n":"Maine-et-Loire","c":11,"k":14,"b":[-0.3776,47.5548,-0.286,47.6397]},"50":{"n":"Manche","c":82,"k":92,"b":[-1.2229,48.5738,-1.0856,48.8385]},"51":{"n":"Marne","c":3,"k":1,"b":[4.0223,49.2511,4.038,49.2558]},"56":{"n":"Morbihan","c":5,"k":4,"b":[-3.0016,47.6896,-2.2795,47.7316]},"59":{"n":"Nord","c":104,"k":96,"b":[2.3718,50.5349,3.2489,51.0355]},"60":{"n":"Oise","c":8,"k":4,"b":[2.7369,49.3041,2.7541,49.3074]},"61":{"n":"Orne","c":8,"k":13,"b":[-0.4486,48.8176,-0.4269,48.8263]},"62":{"n":"Pas-de-Calais","c":6,"k":5,"b":[1.6665,50.4794,2.7169,50.8862]},"64":{"n":"Pyrenees-Atlantiques","c":74,"k":394,"b":[-1.7864,43.1605,-1.2328,43.4261]},"66":{"n":"Pyrenees-Orientales","c":2,"k":2,"b":[2.9172,42.5418,2.9199,42.5437]},"67":{"n":"Bas-Rhin","c":49,"k":31,"b":[7.2978,48.4991,8.132,48.9562]},"68":{"n":"Haut-Rhin","c":1,"k":1,"b":[7.1282,48.0536,7.1286,48.055]},"69":{"n":"Rhone","c":61,"k":26,"b":[4.7739,45.5714,4.9713,45.8996]},"72":{"n":"Sarthe","c":734,"k":722,"b":[-0.4235,47.6124,0.8483,48.4617]},"73":{"n":"Savoie","c":9,"k":8,"b":[5.869,45.3127,6.6508,45.6026]},"74":{"n":"Haute-Savoie","c":11,"k":10,"b":[6.1367,45.9395,6.6773,46.2046]},"75":{"n":"Paris","c":186,"k":69,"b":[2.2368,48.8212,2.4321,48.9013]},"78":{"n":"Yvelines","c":21,"k":32,"b":[1.7611,48.8121,2.0522,49.0336]},"79":{"n":"Deux-Sevres","c":1,"k":3,"b":[-0.6818,46.1915,-0.6653,46.1963]},"81":{"n":"Tarn","c":1,"k":2,"b":[1.6587,43.9971,1.6642,44.0102]},"85":{"n":"Vendee","c":8,"k":3,"b":[-2.029,46.7695,-2.0274,46.7714]},"88":{"n":"Vosges","c":14,"k":19,"b":[6.6039,48.082,6.6134,48.0954]},"91":{"n":"Essonne","c":3,"k":7,"b":[2.1403,48.4008,2.5003,48.519]},"92":{"n":"Hauts-de-Seine","c":1,"k":0,"b":[2.2411,48.8143,2.2424,48.8146]},"93":{"n":"Seine-Saint-Denis","c":15,"k":8,"b":[2.3951,48.8592,2.4408,48.9248]},"94":{"n":"Val-de-Marne","c":3,"k":1,"b":[2.3629,48.743,2.39,48.7686]},"95":{"n":"Val-d'Oise","c":7,"k":3,"b":[2.1256,48.989,2.1932,49.005]}};

    let sdk = null;
    let charges = {};       // code dept -> tableau de mesures
    let enCours = {};       // code dept -> true pendant le telechargement
    let vue = [];
    let minuteur = null;
    let auto = true;
    let filtres = { type: '', alerte: false, horaires: false, riverains: false };

    const $id = i => document.getElementById(i);
    const ech = s => String(s == null ? '' : s).replace(/[&<>"]/g,
        c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

    // ------------------------------------------------------------------
    // Geometrie de la vue
    // ------------------------------------------------------------------
    function vueElargie() {
        let ext = null;
        try { ext = sdk.Map.getMapExtent(); } catch (e) { return null; }
        if (!ext || ext.length !== 4) return null;
        const latMoy = (ext[1] + ext[3]) / 2;
        const dLat = MARGE_KM / 111;
        const dLon = MARGE_KM / (111 * Math.max(0.2, Math.cos(latMoy * Math.PI / 180)));
        return [ext[0] - dLon, ext[1] - dLat, ext[2] + dLon, ext[3] + dLat];
    }

    const seCroisent = (a, b) =>
        !(a[2] < b[0] || a[0] > b[2] || a[3] < b[1] || a[1] > b[3]);

    // Departements dont les DONNEES peuvent concerner la vue elargie.
    function departementsPertinents(boite) {
        const out = [];
        for (const code in INDEX) {
            if (seCroisent(INDEX[code].b, boite)) out.push(code);
        }
        return out;
    }

    // ------------------------------------------------------------------
    // Cache
    // ------------------------------------------------------------------
    function ouvrirBdd() {
        return new Promise((resolve, reject) => {
            const d = indexedDB.open(BDD, 1);
            d.onupgradeneeded = () => {
                if (!d.result.objectStoreNames.contains(MAGASIN)) {
                    d.result.createObjectStore(MAGASIN);
                }
            };
            d.onsuccess = () => resolve(d.result);
            d.onerror = () => reject(d.error);
        });
    }

    async function lireCache(code) {
        try {
            const db = await ouvrirBdd();
            return await new Promise(resolve => {
                const r = db.transaction(MAGASIN, 'readonly').objectStore(MAGASIN).get(code);
                r.onsuccess = () => resolve(r.result || null);
                r.onerror = () => resolve(null);
            });
        } catch (e) { return null; }
    }

    async function ecrireCache(code, donnees) {
        try {
            const db = await ouvrirBdd();
            db.transaction(MAGASIN, 'readwrite').objectStore(MAGASIN)
                .put({ date: Date.now(), d: donnees }, code);
        } catch (e) { console.warn(NOM, 'cache non écrit', e); }
    }

    // ------------------------------------------------------------------
    // Telechargement d'un departement, avec progression reelle
    // ------------------------------------------------------------------
    function telecharger(code, surProgres) {
        return new Promise((resolve, reject) => {
            if (!BASE) return reject(new Error('source non configurée'));
            const url = BASE.replace(/\/+$/, '') + '/dept_' + code + '.json';
            const attendu = (INDEX[code] ? INDEX[code].k : 0) * 1024;
            GM_xmlhttpRequest({
                method: 'GET', url: url, timeout: 180000,
                onprogress: e => {
                    // Content-Length manque souvent en gzip : on retombe sur la
                    // taille connue par l'index, qui suffit pour l'indicateur.
                    const total = (e && e.total) ? e.total : attendu;
                    if (total > 0 && e && e.loaded) {
                        surProgres(Math.min(0.99, e.loaded / total));
                    }
                },
                onload: r => {
                    if (r.status < 200 || r.status >= 300) return reject(new Error('HTTP ' + r.status));
                    try { resolve(JSON.parse(r.responseText)); }
                    catch (e) { reject(new Error('fichier illisible')); }
                },
                onerror: () => reject(new Error('erreur réseau')),
                ontimeout: () => reject(new Error('délai dépassé'))
            });
        });
    }

    async function assurerDepartement(code) {
        if (charges[code] || enCours[code]) return;
        enCours[code] = true;
        try {
            const c = await lireCache(code);
            if (c && c.d && (Date.now() - c.date) < CACHE_JOURS * 864e5) {
                charges[code] = c.d;
                return;
            }
            const nom = INDEX[code] ? INDEX[code].n : code;
            const ko = INDEX[code] ? INDEX[code].k : 0;
            majAnneau(0, 'Chargement du département ' + code + ' — ' + nom
                + (ko ? ' (' + (ko > 1024 ? (ko / 1024).toFixed(1) + ' Mo' : ko + ' Ko') + ')' : ''));
            const d = await telecharger(code, p => majAnneau(p,
                'Chargement du département ' + code + ' — ' + nom
                + ' … ' + Math.round(p * 100) + ' %'));
            charges[code] = d;
            await ecrireCache(code, d);
            majAnneau(1, nom + ' chargé — ' + d.length + ' mesures');
        } catch (e) {
            console.error(NOM, 'département ' + code, e);
            majAnneau(0, 'Échec ' + code + ' : ' + e.message);
        } finally {
            enCours[code] = false;
            setTimeout(() => majAnneau(null), 1200);
        }
    }

    // ------------------------------------------------------------------
    // Rafraichissement
    // ------------------------------------------------------------------
    async function rafraichir() {
        let zoom = 22;
        try { zoom = sdk.Map.getZoomLevel(); } catch (e) { /* ignore */ }
        const boite = vueElargie();
        if (!boite || zoom < ZOOM_MINI) {
            vue = [];
            dessiner();
            rendreListe();
            etat(zoom < ZOOM_MINI ? 'Zoomez pour afficher (niveau ' + ZOOM_MINI + ' minimum)' : '');
            return;
        }

        const codes = departementsPertinents(boite);
        if (!codes.length) {
            vue = [];
            dessiner();
            rendreListe();
            etat('Aucune donnée DiaLog dans ce secteur.');
            return;
        }

        for (const code of codes) {
            if (!charges[code] && !enCours[code]) assurerDepartement(code).then(filtrerEtRendre);
        }
        filtrerEtRendre();
    }

    function passeFiltres(a) {
        if (filtres.type && a.t !== filtres.type) return false;
        if (filtres.alerte && !a.al) return false;
        if (filtres.horaires && a.p) return false;
        if (filtres.riverains && !a.rv) return false;
        return true;
    }

    function filtrerEtRendre() {
        const boite = vueElargie();
        if (!boite) return;
        const out = [];
        for (const code in charges) {
            const li = charges[code];
            for (let i = 0; i < li.length; i++) {
                const a = li[i];
                if (seCroisent(a.b, boite) && passeFiltres(a)) out.push(a);
            }
        }
        vue = out;
        dessiner();
        rendreListe();
        const noms = departementsPertinents(boite)
            .filter(c => charges[c]).map(c => INDEX[c].n);
        if (noms.length) etat(noms.join(', ') + ' · rayon ' + MARGE_KM + ' km');
    }

    function programmer() {
        if (!auto) return;
        if (minuteur) clearTimeout(minuteur);
        minuteur = setTimeout(rafraichir, DELAI);
    }

    // ------------------------------------------------------------------
    // Carte
    // ------------------------------------------------------------------
    function dessiner() {
        try { sdk.Map.removeAllFeaturesFromLayer({ layerName: ID }); }
        catch (e) { /* couche vide */ }
        const li = vue.slice(0, PLAFOND_AFFICHE);
        if (!li.length) return;
        try {
            sdk.Map.addFeaturesToLayer({
                layerName: ID,
                features: li.map((a, i) => ({
                    id: 'dlg-' + i, type: 'Feature', geometry: a.g,
                    properties: {
                        couleur: a.al ? COULEURS.A : COULEURS[a.t],
                        etiquette: a.v
                    }
                }))
            });
        } catch (e) { console.error(NOM, 'ajout des géométries', e); }
    }

    function cadrer(a) {
        try { sdk.Map.centerMapOnGeometry({ geometry: a.g }); return; }
        catch (e) { /* repli */ }
        try {
            sdk.Map.setMapCenter({ lonLat: { lon: a.x, lat: a.y } });
            sdk.Map.setZoomLevel({ zoomLevel: 17 });
        } catch (e2) { console.error(NOM, 'cadrage', e2); }
    }

    // ------------------------------------------------------------------
    // Bouton, anneau de progression, overlay
    // ------------------------------------------------------------------
    const RAYON = 17.5;
    const CIRCONFERENCE = 2 * Math.PI * RAYON;

    const conteneurNatif = () =>
        document.querySelector('.overlay-buttons-container.top')
        || document.querySelector('.overlay-buttons-container');

    function injecterFab() {
        if ($id('dlg-fab-btn')) return;
        const hote = conteneurNatif();
        if (!hote) return;

        const wrap = document.createElement('div');
        wrap.id = 'dlg-fab-wrap';

        // Anneau de progression, dessine AUTOUR du bouton.
        const anneau = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        anneau.id = 'dlg-anneau';
        anneau.setAttribute('viewBox', '0 0 40 40');
        anneau.innerHTML = '<circle cx="20" cy="20" r="' + RAYON + '" fill="none" '
            + 'stroke="rgba(0,0,0,.10)" stroke-width="3"/>'
            + '<circle id="dlg-arc" cx="20" cy="20" r="' + RAYON + '" fill="none" '
            + 'stroke="#0b6bcb" stroke-width="3" stroke-linecap="round" '
            + 'stroke-dasharray="' + CIRCONFERENCE + '" '
            + 'stroke-dashoffset="' + CIRCONFERENCE + '" '
            + 'transform="rotate(-90 20 20)"/>';
        wrap.appendChild(anneau);

        const btn = document.createElement('button');
        btn.id = 'dlg-fab-btn';
        btn.type = 'button';
        btn.title = NOM + ' ' + VERSION;
        btn.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none">'
            + '<circle cx="12" cy="12" r="9.2" fill="#fff" stroke="#d73027" stroke-width="3"/>'
            + '<text x="12" y="16.2" text-anchor="middle" font-size="9.5" '
            + 'font-family="Arial,sans-serif" font-weight="700" fill="#222">30</text></svg>';

        const badge = document.createElement('div');
        badge.id = 'dlg-fab-badge';
        badge.textContent = '0';
        btn.appendChild(badge);

        wrap.appendChild(btn);
        hote.appendChild(wrap);

        btn.addEventListener('click', ev => {
            ev.stopPropagation();
            const ov = $id('dlg-overlay');
            if (ov) ov.classList.toggle('open');
        });
    }

    // part : 0 a 1 pour afficher l'anneau, null pour l'effacer.
    function majAnneau(part, infobulle) {
        const arc = $id('dlg-arc');
        const wrap = $id('dlg-fab-wrap');
        const btn = $id('dlg-fab-btn');
        if (arc && wrap) {
            if (part == null) {
                wrap.classList.remove('charge');
                arc.setAttribute('stroke-dashoffset', CIRCONFERENCE);
            } else {
                wrap.classList.add('charge');
                arc.setAttribute('stroke-dashoffset', CIRCONFERENCE * (1 - part));
            }
        }
        if (infobulle !== undefined && btn) {
            btn.title = infobulle || (NOM + ' ' + VERSION);
        }
        if (infobulle) etat(infobulle);
    }

    function etat(t) {
        const e = $id('dlg-etat');
        if (e && t !== undefined) e.textContent = t;
    }

    function majBadge() {
        const badge = $id('dlg-fab-badge');
        const btn = $id('dlg-fab-btn');
        const n = vue.length;
        if (badge) badge.textContent = n > 999 ? '999+' : String(n);
        if (btn) btn.classList.toggle('a-traiter', n > 0);
        const c = $id('dlg-compteur');
        if (c) {
            const tot = Object.keys(charges).reduce((s, k) => s + charges[k].length, 0);
            c.textContent = n + ' dans la vue (±' + MARGE_KM + ' km) · ' + tot + ' chargées'
                + (n > PLAFOND_AFFICHE ? ' · ' + PLAFOND_AFFICHE + ' tracées' : '');
        }
    }

    function rendreListe() {
        majBadge();
        const box = $id('dlg-liste');
        if (!box) return;
        const li = vue.slice(0, PLAFOND_AFFICHE);
        if (!li.length) {
            box.innerHTML = '<p class="dlg-vide">Rien à traiter dans cette vue.</p>';
            return;
        }
        box.innerHTML = li.map((a, i) =>
            '<div class="dlg-item" data-i="' + i + '">'
            + '<span class="dlg-pastille" style="background:'
            + (a.al ? COULEURS.A : COULEURS[a.t]) + '"></span>'
            + '<div class="dlg-corps">'
            + '<div class="dlg-val">' + ech(a.v) + '</div>'
            + (a.r ? '<div class="dlg-voie">' + ech(a.r) + '</div>' : '')
            + '<div class="dlg-meta">' + ech(a.a)
            + (a.c ? ' · ' + ech(a.c) : '') + '</div>'
            + (a.al ? '<div class="dlg-alerte">' + ech(a.al) + '</div>' : '')
            + '<div class="dlg-titre" title="' + ech(a.ti) + '">' + ech(a.ti) + '</div>'
            + '</div></div>').join('');
        Array.prototype.forEach.call(box.querySelectorAll('.dlg-item'), el => {
            el.addEventListener('click', () => cadrer(li[parseInt(el.dataset.i, 10)]));
        });
    }

    function construireOverlay() {
        if ($id('dlg-overlay')) return;
        const ov = document.createElement('div');
        ov.id = 'dlg-overlay';
        ov.innerHTML = ''
            + '<div id="dlg-tete"><b>DiaLog</b><span id="dlg-ver">v' + VERSION + '</span>'
            + '<button id="dlg-fermer" type="button" title="Fermer">×</button></div>'
            + '<div id="dlg-corps">'
            + '<div id="dlg-barre">'
            + '<select id="dlg-type"><option value="">Toutes</option>'
            + '<option value="V">Vitesse</option>'
            + '<option value="I">Interdiction</option></select>'
            + '<label><input type="checkbox" id="dlg-f-alerte"> à vérifier</label>'
            + '<label><input type="checkbox" id="dlg-f-horaires"> horaires</label>'
            + '<label><input type="checkbox" id="dlg-f-riverains"> riverains</label>'
            + '</div>'
            + '<div id="dlg-barre2">'
            + '<label><input type="checkbox" id="dlg-auto" checked> suivre la vue</label>'
            + '<button id="dlg-fichier-btn" type="button">Charger un fichier</button>'
            + '<input type="file" id="dlg-fichier" accept=".json,.geojson" hidden>'
            + '</div>'
            + '<div id="dlg-etat"></div><div id="dlg-compteur"></div><div id="dlg-liste"></div>'
            + '</div>';
        document.body.appendChild(ov);

        $id('dlg-fermer').addEventListener('click', () => ov.classList.remove('open'));
        $id('dlg-auto').addEventListener('change', e => {
            auto = e.target.checked;
            GM_setValue('auto', auto ? '1' : '0');
            if (auto) rafraichir();
        });

        // Repli sans hebergement : charger un dept_XX.json depuis le disque.
        $id('dlg-fichier-btn').addEventListener('click', () => $id('dlg-fichier').click());
        $id('dlg-fichier').addEventListener('change', ev => {
            const f = ev.target.files && ev.target.files[0];
            if (!f) return;
            const code = (f.name.match(/dept_([0-9AB]+)/i) || [])[1] || 'local';
            const lecteur = new FileReader();
            lecteur.onload = () => {
                try {
                    const d = JSON.parse(lecteur.result);
                    charges[code] = d;
                    ecrireCache(code, d);
                    etat(f.name + ' — ' + d.length + ' mesures');
                    filtrerEtRendre();
                } catch (e) { etat('Fichier illisible : ' + e.message); }
            };
            lecteur.readAsText(f);
        });

        const maj = () => {
            filtres.type = $id('dlg-type').value;
            filtres.alerte = $id('dlg-f-alerte').checked;
            filtres.horaires = $id('dlg-f-horaires').checked;
            filtres.riverains = $id('dlg-f-riverains').checked;
            GM_setValue('filtres', JSON.stringify(filtres));
            filtrerEtRendre();
        };
        ['dlg-type', 'dlg-f-alerte', 'dlg-f-horaires', 'dlg-f-riverains']
            .forEach(i => $id(i).addEventListener('change', maj));

        try {
            const sauv = JSON.parse(GM_getValue('filtres', '{}'));
            if (sauv && typeof sauv === 'object') {
                filtres = Object.assign(filtres, sauv);
                $id('dlg-type').value = filtres.type || '';
                $id('dlg-f-alerte').checked = !!filtres.alerte;
                $id('dlg-f-horaires').checked = !!filtres.horaires;
                $id('dlg-f-riverains').checked = !!filtres.riverains;
            }
        } catch (e) { /* valeurs par defaut */ }
        auto = GM_getValue('auto', '1') !== '0';
        $id('dlg-auto').checked = auto;
    }

    function styles() {
        const css = [
            '#dlg-fab-wrap { position:relative; width:40px; height:40px; border-radius:50%;',
            '  background:#fff; box-shadow:0 2px 6px rgba(0,0,0,.3); display:flex;',
            '  align-items:center; justify-content:center; cursor:pointer; user-select:none; }',
            '#dlg-fab-wrap:hover { box-shadow:0 3px 10px rgba(0,0,0,.4); }',
            '#dlg-anneau { position:absolute; inset:0; width:40px; height:40px;',
            '  pointer-events:none; opacity:0; transition:opacity .2s; }',
            '#dlg-fab-wrap.charge #dlg-anneau { opacity:1; }',
            '#dlg-arc { transition:stroke-dashoffset .25s linear; }',
            '#dlg-fab-btn { position:relative; background:none; border:none; padding:0;',
            '  margin:0; cursor:inherit; display:flex; align-items:center;',
            '  justify-content:center; width:100%; height:100%; border-radius:50%; }',
            '#dlg-fab-badge { position:absolute; top:-4px; right:-4px; background:#9e9e9e;',
            '  color:#fff; border-radius:50px; font-size:10px; padding:0 4px; min-width:16px;',
            '  height:16px; display:flex; align-items:center; justify-content:center;',
            '  border:2px solid #fff; pointer-events:none; box-sizing:border-box; }',
            '#dlg-fab-btn.a-traiter #dlg-fab-badge { background:#1a9850; }',
            '#dlg-overlay { position:fixed; z-index:9990; top:64px; right:16px;',
            '  width:min(380px, calc(100vw - 24px)); max-height:calc(100vh - 96px);',
            '  background:#fff; color:#1a1a1a; border-radius:12px;',
            '  box-shadow:0 6px 24px rgba(0,0,0,.28); display:none; flex-direction:column;',
            '  font-size:12px; overflow:hidden; }',
            '#dlg-overlay.open { display:flex; }',
            '#dlg-tete { display:flex; align-items:center; gap:8px; padding:9px 12px;',
            '  background:#f4f6f8; border-bottom:1px solid #e3e3e3; }',
            '#dlg-tete b { font-size:14px; }',
            '#dlg-ver { color:#999; font-size:10px; flex:1; }',
            '#dlg-fermer { background:none; border:none; font-size:20px; line-height:1;',
            '  cursor:pointer; color:#666; padding:0 2px; }',
            '#dlg-corps { padding:10px 12px; overflow-y:auto; }',
            '#dlg-barre, #dlg-barre2 { display:flex; flex-wrap:wrap; gap:8px;',
            '  align-items:center; margin-bottom:7px; }',
            '#dlg-barre label, #dlg-barre2 label { display:inline-flex; align-items:center; gap:3px; }',
            '#dlg-fichier-btn { padding:3px 9px; cursor:pointer; }',
            '#dlg-etat { color:#666; min-height:15px; margin-bottom:4px; }',
            '#dlg-compteur { color:#999; margin-bottom:7px; }',
            '.dlg-item { display:flex; gap:7px; border:1px solid #e3e3e3; border-radius:5px;',
            '  padding:5px 7px; margin-bottom:5px; cursor:pointer; }',
            '.dlg-item:hover { background:#f2f6fa; }',
            '.dlg-pastille { width:9px; height:9px; border-radius:50%; flex:0 0 auto; margin-top:3px; }',
            '.dlg-corps { min-width:0; flex:1; }',
            '.dlg-val { font-weight:600; }',
            '.dlg-voie { color:#333; }',
            '.dlg-meta { color:#777; font-size:11px; }',
            '.dlg-alerte { color:#b45309; font-size:11px; }',
            '.dlg-titre { color:#aaa; font-size:10px; white-space:nowrap; overflow:hidden;',
            '  text-overflow:ellipsis; }',
            '.dlg-vide { color:#888; }'
        ].join('\n');
        const el = document.createElement('style');
        el.textContent = css;
        document.head.appendChild(el);
    }

    // ------------------------------------------------------------------
    // Demarrage
    // ------------------------------------------------------------------
    async function demarrer() {
        sdk = getWmeSdk({ scriptId: ID, scriptName: NOM });
        await sdk.Events.once({ eventName: 'wme-ready' });

        styles();
        construireOverlay();
        injecterFab();
        setInterval(injecterFab, 4000);

        try {
            sdk.Map.addLayer({
                layerName: ID,
                styleRules: [{
                    style: {
                        strokeColor: '${couleur}', strokeWidth: 8, strokeOpacity: 0.55,
                        label: '${etiquette}', fontColor: '#fff',
                        labelOutlineColor: '#000', labelOutlineWidth: 2, fontSize: 11
                    }
                }]
            });
            sdk.Map.setLayerVisibility({ layerName: ID, visibility: true });
        } catch (e) { console.error(NOM, 'création de la couche', e); }

        sdk.Events.on({ eventName: 'wme-map-move-end', eventHandler: programmer });

        if (!BASE) {
            etat('Source non configurée — utilisez « Charger un fichier ».');
        }
        rafraichir();
        console.log(NOM, VERSION, 'prêt');
    }

    const lancer = () => demarrer().catch(e => console.error(NOM, e));
    if (typeof unsafeWindow !== 'undefined' && unsafeWindow.SDK_INITIALIZED) {
        unsafeWindow.SDK_INITIALIZED.then(lancer);
    } else if (window.SDK_INITIALIZED) {
        window.SDK_INITIALIZED.then(lancer);
    } else {
        document.addEventListener('wme-initialized', lancer, { once: true });
    }
})();
