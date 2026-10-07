// D13 UT T.com 수집기 — target.com 탭에서 실행 (redsky API는 target.com 페이지 안에서만 호출됨)
// 사용: await UTCollect(["013-14-2826", ...이전 회차 DPCI]) → window.__UT 에 JSON 문자열 저장, 요약 반환
// 결과 행: [tcin, dpci, title, itemType, fabricName, material, regPrice, guestId, clearance(0/1), brand]
window.UTCollect = async function (prevDpcis) {
  const KEY = "9f36aeafbe60771e321a7cc95a78140772ab3e96";
  const vid = (document.cookie.match(/visitorId=([^;]+)/) || [])[1] || "";
  const base = "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2";
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const rows = new Map(), log = [];
  const strip = s => String(s || "").replace(/<[^>]*>/g, "").trim();
  const bullet = (bs, k) => { for (const b of bs || []) { const t = strip(b); if (t.toLowerCase().startsWith(k.toLowerCase() + ":")) return t.slice(k.length + 1).trim(); } return ""; };
  function emit(it, price, tcin, parent) {
    it = it || {}; const pit = (parent && parent.item) || {};
    const dpci = it.dpci || pit.dpci; if (!dpci) return;
    const pd = it.product_description || pit.product_description || {};
    const bs = pd.bullet_descriptions || (pit.product_description || {}).bullet_descriptions;
    const pr = price || (parent && parent.price) || {};
    const brand = ((it.primary_brand || pit.primary_brand || {}).name) || "";
    const g = (JSON.stringify(it.enrichment || pit.enrichment || {}).match(/GUEST_[0-9a-f-]{36}/) || [""])[0];
    const reg = pr.reg_retail || pr.reg_retail_max || pr.current_retail || pr.current_retail_max || 0;
    const clr = /clearance/i.test(pr.formatted_current_price_type || "") ? 1 : 0;
    const k = tcin + "|" + dpci;
    if (!rows.has(k)) rows.set(k, [String(tcin), dpci, strip(pd.title), ((it.product_classification || pit.product_classification || {}).item_type || {}).name || "", bullet(bs, "Fabric Name"), bullet(bs, "Material"), reg, g, clr, brand]);
  }
  async function page(params) {
    const q = new URLSearchParams(Object.assign({ key: KEY, channel: "WEB", count: 24, default_purchasability_filter: "false", include_sponsored: "false", platform: "desktop", pricing_store_id: "3991", visitor_id: vid }, params));
    const r = await fetch(base + "?" + q, { credentials: "omit" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json(), s = (j.data || {}).search || {};
    const ps = s.products || [];
    for (const p of ps) {
      if (p.children && p.children.length) p.children.forEach(c => emit(c.item, c.price, c.tcin || p.tcin, p));
      emit(p.item, p.price, p.tcin);
    }
    const tot = ((s.search_response || {}).typed_metadata || {}).total_results || ((s.search_response || {}).metadata || {}).total_results || 0;
    return { n: ps.length, tot };
  }
  async function sweep(label, params, maxPages) {
    let off = 0, got = 0, tot = 0;
    for (let i = 0; i < maxPages; i++) {
      let res; try { res = await page(Object.assign({ offset: off, page: params.category ? "/c/" + params.category : "/s/" + params.keyword }, params)); } catch (e) { log.push(label + " 오류 " + e.message); break; }
      got += res.n; tot = res.tot || tot; off += 24;
      if (!res.n || (tot && off >= tot)) break; await sleep(350);
    }
    log.push(label + ": " + got + "/" + tot);
  }
  await sweep("UT 여성", { category: "5xtd3Z1vs54" }, 40);
  await sweep("UT 브랜드", { category: "1vs54" }, 60);
  for (const kw of ["universal thread women knit", "universal thread women tee", "universal thread women tank", "universal thread sweatshirt", "universal thread knit dress", "universal thread pull-on"]) await sweep("검색 " + kw, { keyword: kw }, 10);
  const have = new Set([...rows.values()].map(r => r[1]));
  let looked = 0;
  for (const d of prevDpcis || []) { if (have.has(d)) continue; looked++; await sweep("DPCI " + d, { keyword: d }, 1); }
  const out = [...rows.values()].filter(r => /universal thread/i.test(r[9]) || !r[9]);
  window.__UT = JSON.stringify(out);
  return { rows: out.length, d013: out.filter(r => r[1].startsWith("013")).length, dpciLookups: looked, chars: window.__UT.length, log };
};
// 큰 결과는 나눠 읽기: UTChunk(0), UTChunk(1) ...
window.UTChunk = i => (window.__UT || "").slice(i * 12000, (i + 1) * 12000);
