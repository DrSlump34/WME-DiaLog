/**
 * Test du filtre "vehicules de tourisme, taxis, motos" du userscript.
 *
 * Le test EXTRAIT le code reel de WME-DiaLog.user.js et l'evalue : il ne
 * reimplemente pas la regle. Une copie de la logique ne testerait rien
 * (lecon de tools/imp-detect.js sur WCT).
 *
 * Usage : node test_filtre_tourisme.js
 */

const fs = require('fs');
const path = require('path');

const RACINE = __dirname;
const SCRIPT = path.join(RACINE, 'WME-DiaLog.user.js');
const CACHE = path.join(RACINE, 'cache_permanents.json');

const src = fs.readFileSync(SCRIPT, 'utf8');

// --- Extraction du code reel -------------------------------------------------
function extraire(motif, nom) {
    const m = src.match(motif);
    if (!m) {
        console.error('ECHEC : impossible d\'extraire ' + nom + ' du userscript.');
        process.exit(1);
    }
    return m[0];
}

const srcRegex = extraire(
    /const RE_HORS_TOURISME = new RegExp\([\s\S]*?'i'\);/, 'RE_HORS_TOURISME');
const srcFonction = extraire(
    /function concerneTourisme\(carac, restrictions\) \{[\s\S]*?\n    \}/, 'concerneTourisme');

const concerneTourisme = new Function(
    srcRegex + '\n' + srcFonction + '\nreturn concerneTourisme;')();

// --- Application sur les donnees reelles -------------------------------------
if (!fs.existsSync(CACHE)) {
    console.error('Cache absent : lancer python phase0_inventaire.py --refresh');
    process.exit(1);
}
const regs = JSON.parse(fs.readFileSync(CACHE, 'utf8')).regulations;

let total = 0, garde = 0, exclu = 0;
const gardeParType = {};
const fuites = [];

for (const r of regs) {
    for (const m of (r.measures || [])) {
        if (m.type !== 'speedLimitation' && m.type !== 'noEntry') continue;
        total++;
        const vs = m.vehicleSet || {};
        const carac = {};
        (vs.maxCharacteristics || []).forEach(c => {
            if (c && c.name != null && c.value != null) carac[c.name] = c.value;
        });
        const restrictions = (vs.restrictedTypes || [])
            .map(t => (t && t.name) ? t.name : t).filter(Boolean).join(' | ');

        if (concerneTourisme(carac, restrictions)) {
            garde++;
            gardeParType[m.type] = (gardeParType[m.type] || 0) + 1;
            // Aucune mesure conservee ne doit porter de contrainte de gabarit.
            if (carac.weight != null || carac.height != null
                || carac.width != null || carac.length != null) {
                fuites.push({ type: m.type, carac: carac, restrictions: restrictions });
            }
        } else {
            exclu++;
        }
    }
}

const V = '\x1b[32m', R = '\x1b[31m', Z = '\x1b[0m';
let echecs = 0;
const verifier = (libelle, obtenu, attendu) => {
    if (obtenu === attendu) {
        console.log(`${V}OK${Z}     ${libelle.padEnd(34)} ${obtenu}`);
    } else {
        echecs++;
        console.log(`${R}ECHEC${Z}  ${libelle.padEnd(34)} obtenu ${obtenu}, attendu ${attendu}`);
    }
};

console.log(`Mesures vitesse + interdiction : ${total}\n`);
verifier('conservees', garde, 7507);
verifier('exclues', exclu, 3013);
verifier('dont vitesse', gardeParType.speedLimitation, 6837);
verifier('dont interdiction', gardeParType.noEntry, 670);

if (fuites.length) {
    echecs++;
    console.log(`${R}ECHEC${Z}  ${fuites.length} mesure(s) conservee(s) portent un gabarit :`);
    fuites.slice(0, 3).forEach(f => console.log('        ', JSON.stringify(f)));
} else {
    console.log(`${V}OK${Z}     aucune contrainte de gabarit conservee`);
}

// Controles de non-regression sur des cas nommes.
const cas = [
    [{}, '', true, 'interdiction generale (vise les voitures)'],
    [{ weight: 7.5 }, '', false, 'limite de 7,5 t'],
    [{ height: 3.4 }, '', false, 'gabarit en hauteur'],
    [{ length: 10 }, '', false, 'gabarit en longueur'],
    [{ width: 2.3 }, '', false, 'gabarit en largeur'],
    [{}, 'hazardousMaterials', false, 'matieres dangereuses'],
    [{}, 'Autocars et autobus', false, 'autocars et autobus'],
    [{}, 'Camping-cars', false, 'camping-cars'],
    [{}, 'engins agricoles', false, 'engins agricoles'],
    [{}, 'Piétons', true, 'pietons (pas une categorie ecartee)']
];
console.log('\nCas nommes :');
cas.forEach(([carac, restr, attendu, libelle]) => {
    const obtenu = concerneTourisme(carac, restr);
    if (obtenu === attendu) {
        console.log(`${V}OK${Z}     ${libelle}`);
    } else {
        echecs++;
        console.log(`${R}ECHEC${Z}  ${libelle} : obtenu ${obtenu}, attendu ${attendu}`);
    }
});

console.log();
if (echecs) {
    console.log(`${R}${echecs} echec(s).${Z}`);
    process.exit(1);
}
console.log(`${V}Tous les controles passent.${Z}`);
