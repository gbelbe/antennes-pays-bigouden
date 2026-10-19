"""Relie chaque décision de corpus/manifest.csv aux concepts de la taxonomie et écrit antenne-decisions.ttl.
Usage : python3 -I tools/corpus/build_decisions.py <dépôt>
Les moyens « évoqués » sont repérés par expression régulière (taxo_spec.py) ; retenus / écartés viennent de lectures_map.py (31 décisions lues)."""
import csv,sys,os,re,html,json,unicodedata,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import taxo_spec as T
from lectures_map import LU,PARTIEL,DATES
repo=sys.argv[1]
def strip(s): return "".join(c for c in unicodedata.normalize("NFKD",s) if not unicodedata.combining(c))
def slug(s): return re.sub(r"[^a-z0-9]+","-",strip(s).lower()).strip("-")
def lit(s): return '"'+s.replace("\\","\\\\").replace('"','\\"').replace("\n"," ")+'"'
def tag(b,t):
    m=re.search(rf"<{t}>(.*?)</{t}>",b,re.S); return html.unescape(m.group(1).strip()) if m else ""
SMALL={"en","de","du","la","le","les","sur","sous","des","d","l"}
def titre(s):
    out=[]
    for i,w in enumerate(re.split(r"(?<=[\s'’-])",s.lower())):
        k=w.strip(" '’-")
        out.append(w if (i and k in SMALL) else w[:1].upper()+w[1:])
    return "".join(out)
RX={cid:re.compile(rx,re.I) for sc in T.ALL.values() for cid,_,_,_,rx in sc if rx}
MOY={c[0] for c in T.MOYENS}
CTX={c[0] for c in T.CONTEXTE}
MECA={"p-regularisation","p-urgence-presumee","p-recours-abusif","p-frais","p-cristallisation"}

LIT={}
for _r in csv.DictReader(open(f"{repo}/corpus/communes_littorales_29.csv",encoding="utf-8")):
    LIT[strip(_r["nom"]).lower().replace("’","'")]=(_r["insee"],_r["statut"])
LITRX=re.compile(r"(?:commune|maire|conseil municipal|ville)\s+(?:de la |de l'|de |d'|du |des )?("+"|".join(re.escape(k) for k in sorted(LIT,key=len,reverse=True))+r")(?![\w-])")
def commune_finistere(txt):
    m=LITRX.search(strip(txt[:6000]).lower().replace("’","'"))
    return LIT[m.group(1)] if m else None

def motifs(txt):
    L=txt.split("\n")
    k=next((n for n,l in enumerate(L) if re.match(r"(?:1\. |Sur les conclusions|Considérant|Sur (?:la|le|l[’']) |En premier lieu|En ce qui concerne)",l.strip())),None)
    if k is None: return ""
    e=next((n for n,l in enumerate(L) if n>k and re.match(r"(?:Article 1|D\s?E\s?C\s?I\s?D\s?E)",l.strip())),len(L))
    return "\n".join(L[k:e])

def juridiction(name,niveau):
    n=strip(name).lower().strip()
    if niveau=="CE" or "section du contentieux" in n: return "conseil-etat","Conseil d'État"
    if niveau=="TA":
        m=re.search(r"tribunal administratif (?:de la |de l'|de |d'|du |d |des )?(.+)",n); c=m.group(1).strip()
        c=re.sub(r"^st ","saint-",c)
        return "ta-"+slug(c),"Tribunal administratif de "+titre(c) if not c.startswith(("a","e","i","o","u","h")) else "Tribunal administratif d'"+titre(c)
    m=re.search(r"cour administrative d'appel (?:de |d'|du |d )?(.+)",n); c=m.group(1).strip()
    return "caa-"+slug(c),"Cour administrative d'appel de "+titre(c)

