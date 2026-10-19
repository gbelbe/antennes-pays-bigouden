#!/usr/bin/env python3
"""Zonage du PLU, prescriptions et bandes de règlement autour du pylône -> antenne-reglement.ttl

Lit sources/gpu/*.geojson (écrits par tools/plu_gpu_fetch.py) et les entités du dossier, puis écrit
antenne-reglement.ttl : chaque zone, prescription ou bande est une ant:ZoneReglementaire avec sa géométrie
(geo:asWKT), sa distance au pylône et à la parcelle, et les règles du PLU (ant:RegleDeZone) qui s'y appliquent.
Les bandes de règlement (recul, distance, rayon) sont des géométries dérivées, calculées ici et signalées comme telles.

Usage : python3 -I tools/plu_gpu.py "$PWD"       (nécessite rdflib et shapely)
"""
import json, math, re, sys, warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from pathlib import Path

import rdflib
from shapely.geometry import Point, Polygon, shape, mapping
from shapely.ops import unary_union
from shapely import affinity

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
GPU = ROOT / "sources" / "gpu"
DATE = json.loads((GPU / "FETCH.json").read_text())["date"]
CLIP_M = 550          # les géométries sont coupées à ce rayon autour du pylône
KEEP_M = 500          # seules les entités à moins de 500 m du pylône sont retenues
SIMPLIFY_M = 0.4

# ── projection locale (mètres) autour du pylône ────────────────────────────
CX, CY = -4.274491, 47.874985
KY = 110540.0
KX = 111320.0 * math.cos(math.radians(CY))
to_m = lambda g: _tx(g, lambda x, y: ((x - CX) * KX, (y - CY) * KY))
to_ll = lambda g: _tx(g, lambda x, y: (x / KX + CX, y / KY + CY))


def _tx(g, f):
    from shapely.ops import transform
    return transform(lambda x, y, z=None: f(x, y), g)


# ── entités déjà dans le dossier ────────────────────────────────────────────
GEOW = rdflib.URIRef("http://www.opengis.net/ont/geosparql#asWKT")
DOS = "https://kersalous.bzh/dossier/"
dg = rdflib.Graph().parse(ROOT / "antenne-dossier.ttl")
from shapely import wkt as _wkt
existing = {}
for s, w in dg.subject_objects(GEOW):
    sid = str(s).replace(DOS, "dos:")
    existing[sid] = to_m(_wkt.loads(str(w)))
PARCELLE = existing["dos:parcelle-yx26"]
# Position du pylône selon le dossier d'information de l'opérateur (Lambert II étendu X 106 077, Y 2 340 312, converti
# en WGS84, cf. dos:m-position-operateur). Elle est celle de dos:projet-pylone (harmonisée ; l'ancien point, milieu de la parcelle, était à 63 m).
PYLONE_LL = (-4.273649, 47.875099)
PYLONE = Point((PYLONE_LL[0] - CX) * KX, (PYLONE_LL[1] - CY) * KY)
EXISTING_ZONES = {k: v for k, v in existing.items()
                  if k in ("dos:haie-nord", "dos:haie-sud", "dos:zone-humide-voisine", "dos:ebc-voisin", "dos:abords-trevilit")}

COMMUNES = {"29174": ("Plonéour-Lanvern", "dos:commune-ploneour"), "29252": ("Saint-Jean-Trolimon", "dos:commune-stjean")}
WINDOW = PYLONE.buffer(CLIP_M, 32)


def esc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def wkt_out(g):
    """Géométrie métrique -> WKT lon lat (6 décimales), simplifiée."""
    g = g.simplify(SIMPLIFY_M, preserve_topology=True)
    return _wkt.dumps(to_ll(g), rounding_precision=6, trim=True)


def dist(g, ref):
    return int(round(g.distance(ref)))


def matches(old, new):
    if old.geom_type in ("LineString", "MultiLineString"):
        return new.hausdorff_distance(old) < 25 and (new.buffer(3).contains(old) or old.buffer(3).contains(new))
    inter = old.intersection(new).area
    return inter / max(old.union(new).area, 1) > 0.8


def fix(g):
    return g.buffer(0) if g.geom_type in ("Polygon", "MultiPolygon") else g


def load(ep):
    d = json.loads((GPU / f"{ep}.geojson").read_text())
    return d.get("features", [])


