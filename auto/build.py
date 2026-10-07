#!/usr/bin/env python3
"""D13 UT T.com 자동 수집 → report.html / index.html 갱신.

사용: python3 build.py --raw raw.json --repo <저장소 폴더> --date 2026-10-19 [--dry]
raw.json = collect.js 결과 (행 목록: [tcin, dpci, title, itemType, fabricName, material, regPrice, guestId, clearance, brand])
같은 달 회차가 이미 있으면 그 회차를 최신 수집으로 갱신(vendor·VN 등 수동 정보는 유지)하고, 없으면 새 회차를 추가합니다.
"""
import argparse, json, re, os, sys, collections

ap = argparse.ArgumentParser()
ap.add_argument("--raw", required=True)
ap.add_argument("--repo", required=True)
ap.add_argument("--date", required=True)
ap.add_argument("--rules", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json"))
ap.add_argument("--dry", action="store_true")
ap.add_argument("--summary", default="summary.json")
A = ap.parse_args()

RU = json.load(open(A.rules, encoding="utf-8"))
OV = RU.get("overrides", {})
raw = json.load(open(A.raw, encoding="utf-8"))
RID = A.date[:7]

# ---------- report.html 읽기 ----------
rp = os.path.join(A.repo, "report.html")
S = open(rp, encoding="utf-8").read()
j = S.index("const DATA=") + len("const DATA=")
DATA, n = json.JSONDecoder().raw_decode(S[j:])
R = DATA["R"]
VO = {}
vp = os.path.join(A.repo, "vendors.json")
if os.path.exists(vp):
    try: VO = json.load(open(vp, encoding="utf-8"))
    except Exception: VO = {}
vk = lambda x: (x.get("d") or "") + "|" + x["p"]
for r in R:  # 사이트에서 수정한 Vendor 반영
    m = VO.get(r["id"], {})
    for x in r["items"]:
        if vk(x) in m: x["v"] = m[vk(x)]

# ---------- 분류 함수 ----------
low = lambda s: (s or "").lower()
has = lambda s, words: any(w in s for w in words)
nm = lambda p: re.sub(r"[^a-z0-9]", "", re.sub(r"^women[’'`]?s\b", "", low(p).strip()))
d5 = lambda d: re.sub(r"\D", "", d or "")[:5]

def fibers(mat):
    out = {}
    for pct, name in re.findall(r"(\d+)%\s*([A-Za-z ]+)", mat or ""):
        out[low(name).strip()] = out.get(low(name).strip(), 0) + int(pct)
    return out

def is_knit(title, itype, fab, mat):
    t, ty, f = low(title), low(itype), low(fab)
    if has(ty, RU["exclude_types"]): return False, "타입:" + itype
    if has(t, RU["exclude_name"]): return False, "상품명 제외어"
    if has(f, RU["woven_fabrics"]): return False, "우븐/스웨터 원단:" + fab
    fb = fibers(mat)
    rv = sum(v for k, v in fb.items() if has(k, ["rayon", "viscose", "lyocell"]))
    if rv >= RU["rayon_woven_threshold"] and not any(has(k, ["spandex", "elastane", "modal"]) for k in fb):
        return False, "레이온 %d%% (우븐 간주)" % rv
    if has(f, RU["knit_fabrics"]): return True, ""
    if not f and has(t, RU["knit_name_fallback"]): return True, "원단명 없음·상품명으로 판단"
    return False, "니트 근거 없음:" + (fab or "원단명 없음")

def cat(title, itype):
    t, ty = low(title), low(itype)
    if has(ty, ["dress", "jumpsuit", "romper"]) or has(t, ["dress", "jumpsuit", "romper"]): return "D"
    if has(ty, ["pant", "short", "skirt", "legging", "jogger", "bottom"]) or has(t, ["pant", "short", "skirt", "legging", "jogger", "sweatpant"]): return "B"
    return "T"

def program(title, dpci, c):
    t = low(title)
    if c in "BD": return "L"
    cls = re.sub(r"\D", "", dpci)[3:5]
    if cls in RU["leisure_classes"] or has(t, RU["leisure_name"]): return "L"
    core = has(t, RU["core_words"]) and not has(t, RU["fashion_words"])
    if has(t, ["tank", "cami"]): return "CT" if core else "FT"
    if not core: return "FT"
    return "CL" if has(t, ["long sleeve"]) else "CS"

# ---------- 수집 행 → 스타일 ----------
seen, kept, dropped = set(), [], []
for row in raw:
    tcin, dpci, title, itype, fab, mat, reg, guest, clr = row[:9]
    if not dpci or not dpci.startswith(RU["dpci_prefix"]) or (tcin, dpci) in seen: continue
    seen.add((tcin, dpci))
    o = OV.get(dpci, {})
    ok, why = is_knit(title, itype, fab, mat)
    if o.get("exclude"): ok, why = False, "사용자 제외"
    if o.get("keep"): ok = True
    (kept if ok else dropped).append(dict(tcin=tcin, d=dpci, p=title, it=itype, fab=fab, mat=mat, r=reg, g=guest, clr=clr, why=why))

groups = collections.OrderedDict()
for x in kept:
    groups.setdefault((nm(x["p"]), d5(x["d"])), []).append(x)

# 이전 회차 인덱스 (이번 달 회차 제외)
prev_rounds = [r for r in R if r["id"] < RID]
same_month = next((r for r in R if r["id"] == RID), None)
def find_prev(key, dpcis, rounds):
    """같은 이름 + DPCI 앞5자리. 여러 개면 DPCI가 겹치는 것 → 가장 최근 회차 우선."""
    hits = [(i, x) for i, r in enumerate(rounds) for x in r["items"] if (nm(x["p"]), d5(x.get("d"))) == key]
    if not hits: return None
    exact = [h for h in hits if h[1].get("d") in dpcis]
    return max(exact or hits, key=lambda h: h[0])[1]

items, review = [], []
for key, vs in groups.items():
    dps = sorted({v["d"] for v in vs})
    pv = find_prev(key, dps, prev_rounds)
    sm = find_prev(key, dps, [same_month]) if same_month else None
    base = sm or pv
    d = base["d"] if base and base.get("d") in dps else dps[0]
    v0 = next(v for v in vs if v["d"] == d)
    c = (base or {}).get("c") or cat(v0["p"], v0["it"])
    if c not in "TBD": c = cat(v0["p"], v0["it"])
    s = (base or {}).get("s") or program(v0["p"], d, c)
    it = {"p": v0["p"], "d": d, "c": c, "g": RU["dpci_prefix"], "s": s,
          "f": ", ".join(x for x in [v0["fab"], v0["mat"]] if x),
          "u": "https://www.target.com/p/-/A-" + v0["tcin"]}
    regs = [v["r"] for v in vs if v["r"]]
    if regs: it["r"] = max(regs) if max(regs) != int(max(regs)) else int(max(regs))
    if v0["g"]: it["iu"] = "https://target.scene7.com/is/image/Target/" + v0["g"] + "?wid=600&hei=750&fmt=webp&fit=crop"
    elif base and base.get("iu"): it["iu"] = base["iu"]
    if any(v["clr"] for v in vs): it["clr"] = 1
    vend = (sm or {}).get("v") or (pv or {}).get("v") or OV.get(d, {}).get("v")
    if vend: it["v"] = vend
    for k in ("vn", "fp"):
        if sm and sm.get(k): it[k] = sm[k]
    if pv:
        if pv.get("d") and pv["d"] != d: it["q"] = pv["d"]
        elif pv.get("q"): it["q"] = pv["q"]
    elif not OV.get(d, {}).get("not_new") and not any(OV.get(x, {}).get("not_new") for x in dps):
        it["t"] = "n"
    if not base: review.append(f'{it["p"]} ({d}) → {({"CT":"Core Tank","CS":"Core SS","CL":"Core LS","FT":"Fashion Top","L":"Leisure"})[s]} 자동 분류')
    items.append(it)

ord_ = lambda x: ("KLD".index("K" if x["s"] in ("CT","CS","CL","FT") else "L"), "TBD".index(x["c"]), ["CT","CS","CL","FT","L"].index(x["s"]) if x["s"] in ["CT","CS","CL","FT","L"] else 9, x["p"])
items.sort(key=ord_)

if len(items) < 30:
    sys.exit(f"중단: 수집된 니트 스타일이 {len(items)}개뿐입니다 (수집 오류 가능성). 사이트를 바꾸지 않았습니다.")

# 이번 업데이트에서 처음 나온 NEW (같은 달 갱신 시, 직전 업데이트에는 없던 것)
_old = {(nm(x["p"]), d5(x.get("d"))) for x in (same_month or {"items": []})["items"]}
fresh = [x for x in items if x.get("t") == "n" and (nm(x["p"]), d5(x["d"])) not in _old]

# 단종(이전 회차에 있었는데 이번에 없는 것)
last = prev_rounds[-1] if prev_rounds else None
cur_keys = {(nm(x["p"]), d5(x["d"])) for x in items}
_dk = set()
drop = [{k: x.get(k) for k in ("p", "d", "c", "v", "r") if x.get(k) is not None} for x in (last["items"] if last else []) if (nm(x["p"]), d5(x.get("d"))) not in cur_keys and not (vk(x) in _dk or _dk.add(vk(x)))]

rnd = {"id": RID, "base": False,
       "cmp": f'{last["id"] if last else "-"} 대비 · NEW=이전 전체 회차에 없던 스타일 · T.com 자동 수집({A.date}) · DPCI {RU["dpci_prefix"]} + 니트 원단 (클리어런스 포함) · 가격: T.com 정가 · Vendor: 이전 회차·사이트 수정값 승계',
       "auto": True, "items": items, "drop": drop}
if same_month: R[R.index(same_month)] = rnd
else: R.append(rnd)

# vendors.json 의 이번 달 수정값은 key(d|p)가 같으면 페이지가 계속 적용함 → 별도 처리 불필요

GK = lambda x: "K" if x["s"] in ("CT","CS","CL","FT") else "L"
st = dict(id=RID, all=len(items), nw=sum(x.get("t") == "n" for x in items),
          k=sum(GK(x) == "K" for x in items), kn=sum(GK(x) == "K" and x.get("t") == "n" for x in items),
          l=sum(GK(x) == "L" for x in items), ln=sum(GK(x) == "L" and x.get("t") == "n" for x in items),
          d=0, sae=sum(x.get("v") == "Sae-A" for x in items), auto=True)

summary = dict(round=RID, date=A.date, replaced=bool(same_month), stats=st,
               new=[f'{x["p"]} ({x["d"]}) {x.get("v","Vendor 미기재")}' for x in items if x.get("t") == "n"],
               new_since_last_update=[f'{x["p"]} ({x["d"]}) {x.get("v","Vendor 미기재")}' for x in fresh],
               dropped_styles=[f'{x["p"]} ({x.get("d","")})' for x in drop],
               no_vendor=[f'{x["p"]} ({x["d"]})' for x in items if not x.get("v")],
               auto_program=review,
               excluded_013=[f'{x["p"]} ({x["d"]}) — {x["why"]}' for x in dropped],
               raw_rows=len(raw))
json.dump(summary, open(A.summary, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if A.dry:
    print(json.dumps(st, ensure_ascii=False)); sys.exit(0)

# ---------- 쓰기 ----------
S2 = S[:j] + json.dumps(DATA, ensure_ascii=False, separators=(",", ":")) + S[j + n:]
S2 = re.sub(r"2026-01 ~ \d{4}-\d{2}|(\d{4}-\d{2}) ~ \d{4}-\d{2}(?=</p>)", lambda m: m.group(0)[:10] + RID, S2, count=1)
open(rp, "w", encoding="utf-8").write(S2)

ip = os.path.join(A.repo, "index.html")
I = open(ip, encoding="utf-8").read()
m = re.search(r"const TCOM = \[\n(.*?)\n\];", I, re.S)
rows = [l for l in m.group(1).split("\n") if l.strip()]
line = "  {id:\"%s\", all:%d, nw:%d, k:%d, kn:%d, l:%d, ln:%d, d:0, sae:%d, auto:true}" % (RID, st["all"], st["nw"], st["k"], st["kn"], st["l"], st["ln"], st["sae"])
rows = [l.rstrip(",") for l in rows if f'id:"{RID}"' not in l]
rows.insert(0, line)
I = I[:m.start(1)] + ",\n".join(rows) + I[m.end(1):]
open(ip, "w", encoding="utf-8").write(I)
print(json.dumps(st, ensure_ascii=False))