def effet(issue,plaig,sol):
    if issue.startswith("PROJET AUTORISÉ"): return "e-debloque"
    if issue.startswith("PROJET MAINTENU"): return "e-maintenu"
    if issue.startswith(("OPPOSITION MAINTENUE","OPPOSITION CONFIRMÉE","OPPOSITION RÉTABLIE","RETRAIT/REFUS MAINTENU","PROJET ANNULÉ")): return "e-bloque"
    if issue.startswith("PROJET RÉTABLI"): return "e-maintenu"
    if "Sursis" in issue or sol=="Satisfaction partielle": return "e-retarde"
    r=plaig in ("particuliers/riverains","association/collectif")
    if "Désistement" in issue and r: return "e-maintenu"
    if sol=="Satisfaction totale": return "e-bloque" if r else ("e-debloque" if plaig=="opérateur/société pylônes" else "e-indetermine")
    if sol.startswith("Rejet"): return "e-maintenu" if r else ("e-bloque" if plaig=="opérateur/société pylônes" else "e-indetermine")
    return "e-indetermine"

def resultat(sol,stade,issue,niveau,tail):
    out=[]
    s=sol
    if s=="Rejet": out.append("r-rejet-fond")
    elif s=="Rejet défaut de doute sérieux": out.append("r-rejet-doute")
    elif s.startswith("Rejet") or s.startswith("R.822-5") and "Rejet" in s or "R.222-1" in s: out.append("r-rejet-manifeste")
    if "irrecevab" in s.lower() or (s.startswith("Rejet") and re.search(r"irrecevable",tail,re.I)): out.append("r-irrecevable")
    if s.startswith("Désistement") or s.startswith("R.822-5 Désistement") or s.startswith("Radiation"): out.append("r-desistement")
    if s=="Non-lieu": out.append("r-non-lieu")
    if s in ("Sursis à statuer","Supplément d'instruction","Enquête","Renvoi","Renvoi après cassation"): out.append("r-sursis")
    if s=="Suspension accordée": out.append("r-suspension")
    if s=="Satisfaction partielle": out.append("r-annulation-partielle")
    if s=="Satisfaction totale": out.append("r-suspension" if stade=="référé" else "r-annulation-totale")
    if niveau=="CAA":
        if re.search(r"confirm|REJET",issue) and "infirm" not in issue: out.append("r-appel-confirme")
        if re.search(r"EN APPEL|infirmée|RÉTABLI|RÉTABLIE",issue): out.append("r-appel-infirme")
    return list(dict.fromkeys(out))

OPREQ=re.compile(r"\b(?:Free|Orange|Bouygues|SFR|Cellnex|Hivory|ATC|Totem|TDF|Phoenix|Towercast|On Tower|Telco|Axians|Infracos|FPS|Altitude|Itas|Circet|Eiffage|Zayo|OTF)\b|Société [Ff]rançaise (?:du|de) [Rr]adiotéléphon|société[^,.]{0,40}(?:infrastructure|télécom|mobile|tower)",re.I)
def requerant(txt,fallback):
    """Qui saisit la juridiction : lu dans la phrase d'ouverture (« Par une requête…, X, représenté par Me Y, demande »)."""
    m=re.search(r"(?:Par (?:une|deux|trois)?\s?(?:requêtes?|demandes?|ordonnances?|déférés?)|requête|déféré|appel)[^:]{0,80}?(?:enregistré|déposé)[^,]{0,140},?([^.]{0,320}?)\b(?:demand|conclu)",re.sub(r"\s+"," ",txt[:3500]))
    r=m.group(1) if m else ""
    if not r:
        m2=re.search(r"([^.]{0,260}?)\b(?:a demandé|ont demandé|demande|demandent)\b",re.sub(r"\s+"," ",txt[:2500]))
        r=m2.group(1) if m2 else ""
    if re.search(r"préfet|préfète|déféré",r,re.I): return "q-prefet"
    if re.search(r"\bla (?:commune|ville) d|\ble département|communauté (?:de communes|d.agglomération|urbaine)|métropole",r,re.I) and not OPREQ.search(r): return "q-commune"
    if OPREQ.search(r): return "q-operateur"
    if re.search(r"\bl.association\b|\bassociation\b|collectif",r,re.I): return "q-association"
    if re.search(r"syndicat des copropriétaires|SCI\b|société civile",r,re.I): return "q-syndicat"
    if re.search(r"\bM\. |\bMme |\bMM\. |consorts|épous|époux|\bMlle",r): return "q-riverains"
    return fallback