# ── 1. entités issues du GPU ────────────────────────────────────────────────
ZONE_TYPE = {"A": "skt:zone-A", "N": "skt:zone-N", "U": "skt:zone-U", "AU": "skt:zone-AU"}
items = []   # dict(id, label, type, commune, geom, props, note)
for f in load("zone-urba"):
    p = f["properties"]
    g = fix(shape(f["geometry"]))
    lib = p["libelle"]
    kind = p["typezone"]
    items.append(dict(src="zone-urba", partition=p["partition"], g=to_m(g), lib=lib, long=p["libelong"], kind=kind,
                      type=ZONE_TYPE.get(kind, "skt:zone-U"), idurba=p["idurba"], datvalid=p.get("datvalid")))
for ep in ("prescription-surf", "prescription-lin", "prescription-pct"):
    for f in load(ep):
        p = f["properties"]
        lab = p["libelle"]
        if "humide" in lab:
            t, nm = "skt:zone-humide", "Zone humide protégée (L.151-23)"
        elif "boisé" in lab:
            t, nm = "skt:ebc", "Espace boisé classé"
        elif "Haie" in lab:
            t, nm = "skt:haie-talus", "Haie ou talus à préserver (L.151-23)"
        elif "cours d'eau" in lab:
            t, nm = "skt:cours-eau", "Cours d'eau protégé (R.151-43 4°)"
        elif "Puits" in lab:
            t, nm = "skt:element-patrimoine-local", lab
        else:
            t, nm = "skt:zone-U", lab
        items.append(dict(src=ep, partition=p["partition"], g=to_m(fix(shape(f["geometry"]))), lib=nm, long=lab,
                          kind=nm, type=t, idurba=p["idurba"], datvalid=p.get("datvalid")))

# zones qui contiennent le pylône ou la parcelle
for it in items:
    it["d_pylone"] = dist(it["g"], PYLONE)
    it["d_parcelle"] = dist(it["g"], PARCELLE)
items = [i for i in items if i["d_pylone"] <= KEEP_M]
items.sort(key=lambda i: (i["d_pylone"], i["partition"], i["lib"]))

# rattachement aux entités existantes
used = set()
for it in items:
    it["existing"] = None
    if it["src"] == "zone-urba" and it["partition"] == "DU_29174" and it["lib"] == "A" and it["g"].intersects(PARCELLE):
        it["existing"] = "dos:zone-plu-a"
        continue
    for k, old in EXISTING_ZONES.items():
        if k in used:
            continue
        want = {"skt:haie-talus": ("dos:haie-nord", "dos:haie-sud"), "skt:zone-humide": ("dos:zone-humide-voisine",), "skt:ebc": ("dos:ebc-voisin",)}.get(it["type"], ())
        if k in want and matches(old, it["g"]):
            it["existing"] = k
            used.add(k)
            break

SLUG = {}
count = {}
for it in items:
    base = re.sub(r"[^a-z0-9]+", "-", (f"{it['partition'][3:]}-zone-{it['lib']}" if it["src"] == "zone-urba"
                                       else f"{it['partition'][3:]}-{it['type'].split(':')[1]}").lower()).strip("-")
    count[base] = count.get(base, 0) + 1
    it["slug"] = f"gpu-{base}-{count[base]}"
    it["id"] = it["existing"] or f"dos:{it['slug']}"

# ── 2. bandes de règlement dérivées ─────────────────────────────────────────
bands = []
# 3 m en limite de parcelle (règle A II-1-c) : couronne intérieure
ring3 = PARCELLE.difference(PARCELLE.buffer(-3))
bands.append(dict(id="dos:bande-recul-limites-3m", label="Bande de recul de 3 m en limite de parcelle (A II-1-c)",
                  g=ring3, radius=3, rule="dos:plu-a-ii-1-c-limites",
                  note="Couronne de 3 m le long des limites de la parcelle YX 26 : recul minimal des constructions par rapport aux limites séparatives en zone A. Le règlement exempte les « ouvrages techniques » (supports de télécommunications) nécessaires aux réseaux existants : la question est de savoir si ce relais en fait partie. Le pylône est à 4,4 m du bord de parcelle."))
# 5 m à partir de l'alignement des voies communales (règle A II-1-b §3)
routes = []
for f in load("routes_bdtopo"):
    p = f["properties"]
    if p.get("nature") in ("Sentier",):
        continue
    g = to_m(shape(f["geometry"]))
    if g.distance(PARCELLE) < 80:
        half = (float(p.get("largeur_de_chaussee") or 3.5)) / 2
        routes.append(g.buffer(half + 5))
