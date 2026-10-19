"""Rapport PDF « quels moyens plaider à Kersalous ? » à partir du corpus de jurisprudence.
Usage : python3 tools/corpus/rapport.py <dépôt>   (après verif_victoires.py, appels.py, build_decisions.py, build_site.py, rapport_data.py)
Écrit rapports/moyens-kersalous.html puis, si Chrome est présent, rapports/moyens-kersalous.pdf."""
import sys,os,re,json,html,subprocess,datetime,collections
repo=sys.argv[1]
OUT=f"{repo}/rapports"; os.makedirs(OUT,exist_ok=True)
C=json.load(open(f"{repo}/_site/data/corpus.json")); META=json.load(open(f"{repo}/_site/data/meta.json"))
for r in C["decisions"]: r["id"]=r["id"].replace("dos:","")
D={r["id"]:r for r in C["decisions"]}
CS={c["id"].replace("skt:",""):c for c in C["concepts"]}
R=json.load(open("/tmp/rapport_data.json")); S={k.replace("skt:",""):v for k,v in R["stats"].items()}
POP=R["pop"]; GAG=R["pop_gagnees"]
MOIS=["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
def datefr(d): y,m,j=d.split("-"); return f"{int(j)}{'er' if int(j)==1 else ''} {MOIS[int(m)-1]} {y}"
def esc(s): return html.escape(str(s))
def pct(g,n): return f"{round(100*g/n)} %" if n else "—"
def stat(m):
    s=S.get("m-"+m) if not m.startswith("m-") else S.get(m)
    return s
def sg(*ms):
    W=set();L=set()
    for m in ms:
        s=S["m-"+m]; W|=set(s["retenus"]); L|=set(s["ecartes"])
    return len(W),len(W|L)
# ── annexe : numérotation par première citation ──
ANNEXE=collections.OrderedDict()
def cite(did):
    if did not in D: raise KeyError(did)
    if did not in ANNEXE: ANNEXE[did]=len(ANNEXE)+1
    n=ANNEXE[did]; return f'<a class="cite" href="#A{n}">[A{n}]</a>'
def cites(ids): return " ".join(cite(i) for i in ids)
def pick(m,kind,k,prefer_lu=True):
    s=S["m-"+m]; ids=s["retenus"] if kind=="g" else s["ecartes"]
    ids=[i for i in ids if i in D]
    if kind=="g": ids=sorted(ids,key=lambda i:D[i]["date"],reverse=True)
    else:
        def key(i):
            r=D[i]; lu=("skt:l-lu" in r["c"] or "skt:l-partiel" in r["c"])
            return (-int(lu and prefer_lu),-r["score"],r["date"])
        ids=sorted(ids,key=key)
    return ids[:k]
def N(*ms):
    g,n=sg(*ms); return f"dans {g} des {n}"
def box(m,label=None):
    g,n=sg(*m) if isinstance(m,(list,tuple)) else sg(m)
    w=0 if not n else 100*g/n
    return (f'<div class="chiffre"><div class="big">{g} / {n}</div><div class="lib">décisions où le moyen a été retenu, '
            f'sur celles où il a été jugé, hors abandon ({pct(g,n)})</div>'
            f'<div class="bar"><i style="width:{min(100,w*3):.0f}%"></i></div></div>')
def etapes(lst): return "<ol class='etapes'>"+"".join(f"<li>{x}</li>" for x in lst)+"</ol>"
def p(x): return f"<p>{x}</p>"

# ── contenu : partie A ──
A=[]
def add_A(titre,ms,base,ce,steps,juge,kers,regul,gk=3,ek=2,tag="oui"):
    A.append(dict(titre=titre,ms=ms,base=base,ce=ce,steps=steps,juge=juge,kers=kers,regul=regul,gk=gk,ek=ek,tag=tag))

add_A("Raccordement électrique du pylône",["desserte"],"Article L.111-11 du code de l'urbanisme",
 "Si le raccordement exige des travaux sur le réseau public d'électricité (ou d'eau), l'autorité qui instruit doit pouvoir dire dans quel délai et par quelle collectivité ou quel concessionnaire ils seront faits. Sinon elle doit refuser ; pour une déclaration préalable, elle doit s'opposer.",
 ["<b>Obtenir la déclaration préalable complète</b> (pièces DP1 à DP8) et la décision de non-opposition. Tout le reste en dépend.",
  "<b>Chercher comment le pylône est alimenté</b> : plan de masse, notice, mention d'un raccordement Enedis, d'une extension de réseau ou d'un poste de transformation.",
  "<b>Mesurer la distance au réseau</b> le plus proche (plan des réseaux demandé à la mairie ou au gestionnaire). À La Gouesnière l'extension était de 408 m ; à Bouc-Bel-Air le poste était à une centaine de mètres.",
  "<b>Regarder ce que la mairie savait</b> : avis du gestionnaire, engagement écrit de l'opérateur de payer, démarches auprès du syndicat d'énergie du département. Si une extension est nécessaire et que rien n'établit qui la réalise et quand, le moyen est sérieux.",
  "<b>Le plaider avec des pièces</b> (courrier au maire, réponse du gestionnaire) et prévoir qu'il puisse être régularisé."],
 "Retenu à La Gouesnière, dans le ressort de Kersalous : le tribunal de Rennes a suspendu la déclaration en octobre 2025 puis l'a annulée en mars 2026, le maire n'ayant fait aucune démarche auprès du syndicat d'énergie pour une extension de 408 m. Retenu aussi à Bouc-Bel-Air (raccordement non précisé) et, en appel, à Lyon (un engagement de payer « en cas d'extension » est trop vague). Écarté quand l'arrêté met le coût du raccordement à la charge de l'opérateur ou quand le gestionnaire a été consulté.",
 "Le dossier ne dit rien de l'alimentation électrique. C'est le moyen le plus ouvert : il dépend d'un fait que personne n'a encore vérifié.",
 "Oui : un arrêté complémentaire visant l'avis du gestionnaire et l'engagement de l'opérateur suffit. Le moyen retarde plus qu'il ne tue le projet.",gk=5)

add_A("Clôture du poste technique",["regle-cloture"],"Règlement de la zone A du PLU",
 "Le règlement fixe souvent la hauteur et la nature des clôtures (1,50 m, 1,80 m, mailles ou passages pour la petite faune). Le poste technique d'une antenne est entouré d'un grillage de 2 m.",
 ["<b>Lire l'article du règlement de la zone A sur les clôtures</b> (mairie ou Géoportail de l'urbanisme).",
  "<b>Relever la clôture dans la déclaration</b> : hauteur, matériau, longueur. Le dossier mentionne une « zone clôturée ».",
  "<b>Distinguer clôture et séparation interne</b> : un grillage qui protège l'ouvrage à l'intérieur de la parcelle n'est pas toujours une clôture (Guiclan), mais l'est du côté qui donne sur l'extérieur (Douai).",
  "<b>Comparer</b>. Un dépassement est une règle précise, facile à prouver sur pièces.",
  "<b>Mesurer l'effet</b> : annulation partielle, 3 à 6 mois pour régulariser. C'est un levier de retard, pas d'abandon."],
 "C'est le motif précis du PLU le plus souvent retenu : clôture de 2 m au-delà du maximum du règlement (1,50 m à Verrens-Arvey, 1,80 m à Fégréac, 1,60 m en Haute-Savoie), grillage sans mailles progressives à Toutainville, et en appel à Douai et à Lyon. Le juge annule la clôture seulement et laisse régulariser.",
 "La clôture du poste technique n'est pas connue : à lire dans les pièces de la déclaration, puis à comparer au règlement de la zone A.",
 "Oui, presque toujours (annulation partielle, L.600-5).",gk=6)

add_A("Accès à la parcelle",["acces"],"Règlement du PLU (accès) ; article R.423-53 du code de l'urbanisme",
 "Un terrain doit avoir un accès à une voie publique ou privée, et un nouvel accès sur une route départementale ou communale exige la consultation du gestionnaire de la voirie. Le règlement du PLU fixe aussi des règles d'accès.",
 ["<b>Repérer l'accès sur le plan de masse</b> : existant ou à créer, sur quelle voie, de quelle largeur.",
  "<b>Vérifier que le terrain a un accès légal</b> (voie publique, passage sur fonds voisin) : un terrain enclavé est inconstructible.",
  "<b>Contrôler la consultation du gestionnaire de voirie</b> si l'accès donne sur une route départementale.",
  "<b>Écarter si l'accès existe déjà</b> : c'est ce qui a fait échouer le moyen à Pluguffan."],
 "Retenu à Saint-Cyr-en-Talmondais (nouvel accès sur la RD 45, règle de consultation du gestionnaire non respectée, annulation partielle) et à Sainte-Rose en Guadeloupe (terrain enclavé, sursis pour régulariser). Écarté quand l'accès est déjà en place.",
 "Le tracé de l'accès n'est pas encore vérifié sur le plan de masse.",
 "Oui (annulation partielle ou accord du gestionnaire).",gk=4)

add_A("Haies, talus protégés et plantations",["regle-plantations"],"Article 6 du PLU de Plonéour-Lanvern (éléments paysagers) ; L.151-23 ; articles du règlement sur les plantations",
 "À Plonéour-Lanvern, toute suppression de haie ou de talus protégé exige une déclaration distincte, examinée par une commission créée par le maire. Deux linéaires protégés (121 m et 183 m) touchent la parcelle. Le règlement de la zone peut aussi imposer des plantations (haies, arbres) sur les limites.",
 ["<b>Superposer le tracé de l'accès et de la plateforme</b> avec les haies et talus protégés de la carte du dossier.",
  "<b>Demander au service urbanisme</b> si une déclaration distincte pour l'arasement a été déposée.",
  "<b>Lire l'article du règlement sur les plantations</b> et regarder si le projet en prévoit.",
  "<b>Écarter si aucun arasement n'est nécessaire</b> : à Pluguffan, le moyen a échoué parce que l'accès passait par une ouverture existante."],
 "Plantations retenues à Genas (limites de parcelle non plantées), à Saint-Nicolas-de-Redon et à Pont-de-Metz (arbres ou arbustes prévus par le règlement). Le moyen du talus a échoué à Pluguffan, la déclaration n'étant pas incomplète puisque l'accès existait.",
 "Deux linéaires protégés (121 m et 183 m) touchent la parcelle ; l'arasement éventuel est à vérifier sur le plan de masse.",
 "Oui (annulation partielle, nouvelle déclaration ou plantations ajoutées).",gk=3)

add_A("Plan de prévention des risques et zone humide",["risques-naturels","zone-humide"],"Plan de prévention des risques ; règlement du PLU ; L.151-23",
 "Un plan de prévention des risques (inondation, incendie) interdit ou limite les constructions dans ses zones, avec souvent une exception pour les équipements publics que les antennes d'opérateurs privés ne remplissent pas. Une zone humide protégée par le PLU peut aussi limiter les travaux.",
 ["<b>Consulter Géorisques et le PLU</b> pour savoir si la parcelle est dans une zone inondable ou couverte par un plan de prévention des risques.",
  "<b>Regarder le classement de la zone humide</b> à 8 m : inventaire communal, règlement du PLU. Une proximité ne suffit pas, il faut une règle opposable ou une atteinte démontrée.",
  "<b>Examiner la piste d'accès et l'évacuation des eaux pluviales de la dalle</b> : c'est là que l'atteinte peut se jouer.",
  "<b>Si un plan de prévention s'applique</b>, lire son tableau des constructions admises : une antenne n'est pas un « réseau public ».",
  "<b>Faire vérifier par un hydrologue</b> si la zone humide est en jeu : le juge se fonde sur des éléments circonstanciés."],
 "Retenu à Guichen, en Ille-et-Vilaine : zone rouge du plan de prévention des inondations de la Vilaine, annulation par le tribunal de Rennes puis confirmation par la cour de Nantes en 2025 (c'est l'affaire de l'avis du Conseil d'État sur l'emprise). Retenu aussi à Nice (incendie), à Marseillan et à Lyon (dalle sous la cote de référence). Écarté quand le projet est surélevé et non clôturé (Latresne).",
 "La zone humide est à 8 m de la parcelle. On ignore si un plan de prévention des risques s'applique : à vérifier.",
 "Non en général : une construction interdite par le plan ne se régularise pas, sauf déplacement.",gk=5,ek=3)

add_A("Servitudes particulières : emplacement réservé et captage d'eau",["emplacement-reserve","captage"],"PLU (L.151-41) ; arrêté préfectoral de protection d'un captage",
 "Un emplacement réservé destine la parcelle à un autre usage public (parking, voie) ; un périmètre de protection d'un captage d'eau potable interdit certaines constructions. Dans les deux cas l'antenne est illégale quelle que soit sa qualité.",
 ["<b>Ouvrir le plan de zonage du PLU</b> sur Géoportail de l'urbanisme et la liste des emplacements réservés : la parcelle YX 26 en porte-t-elle un ?",
  "<b>Interroger la mairie et l'agence régionale de santé</b> sur un périmètre de captage à proximité.",
  "<b>Rien à plaider si les deux réponses sont négatives</b> : la vérification prend dix minutes."],
 "Emplacement réservé retenu à Châteauneuf-Grasse (parking, TA de Nice 2025) et à Saint-Just (projet de déviation, suspension de la déclaration de Phoenix en 2026). Captage retenu à Rethondes (périmètre de protection, non régularisable).",
 "Le dossier ne mentionne ni emplacement réservé ni captage, mais cela n'a pas été vérifié sur le zonage.",
 "Non pour l'emplacement réservé et le captage (changer de terrain).",gk=4)

add_A("Qualité du pétitionnaire",["qualite-petitionnaire"],"Articles R.423-1 et R.431-35 du code de l'urbanisme",
 "Le demandeur doit être propriétaire du terrain, son mandataire, ou attester sur l'honneur y être autorisé par lui. Le maire ne vérifie pas les titres : il ne refuse qu'en cas de fraude ou si le demandeur n'a manifestement aucun droit.",
 ["<b>Identifier le propriétaire de la parcelle YX 26</b> (cadastre, demande au service de publicité foncière).",
  "<b>Lire l'attestation de la déclaration</b> et le contrat ou la promesse qui lie l'opérateur au propriétaire.",
  "<b>Chercher une anomalie</b> : propriétaire erroné, indivision, parcelle du domaine communal, espaces communs d'un lotissement.",
  "<b>Se limiter aux faits établis</b> : sans anomalie, le moyen est écarté (droit des tiers).",
  "<b>Le plaider en référé</b> si l'anomalie est établie : c'est là qu'il a été retenu."],
 "Retenu seulement en référé : à Beuvry la commune reconnaît s'être trompée sur sa qualité de propriétaire (TA de Lille, 2026) ; à Talmont-Saint-Hilaire les droits sur les espaces communs d'un lotissement étaient douteux (TA de Nantes, 2024). Écarté partout ailleurs.",
 "Le dossier prévoit de rencontrer le propriétaire et de demander au service de publicité foncière de Quimper des renseignements sur le terrain. Rien n'est établi à ce jour.",
 "Oui si l'opérateur obtient ensuite l'accord du propriétaire.",gk=3)

add_A("Compétence du signataire",["competence"],"Délégation de fonctions et de signature du maire",
 "L'arrêté doit être signé par le maire ou par un adjoint ou un agent disposant d'une délégation suffisamment précise et publiée.",
 ["<b>Obtenir l'arrêté ou le certificat de non-opposition</b> et lire le nom du signataire.",
  "<b>Demander l'arrêté de délégation</b> et la preuve de sa publication ou de son affichage.",
  "<b>Vérifier sa précision</b> : une délégation « urbanisme » couvre les déclarations préalables ; une délégation vague, non.",
  "<b>Garder le moyen en réserve</b> : facile à vérifier, il se règle par un nouvel arrêté signé du bon signataire."],
 "Retenu à Vallons-de-l'Erdre (sursis à statuer, la commune régularise) ; aussi à Achy dans une décision hors de cette population. Écarté dans la plupart des décisions : les délégations sont presque toujours suffisantes.",
 "La décision attaquable n'est pas encore bien identifiée (déclaration du 18 août ou renouvellement) ; à contrôler une fois l'arrêté ou le certificat obtenu.",
 "Oui (régularisation par le maire).",gk=3)

add_A("Hauteur et recul du règlement de la zone A",["regle-hauteur","regle-implantation"],"Règlement de la zone A du PLU",
 "Le règlement peut limiter la hauteur des constructions et imposer un recul par rapport aux voies et aux limites séparatives.",
 ["<b>Lire les articles hauteur et implantation de la zone A.</b>",
  "<b>Comparer avec le projet</b> : 30 m (32,65 m avec les antennes), pylône à environ 4 m du bord de la parcelle.",
  "<b>Regarder l'exception pour les équipements d'intérêt collectif</b> : certains règlements les dispensent de la règle de hauteur (cour de Toulouse, Rousson) ; d'autres l'appliquent aux antennes (Montferrier-sur-Lez, Teyran).",
  "<b>Compter sur une annulation partielle</b> et un délai de régularisation."],
 "Hauteur retenue à Montferrier-sur-Lez et à Teyran (35,5 m contre 10 m). Recul retenu à Beaumont-lès-Valence (10 m de l'alignement, confirmé en appel). Le moyen échoue quand le règlement exempte les équipements collectifs.",
 "Aucune de ces règles n'a encore été lue pour Plonéour-Lanvern. Le pylône est à environ 4 m du bord de la parcelle : le recul est à regarder en premier.",
 "Souvent pour le recul (déplacement) ; la hauteur est plus difficile à corriger.",gk=5)

add_A("Pièces du dossier contradictoires",["pieces-contradictoires"],"Décision fondée sur des faits matériellement inexacts",
 "Si les pièces de la déclaration se contredisent sur un fait qui compte (hauteur, emprise, position), l'administration a décidé sur des données inexactes.",
 ["<b>Lister les hauteurs</b> données par chaque pièce : avis de dépôt, panneau, plan de coupe, notice, dossier d'information.",
  "<b>Ne retenir que les pièces de la déclaration elle-même</b> : 30 m sur le panneau et 32,65 m dans le dossier d'information de l'opérateur ne suffisent pas, c'est la déclaration qui compte.",
  "<b>Faire constater l'écart</b> par un constat de commissaire de justice si la contradiction porte sur la position ou la hauteur sur place.",
  "<b>Envisager un référé</b> : l'unique cas gagné l'a été en référé, avec urgence présumée."],
 "Retenu une seule fois : TA de Nîmes (référé du 11 septembre 2026) a suspendu une déclaration de Phoenix France Infrastructure dont les pièces se contredisaient sur la hauteur du pylône. Écarté dans toutes les autres décisions, souvent faute de contradiction réelle.",
 "L'écart 30 m / 32,65 m existe entre le panneau et le dossier d'information, pas encore entre les pièces de la déclaration. À vérifier dès que le dossier est obtenu.",
 "Oui (nouvelle déclaration corrigée).",gk=2,ek=3)

add_A("Zone agricole : les conditions de l'article A du PLU",["zone-agri-naturelle"],"Règlement de la zone A, article A I-2 §3",
 "En zone agricole, les équipements d'intérêt collectif ne sont admis que s'ils ne sont pas incompatibles avec l'activité agricole de l'unité foncière et ne portent pas atteinte aux espaces naturels et aux paysages. Deux conditions cumulatives.",
 ["<b>Lire le texte exact</b> de l'article A et de son préambule. Les annulations viennent de la rédaction locale du PLU.",
  "<b>Établir l'usage agricole réel</b> de la parcelle (3 440 m²) et de l'unité foncière : exploitée, louée, en friche ?",
  "<b>Montrer l'atteinte au paysage</b> : covisibilité directe avec le manoir, habitations à 23 m, 32 m et 32 m, haies protégées.",
  "<b>Chercher la condition d'impératif technique</b> : certains PLU exigent de prouver qu'aucun autre emplacement n'est possible.",
  "<b>Garder en tête que le juge admet en général l'antenne comme équipement d'intérêt collectif</b> ; il faut donc un fait précis pour renverser."],
 f"Retenu {N('zone-agri-naturelle')} décisions où il a été jugé : à Amiens, où l'antenne n'est pas un « équipement public » et n'est admise que si un impératif technique justifie son emplacement ; à Bordeaux, où le PLU modifié interdisait toute construction en zone N. Écarté presque partout (Pluguffan, Guiclan, La Gouesnière, cour de Toulouse à Rousson).",
 "C'est le moyen central du dossier, mais le moins prometteur statistiquement. Il ne vaut que par un fait précis sur l'usage agricole ou par une rédaction particulière du PLU.",
 "Non si le terrain est reconnu agricole ; oui si le règlement est corrigé.",gk=3,ek=3)

add_A("Insertion dans le paysage et covisibilité",["paysage","covisibilite"],"Article R.111-27 du code de l'urbanisme",
 "Le projet peut être refusé s'il porte atteinte au caractère ou à l'intérêt des lieux avoisinants, aux sites, aux paysages. Le juge ne retient que l'erreur manifeste d'appréciation.",
 ["<b>Rassembler des vues</b> prises depuis les habitations et le manoir : photographies datées, photomontages, vue aérienne.",
  "<b>Qualifier le paysage</b> : environnement exceptionnel (site, espaces naturels), bâti remarquable, ou paysage rural ordinaire.",
  "<b>Comparer au projet</b> : pylône treillis de 30 m, aucune insertion particulière.",
  "<b>Utiliser ce moyen en renfort</b> : il ne gagne presque jamais seul, mais il complète un moyen précis.",
  "<b>Associer l'association Sites et Monuments ou l'UDAP</b> pour un avis sur la covisibilité avec le manoir."],
 f"Retenu {N('paysage')} décisions jugées (paysage) et {N('covisibilite')} (covisibilité) : Biot en référé (environnement de golf et d'espaces naturels, mais rejeté au fond), Roscoff, Beyrie-sur-Joyeuse. Un pylône treillis entouré de végétation passe presque toujours.",
 "La covisibilité avec le manoir est directe d'après le dossier, mais la parcelle est à 163 m du périmètre des abords et le manoir à 648 m : moyen de renfort, jamais autonome.",
 "Non en général (vice de fond).",gk=3,ek=2)

add_A("Dossier de déclaration incomplet",["dossier-incomplet"],"Articles R.431-35 à R.431-37 et R.431-10 du code de l'urbanisme",
 "Les pièces d'une déclaration préalable sont limitativement listées. Une insuffisance n'annule que si elle a faussé l'appréciation de l'administration.",
 ["<b>Comparer la déclaration à la liste des pièces</b> exigées.",
  "<b>Examiner les photomontages</b> : montrent-ils le pylône sur toute sa hauteur et les constructions voisines ?",
  "<b>Relever les omissions réelles</b> (plan coté, insertion, accès), pas les imprécisions.",
  "<b>Ne le plaider qu'en renfort</b> : une victoire seulement sur près de cent décisions."],
 f"Retenu {N('dossier-incomplet')} décisions où il a été jugé : Dammarie-les-Lys (cour de Paris, 2025), où les photomontages ne montraient ni les maisons voisines ni le pylône en entier ; la régularisation n'a pas suffi. Presque toujours écarté.",
 "Les pièces DP1 à DP8 n'ont pas encore été obtenues dans leur intégralité : à contrôler.",
 "Oui en principe (nouveaux photomontages).",gk=2,ek=3)

APPL_T={"Raccordement électrique du pylône":"à vérifier dans la déclaration","Clôture du poste technique":"à vérifier (règlement de la zone A)","Accès à la parcelle":"à vérifier (plan de masse)",
 "Haies, talus protégés et plantations":"à vérifier (plan de masse, PLU)","Plan de prévention des risques et zone humide":"à vérifier (plan de risques, zone humide)","Servitudes particulières : emplacement réservé et captage d'eau":"à vérifier sur le zonage",
 "Qualité du pétitionnaire":"à établir (propriétaire)","Compétence du signataire":"à vérifier (arrêté)","Hauteur et recul du règlement de la zone A":"à vérifier (règlement)","Pièces du dossier contradictoires":"à vérifier (pièces)",
 "Zone agricole : les conditions de l'article A du PLU":"central, peu prometteur","Insertion dans le paysage et covisibilité":"en renfort","Dossier de déclaration incomplet":"en renfort"}
def _rate(a):
    g,n=sg(*a["ms"]); return (-(g/n if n else 0),-n)
A.sort(key=_rate)
# ── partie B : sans réussite dans les cas proches ──
B1=[
 ("Emprise des locaux techniques et seuil de 20 m²",["emprise-locaux"],"Écarté dans toutes les décisions. L'avis du Conseil d'État du 21 mars 2024 (n° 490536, lu à la source) précise que seules comptent les locaux et installations techniques, pas les pylônes : un massif béton de 31 m² a été jugé sans effet (Nantes), une dalle enterrée de 25 m² aussi (Biot).","La fondation de 29,16 m² relève du pylône et ne compte donc très probablement pas ; la dalle technique fait 2 m²."),
 ("Ondes, santé et principe de précaution",["ondes"],"Écarté partout : la police des ondes appartient à l'État et aucun élément circonstancié n'est apporté. Le moyen décrédibilise les autres.","À ne pas invoquer."),
 ("Dossier d'information du maire (L.34-9-1 du code des postes)",["dim"],"Écarté comme inopérant (indépendance des législations) : il relève du droit des communications électroniques, pas de l'urbanisme. Le décret du 3 mai 2002 sur l'exposition suit le même sort.","Utile politiquement et pour le calendrier (le maire demande à l'opérateur de renouveler sa demande), pas devant le juge."),
 ("Sécurité et salubrité publiques (R.111-2)",["r111-2"],"Écarté sauf cas locaux (incendie dans le Var, cyclones aux Antilles). Un risque de chute du pylône sans élément concret ne suffit pas (Pluguffan).","Sans objet en l'état."),
 ("Mutualisation, choix d'un autre site et utilité de l'antenne",["mutualisation","utilite"],"Aucune obligation légale de partage de site ni de rechercher un autre emplacement ; la couverture et l'intérêt général ne sont pas des motifs de légalité d'une déclaration.","À ne pas invoquer. La comparaison de couverture reste utile pour la discussion avec la mairie."),
 ("Affichage et délais de recours",["affichage","delai-recours","notification"],"Écarté dans tous les cas où il a été jugé : un affichage irrégulier n'annule pas l'autorisation, il empêche seulement le délai de courir.","Utile pour le calendrier : numéro de dossier discordant sur le panneau (DP 000139 contre 00122), mention « permis de construire », surface laissée vide. Délai de recours au plus tard le 14 décembre 2026."),
 ("Délai d'instruction, retrait de la décision, pouvoirs de police du maire",["delai-instruction","retrait","police-maire"],"Aucune victoire d'un tiers. Le retrait d'une non-opposition à une antenne est interdit (article 222 de la loi ELAN) : il joue en faveur de l'opérateur.","Si la mairie retirait ou faisait renouveler sa décision, ce serait un risque pour nous, pas un moyen."),
 ("Espace boisé classé, Natura 2000, droit des tiers, fraude",["ebc","natura","droits-tiers","fraude"],"Écartés partout : un espace boisé classé à 34 m n'est pas touché par le projet, les zonages d'inventaire ne protègent pas du pylône, le droit de propriété est réservé, la fraude n'est pas établie.","À ne pas invoquer sans fait nouveau (par exemple abattage d'arbres dans l'espace boisé)."),
 ("Zone urbaine, aspect extérieur, site protégé",["zone-urbaine","regle-aspect","patrimoine"],"Rarement retenus : règles d'aspect propres à certains PLU (toitures, immeubles) ou sites patrimoniaux, qui ne correspondent pas à un pylône en zone agricole.","Sans objet ici."),
]
B2=[
 ("Loi Littoral",["littoral-urbanisation","littoral-espaces"],f"C'est le moyen qui gagne le plus (retenu {N('littoral-urbanisation')} décisions où il est jugé), mais seulement pour les communes littorales. Plonéour-Lanvern n'est pas dans la liste officielle des 121 communes littorales du Finistère (DDTM 29, vérifiée le 15 octobre 2026) ; ses voisines Plomeur, Saint-Jean-Trolimon, Plovan, Pouldreuzic et Pont-l'Abbé le sont."),
 ("Constructibilité limitée (règlement national d'urbanisme, loi Montagne)",["rnu","montagne"],"Elle s'applique aux communes sans PLU ou de montagne ; Plonéour-Lanvern a un PLU et n'est pas en montagne."),
 ("Permis de construire à titre précaire",["permis-precaire"],"Moyen propre à des antennes installées sur le domaine public avec un permis précaire (Trouville-sur-Mer) ; sans objet pour une déclaration préalable sur terrain privé."),
 ("Risque d'incendie de forêt",["incendie"],"Retenu dans le Var au contact de massifs boisés sans point d'eau ; peu transférable en Finistère."),
 ("Abords d'un monument historique, avis de l'architecte des Bâtiments de France",["abords-mh-pc","abf","hauteur-12m"],"Pour que le pylône de plus de 12 m exige un permis, il doit être dans les abords du monument et en covisibilité avec lui. La parcelle est à 163 m du périmètre délimité des abords et le manoir à 648 m, au-delà de 500 m : la condition n'est probablement pas remplie. Trois tribunaux ont pourtant annulé pour ce motif (Le Vigan, Mont-Saint-Jean, Fourques), sans régularisation possible à Dijon. À faire confirmer par l'UDAP avant de l'abandonner."),
]

# ── construction du HTML ──
def row_synth(rank,titre,ms,appl):
    g,n=sg(*ms); return f"<tr><td>{rank}</td><td>{esc(titre)}</td><td class='num'>{g} / {n}</td><td class='num'>{pct(g,n)}</td><td>{esc(appl)}</td></tr>"
APPL={0:"à vérifier dans la déclaration",1:"à vérifier (règlement de la zone A)",2:"à vérifier (plan de masse)",3:"à vérifier (plan de risques, zone humide)",4:"à vérifier sur le zonage",5:"à établir (propriétaire)",6:"à vérifier (arrêté)",7:"à vérifier (règlement)",8:"à vérifier (pièces)",9:"central, peu prometteur",10:"en renfort",11:"en renfort"}
syn="".join(row_synth(i+1,a["titre"],a["ms"],APPL_T.get(a["titre"],"")) for i,a in enumerate(A))
partA=""
for i,a in enumerate(A,1):
    gids=[];
    for m in a["ms"]: gids+=pick(m,"g",a["gk"])
    gids=list(dict.fromkeys(gids))[:a["gk"]+2]
    eids=[]
    for m in a["ms"]: eids+=pick(m,"e",a["ek"])
    eids=list(dict.fromkeys(eids))[:a["ek"]+1]
    chiffres="".join(box(m) for m in ([a["ms"][0]] if len(a["ms"])==1 else a["ms"]))
    if len(a["ms"])>1:
        names="".join(f"<div class='sub'>{esc(S['m-'+m]['label'])}</div>"+box(m) for m in a["ms"])
        chiffres=names
    partA+=f"""<section class="moyen"><h3>A{i}. {esc(a['titre'])}</h3>
<div class="base">{esc(a['base'])}</div>{chiffres}
<p>{esc(a['ce'])}</p>
<h4>Étape par étape</h4>{etapes(a['steps'])}
<h4>Ce qu'ont fait les juges</h4>{p(esc(a['juge']))}
<p class="cas"><b>Cas où le moyen a été retenu :</b> {cites(gids) if gids else 'aucun'}<br><b>Cas où il a été écarté :</b> {cites(eids) if eids else 'aucun'}</p>
<h4>Situation à Kersalous</h4>{p(esc(a['kers']))}
<p class="regul"><b>Régularisable ?</b> {esc(a['regul'])}</p></section>"""
partB1=""
for t,ms,why,kers in B1:
    g,n=sg(*ms); eids=[]
    for m in ms: eids+=pick(m,"e",2)
    eids=list(dict.fromkeys(eids))[:3]
    partB1+=f"""<section class="moyen petit"><h3>{esc(t)}</h3><div class="mini"><b>{g} / {n}</b> retenu(s) sur les décisions où le moyen a été jugé, hors abandon ({pct(g,n)})</div>
<p>{esc(why)}</p><p class="kers"><b>À Kersalous :</b> {esc(kers)}</p><p class="cas"><b>Cas écartés :</b> {cites(eids) if eids else 'aucun'}</p></section>"""
partB2=""
for t,ms,why in B2:
    g,n=sg(*ms); gids=[]
    for m in ms: gids+=pick(m,"g",3)
    gids=list(dict.fromkeys(gids))[:4]
    eids=[]
    for m in ms: eids+=pick(m,"e",1)
    eids=list(dict.fromkeys(eids))[:2]
    partB2+=f"""<section class="moyen petit"><h3>{esc(t)}</h3><div class="mini"><b>{g} / {n}</b> retenu(s) sur les décisions où le moyen a été jugé, hors abandon ({pct(g,n)})</div>
<p>{esc(why)}</p><p class="cas"><b>Cas retenus :</b> {cites(gids) if gids else 'aucun'} &nbsp; <b>Cas écartés :</b> {cites(eids) if eids else 'aucun'}</p></section>"""

# ── annexe ──
OPS=["Free","Orange","Bouygues","SFR","Cellnex","Hivory","ATC","Totem","TDF","Phoenix","Towercast","On Tower","Axians","Telco"]
def meta_dec(did):
    r=D[did]; t=open(f"{repo}/{r['path']}",encoding="utf-8").read()
    t=html.unescape(re.sub(r"<[^>]+>"," ",t)); t=re.sub(r"\s+"," ",t)
    m=re.search(r"(?:maire|commune|conseil municipal|ville|préfet(?:e)? )\s*(?:de la commune |de la ville )?(?:d[’']|de |du |des |de l[’'])\s?([A-ZÉÈ][\w’'\-]+(?: [A-ZÉÈ][\w’'\-]+){0,3})",t[:6000])
    commune=m.group(1) if m else ""
    commune=re.sub(r"\s+(?:a|ne|s|et|le|la|du|de)$","",commune)
    ops=[o for o in OPS if re.search(r"\b"+re.escape(o)+r"\b",t[:6000])]
    return commune,ops
def label_c(ids):
    return ", ".join(CS[i.replace("skt:","")]["label"].split(" (")[0] for i in ids)
RES={"skt:r-annulation-totale":"annulation","skt:r-annulation-partielle":"annulation partielle","skt:r-sursis":"sursis à statuer","skt:r-suspension":"suspension","skt:r-rejet-fond":"rejet","skt:r-rejet-doute":"rejet en référé","skt:r-rejet-manifeste":"rejet par ordonnance","skt:r-irrecevable":"irrecevable","skt:r-appel-confirme":"jugement confirmé","skt:r-appel-infirme":"jugement infirmé"}
ann=""
for did,n in ANNEXE.items():
    r=D[did]; commune,ops=meta_dec(did)
    res=", ".join(RES[x] for x in r["c"] if x in RES)
    req=next((CS[x.replace('skt:','')]["label"] for x in r["c"] if x.startswith("skt:q-")),"")
    ret=label_c([x for x in r["re"]]); ec=label_c([x for x in (r["ec"]+r["ed"])][:6])
    lu="lue" if "skt:l-lu" in r["c"] else "lue en partie" if "skt:l-partiel" in r["c"] else "classement automatique"
    ann+=f"""<div class="ann" id="A{n}"><div class="ahead"><b>A{n}</b> · {esc(r['court'])}, {datefr(r['date'])}, {esc(r['ref'])}</div>
<div class="ameta">{esc(commune)}{' · ' if commune else ''}{esc(', '.join(ops))}{' · ' if ops else ''}{esc(req)} · {esc(res)} · {lu}</div>
{('<div class="ameta"><b>Moyens retenus :</b> '+esc(ret)+'</div>') if ret else ''}{('<div class="ameta"><b>Moyens écartés :</b> '+esc(ec)+'</div>') if ec else ''}
<div class="alinks"><a href="{esc(r['url'])}">Texte de la décision (copie dans le dépôt)</a> · <a href="{esc(r['zip'])}">Archive officielle du mois</a></div></div>"""

today=datetime.date.today()
CSS="""@page{size:A4;margin:18mm 16mm 18mm 16mm;@bottom-center{content:"Kersalous — moyens à plaider · page " counter(page);font:8pt Helvetica,Arial,sans-serif;color:#667}}
body{font:10pt/1.45 -apple-system,Helvetica,Arial,sans-serif;color:#1c2430}
h1{font-size:22pt;margin:0 0 4pt}h2{font-size:15pt;margin:20pt 0 6pt;border-bottom:2px solid #1570ef;padding-bottom:3pt;page-break-after:avoid}
h3{font-size:12pt;margin:14pt 0 3pt;page-break-after:avoid}h4{font-size:10pt;margin:8pt 0 2pt;color:#1570ef;page-break-after:avoid}
a{color:#1155cc;text-decoration:none}a.cite{font-weight:600;white-space:nowrap}
.sub{margin:6pt 0 0;font-weight:600;font-size:9pt}.lead{font-size:11pt;color:#334}
.warn{background:#fff4e5;border:1px solid #f0b86e;padding:7pt 9pt;border-radius:4pt;margin:8pt 0;font-size:9pt}
table{border-collapse:collapse;width:100%;font-size:8.5pt;margin:6pt 0}th,td{border-bottom:1px solid #d8dde6;padding:3pt 4pt;text-align:left;vertical-align:top}th{background:#f2f5fa}.num{text-align:right;white-space:nowrap}
.chiffre{display:flex;align-items:center;gap:10pt;background:#f2f6ff;border-radius:4pt;padding:5pt 8pt;margin:4pt 0}.big{font-size:17pt;font-weight:700;color:#1570ef;min-width:62pt}.lib{font-size:8.5pt;color:#445;flex:1}
.bar{width:90pt;height:7pt;background:#dfe6f3;border-radius:4pt;overflow:hidden}.bar i{display:block;height:100%;background:#1570ef}
.base{font-size:8.5pt;color:#667;margin-bottom:2pt}.moyen{page-break-inside:avoid-page}.petit{margin-bottom:8pt}.mini{font-size:9pt;color:#334}
ol.etapes{margin:2pt 0 4pt 16pt;padding:0}ol.etapes li{margin:1.5pt 0}.cas{font-size:9pt;color:#334}.regul{font-size:9pt}.kers{font-size:9.5pt}
.ann{border-left:3px solid #1570ef;padding:3pt 8pt;margin:5pt 0;page-break-inside:avoid;font-size:8.5pt}.ahead{font-size:9pt}.ameta{color:#445}.alinks{margin-top:1pt}
.cover{padding-top:40pt}.sub2{font-size:12pt;color:#445}.meta{font-size:9pt;color:#667;margin-top:10pt}
"""
htmldoc=f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Kersalous : quels moyens plaider ?</title><style>{CSS}</style></head><body>
<div class="cover"><h1>Antenne de Kersalous (Plonéour-Lanvern)<br>Quels moyens plaider ?</h1>
<div class="sub2">Ce que montrent {format(len(C['decisions']),',').replace(',','\u202f')} décisions de justice administrative sur des antennes-relais, ramené au cas de Kersalous</div>
<p class="meta">Déclaration préalable DP 029 174 26 00122 · Phoenix France Infrastructures pour Bouygues Telecom · pylône treillis de 30 m (32,65 m avec les antennes) · parcelle YX 26, zone A du PLU<br>
Document de travail du {datefr(today.isoformat())}. Données : open data de la justice administrative (Licence Ouverte 2.0), collectées le 15 octobre 2026 ; site : {esc('https://gbelbe.github.io/antennes-pays-bigouden/')}</p>
<div class="warn"><b>Ce document n'est pas un avis juridique.</b> Les chiffres sont un repère statistique : ils ne prédisent pas l'issue d'un recours précis. Les décisions ont été classées en partie automatiquement ; seules {sum(1 for r in C['decisions'] if 'skt:l-lu' in r['c'] or 'skt:l-partiel' in r['c'])} ont été lues. Tout moyen doit être vérifié sur les pièces de la déclaration et validé par un avocat en droit de l'urbanisme avant d'être invoqué.</div></div>

<h2>L'essentiel</h2>
<ul>
<li><b>{pct(GAG,POP)} des recours de tiers gagnent.</b> Sur {POP} décisions où un tiers (riverain, association, syndicat, préfet) attaque l'autorisation d'une antenne hors toiture, hors désistement, {GAG} ont abouti à une annulation, une suspension ou un sursis à statuer.</li>
<li><b>Ce qui gagne tient à une règle écrite et vérifiable sur pièces</b> : servitudes particulières, raccordement électrique, clôture, accès, plan de prévention des risques, signataire. Ce sont aussi des vices souvent régularisables : ils retardent plus qu'ils ne tuent le projet.</li>
<li><b>Ce qui ne gagne presque jamais est général</b> : santé, utilité, information du maire, seuil de 20 m², mutualisation, paysage.</li>
<li><b>Le moyen le plus efficace ailleurs, la loi Littoral, ne s'applique pas ici</b> : Plonéour-Lanvern n'est pas dans la liste officielle des communes littorales.</li>
<li><b>Le délai de recours expire au plus tard le 14 décembre 2026</b>, plus tôt si un constat d'affichage est antérieur au 14 octobre.</li></ul>
<h3>Classement des moyens à étudier</h3>
<table><tr><th>#</th><th>Moyen</th><th class="num">Retenu / jugé</th><th class="num">Taux</th><th>État à Kersalous</th></tr>{syn}</table>
<p class="cas">« Retenu / jugé » : nombre de décisions où le juge a accueilli le moyen, sur celles où il l'a examiné (retenu ou écarté), hors désistement et non-lieu. Population : {POP} décisions de tribunaux administratifs et de cours d'appel. Un moyen examiné dans le même arrêt que d'autres peut ne pas être le motif décisif.</p>

<h2>Feuille de route</h2>
<ol class="etapes">
<li><b>Sécuriser le délai et la décision.</b> Obtenir la décision de non-opposition (ou le certificat) et le numéro exact du dossier (00122 ou 000139), la date de pose du panneau et la copie du constat de commissaire de justice. Le délai de recours de deux mois court à partir de l'affichage régulier sur le terrain.</li>
<li><b>Obtenir la déclaration complète</b> (pièces DP1 à DP8) auprès du service urbanisme.</li>
<li><b>Vérifier les moyens de la partie A</b> dans l'ordre du classement du tableau ci-dessus.</li>
<li><b>Consulter un avocat en droit de l'urbanisme</b> avec ce document et les pièces, sans attendre la fin du délai.</li>
<li><b>Déposer le recours</b> avec les moyens retenus et le notifier à la commune et à l'opérateur dans les quinze jours (obligation à peine d'irrecevabilité).</li>
<li><b>Examiner un référé-suspension</b> : l'urgence est présumée contre une autorisation d'urbanisme, mais ses conditions de délai sont à valider avec l'avocat.</li></ol>