def asso_type(name):
    n=strip(name).lower()
    if re.search(r"patrimoine|sites? et monuments|vieilles maisons|monuments|histoire|sauvegarde",n): return "q-asso-patrimoine"
    if re.search(r"collectif|riverains|habitants|defense|quartier|voisins|vigilance|stop|non a",n): return "q-collectif"
    return "q-asso-environnement"

def avocats(text):
    out={"requerant":[],"adverse":[]}
    for m in re.finditer(r"(?:représentée?s?|assistée?s?)(?: en dernier lieu| en dernier ressort)? par (?:Mes?|Maîtres?)\s+([A-ZÉÈ][^,;()]{1,60}?)(?=,| avocat|\(|\.| demand| conclu| et | ainsi)",text):
        nm=re.sub(r"\s+"," ",m.group(1)).strip(" ,")
        if len(nm)<3 or not re.match(r"^[A-ZÉÈ][\w'’\-éèêëàâîïôöûüç ]+$",nm): continue
        after=text[m.end():m.end()+160]
        if re.search(r"^[^.]{0,120}?\bdemand",after): out["requerant"].append(nm)
        elif re.search(r"^[^.]{0,120}?\b(?:conclu|défense|rejet)",after): out["adverse"].append(nm)
    return {k:list(dict.fromkeys(v)) for k,v in out.items()}

ASSO=re.compile(r"(?:l['’]|L['’]|la |le |les )?(association|collectif|syndicat|fédération|comité)\s+(?:dite?s?\s+)?(?:«\s*)?([^,;()«»\"“”]{3,90}?)(?:\s*»|,|;|\(| représent| dont| ayant| et autres| demand| sur le fondement| soutien| tend|$)",re.I)
def asso(text):
    i=re.search(r"\bdemand(?:e|ent|ant)\b|doivent être regardés",text)
    head=text[:i.start()] if i else text[:800]
    head=head[-500:]
    m=ASSO.search(head)
    if not m: return None
    nm=re.sub(r"\s+"," ",m.group(2)).strip(" «»\"'’-")
    if len(nm)<4 or re.match(r"^(?:et|ou|de|des|du|dont|qui)\b",nm,re.I) or nm.lower().startswith(("requérant","demandeur")): return None
    nm=re.split(r"\s+et\s+(?:M\.|Mme|Mmes|MM\.|Mlle)\b",nm)[0].strip()
    if len(nm)<4: return None
    return (m.group(1).lower(),m.group(1).capitalize()+" "+nm)

DIST=re.compile(r"\bà\s+(?:environ\s+|seulement\s+|moins de\s+|plus de\s+|près de\s+)?(\d{1,4}(?:[,.]\d+)?)\s*(?:mètres|metres|m)\b[^.]{0,70}?(?:du pylône|de la station|de l'antenne|de l'installation|du projet|du terrain d'assiette|du site|de l'ouvrage|du futur pylône|de la parcelle|du mât|des antennes)",re.I)
def distance(text):
    v=[float(m.group(1).replace(",",".")) for m in DIST.finditer(text)]
    v=[x for x in v if 5<=x<=2000]
    return min(v) if v else None

