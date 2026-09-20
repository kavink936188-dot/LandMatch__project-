const $ = id => document.getElementById(id);
const me = requireRole("buyer");

const num = (id, mult = 1) => ($(id).value === "" ? null : +$(id).value * mult);
const clean = v => (v == null ? "" : +v.toFixed(2));

function describe(r) {
  const p = [];
  if (r.district) p.push(r.district);
  if (r.land_type) p.push(r.land_type);
  if (r.min_area_sqft != null || r.max_area_sqft != null)
    p.push(`${r.min_area_sqft != null ? fmtArea(r.min_area_sqft) : "any"} – ${r.max_area_sqft != null ? fmtArea(r.max_area_sqft) : "any"}`);
  if (r.min_price != null || r.max_price != null)
    p.push(`${r.min_price != null ? fmtPrice(r.min_price) : "₹0"} – ${r.max_price != null ? fmtPrice(r.max_price) : "any"}`);
  if (r.keywords) p.push(`“${r.keywords}”`);
  return p.map(x => `<span class="chip">${esc(x)}</span>`).join(" ");
}

async function loadReqs() {
  const reqs = await api("/buyers/requirements");
  $("reqs").innerHTML = reqs.length ? reqs.map(r => `
    <div class="list-item">
      <div class="top"><div class="reasons" style="margin:0">${describe(r)}</div>
        <div class="row"><button class="btn small" onclick="showMatches(${r.id})">Find matches</button>
        <button class="btn danger small" onclick="delReq(${r.id})">Delete</button></div></div>
      <div id="m-${r.id}" style="margin-top:14px"></div>
    </div>`).join("")
    : '<div class="empty">No requirements yet. Fill in the form, or tap the mic and describe what you want.</div>';
}

async function showMatches(id) {
  const box = $("m-" + id);
  box.innerHTML = '<p class="muted">Matching…</p>';
  try {
    const ms = await api(`/buyers/requirements/${id}/matches`);
    box.innerHTML = ms.length
      ? '<div class="cards" style="grid-template-columns:repeat(auto-fill,minmax(230px,1fr))">' + ms.map(m => landCard(m.land,
          `<div class="score" title="${m.score}% match"><i style="width:${m.score}%"></i></div>
           <strong style="font-size:.9rem">${m.score}% match</strong>
           <div class="reasons">${m.reasons.map(r => `<span class="chip">${esc(r)}</span>`).join("")}</div>`)).join("") + "</div>"
      : '<div class="empty">Nothing matches yet. We check again whenever you open this page, so new listings appear here.</div>';
  } catch (e) { box.innerHTML = ""; toast(e.message, true); }
}

async function delReq(id) {
  if (!confirm("Delete this requirement?")) return;
  try { await api(`/buyers/requirements/${id}`, { method: "DELETE" }); toast("Requirement deleted"); loadReqs(); } catch (e) { toast(e.message, true); }
}

$("req-form").onsubmit = async e => {
  e.preventDefault();
  const u = UNITS[$("unit").value];
  const body = {
    district: $("district").value || null, land_type: $("land_type").value || null,
    min_price: num("min_price", 1e5), max_price: num("max_price", 1e5),
    min_area_sqft: num("min_area", u), max_area_sqft: num("max_area", u),
    keywords: $("keywords").value.trim() || null,
  };
  try { await api("/buyers/requirements", { method: "POST", body }); toast("Requirement saved"); e.target.reset(); loadReqs(); }
  catch (err) { toast(err.message, true); }
};

// Voice: parse the sentence on the server, then fill the form so the buyer can review before saving.
function fillFromParsed(p) {
  if (p.district) $("district").value = p.district;
  if (p.land_type) $("land_type").value = p.land_type;
  if (p.min_price) $("min_price").value = clean(p.min_price / 1e5);
  if (p.max_price) $("max_price").value = clean(p.max_price / 1e5);
  const big = (p.max_area || p.min_area || 0) >= ACRE;
  $("unit").value = big ? "acre" : (p.max_area || p.min_area) ? "cent" : $("unit").value;
  const d = UNITS[$("unit").value];
  if (p.min_area) $("min_area").value = clean(p.min_area / d);
  if (p.max_area) $("max_area").value = clean(p.max_area / d);
  if (p.q) $("keywords").value = p.q;
}

if (me) {
  loadOptions({ el: $("district"), kind: "district", blank: "Any district" }, { el: $("land_type"), kind: "type", blank: "Any type" });
  initVoice({
    button: $("mic"), langSelect: $("lang"), onState: s => ($("voice-status").textContent = s),
    onText: async text => {
      try { const r = await api("/buyers/voice-search?q=" + encodeURIComponent(text) + "&limit=1"); fillFromParsed(r.parsed); toast("Form filled from your voice. Check it, then save."); }
      catch (e) { toast(e.message, true); }
    },
  });
  loadReqs().catch(e => toast(e.message, true));
}