<h2>Méthode et limites</h2>
<p><b>Population de référence.</b> Décisions de tribunaux administratifs et de cours d'appel dans lesquelles un tiers (riverain, association, syndicat de copropriétaires, préfet) attaque une non-opposition ou un permis relatif à une antenne autre que sur une toiture, avec une décision tranchée : les désistements et non-lieux, c'est-à-dire les abandons, sont exclus. Le requérant et l'acte attaqué sont lus dans le texte des décisions et vérifiés par deux signaux indépendants (voir corpus/VERIFICATION.md).</p>
<p><b>« Retenu » et « jugé ».</b> Un moyen est « retenu » quand le juge l'accueille, « jugé » quand il l'a accueilli ou écarté. Les moyens retenus ont été lus à la main dans les {sum(1 for r in C['decisions'] if 'skt:l-lu' in r['c'] or 'skt:l-partiel' in r['c'])} décisions lues. Les moyens écartés sont lus ou déduits : dans un rejet complet de la requête, tout moyen discuté dans les motifs est écarté. Les référés rejetés sans motivation détaillée n'apportent pas de moyen écarté.</p>
<p><b>Limites.</b> Les décisions publiées en open data seulement (depuis 2022) ; les taux dépendent de l'identification automatique des moyens ; de petits effectifs donnent des pourcentages fragiles (un seul cas gagné sur une soixantaine fait 2 %). Les références d'articles viennent de ma connaissance du droit et ne sont pas relues à la source.</p>