def proximite(d):
    s=0;why=[]
    def a(n,t): 
        nonlocal s; s+=n; why.append(f"{'+' if n>0 else ''}{n} {t}")
    ev=d["evoque"]|set(d["ctx"])
    if "c-toiture" in d["ctx"] and "c-pylone" not in d["ctx"]: a(-30,"antenne sur toiture")
    elif "c-pylone" in d["ctx"]: a(20,"pylône hors toiture")
    if d["acte"] in ("a-non-opposition","a-opposition","a-retrait","a-pc"): a(10,"acte d'urbanisme (DP ou permis)")
    if d["req"][0] in ("q-riverains","q-association"): a(20,"riverains ou association contre le projet")
    elif d["req"][0]=="q-operateur": a(5,"recours d'opérateur")
    if "c-rural" in d["ctx"]: a(15,"zone A ou N")
    if "c-urbain" in d["ctx"] and "c-rural" not in d["ctx"]: a(-5,"zone urbaine")
    if "c-littoral" in d["ctx"]: a(-15,"loi Littoral (inapplicable à Plonéour-Lanvern)")
    if "c-abords-mh" in d["ctx"] or "m-covisibilite" in ev: a(10,"abords de monument ou covisibilité")
    if d["dist"] is not None and d["dist"]<100: a(10,f"habitation à {int(d['dist'])} m")
    if "m-zone-humide" in ev or "m-ebc" in ev: a(5,"zone humide ou boisement évoqués")
    if d["lu"]: a(10,"décision lue")
    if d["ressort"]: a(5,"ressort de la CAA de Nantes")
    return max(0,min(100,s)),"; ".join(why)