if routes:
    bands.append(dict(id="dos:bande-recul-voie-5m", label="Bande de recul de 5 m depuis l'alignement des voies (A II-1-b)",
                      g=unary_union(routes), radius=5, rule="dos:plu-a-ii-1-b-voies",
                      note="Approximation : axe des voies de la BD TOPO élargi de la demi-chaussée puis de 5 m (l'alignement exact, limite du domaine public, n'est pas dans les données). Recul de 5 m des constructions nouvelles par rapport à l'alignement des voies communales ; mêmes exemptions pour les ouvrages techniques. Les routes départementales ont des reculs plus grands (15 à 35 m), mais aucune n'est à proximité."))
# 10 m de part et d'autre des cours d'eau protégés (règle A I-1 §2)
for it in items:
    if it["type"] == "skt:cours-eau" and it["g"].distance(PYLONE) < KEEP_M:
        bands.append(dict(id=f"dos:bande-{it['slug'][4:]}-10m", label="Bande inconstructible de 10 m le long du cours d'eau (A I-1)",
                          g=it["g"].buffer(10), radius=10, rule="dos:plu-a-i-1-cours-eau",
                          note="Aucune nouvelle construction à moins de 10 m des berges des cours d'eau, en zone A."))
# rayon égal à la hauteur sommitale du pylône (indicatif, ce n'est pas une règle du PLU)
bands.append(dict(id="dos:rayon-hauteur-pylone", label="Rayon indicatif : hauteur sommitale du pylône (32,65 m)",
                  g=PYLONE.buffer(32.65, 64), radius=32.65, rule=None,
                  note="Cercle de rayon égal à la hauteur du pylône avec ses antennes (32,65 m, dossier d'information, p. 13). **Ce n'est pas une règle du PLU** : il montre ce qui se trouve à une distance inférieure à la hauteur de la structure, argument usuel sur la sécurité (R. 111-2) mais rarement retenu seul."))
for b in bands:
    b["d_pylone"] = dist(b["g"], PYLONE)
    b["d_parcelle"] = dist(b["g"], PARCELLE)

def nearest(t, part=None):
    ds = sorted(i["d_pylone"] for i in items if i["type"] == t and (part is None or i["partition"] == part))
    return ds[0] if ds else None


ND = {"ce": nearest("skt:cours-eau"), "zh": nearest("skt:zone-humide"), "ebc29": nearest("skt:ebc", "DU_29252"), "ebc74": nearest("skt:ebc", "DU_29174")}