<h2>Partie A : les moyens les plus intéressants</h2>
<p class="lead">Classés du plus au moins prometteur d'après le taux de victoire observé dans les cas proches (retenu sur jugé, une décision comptée une fois). Les effectifs sont petits : un taux élevé sur une dizaine de décisions pèse moins qu'un taux plus bas sur plusieurs dizaines. Ce qu'on sait du dossier est indiqué pour chaque moyen. Chaque moyen indique les étapes de vérification, ce que les juges ont décidé et les cas cités (liens vers l'annexe).</p>
{partA}

<h2>Partie B : les moyens qui ont le moins de chances de porter</h2>
<h3>B1. Moyens jamais ou presque jamais retenus dans les cas proches</h3>
{partB1}
<h3>B2. Moyens efficaces ailleurs, sans objet à Kersalous</h3>
{partB2}

<h2>Annexe : décisions citées</h2>
<p class="cas">{len(ANNEXE)} décisions. Chaque référence renvoie à la copie du texte conservée dans le dépôt public (<a href="{esc('https://github.com/gbelbe/antennes-pays-bigouden')}">github.com/gbelbe/antennes-pays-bigouden</a>) et à l'archive mensuelle de l'open data de la justice administrative d'où elle provient. Les noms de particuliers sont pseudonymisés par les juridictions. La commune et les opérateurs sont repérés automatiquement dans le texte et peuvent être inexacts : se reporter au texte de la décision.</p>
{ann}
</body></html>"""
path=f"{OUT}/moyens-kersalous.html"; open(path,"w",encoding="utf-8").write(htmldoc)
print("HTML écrit :",path,"; annexe :",len(ANNEXE),"décisions")
chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if os.path.exists(chrome):
    pdf=f"{OUT}/moyens-kersalous.pdf"
    for _ in range(3):   # Chrome headless échoue parfois au premier essai
        r=subprocess.run([chrome,"--headless=new","--disable-gpu","--no-pdf-header-footer",f"--print-to-pdf={pdf}",f"file://{path}"],capture_output=True,timeout=180)
        if r.returncode==0: break
    print("PDF écrit :",pdf,os.path.getsize(pdf)//1024,"Ko")