RESSORT_NANTES={"ta-rennes","ta-nantes","ta-caen","ta-rouen","ta-orleans","ta-poitiers","caa-nantes"}  # ressort de la CAA de Nantes (+ Rouen/Orléans/Poitiers hors CAA Nantes ? voir note)
RESSORT_NANTES={"ta-rennes","ta-nantes","ta-caen","ta-rouen"} | {"caa-nantes"}
raw={}
rows=list(csv.DictReader(open(f"{repo}/corpus/manifest.csv",encoding="utf-8")))
idx={x["fichier_opendata"].split("/")[1]:x for x in csv.DictReader(open(f"{repo}/corpus/index_decisions.csv",encoding="utf-8"))}
out=[]
H="""@prefix ant:  <https://kersalous.bzh/ontology/antenne#> .
@prefix dos:  <https://kersalous.bzh/dossier/> .
@prefix skt:  <https://kersalous.bzh/taxonomie/> .
@prefix src:  <https://kersalous.bzh/provenance/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix dcat: <http://www.w3.org/ns/dcat#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix note: <https://example.org/ontology/kai-internal-knowledge#> .

# ═══════════════════════════════════════════════════════════════
#  DÉCISIONS DU CORPUS (open data de la justice administrative)
#  Fichier GÉNÉRÉ par tools/corpus/build_decisions.py : ne pas modifier à la main.
#  Classement automatique (expressions régulières) sauf pour les décisions « lues » (corpus/lectures.csv).
#  Les particuliers sont pseudonymisés par les juridictions et ne figurent jamais ici.
# ═══════════════════════════════════════════════════════════════
src:opendata-justice-administrative a owl:NamedIndividual, src:JeuDeDonnees ;
    rdfs:label "Open data des décisions de la justice administrative"@fr ;
    dcat:accessURL "https://opendata.justice-administrative.fr"^^xsd:anyURI ;
    dcterms:publisher src:conseil-etat-publisher ; dcterms:license "Licence Ouverte 2.0" ;
    prov:generatedAtTime "2026-10-15"^^xsd:date ;
    note:note "Archives mensuelles de décisions du Conseil d'État (depuis 2021-06), des cours administratives d'appel (depuis 2022-03) et des tribunaux administratifs (depuis 2022-06). Copies locales dans corpus/decisions/, empreintes dans corpus/manifest.csv. Les décisions retenues sont celles qui parlent d'antenne-relais ou de pylône de téléphonie et d'urbanisme (filtre large, faux positifs possibles)." .

src:conseil-etat-publisher a owl:NamedIndividual, prov:Organization ;
    rdfs:label "Conseil d'État (justice administrative)"@fr .

src:DecisionOpenData a owl:Class ; rdfs:subClassOf prov:Entity ;
    rdfs:label "Décision publiée en open data"@fr .

"""
out.append(H)
juris={};assos={};avs={};stats=collections.Counter()
decs=[]
for r in rows:
    name=os.path.basename(r["fichier"]); x=idx[name]
    b=open(f"{repo}/{r['fichier']}",encoding="utf-8").read()
    txt=html.unescape(re.sub(r"<[^>]+>","\n",tag(b,"Texte_Integral") or b)); txt=re.sub(r"[ \t\u00a0]+"," ",txt); txt=re.sub(r"\n\s*\n+","\n",txt)
    low=txt
    niveau=r["niveau"]; stade=x["stade"]
    jid,jlab=juridiction(r["juridiction"],niveau); juris[jid]=jlab
    ev={c for c,rx in RX.items() if c in MOY and rx.search(low)}
    ctx=[c for c,rx in RX.items() if c in CTX and rx.search(low)]
    if "c-pylone-treillis" in ctx and "c-pylone" not in ctx: ctx.append("c-pylone")
    dist=distance(txt)
    if dist is not None: ctx.append("c-hab-50" if dist<50 else "c-hab-100" if dist<100 else "c-hab-300" if dist<300 else "c-hab-loin")
    mec=[c for c,rx in RX.items() if c in MECA and rx.search(low)]
    plaig=x["plaignant"]
    req={"particuliers/riverains":"q-riverains","association/collectif":"q-association","collectivité":"q-commune","opérateur/société pylônes":"q-operateur"}.get(plaig,"q-indetermine")
    acte={"opposition à DP":"a-opposition","non-opposition à DP":"a-non-opposition","permis de construire":"a-pc","retrait de non-opposition":"a-retrait","certificat de non-opposition":"a-certificat","raccordement":"a-autre","autre":"a-autre"}.get(x["acte"],"a-indetermine")
    if x["acte"]=="DP (sens ?)": acte="a-indetermine"
    voie="p-fond" if niveau=="TA" and stade=="fond" else "p-refere" if stade=="référé" and niveau=="TA" else "p-appel" if niveau=="CAA" else "p-cassation"
    sol=x["solution"]; res=resultat(sol,stade,x["issue"],niveau,txt[-1500:])
    eff=effet(x["issue"],plaig,sol)
    num=x["num"]
    _ok=(num not in DATES) or (r["date_lecture"] in DATES[num])
    ret,eca,tr=((LU.get(num) or PARTIEL.get(num)) if _ok else None) or ([],[],None)
    lu=(num in LU) and _ok; partiel=(num in PARTIEL) and _ok
    ecd=[]
    if not lu and not partiel and niveau in ("TA","CAA") and "r-rejet-fond" in res and "r-irrecevable" not in res and stade=="fond":
        mt=motifs(txt)
        if mt: ecd=sorted(c for c,rx in RX.items() if c in MOY and rx.search(mt))
    a=None; av={"requerant":[],"adverse":[]}
    req=requerant(txt,req)
    if req in ("q-riverains","q-indetermine","q-syndicat","q-association"):
        a=asso(txt)
        if a: req="q-association"
    if req=="q-association" and a is None: req="q-indetermine"
    av=avocats(txt)
    if a: req2=asso_type(a[1])
    d=dict(evoque=ev,ctx=ctx,acte=acte,req=[req],dist=dist,lu=lu or partiel,ressort=jid in RESSORT_NANTES)
    sc,why=proximite(d)
    prox="x-tres-proche" if sc>=75 else "x-proche" if sc>=50 else "x-eloigne" if sc>=25 else "x-non-pertinente"
    did=f"dec-{niveau.lower()}-{slug(num)}-{r['date_lecture'].replace('-','')}"
    reqs=[req]+([req2] if a else [])
    L=[f"dos:{did} a owl:NamedIndividual, ant:Jurisprudence ;",
       f"    rdfs:label {lit(jlab.replace('Tribunal administratif','TA').replace('Cour administrative d\'appel','CAA')+', '+r['date_lecture']+' — n° '+num)}@fr ;",
       f"    ant:reference {lit('n° '+num)} ; ant:dateDecision \"{r['date_lecture']}\"^^xsd:date ;",
       f"    ant:rendueParJuridiction dos:{jid} ;"]
    def add(prop,vals):
        if vals: L.append(f"    ant:{prop} "+", ".join(("skt:"+v) for v in vals)+" ;")
    add("niveauJuridiction",["j-premier" if niveau=="TA" else "j-appel" if niveau=="CAA" else "j-cassation"])
    add("voieDeDroit",[voie]); add("acteAttaque",[acte]); add("typeRequerant",reqs); add("resultat",res); add("effetProjet",[eff])
    add("moyenEvoque",sorted(ev)); add("moyenRetenu",ret); add("moyenEcarte",eca); add("moyenEcarteDeduit",ecd)
    add("contexteSite",ctx); add("mecanismeProcedural",mec)
    cf=commune_finistere(txt) if jid in ("ta-rennes","caa-nantes") else None
    if cf: L.append(f"    ant:communeLittorale skt:ll-{cf[0]} ; ant:statutLoiLittoral skt:ll-{cf[1]} ;"); stats["finistere"]+=1
    add("transferabilite",[tr] if tr else []); add("proximiteKersalous",[prox]); add("niveauLecture",["l-lu" if lu else "l-partiel" if partiel else "l-auto"])
    L.append(f"    ant:scoreProximite {sc} ; ant:detailScore {lit(why)} ;")
    if a:
        k="asso-"+slug(a[1])[:60]; assos[k]=a[1]; L.append(f"    ant:requerantNomme dos:{k} ;")
    for side,prop in (("requerant","avocatRequerant"),("adverse","avocatAdverse")):
        for nm in av[side]:
            k="avocat-"+slug(nm); avs[k]="Me "+nm; L.append(f"    ant:{prop} dos:{k} ;")
    if x["avocat_metadonnee_peu_fiable"]: L.append(f"    ant:avocatOpenData {lit(x['avocat_metadonnee_peu_fiable'])} ;")
    L.append(f"    prov:wasDerivedFrom src:{did} ; ant:verifieSurSource false .")
    out.append("\n".join(L)+"\n")
    out.append(f"src:{did} a owl:NamedIndividual, src:DecisionOpenData ;\n    rdfs:label {lit('Texte de la décision '+jlab+' n° '+num)}@fr ;\n    ant:cheminLocal {lit(r['fichier'])} ; ant:empreinteSha256 {lit(r['sha256'])} ;\n    ant:archiveOrigine \"{r['archive_url']}\"^^xsd:anyURI ; dcterms:isPartOf src:opendata-justice-administrative ;\n    dcterms:license \"Licence Ouverte 2.0\" ; prov:generatedAtTime \"{r['date_collecte']}\"^^xsd:date ;\n    note:note {lit('Membre de l’archive : '+r['membre_archive'])} .\n")
    stats["ecd"]+=bool(ecd); stats["partiel"]+=partiel; stats["n"]+=1; stats["asso"]+=bool(a); stats["av_req"]+=bool(av["requerant"]); stats["av_adv"]+=bool(av["adverse"]); stats["dist"]+=dist is not None
    stats[prox]+=1
    decs.append(dict(id=did,score=sc,prox=prox,res=res,eff=eff,req=reqs,ev=sorted(ev),asso=a,av=av))
out.append("# ── Juridictions ──")
for k,v in sorted(juris.items()): out.append(f"dos:{k} a owl:NamedIndividual, ant:Juridiction ; rdfs:label {lit(v)}@fr .")
out.append("\n# ── Associations et collectifs nommés dans les décisions ──")
for k,v in sorted(assos.items()): out.append(f"dos:{k} a owl:NamedIndividual, ant:Association ; rdfs:label {lit(v)}@fr .")
out.append("\n# ── Avocats nommés dans les décisions ──")
for k,v in sorted(avs.items()): out.append(f"dos:{k} a owl:NamedIndividual, ant:Avocat ; rdfs:label {lit(v)}@fr .")
open(f"{repo}/antenne-decisions.ttl","w",encoding="utf-8").write("\n".join(out)+"\n")
json.dump(decs,open(f"{repo}/corpus/classement.json","w",encoding="utf-8"),ensure_ascii=False)
print(dict(stats),len(juris),len(assos),len(avs))
