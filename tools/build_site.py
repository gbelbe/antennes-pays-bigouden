#!/usr/bin/env python3
"""Construit le site statique du dossier à partir des fichiers Turtle.

    python3 tools/build_site.py            # écrit _site/
    python3 tools/build_site.py --serve    # puis sert http://localhost:8000

Dépendances : Python 3.11+, rdflib. Réglages : publish.toml.
Le site lit uniquement des fichiers JSON générés (_site/data/) : rien n'est interrogé en ligne.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

import rdflib
from rdflib import RDF, RDFS, OWL, Literal, URIRef
from rdflib.namespace import SKOS, XSD

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"

ANT = "https://kersalous.bzh/ontology/antenne#"
DOS = "https://kersalous.bzh/dossier/"
SKT = "https://kersalous.bzh/taxonomie/"
SRC = "https://kersalous.bzh/provenance/"
NOTE = URIRef("https://example.org/ontology/kai-internal-knowledge#note")
GEOW = URIRef("http://www.opengis.net/ont/geosparql#asWKT")
PROV = "http://www.w3.org/ns/prov#"
DCAT_URL = URIRef("http://www.w3.org/ns/dcat#accessURL")
PREFIXES = {DOS: "dos:", SKT: "skt:", SRC: "src:", ANT: "ant:"}
SKIP_PREDICATES = {RDF.type, RDFS.label, SKOS.prefLabel, GEOW, NOTE, SKOS.inScheme, SKOS.topConceptOf,
                   SKOS.hasTopConcept, SKOS.member}


def A(name):
    return URIRef(ANT + name)


def short(uri):
    s = str(uri)
    for ns, p in PREFIXES.items():
        if s.startswith(ns):
            return p + s[len(ns):]
    return s


def is_ours(uri):
    s = str(uri)
    return s.startswith((DOS, SKT, SRC))


CORPUS_TTL = "antenne-decisions.ttl"   # 3 000+ décisions : graphe à part (vue « Corpus »), jamais dans les fiches ni la chronologie


def load_graph():
    g = rdflib.Graph()
    for f in sorted(ROOT.glob("*.ttl")):
        if f.name != CORPUS_TTL:
            g.parse(f)
    return g


def load_corpus_graph():
    g = rdflib.Graph()
    if (ROOT / CORPUS_TTL).exists():
        g.parse(ROOT / CORPUS_TTL)
    return g


def _flat(n):
    yield n["id"]
    for c in n["children"]:
        yield from _flat(c)


class Site:
    def __init__(self, cfg):
        self.cfg = cfg
        self.g = load_graph()
        self.redact = [re.compile(p) for p in cfg["privacy"].get("redact", [])]
        self.published = {Path(f).name for f in cfg["files"]["publish"]}
        self.hidden = self._hidden()
        self.g2 = self._public_graph()

    # ── confidentialité ──────────────────────────────────────────
    def _hidden(self):
        g, p = self.g, self.cfg["privacy"]
        hide = {ids for ids in p.get("exclude_ids", [])}
        classes = {A(c) for c in p.get("exclude_classes", [])}
        allow = set(p.get("allow_persons", []))
        out = set()
        for s in set(g.subjects()):
            if not isinstance(s, URIRef):
                continue
            sid = short(s)
            types = set(g.objects(s, RDF.type))
            if sid in hide or types & classes:
                out.add(s)
            elif A("Personne") in types and sid not in allow:
                out.add(s)
        return out

    def clean(self, text):
        for rx in self.redact:
            text = rx.sub("[masqué]", text)
        return text

    def _public_graph(self):
        g2 = rdflib.Graph()
        for pfx, ns in (("ant", ANT), ("dos", DOS), ("skt", SKT), ("src", SRC), ("skos", SKOS)):
            g2.bind(pfx, ns)
        for s, p, o in self.g:
            if s in self.hidden or o in self.hidden:
                continue
            if isinstance(o, Literal) and self.redact:
                o = Literal(self.clean(str(o)), lang=o.language, datatype=o.datatype)
            g2.add((s, p, o))
        return g2

    # ── accès ────────────────────────────────────────────────────
    def label(self, s):
        g = self.g2
        for pred in (RDFS.label, SKOS.prefLabel):
            for o in g.objects(s, pred):
                if o.language in ("fr", None):
                    return self.clean(str(o))
        return short(s).split(":")[-1]

    def types(self, s):
        out = []
        for t in self.g2.objects(s, RDF.type):
            if t in (OWL.NamedIndividual, SKOS.Concept):
                continue
            out.append(str(t).split("#")[-1].split("/")[-1])
        return out

    def val(self, s, pred, default=None):
        for o in self.g2.objects(s, pred):
            return o
        return default

    def note(self, s):
        o = self.val(s, NOTE)
        return self.clean(str(o)) if o is not None else ""

    def ref(self, o):
        """Un objet URI devient {id,label} s'il est dans nos espaces de noms et visible."""
        if isinstance(o, URIRef) and is_ours(o) and o not in self.hidden:
            return {"id": short(o), "label": self.label(o)}
        return None

    def sources_of(self, s):
        out = []
        for o in self.g2.objects(s, URIRef(PROV + "wasDerivedFrom")):
            r = self.ref(o)
            if r:
                out.append(r)
        return out

    def prop_label(self, p):
        for o in self.g.objects(p, RDFS.label):
            return str(o)
        return str(p).split("#")[-1].split("/")[-1]

    # ── entités ──────────────────────────────────────────────────
    def entities(self):
        g = self.g2
        ents = {}
        for s in set(g.subjects()):
            if not (isinstance(s, URIRef) and is_ours(s)):
                continue
            types = self.types(s)
            if not types and not self.val(s, RDFS.label):
                continue
            props = []
            for p, o in g.predicate_objects(s):
                if p in SKIP_PREDICATES or str(p).startswith(PROV):
                    continue
                pl = self.prop_label(p)
                if isinstance(o, Literal):
                    v = self.clean(str(o))
                    if p == A("urlSource") and not v.startswith("http") and Path(v).name not in self.published:
                        continue   # renvoi vers un fichier non publié : pas de lien mort
                    if len(v) > 400:
                        v = v[:400] + "…"
                    props.append({"p": pl, "v": v})
                else:
                    r = self.ref(o)
                    if r:
                        props.append({"p": pl, "ref": r})
            props.sort(key=lambda x: x["p"])
            ents[short(s)] = {
                "id": short(s), "label": self.label(s), "types": types,
                "note": self.note(s), "props": props,
                "sources": self.sources_of(s),
                "geom": bool(self.val(s, GEOW)),
            }
        # relations entrantes (qui pointe vers moi)
        inc = defaultdict(list)
        for s in set(g.subjects()):
            if not (isinstance(s, URIRef) and is_ours(s)) or short(s) not in ents:
                continue
            for p, o in g.predicate_objects(s):
                if p in SKIP_PREDICATES or str(p).startswith(PROV) or isinstance(o, Literal):
                    continue
                if is_ours(o) and short(o) in ents:
                    inc[short(o)].append({"p": self.prop_label(p), "ref": {"id": short(s), "label": ents[short(s)]["label"]}})
        for k, v in inc.items():
            ents[k]["incoming"] = sorted(v, key=lambda x: (x["p"], x["ref"]["label"]))[:60]
        return ents

    # ── cartes ───────────────────────────────────────────────────
    @staticmethod
    def parse_wkt(w):
        """WKT -> structure Leaflet [lat, lon] : Point (ll), LineString (pts), (Multi)Polygon (rings ; polys si multiple)."""
        w = w.strip()
        up = w.upper()
        if up.startswith("POINT"):
            x, y = [float(a) for a in re.search(r"\(([^)]+)\)", w).group(1).split()]
            return {"type": "Point", "ll": [round(y, 6), round(x, 6)]}
        stack = [[]]
        for tok in re.findall(r"\(|\)|[-+0-9.eE]+\s+[-+0-9.eE]+", w):
            if tok == "(":
                stack.append([])
            elif tok == ")":
                done = stack.pop()
                stack[-1].append(done)
            else:
                x, y = [float(a) for a in tok.split()]
                stack[-1].append([round(y, 6), round(x, 6)])
        top = stack[0][0]
        if up.startswith("LINESTRING"):
            return {"type": "Line", "pts": top}
        if up.startswith("MULTIPOLYGON"):
            polys = [list(poly) for poly in top]
            return {"type": "Polygon", "rings": [r for poly in polys for r in poly], "polys": polys}
        return {"type": "Polygon", "rings": list(top)}

    def map_data(self, ents):
        g = self.g2
        feats, cover = [], []
        projet = None
        for s, w in g.subject_objects(GEOW):
            if short(s) not in ents:
                continue
            geom = self.parse_wkt(str(w))
            types = ents[short(s)]["types"]
            sid = short(s)
            if "ZoneDeCouverture" in types:
                cover.append({
                    "id": sid, "label": ents[sid]["label"], "geom": geom,
                    "level": next((self.label(o) for o in g.objects(s, A("niveauDeCouverture"))), ""),
                    "operator": next((self.label(o) for o in g.objects(s, A("operateurCouvert"))), ""),
                    "gen": next((self.label(o) for o in g.objects(s, A("generationCouverte"))), ""),
                })
                continue
            f = {"id": sid, "label": ents[sid]["label"], "types": types, "geom": geom}
            if "SupportAntenne" in types or "ProjetAntenne" in types:
                owner = next(iter(g.objects(s, A("proprietaireSupport"))), None)
                ops = [self.label(o) for o in g.objects(s, A("operateurPresent"))]
                f.update({
                    "owner": self.label(owner) if owner else "",
                    "owner_id": short(owner) if owner else "",
                    "operators": sorted(ops),
                    "status": next((self.label(o) for o in g.objects(s, A("statutInstallation"))), ""),
                    "height": next((str(o) for o in g.objects(s, A("hauteurSupport"))), ""),
                    "anfr": next((str(o) for o in g.objects(s, A("identifiantSupportAnfr"))), ""),
                })
                if "ProjetAntenne" in types:
                    f["kind"] = "projet"
                    projet = geom.get("ll")
                elif owner is not None and short(owner) == "skt:prop-73":
                    f["kind"] = "phoenix"
                else:
                    f["kind"] = "support"
            elif "ZoneReglementaire" in types:
                f["kind"] = "zone"
                tz = next(iter(g.objects(s, A("typeDeZone"))), None)
                f["ztype"] = short(tz) if tz else ""
                f["ztype_label"] = self.label(tz) if tz else ""
                d = self.val(s, A("distanceProjet"))
                f["d"] = float(d) if d is not None else None
                f["derived"] = bool(self.val(s, A("geometrieDerivee")))
                r = self.val(s, A("rayonAffichage"))
                f["radius"] = float(r) if r is not None else None
                f["text"] = ents[sid]["note"][:500]
                rules = []
                for rs in g.subjects(A("reglementeZone"), s):
                    v = self.val(rs, A("valeurLimite"))
                    rules.append({"id": short(rs), "label": self.label(rs), "app": str(self.val(rs, A("applicabiliteAuProjet"), "")),
                                  "art": str(self.val(rs, A("articlePlu"), "")),
                                  "value": (float(v) if v is not None else None), "unit": str(self.val(rs, A("uniteLimite"), ""))})
                f["rules"] = sorted(rules, key=lambda r: r["label"])
            elif sid == "dos:position-pylone-operateur":
                f["kind"] = "pylone"
            else:
                f["kind"] = "autre"
            feats.append(f)
        return {"features": feats, "center": projet or self.cfg["site"]["fallback_center"]}, cover

    # ── chronologie ──────────────────────────────────────────────
    def timeline(self, ents):
        g = self.g2
        items = []

        def add(s, date, title, cat, extra=None):
            if not date:
                return
            it = {"id": short(s), "date": str(date), "title": title, "cat": cat,
                  "note": ents.get(short(s), {}).get("note", "")[:500]}
            if extra:
                it.update(extra)
            items.append(it)

        for s in g.subjects(RDF.type, A("Evenement")):
            if s in self.hidden:
                continue
            add(s, self.val(s, A("dateEvenement")), self.label(s), "Procédure")
        for s in g.subjects(RDF.type, A("OperationSurSites")):
            add(s, self.val(s, A("dateEvenement")), self.label(s), "Sociétés de pylônes",
                {"sites": str(self.val(s, A("nombreSites"), ""))})
        for s in g.subjects(RDF.type, A("Delai")):
            end = self.val(s, A("expireLe"))
            if end:
                add(s, end, self.label(s), "Délais", {"start": str(self.val(s, A("debuteLe"), ""))})
        for s in g.subjects(RDF.type, A("Action")):
            ech = self.val(s, A("echeance"))
            if ech:
                st = self.val(s, A("statut"))
                add(s, ech, self.label(s), "Actions", {"status": self.label(st) if st else ""})
        for s in g.subjects(RDF.type, A("Jurisprudence")):
            add(s, self.val(s, A("dateDecision")), self.label(s), "Jurisprudence")
        for s in g.subjects(RDF.type, A("Document")):
            if s in self.hidden:
                continue
            add(s, self.val(s, A("datePublication")), self.label(s), "Pièces")
        items.sort(key=lambda x: x["date"])
        return items

    # ── corpus : décisions classées par la taxonomie du contentieux ──
    FACET = {"moyenEvoque": "ev", "moyenRetenu": "re", "moyenEcarte": "ec", "moyenEcarteDeduit": "ed"}

    def corpus(self, repo_url):
        gc = load_corpus_graph()
        if not len(gc):
            return {"schemes": [], "concepts": [], "decisions": [], "names": {}}
        g = self.g

        def lab(x):
            for pred in (RDFS.label, SKOS.prefLabel):
                for o in gc.objects(x, pred):
                    return str(o)
            for pred in (RDFS.label, SKOS.prefLabel):
                for o in g.objects(x, pred):
                    return str(o)
            return short(x).split(":")[-1]

        used = set()
        decisions = []
        for d in gc.subjects(RDF.type, A("Jurisprudence")):
            row = {"id": short(d), "label": lab(d), "ref": str(self.val_in(gc, d, A("reference"), "")),
                   "date": str(self.val_in(gc, d, A("dateDecision"), "")),
                   "score": int(self.val_in(gc, d, A("scoreProximite"), 0)),
                   "why": str(self.val_in(gc, d, A("detailScore"), "")),
                   "court": "", "c": [], "ev": [], "re": [], "ec": [], "ed": [], "as": [], "ar": [], "aa": [], "am": ""}
            for p, o in gc.predicate_objects(d):
                name = str(p).replace(ANT, "")
                if name == "rendueParJuridiction":
                    row["court"] = lab(o)
                elif name in self.FACET and isinstance(o, URIRef):
                    row[self.FACET[name]].append(short(o)); used.add(short(o))
                elif isinstance(o, URIRef) and str(o).startswith(SKT):
                    row["c"].append(short(o)); used.add(short(o))
                elif name == "requerantNomme":
                    row["as"].append({"id": short(o), "label": lab(o)})
                elif name == "avocatRequerant":
                    row["ar"].append({"id": short(o), "label": lab(o)})
                elif name == "avocatAdverse":
                    row["aa"].append({"id": short(o), "label": lab(o)})
                elif name == "avocatOpenData":
                    row["am"] = str(o)
                elif p == URIRef(PROV + "wasDerivedFrom"):
                    for q in (A("cheminLocal"), A("empreinteSha256"), A("archiveOrigine")):
                        v = self.val_in(gc, o, q)
                        row[{"cheminLocal": "path", "empreinteSha256": "sha", "archiveOrigine": "zip"}[str(q).replace(ANT, "")]] = str(v) if v else ""
            if row.get("path"):
                row["url"] = f"{repo_url}/blob/master/{row['path']}"
            for k in ("ev", "re", "ec", "ed", "c"):
                row[k].sort()
            decisions.append(row)
        # concepts des schémas utilisés par les décisions
        schemes = {}
        for c in g.subjects(RDF.type, SKOS.Concept):
            for sc in g.objects(c, SKOS.inScheme):
                schemes.setdefault(short(sc), []).append(c)
        out_schemes, concepts = [], {}
        for sid, cs in schemes.items():
            if not any(short(c) in used for c in cs):
                continue
            n = self.val_in(g, URIRef(SKT + sid.split(":")[1]), SKOS.notation, "")
            out_schemes.append({"id": sid, "label": self.label(URIRef(SKT + sid.split(":")[1])), "notation": str(n),
                                "definition": str(self.val_in(g, URIRef(SKT + sid.split(":")[1]), SKOS.definition, ""))})
            for c in cs:
                b = self.val_in(g, c, SKOS.broader)
                concepts[short(c)] = {"id": short(c), "label": self.label(c), "scheme": sid,
                                      "broader": short(b) if b else "", "notation": str(self.val_in(g, c, SKOS.notation, "")),
                                      "definition": str(self.val_in(g, c, SKOS.definition, "")),
                                      "explication": str(self.val_in(g, c, SKOS.scopeNote, ""))}
        # schéma des communes : ne garder que les communes qui ont des décisions (et leurs statuts)
        usedc = {i for i in used}
        for cid in list(concepts):
            c = concepts[cid]
            if c["scheme"] == "skt:LoiLittoral" and c["broader"] and cid not in usedc:
                del concepts[cid]
        out_schemes.sort(key=lambda x: x["notation"])
        decisions.sort(key=lambda r: (-r["score"], r["date"]))
        return {"schemes": out_schemes, "concepts": sorted(concepts.values(), key=lambda c: c["notation"].replace(".", "~")),
                "decisions": decisions}

    def moyens_vs_corpus(self, moyens, corpus):
        """Moyens du dossier et taxonomie des moyens, chacun avec ce que dit le corpus de décisions.
        Retourne l'arbre des moyens (groupes > concepts > moyens du dossier)."""
        D = corpus["decisions"]
        cs = {c["id"]: c for c in corpus["concepts"]}
        kids = defaultdict(list)
        for c in corpus["concepts"]:
            if c["scheme"] == "skt:Moyens":
                kids[c["broader"] or "root"].append(c["id"])

        def below(i):
            return [i] + [x for k in kids.get(i, []) for x in below(k)]
        lues = {d["id"] for d in D if "skt:l-lu" in d["c"] or "skt:l-partiel" in d["c"]}

        def stats(ids):
            ids = set(ids)
            ev = [d for d in D if ids & set(d["ev"])]
            return {
                "evoque": len(ev), "proches": sum(1 for d in ev if d["score"] >= 50),
                "retenu": sum(1 for d in D if ids & set(d["re"])),
                "ecarte_lu": sum(1 for d in D if ids & set(d["ec"])),
                "ecarte_deduit": sum(1 for d in D if ids & set(d["ed"])),
                "total": len(D), "lues": len(lues),
            }
        for m in moyens:
            ids = {x for c in m["concepts"] for x in below(c)}
            m["corpus"] = dict(stats(ids), concepts=[{"id": c, "label": cs[c]["label"] if c in cs else c} for c in m["concepts"]]) if ids else None
        by_concept = defaultdict(list)
        for m in moyens:
            if m["concepts"]:
                by_concept[m["concepts"][0]].append(m["id"])

        def node(i):
            c = cs[i]
            return {"id": i, "label": c["label"], "definition": c["definition"], "explication": c.get("explication", ""), "notation": c["notation"],
                    "stats": stats(below(i)), "moyens": by_concept.get(i, []), "children": [node(k) for k in kids.get(i, [])]}
        arbre = [node(i) for i in kids.get("root", [])]
        known = {x for g in arbre for x in _flat(g)}
        orphans = [m["id"] for m in moyens if not m["concepts"] or m["concepts"][0] not in known]
        return {"groupes": arbre, "orphelins": orphans, "total": len(D), "lues": len(lues)}

    def couverture(self):
        """Mesures de couverture au site et comparaison avec les autres communes, pour l'onglet Couverture."""
        g = self.g2
        site, cmp_ = [], {}
        names = {"rural": "Communes rurales de France métropolitaine", "fin_rural": "Communes rurales du Finistère",
                 "similar": "Communes de taille et de densité proches de Plonéour-Lanvern", "near10": "Communes dans les 10 km du site",
                 "france": "Toutes les communes de France métropolitaine"}
        for s in g.subjects(RDF.type, A("Mesure")):
            sid = short(s)
            val = self.val(s, A("valeur")); unit = self.val(s, A("unite"))
            if val is None:
                continue
            row = {"id": sid, "label": self.label(s), "value": float(val), "unit": str(unit or "")}
            m = re.match(r"dos:m-cmp-(.+?)-(tres-bonne|bonne)$", sid)
            if m and m.group(1) in names:
                cmp_.setdefault(m.group(1), {"id": m.group(1), "label": names[m.group(1)]})[m.group(2)] = row["value"]
            elif m and m.group(1).startswith("rang-finistere"):
                cmp_.setdefault("rang", {"id": "rang", "label": "Rang du Finistère parmi 90 départements (communes rurales, 1 = meilleur)"})[m.group(2)] = row["value"]
            elif sid.startswith("dos:m-cmp"):
                continue
            elif "Bouygues Telecom 4G" in row["label"] or "couverture" in row["label"].lower():
                site.append(row)
        order = ["rural", "fin_rural", "similar", "near10", "france", "rang"]
        return {"site": site, "comparaison": [cmp_[k] for k in order if k in cmp_]}

    @staticmethod
    def val_in(graph, s, pred, default=None):
        for o in graph.objects(s, pred):
            return o
        return default

    # ── dossier : moyens, actions, délais ────────────────────────
    def dossier(self, ents):
        g = self.g2
        moyens = []
        for s in g.subjects(RDF.type, A("MoyenJuridique")):
            moyens.append({
                "id": short(s), "label": self.label(s), "note": self.note(s),
                "concepts": [short(o) for o in g.objects(s, A("concordeAvecConcept"))],
                "fondements": [r for o in g.objects(s, A("fondementJuridique")) if (r := self.ref(o))],
                "preuves": [r for o in list(g.objects(s, A("etayePar"))) + list(g.objects(s, A("etayeParMesure"))) if (r := self.ref(o))],
                "actions": [r for a in g.subjects(A("soutient"), s) if (r := self.ref(a))],
            })
        moyens.sort(key=lambda m: m["label"])
        actions = []
        for s in g.subjects(RDF.type, A("Action")):
            st = self.val(s, A("statut"))
            actions.append({
                "id": short(s), "label": self.label(s), "status": self.label(st) if st else "",
                "date": str(self.val(s, A("echeance"), "")), "note": self.note(s),
                "target": [r for o in g.objects(s, A("cible")) if (r := self.ref(o))],
            })
        actions.sort(key=lambda a: (a["date"] or "9999", a["label"]))
        delais = []
        for s in g.subjects(RDF.type, A("Delai")):
            delais.append({"id": short(s), "label": self.label(s), "start": str(self.val(s, A("debuteLe"), "")),
                           "end": str(self.val(s, A("expireLe"), "")), "note": self.note(s)})
        measures = []
        for s in g.subjects(RDF.type, A("Mesure")):
            if self.val(s, A("surProprietaire")) is not None or self.val(s, A("operateurHeberge")) is not None:
                continue
            measures.append({"id": short(s), "label": self.label(s), "value": str(self.val(s, A("valeur"), "")),
                             "unit": str(self.val(s, A("unite"), ""))})
        return {"moyens": moyens, "actions": actions, "delais": delais, "mesures": measures}

    # ── réseaux et propriétaires ─────────────────────────────────
    def reseau(self, ents):
        g = self.g2
        ens = []
        for s in g.subjects(RDF.type, A("EnsembleTerritorial")):
            sid = short(s)
            owners, bouy, total, btotal = [], [], None, None
            for m in g.subjects(A("porteSurObjet"), s):
                ow = self.val(m, A("surProprietaire"))
                heb = self.val(m, A("operateurHeberge"))
                v = self.val(m, A("valeur"))
                if ow is not None:
                    row = {"owner": self.label(ow), "owner_id": short(ow), "pct": float(v),
                           "n": int(self.val(m, A("nombreSupports"))), "total": int(self.val(m, A("nombreSupportsTotal")))}
                    (bouy if heb is not None else owners).append(row)
                elif heb is not None:
                    btotal = int(v)
                else:
                    total = int(v)
            owners.sort(key=lambda r: -r["pct"])
            bouy.sort(key=lambda r: -r["pct"])
            ens.append({"id": sid, "label": self.label(s), "total": total, "bouygues_total": btotal,
                        "owners": owners, "bouygues_owners": bouy})
        ens.sort(key=lambda e: e["label"])
        ops = []
        for s in g.subjects(RDF.type, A("OperationSurSites")):
            acq = self.val(s, A("acquereur"))
            ops.append({
                "id": short(s), "label": self.label(s), "date": str(self.val(s, A("dateEvenement"), "")),
                "sites": int(self.val(s, A("nombreSites"), 0) or 0),
                "buyer": self.label(acq) if acq else "",
                "sellers": [self.label(o) for o in g.objects(s, A("cedant"))],
                "note": self.note(s), "sources": self.sources_of(s),
            })
        ops.sort(key=lambda o: o["date"])
        towercos = []
        for s in g.subjects(RDF.type, A("SocietePylones")):
            code = self.val(s, A("codeProprietaireAnfr"))
            parent = self.val(s, A("filialeDe"))
            towercos.append({"id": short(s), "label": self.label(s), "code": int(code) if code is not None else None,
                             "parent": self.label(parent) if parent else "", "note": self.note(s)})
        towercos.sort(key=lambda t: t["label"])
        return {"ensembles": ens, "operations": ops, "societes": towercos}

    # ── sources ──────────────────────────────────────────────────
    def sources(self):
        g = self.g2
        derived = defaultdict(int)
        for s, o in g.subject_objects(URIRef(PROV + "wasDerivedFrom")):
            derived[short(o)] += 1
        rows = []
        for cls in ("DocumentSource", "JeuDeDonnees", "RechercheWeb"):
            for s in g.subjects(RDF.type, URIRef(SRC + cls)):
                niv = self.val(s, URIRef(SRC + "niveauDePreuve"))
                url = self.val(s, DCAT_URL)
                rows.append({
                    "id": short(s), "label": self.label(s), "kind": cls,
                    "level": self.label(niv) if niv else "", "level_id": short(niv) if niv else "",
                    "url": str(url) if url else "", "note": self.note(s),
                    "date": str(self.val(s, URIRef(SRC + "dateDonnees"), "")),
                    "used": derived.get(short(s), 0),
                })
        rows.sort(key=lambda r: (r["level_id"] != "src:primaire", r["label"]))
        levels = []
        for s in g.subjects(RDF.type, URIRef(SRC + "NiveauDePreuve")):
            levels.append({"id": short(s), "label": self.label(s), "note": self.note(s)})
        return {"sources": rows, "levels": levels}


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build():
    cfg = tomllib.loads((ROOT / "publish.toml").read_text(encoding="utf-8"))
    site = Site(cfg)
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)

    ents = site.entities()
    map_data, cover = site.map_data(ents)
    tl = site.timeline(ents)
    dos = site.dossier(ents)
    res = site.reseau(ents)
    src = site.sources()
    corpus = site.corpus(cfg["site"]["repo_url"])
    dos["arbre"] = site.moyens_vs_corpus(dos["moyens"], corpus)
    couv = site.couverture()

    key = os.environ.get(cfg["maps"].get("env_key", "GOOGLE_MAPS_API_KEY"), "")
    meta = {
        "title": cfg["site"]["title"], "subtitle": cfg["site"]["subtitle"], "disclaimer": cfg["site"]["disclaimer"],
        "repo_url": cfg["site"]["repo_url"], "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": git("rev-parse", "--short", "HEAD"), "commit_date": git("log", "-1", "--format=%cI"),
        "google_maps_key": key,
        "stats": {
            "supports": sum(1 for f in map_data["features"] if f["kind"] in ("support", "phoenix", "projet")),
            "phoenix_supports": sum(1 for f in map_data["features"] if f["kind"] == "phoenix"),
            "entities": len(ents), "triples": len(site.g2),
            "decisions": len(corpus["decisions"]), "sources": len(src["sources"]), "moyens": len(dos["moyens"]),
        },
        "published_files": [Path(f).name for f in cfg["files"]["publish"] if (ROOT / f).exists()],
    }
    write_json(OUT / "data" / "meta.json", meta)
    write_json(OUT / "data" / "entities.json", ents)
    write_json(OUT / "data" / "map.json", map_data)
    write_json(OUT / "data" / "coverage.json", cover)
    write_json(OUT / "data" / "timeline.json", tl)
    write_json(OUT / "data" / "dossier.json", dos)
    write_json(OUT / "data" / "reseau.json", res)
    write_json(OUT / "data" / "sources.json", src)
    write_json(OUT / "data" / "corpus.json", corpus)
    write_json(OUT / "data" / "couverture.json", couv)
    taux = ROOT / "corpus" / "taux.json"
    write_json(OUT / "data" / "taux.json", json.loads(taux.read_text(encoding="utf-8")) if taux.exists() else {"colonnes": [], "lignes": []})
    if (ROOT / CORPUS_TTL).exists():
        shutil.copy2(ROOT / CORPUS_TTL, OUT / "data" / "corpus.ttl")

    # graphe public filtré (sans les entités masquées)
    site.g2.serialize(OUT / "data" / "graphe-public.ttl", format="turtle")

    # fichiers autorisés
    (OUT / "files").mkdir()
    for f in cfg["files"]["publish"]:
        p = ROOT / f
        if p.exists():
            shutil.copy2(p, OUT / "files" / p.name)

    # coquille de l'application
    for f in (ROOT / "site-src").iterdir():
        if f.is_file():
            shutil.copy2(f, OUT / f.name)
    (OUT / ".nojekyll").write_text("")
    print(f"site construit dans {OUT} : {len(ents)} entités, {len(site.g2)} triplets publics, "
          f"{len(map_data['features'])} objets cartographiés, {len(tl)} évènements, {len(corpus['decisions'])} décisions")
    hidden = len(site.hidden)
    print(f"confidentialité : {hidden} entités masquées")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    build()
    if a.serve:
        import http.server, socketserver, functools
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        with socketserver.TCPServer(("127.0.0.1", a.port), h) as httpd:
            print(f"http://localhost:{a.port}")
            httpd.serve_forever()