# ── 3. règles du PLU ────────────────────────────────────────────────────────
PLU = "règlement écrit du PLU de Plonéour-Lanvern (modification n°1, approuvée le 2026-03-05)"
zones_of = lambda t, part="DU_29174": [i["id"] for i in items if i["type"] == t and i["partition"] == part]
zoneA_all = zones_of("skt:zone-A")
rules = [
    dict(id="dos:plu-regle-a-i-2-3", exists=True, zones=zoneA_all, app="a-verifier",
         art="A I-2 §3, règlement écrit p. 96"),
    dict(id="dos:plu-art-9-ouvrages", label="PLU Plonéour-Lanvern — dispositions générales, art. 9 (ouvrages spécifiques)", zones=zoneA_all,
         app="oui", art="Dispositions générales, art. 9, p. 14-15 ; répété en A II-1-b et A II-1-c, p. 98",
         note="« Il n'est pas fixé de règles spécifiques en matière d'emprise au sol, de hauteur, d'aspect extérieur et de stationnement » pour les ouvrages techniques (transformateurs, supports de transport d'énergie ou de **télécommunications**…) nécessaires au fonctionnement des réseaux existants d'utilité publique ; leur édification est appréciée selon leur apport à la vie sociale et leur insertion dans l'environnement. **Règle clé pour ce dossier** : elle écarte les limites de hauteur et de recul de la zone A, mais seulement pour un ouvrage « nécessaire au fonctionnement des réseaux **existants** »."),
    dict(id="dos:plu-a-ii-1-a-hauteur", label="PLU Plonéour-Lanvern — zone A, hauteur (A II-1-a)", zones=zoneA_all, app="a-verifier", value=9, unit="m",
         art="A II-1-a, p. 97",
         note="Hauteur mesurée du terrain naturel au sommet, ouvrages techniques, cheminées et superstructures exclus : 8 m pour l'habitation, **9 m pour les activités**, 4 m pour les annexes. Le pylône mesure 30 m (32,65 m avec les antennes). La règle ne le vise pas expressément ; l'exemption de l'art. 9 des dispositions générales suppose un ouvrage technique « nécessaire aux réseaux existants »."),
    dict(id="dos:plu-a-ii-1-b-voies", label="PLU Plonéour-Lanvern — zone A, recul par rapport aux voies (A II-1-b)", zones=zoneA_all, app="a-verifier", value=5, unit="m",
         art="A II-1-b, p. 97-98",
         note="5 m minimum par rapport à l'alignement des voies publiques ou privées (autres que départementales). Départementales : 15 à 35 m selon la route ; RD 785 : 75 m pour les habitations. Exemption des ouvrages techniques comme ci-dessus."),
    dict(id="dos:plu-a-ii-1-c-limites", label="PLU Plonéour-Lanvern — zone A, recul par rapport aux limites séparatives (A II-1-c)", zones=zoneA_all, app="a-verifier", value=3, unit="m",
         art="A II-1-c, p. 98",
         note="Recul minimal de 3 m par rapport aux limites séparatives ; annexes en limite ou à 3 m. Exemption des ouvrages techniques comme ci-dessus. Distance du pylône au bord de la parcelle : 4,4 m."),
    dict(id="dos:plu-a-ii-2-cloture", label="PLU Plonéour-Lanvern — zone A, clôtures (A II-2 §3)", zones=zoneA_all, app="oui", value=2, unit="m",
         art="A II-2 §3, p. 100",
         note="En limite séparative, 2 m maximum au-dessus du terrain naturel ; en bordure de voie 1,40 m (mur bahut de 0,80 m surmonté d'une claire-voie). Matériaux de fortune, parpaings non enduits et plaques de béton interdits. Au-delà de 2 m seulement « en cas de nécessité impérative liée à l'activité », avec doublement par une haie si la clôture est visible de la voie publique. La clôture du projet (grillage de 2 m, RAL 6005) est **exactement à la limite**, et longe une route."),
    dict(id="dos:plu-a-ii-2-insertion", label="PLU Plonéour-Lanvern — zone A, qualité architecturale et paysagère (A II-2)", zones=zoneA_all, app="oui",
         art="A II-2, p. 99-100",
         note="Le permis peut être refusé ou assorti de prescriptions si la situation, l'architecture, les dimensions ou l'aspect de l'ouvrage portent atteinte au caractère des lieux, aux sites, aux paysages ou aux perspectives monumentales. Le texte ajoute qu'un argumentaire d'insertion paysagère accompagne la demande (le texte paraît lié au secteur At ; lecture à confirmer)."),
    dict(id="dos:plu-a-i-1-zones-humides", label="PLU Plonéour-Lanvern — zone A, zones humides (A I-1 §1, A I-2 §4)", zones=zones_of("skt:zone-humide"), app="a-verifier",
         art="A I-1 §1, p. 93 ; A I-2 §4, p. 96",
         note="Dans une zone humide L.151-23 : interdits tous travaux relevant de l'urbanisme affectant son fonctionnement (construction, remblaiement, exhaussement, affouillement, dépôts, création de plan d'eau, imperméabilisation). Admis : aménagements légers et ouvrages strictement nécessaires aux **réseaux d'utilité publique** si leur localisation répond à une nécessité technique impérative d'intérêt général. La zone humide la plus proche est à "+str(ND['zh'])+" m du pylône : vérifier le tracé de la piste d'accès, de la tranchée de raccordement et l'exutoire des eaux."),
    dict(id="dos:plu-a-i-1-cours-eau", label="PLU Plonéour-Lanvern — zone A, cours d'eau protégés (A I-1 §2)", zones=zones_of("skt:cours-eau"), app="non", value=10, unit="m",
         art="A I-1 §2, p. 94",
         note="Pas de nouvelle construction à moins de 10 m des berges, exhaussements et affouillements interdits. Le cours d'eau protégé le plus proche est à "+str(ND['ce'])+" m du pylône : sans effet sur ce projet."),
    dict(id="dos:plu-art-6", exists=True, zones=zones_of("skt:haie-talus"), app="oui", art="Dispositions générales, art. 6, p. 13"),
    dict(id="dos:plu-art-7-ebc", label="PLU Plonéour-Lanvern — dispositions générales, art. 7 (espaces boisés classés)", zones=zones_of("skt:ebc", "DU_29174") + zones_of("skt:ebc", "DU_29252"), app="non",
         art="Dispositions générales, art. 7, p. 13",
         note="Le classement interdit tout changement d'affectation du sol de nature à compromettre la conservation ou la création des boisements et entraîne le rejet de plein droit de toute demande de défrichement. Les EBC les plus proches sont à "+str(ND['ebc29'])+" m (Saint-Jean-Trolimon) et "+str(ND['ebc74'])+" m (Plonéour-Lanvern) : sans effet direct sur l'emprise de la parcelle."),
    dict(id="dos:plu-a-iii-1-desserte", label="PLU Plonéour-Lanvern — zone A, accès et voirie (A III-1)", zones=zoneA_all, app="oui", value=4, unit="m",
         art="A III-1, p. 101-102",
         note="Accès sécurisé (permis subordonné à des aménagements si l'accès présente un risque), nombre d'accès limité, voie d'au moins 4 m de chaussée carrossable en tout temps. Le terrain doit avoir accès à une voie publique ou privée, éventuellement par servitude (art. 682 du code civil)."),
    dict(id="dos:plu-a-iii-2-reseaux", label="PLU Plonéour-Lanvern — zone A, réseaux (A III-2-d)", zones=zoneA_all, app="oui",
         art="A III-2-d, p. 103",
         note="Les nouveaux raccordements électriques et de communications sont réalisés en souterrain, aux frais du constructeur. Une tranchée de raccordement traverse les terrains voisins : lire avec le moyen « raccordement électrique » (L.111-11)."),
    dict(id="dos:plu-a-captage", label="PLU Plonéour-Lanvern — zone A, périmètre de protection de captage", zones=zoneA_all, app="a-verifier",
         art="Introduction de la zone A, p. 93",
         note="Le règlement signale que la zone A est « concernée par un périmètre de protection d'un captage d'eau potable » et renvoie à l'annexe du PLU. Le périmètre n'a pas été localisé : à vérifier dans les annexes (servitude AS1)."),
]
band_rule_zone = {b["rule"]: b["id"] for b in bands if b.get("rule")}

