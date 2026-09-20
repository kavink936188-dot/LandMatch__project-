const $ = id => document.getElementById(id);
const me = requireRole("seller");

const STATUS_TEXT = {
  approved: "Live", pending: "In review", rejected: "Rejected", sold: "Sold",
};

async function load() {
  const lands = await api("/lands/mine");
  const count = s => lands.filter(l => l.status === s).length;
  $("stats").innerHTML = ["approved", "pending", "rejected", "sold"]
    .map(s => `<div class="stat"><b>${count(s)}</b>${STATUS_TEXT[s]}</div>`).join("");

  if (!lands.length) { $("mine").innerHTML = '<div class="empty">No listings yet. Fill in the form to post your first land.</div>'; return; }
  $("mine").innerHTML = lands.map(l => `
    <div class="list-item" id="land-${l.id}">
      <div class="top"><h3 style="margin:0"><a href="land.html?id=${l.id}">${esc(l.title)}</a></h3>
        <span class="chip status-${l.status}">${STATUS_TEXT[l.status]}</span></div>
      <p class="loc" style="margin:4px 0">${esc([l.village, l.district].filter(Boolean).join(", "))} · ${fmtArea(l.area_sqft)} · ${fmtPrice(l.price)}</p>
      ${l.status === "pending" ? '<p class="hint">An admin is checking this listing. It usually takes a day or less.</p>' : ""}
      ${l.status === "rejected" ? `<p class="hint" style="color:var(--danger)">Rejected${l.admin_note ? ": " + esc(l.admin_note) : ""}. Fix the issue and post it again.</p>` : ""}
      <p class="hint demand" data-id="${l.id}"></p>
      <div class="row">
        ${l.status === "approved" ? `<button class="btn ghost small" onclick="markSold(${l.id})">Mark as sold</button>` : ""}
        <button class="btn danger small" onclick="removeLand(${l.id})">Delete</button>
      </div>
    </div>`).join("");

  document.querySelectorAll(".demand").forEach(async el => {
    const land = lands.find(l => l.id == el.dataset.id);
    if (land.status !== "approved") return;
    try {
      const d = await api(`/lands/${land.id}/demand`);
      el.textContent = d.interested_buyers
        ? `${d.interested_buyers} buyer${d.interested_buyers > 1 ? "s are" : " is"} looking for land like this (best match ${d.best_score}%).`
        : "No buyer requirements match this land yet.";
    } catch { /* ignore */ }
  });
}

async function markSold(id) {
  if (!confirm("Mark this land as sold? It will disappear from search.")) return;
  try { await api(`/lands/${id}/sold`, { method: "POST" }); toast("Marked as sold"); load(); } catch (e) { toast(e.message, true); }
}
async function removeLand(id) {
  if (!confirm("Delete this listing and its files? This can't be undone.")) return;
  try { await api(`/lands/${id}`, { method: "DELETE" }); toast("Listing deleted"); load(); } catch (e) { toast(e.message, true); }
}

$("price").addEventListener("input", () => { const v = +$("price").value; $("price-hint").textContent = v ? "= " + fmtPrice(v) : ""; });

$("locate").onclick = () => {
  if (!navigator.geolocation) return toast("Location isn't available in this browser.", true);
  navigator.geolocation.getCurrentPosition(
    p => { $("latitude").value = p.coords.latitude.toFixed(6); $("longitude").value = p.coords.longitude.toFixed(6); toast("Location filled in"); },
    () => toast("Couldn't read your location. Allow location access or enter it manually.", true));
};

$("land-form").onsubmit = async e => {
  e.preventDefault();
  const fd = new FormData();
  ["title", "land_type", "district", "village", "survey_number", "address", "description"].forEach(k => fd.append(k, $(k).value));
  fd.append("area_sqft", (+$("area").value * UNITS[$("unit").value]).toFixed(2));
  fd.append("price", $("price").value);
  if ($("latitude").value) fd.append("latitude", $("latitude").value);
  if ($("longitude").value) fd.append("longitude", $("longitude").value);
  [...$("images").files].forEach(f => fd.append("images", f));
  [...$("documents").files].forEach(f => fd.append("documents", f));

  const btn = $("submit-btn"); btn.disabled = true; btn.textContent = "Uploading…";
  try {
    const land = await api("/lands", { method: "POST", form: fd });
    toast(land.status === "approved" ? "Listing is live" : "Submitted. An admin will review it shortly.");
    e.target.reset(); $("price-hint").textContent = "";
    load();
  } catch (err) { toast(err.message, true); }
  finally { btn.disabled = false; btn.textContent = "Submit listing"; }
};

if (me) {
  loadOptions({ el: $("district"), kind: "district" }, { el: $("land_type"), kind: "type" }).then(() => { $("district").value = "Tiruppur"; });
  load().catch(e => toast(e.message, true));
}
