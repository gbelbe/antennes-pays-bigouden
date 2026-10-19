"""Statistiques par moyen sur la population de référence « cas proches » (pour le rapport PDF).
Population : décisions de TA ou de CAA où un tiers (riverain, association, syndicat, préfet) attaque une non-opposition ou un permis,
pour une antenne autre que sur toiture, avec une décision tranchée (hors désistement et non-lieu).
Usage : rapport_data.py <dépôt> -> /tmp/rapport_data.json"""
import sys,json,re,collections
repo=sys.argv[1]
C=json.load(open(f"{repo}/_site/data/corpus.json")); D=C["decisions"]
for _r in D: _r["id"]=_r["id"].replace("dos:",""); cs={c["id"]:c for c in C["concepts"]}
V={f"dec-ta-{re.sub(r'[^a-z0-9]+','-',v['num'].lower()).strip('-')}-{v['date'].replace('-','')}":(v["act"] if v["act"]!="inconnu" else v.get("first")) for v in json.load(open("/tmp/verif2.json")) if v["niveau"]=="TA"}
A2={f"dec-{v['niveau'].lower()}-{re.sub(r'[^a-z0-9]+','-',v['num'].lower()).strip('-')}-{v['date'].replace('-','')}":v["act"] for v in json.load(open("/tmp/appels2.json"))}
tiers={"skt:q-riverains","skt:q-association","skt:q-syndicat","skt:q-prefet","skt:q-asso-environnement","skt:q-asso-patrimoine","skt:q-collectif"}
pop=[]
for r in D:
    c=set(r["c"]); act=V.get(r["id"]) or A2.get(r["id"])
    fav= act=="favorable" or (act is None and ("skt:a-non-opposition" in c or "skt:a-pc" in c))
    if not fav or not (c&tiers) or (c&{"skt:r-desistement","skt:r-non-lieu"}): continue
    if "skt:c-toiture" in c and "skt:c-pylone" not in c: continue
    if r["id"].startswith("dec-ce"): continue
    pop.append(r)
gagne=[r for r in pop if any(x in r["c"] for x in("skt:r-annulation-totale","skt:r-annulation-partielle","skt:r-sursis","skt:r-suspension"))]
stats={}
for m in [k for k,v in cs.items() if v["scheme"]=="skt:Moyens"]:
    W=[r["id"] for r in pop if m in r["re"]]; L=[r["id"] for r in pop if m in r["ec"] or m in r["ed"]]
    stats[m]={"label":cs[m]["label"],"gagne":len(W),"juge":len(W)+len(L),"retenus":W,"ecartes":L}
json.dump({"pop":len(pop),"pop_gagnees":len(gagne),"stats":stats,"ids":[r["id"] for r in pop]},open("/tmp/rapport_data.json","w"),ensure_ascii=False)
print(len(pop),"décisions dans la population ;",len(gagne),"gagnées (annulation, suspension, sursis)")
for m,s in sorted(stats.items(),key=lambda kv:(-(kv[1]["gagne"]/kv[1]["juge"] if kv[1]["juge"] else 0),-kv[1]["juge"])):
    if s["juge"] and (s["gagne"]>0 or s["juge"]>=15): print(f"{m:30s} {s['gagne']:3d}/{s['juge']:3d}  {s['label'][:50]}")