# ── 4. écriture du Turtle ───────────────────────────────────────────────────
o = []
w = o.append
w("""@prefix ant:  <https://kersalous.bzh/ontology/antenne#> .
@prefix dos:  <https://kersalous.bzh/dossier/> .
@prefix skt:  <https://kersalous.bzh/taxonomie/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix geo:  <http://www.opengis.net/ont/geosparql#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix src:  <https://kersalous.bzh/provenance/> .
@prefix note: <https://example.org/ontology/kai-internal-knowledge#> .

# Fichier généré par tools/plu_gpu.py (ne pas modifier à la main).
# Sources : Géoportail de l'urbanisme (API Carto IGN), BD TOPO (WFS Géoplateforme), règlement écrit du PLU.
# Les géométries sont coupées à %d m autour du pylône ; les distances sont des distances géodésiques approchées
# (projection locale), au mètre près.

<https://kersalous.bzh/reglement> a owl:Ontology ;
    rdfs:label "Antenne — zonage et règlement du PLU autour du pylône"@fr .
""" % CLIP_M)

w("""# ═══ Position du pylône selon le dossier d'information ═══

dos:position-pylone-operateur a owl:NamedIndividual, ant:ObjetGeographique ;
    rdfs:label "Position du pylône selon le dossier d'information de l'opérateur"@fr ;
    ant:dansLieu dos:lieudit-kerfilin-sud ;
    ant:distanceParcelle 4.4 ;
    geo:asWKT "POINT(%s %s)"^^geo:wktLiteral ;
    prov:wasDerivedFrom src:dim-bouygues ;
    note:note "Coordonnées Lambert II étendu du dossier d'information (X 106 077, Y 2 340 312) converties en WGS84 (voir dos:m-position-operateur ; quelques mètres d'incertitude). **Toutes les distances au pylône de ce fichier partent de ce point.** dos:projet-pylone porte désormais le même point (il était auparavant au milieu de la parcelle, à 63 m)." .

""" % PYLONE_LL)
w("# ═══ Zones et prescriptions (Géoportail de l'urbanisme) ═══\n")
for it in items:
    com_name, com_id = COMMUNES.get(it["partition"][3:], (it["partition"], "dos:commune-ploneour"))
    reg = [r["id"] for r in rules if it["id"] in r["zones"]]
    if it["existing"]:
        po = [f"ant:distanceProjet {it['d_pylone']}", f"ant:origineGpu \"{esc(it['idurba'])}\""]
        if it["id"] == "dos:zone-plu-a":
            po.append(f"geo:asWKT \"{wkt_out(it['g'].intersection(WINDOW))}\"^^geo:wktLiteral")
        po.append("prov:wasDerivedFrom src:apicarto-gpu-2026-10")
        w(f"{it['id']} " + " ;\n    ".join(po) + " .\n")
        continue
    if it["src"] == "zone-urba":
        label = f"Zone {it['lib']} — PLU de {com_name}"
        text = f"{it['long']}. Zone du PLU {it['idurba']} (partition {it['partition']}), à {it['d_pylone']} m du pylône."
    else:
        label = f"{it['lib']} — PLU de {com_name}"
        text = f"Prescription « {it['long']} » ({it['idurba']}), à {it['d_pylone']} m du pylône et {it['d_parcelle']} m de la parcelle."
    w(f"{it['id']} a owl:NamedIndividual, ant:ZoneReglementaire ;")
    w(f"    rdfs:label \"{esc(label)}\"@fr ;\n    ant:typeDeZone {it['type']} ;\n    ant:dansLieu {com_id} ;")
    w(f"    ant:distanceProjet {it['d_pylone']} ;\n    ant:distanceParcelle {it['d_parcelle']} ;")
    w(f"    ant:origineGpu \"{esc(it['idurba'])}\" ;")
    w(f"    geo:asWKT \"{wkt_out(it['g'].intersection(WINDOW))}\"^^geo:wktLiteral ;")
    w(f"    prov:wasDerivedFrom src:apicarto-gpu-2026-10 ;")
    w(f"    note:note \"{esc(text)}\" .\n")

w("# ═══ Bandes de règlement (géométries dérivées) ═══\n")
for b in bands:
    w(f"{b['id']} a owl:NamedIndividual, ant:ZoneReglementaire ;")
    w(f"    rdfs:label \"{esc(b['label'])}\"@fr ;\n    ant:typeDeZone skt:bande-de-regle ;\n    ant:dansLieu dos:lieudit-kerfilin-sud ;")
    w(f"    ant:rayonAffichage {b['radius']} ;\n    ant:distanceProjet {b['d_pylone']} ;\n    ant:distanceParcelle {b['d_parcelle']} ;")
    w(f"    ant:geometrieDerivee true ;")
    w(f"    geo:asWKT \"{wkt_out(b['g'])}\"^^geo:wktLiteral ;")
    w("    prov:wasDerivedFrom src:apicarto-gpu-2026-10, src:bdtopo-routes-2026-10 ;")
    w(f"    note:note \"{esc(b['note'])}\" .\n")

w("# ═══ Règles du règlement écrit ═══\n")
for r in rules:
    zs = list(r["zones"])
    if r["id"] in band_rule_zone:
        zs.append(band_rule_zone[r["id"]])
    po = []
    if not r.get("exists"):
        po += ["a owl:NamedIndividual, ant:RegleDeZone", f"rdfs:label \"{esc(r['label'])}\"@fr"]
    po += [f"ant:applicabiliteAuProjet \"{r['app']}\"", f"ant:articlePlu \"{esc(r['art'])}\""]
    if r.get("value") is not None:
        po += [f"ant:valeurLimite {r['value']}", f"ant:uniteLimite \"{r['unit']}\""]
    if not r.get("exists"):
        po += ["prov:wasDerivedFrom src:plu-reglement-ecrit-2026-03", f"note:note \"{esc(r['note'])}\""]
    if zs:
        po.append("ant:reglementeZone " + ", ".join(zs))
    w(f"{r['id']} " + " ;\n    ".join(po) + " .\n")

(ROOT / "antenne-reglement.ttl").write_text("\n".join(o), encoding="utf-8")
print("zones", len(items), "bandes", len(bands), "règles", len(rules))
for it in items:
    print(f"  {it['d_pylone']:4d} m  {it['id']:50s} {it['type']:28s} {'-> ' + it['existing'] if it['existing'] else ''}")
for b in bands:
    print("  bande", b["id"], b["d_pylone"], b["g"].geom_type)
