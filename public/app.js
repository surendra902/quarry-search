/* Public API dashboard. Never interpret API/source strings as HTML. */
(() => {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const text = (value, fallback = "Unknown") => value === null || value === undefined || value === ""
    ? fallback : typeof value === "object" ? JSON.stringify(value) : String(value);
  const count = (value) => Number.isInteger(value) && value >= 0 ? String(value) : "Unknown";
  const element = (tag, value, className) => {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = text(value);
    if (className) node.className = className;
    return node;
  };
  const status = (id, message, tone = "") => {
    const node = byId(id);
    node.textContent = message;
    node.className = `status ${tone}`;
  };

  function safeLink(value) {
    const label = text(value);
    try {
      // Absolute HTTP(S) only: reject javascript:, data:, and relative URLs.
      const url = new URL(label);
      if (!["http:", "https:"].includes(url.protocol)) throw new Error("Unsafe URL");
      const link = element("a", label);
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      return link;
    } catch (_) {
      return element("span", label);
    }
  }

  function addRow(parent, key, value, link = false) {
    const row = element("div", undefined, "result-row");
    const content = element("span", undefined, "result-val");
    content.append(link ? safeLink(value) : document.createTextNode(text(value)));
    row.append(element("span", key, "result-key"), content);
    parent.append(row);
  }

  function evidenceLabel(record) {
    if (record.evidence_kind === "direct_match") return "Direct source match";
    if (record.evidence_kind === "archive_match") return "Archived source match — not a live-page check";
    if (record.evidence_kind === "candidate_only") return "Candidate only — unresolved";
    return "Legacy / unverified — unresolved";
  }

  function recordDetails(record) {
    const block = element("div", undefined, "evidence-record");
    addRow(block, "Referral code", record.referral_code);
    addRow(block, "Referral URL", record.url, true);
    addRow(block, "Evidence", evidenceLabel(record));
    addRow(block, "Observed source", record.source_url, true);
    addRow(block, "Platform", record.platform);
    addRow(block, "Author", record.author);
    addRow(block, "Source publication time", record.published_at);
    addRow(block, "Source update time", record.source_updated_at);
    addRow(block, "Timestamp basis", record.timestamp_basis);
    addRow(block, "Collector observation", record.observed_at || record.discovered_at);
    if (record.last_seen_at) addRow(block, "Last observed", record.last_seen_at);
    if (Number.isInteger(record.occurrence_count)) addRow(block, "Stored occurrence count", record.occurrence_count);
    addRow(block, "Evidence snippet", record.evidence_snippet);
    addRow(block, "Reported status (unverified)", record.status);
    addRow(block, "Redemption", "Unknown — not validated by this dashboard");
    return block;
  }

  function sourceReports(reports) {
    const details = element("details");
    details.append(element("summary", "Source reports and coverage"));
    details.append(element("p", "Unavailable, blocked, or failed sources are not evidence of no match. Reports cover only the sources queried by this request.", "note"));
    const entries = isObject(reports) ? Object.entries(reports) : [];
    if (!entries.length) {
      details.append(element("p", "No per-source report supplied. Coverage is unknown.", "note"));
      return details;
    }
    const list = element("ul", undefined, "report-list");
    for (const [name, report] of entries) {
      const item = element("li");
      item.append(element("strong", name));
      if (isObject(report)) {
        for (const [key, value] of Object.entries(report)) addRow(item, key, value);
      } else {
        item.append(element("p", report));
      }
      list.append(item);
    }
    details.append(list);
    return details;
  }

  async function request(path, { method = "GET", controller = new AbortController() } = {}) {
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 120000);
    try {
      const response = await fetch(path, { method, signal: controller.signal, headers: { Accept: "application/json" }, cache: "no-store" });
      let data;
      try { data = await response.json(); }
      catch (_) { throw new Error(`HTTP ${response.status}: unreadable JSON response`); }
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${text(data && data.error, "Request failed")}`);
      if (isObject(data) && data.error) throw new Error(text(data.error));
      return data;
    } catch (error) {
      if (timedOut) throw new Error("Request timed out. Coverage and outcome are unknown; retry when the service is available.");
      throw error;
    } finally { clearTimeout(timer); }
  }

  function tableMessage(message) {
    const row = element("tr");
    const cell = element("td", message);
    cell.colSpan = 5;
    row.append(cell);
    byId("tableBody").replaceChildren(row);
  }

  function renderTable(records) {
    if (!records.length) { tableMessage("No stored records returned."); return; }
    const rows = records.map((record) => {
      const row = element("tr");
      const code = element("td");
      code.append(element("span", record.referral_code, "code-tag"));
      const source = element("td");
      source.append(element("p", record.platform), safeLink(record.source_url));
      const evidence = element("td");
      evidence.append(element("p", evidenceLabel(record)), element("p", "Redemption: unknown", "note"));
      const timestamp = element("td");
      timestamp.append(element("p", record.published_at), element("p", `Basis: ${text(record.timestamp_basis)}`, "note"));
      const more = element("td");
      const details = element("details");
      details.append(element("summary", `Details: ${text(record.referral_code)}`), recordDetails(record));
      more.append(details);
      row.append(code, source, evidence, timestamp, more);
      return row;
    });
    byId("tableBody").replaceChildren(...rows);
  }

  async function loadLinks() {
    status("linksStatus", "Loading stored records…");
    try {
      const records = await request("/api/links");
      if (!Array.isArray(records) || !records.every(isObject)) throw new Error("Unexpected links response.");
      renderTable(records);
      status("linksStatus", `${records.length} stored records displayed from this response. The API may limit this list; total counts are reported above.`);
    } catch (error) {
      tableMessage("Stored records unavailable. This is not an empty database result.");
      status("linksStatus", `Could not load stored records. ${error.message}`, "error");
    }
  }

  async function loadStatus() {
    status("serviceStatus", "Loading service status…");
    try {
      const data = await request("/api/status");
      if (!isObject(data) || !isObject(data.storage) || !isObject(data.collector) || !Array.isArray(data.sources)) throw new Error("Unexpected status response.");
      byId("statCount").textContent = count(data.total_links);
      byId("statOccurrences").textContent = count(data.total_occurrences);
      byId("statSources").textContent = String(data.sources.length);
      byId("sourceNames").textContent = data.sources.length ? data.sources.map((item) => text(item)).join(", ") : "No discovery sources configured";
      const storage = data.storage;
      if (storage.mode === "deployment_snapshot") {
        byId("storageBadge").textContent = "Deployment snapshot";
        byId("storageNote").textContent = "Deployment snapshot: not durable storage for new discoveries. Sweep results can be shown in the current response without being saved.";
      } else if (storage.mode === "local_persistent" && storage.persistent === true) {
        byId("storageBadge").textContent = "Local persistent storage";
        byId("storageNote").textContent = "Records persist on this local storage volume. This does not establish a durable cloud deployment.";
      } else {
        byId("storageBadge").textContent = "Storage durability unknown";
        byId("storageNote").textContent = "Durable storage has not been confirmed.";
      }
      byId("storageNote").append(document.createTextNode(` Writes: ${storage.writable === true ? "available" : storage.writable === false ? "unavailable" : "unknown"}.`));
      const collector = data.collector;
      byId("statCollector").textContent = collector.configured === true ? text(collector.status) : "Unavailable";
      byId("collectorNote").textContent = collector.configured === true
        ? `Reported status: ${text(collector.status)}. Last heartbeat: ${text(collector.last_heartbeat, "none reported; continuous operation unconfirmed")}.`
        : "Continuous collector is not configured. Manual lookup and sweep only.";
      byId("capabilitiesNote").textContent = `Referral validation: ${text(data.validation).replaceAll("_", " ")}. Notifications: ${text(data.notifications).replaceAll("_", " ")}. No redemption guarantee is provided.`;
      let yieldNote = byId("dailyYieldNote");
      if (!yieldNote) {
        yieldNote = element("p", "", "note");
        yieldNote.id = "dailyYieldNote";
        byId("capabilitiesNote").after(yieldNote);
      }
      const today = data.daily_yield && data.daily_yield.today;
      yieldNote.textContent = today
        ? `UTC ${text(today.date)}: ${count(today.first_observed_unique)} codes first observed in stored history; ${count(today.recent_dated_candidates)} same-day dated candidates; ${count(today.historical_dated)} historical; ${count(today.unknown_publication)} with unknown publication. The 30–50/day target is ${data.daily_yield.target_verified === true ? "met by the last seven complete measured days, not guaranteed for future days" : "not yet established"}.`
        : "Daily yield has not been measured. Stored inventory is not a daily discovery rate.";
      status("serviceStatus", `Service status loaded. Version: ${text(data.version)}.`);
    } catch (error) {
      for (const id of ["statCount", "statOccurrences", "statSources", "statCollector"]) byId(id).textContent = "—";
      byId("storageBadge").textContent = "Service status unavailable";
      byId("sourceNames").textContent = "Source configuration unknown";
      byId("collectorNote").textContent = "Continuous collector status unknown.";
      byId("storageNote").textContent = "Storage durability and write availability are unknown.";
      byId("capabilitiesNote").textContent = "Validation and notification configuration are unknown. Redemption is unvalidated.";
      if (byId("dailyYieldNote")) byId("dailyYieldNote").textContent = "Daily yield unavailable.";
      status("serviceStatus", `Could not load service status. ${error.message}`, "error");
    }
  }

  let refreshing = false;
  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    byId("refreshBtn").disabled = true;
    try { await Promise.all([loadStatus(), loadLinks()]); }
    finally { refreshing = false; byId("refreshBtn").disabled = false; }
  }

  let lookupController = null;
  let lookupSequence = 0;
  function lookupBusy(busy) {
    byId("lookupBtn").disabled = busy;
    byId("targetBtn").disabled = busy;
    const s1 = byId("sample1Btn"), s2 = byId("sample2Btn");
    if (s1) s1.disabled = busy;
    if (s2) s2.disabled = busy;
    byId("lookupBtn").textContent = busy ? "Searching…" : "Find source evidence";
    byId("lookupForm").setAttribute("aria-busy", String(busy));
  }

  async function lookup() {
    const query = byId("lookupInput").value.trim();
    const sequence = ++lookupSequence;
    if (lookupController) lookupController.abort();
    byId("lookupResult").replaceChildren();
    byId("lookupResult").hidden = true;
    if (!query) {
      lookupBusy(false);
      status("lookupStatus", "Enter a referral URL or code.", "warning");
      byId("lookupInput").focus();
      return;
    }
    lookupController = new AbortController();
    lookupBusy(true);
    status("lookupStatus", `Searching source evidence for ${query}…`);
    try {
      const data = await request(`/api/lookup?q=${encodeURIComponent(query)}`, { controller: lookupController });
      if (sequence !== lookupSequence) return;
      if (!isObject(data) || typeof data.found !== "boolean" || (data.found && !isObject(data.record))) throw new Error("Unexpected lookup response.");
      const box = byId("lookupResult");
      const record = isObject(data.record) ? data.record : null;
      const matched = data.found && record && ["direct_match", "archive_match"].includes(record.evidence_kind);
      const matchDescription = record && record.evidence_kind === "archive_match" ? "Archived source evidence" : "Direct source evidence";
      status("lookupStatus", matched ? `${matchDescription} returned for ${query}. Original public origin and redemption remain unverified.` : `Unresolved: no direct or archived source evidence established for ${query}.`, matched ? "" : "warning");
      box.append(element("p", "Only observed evidence is shown. Even the earliest observed occurrence is not proof of the original public source. No inference about private sharing, deletion, or expiry can be made from an unsuccessful search.", "note"));
      if (data.partial === true) box.append(element("p", "Partial search: some source coverage is unavailable or incomplete. This is not a definitive no-match result.", "warning"));
      if (data.message) box.append(element("p", data.message, "note"));
      if (record) box.append(recordDetails(record));
      const occurrences = Array.isArray(data.occurrences) ? data.occurrences.filter(isObject) : [];
      const observations = occurrences.map((item) => item.observed_at || item.discovered_at).filter((value) => typeof value === "string" && Number.isFinite(Date.parse(value)));
      observations.sort((a, b) => Date.parse(a) - Date.parse(b));
      addRow(box, "Earliest collector observation in these occurrences", observations[0] || "Not reported");
      const details = element("details");
      details.append(element("summary", `Observed occurrences (${occurrences.length} returned)`));
      if (!occurrences.length) details.append(element("p", "No occurrence details supplied.", "note"));
      const list = element("ol", undefined, "occurrences");
      for (const occurrence of occurrences) {
        const item = element("li");
        item.append(recordDetails(occurrence));
        list.append(item);
      }
      details.append(list);
      box.append(details, sourceReports(data.source_reports));
      box.hidden = false;
    } catch (error) {
      if (sequence === lookupSequence) status("lookupStatus", `Lookup failed; target remains unresolved. ${error.message}`, "error");
    } finally {
      if (sequence === lookupSequence) { lookupController = null; lookupBusy(false); }
    }
  }

  let sweeping = false;
  async function sweep() {
    if (sweeping) return;
    sweeping = true;
    byId("sweepBtn").disabled = true;
    byId("sweepBtn").textContent = "Searching sources…";
    byId("sweepResults").replaceChildren();
    byId("sweepResults").hidden = true;
    status("sweepStatus", "Discovery request running. Source coverage and persistence will be reported when it completes.");
    try {
      const data = await request("/api/discover", { method: "POST" });
      if (!isObject(data) || !Array.isArray(data.new_records) || !data.new_records.every(isObject)) throw new Error("Unexpected discovery response.");
      // new_records contains saved additions only; snapshot sweeps expose live
      // occurrences separately. Never label candidate_records as saved records.
      const candidates = data.candidate_records === undefined ? data.new_records : data.candidate_records;
      if (!Array.isArray(candidates) || !candidates.every(isObject)) throw new Error("Unexpected discovery candidates response.");
      const saved = data.stored === true && data.persistent === true;
      const persistence = saved ? `${count(data.new_unique_links_saved)} new unique records saved to persistent storage.`
        : data.stored === true ? "Storage reported a write, but durable persistence is not confirmed."
          : "Results were not saved; current response only, not durable storage.";
      status("sweepStatus", `${data.partial === true ? "Partial sweep" : "Sweep response received"}: ${count(data.total_candidates_found)} candidates reported. ${persistence}`, saved ? "" : "warning");
      const box = byId("sweepResults");
      box.append(element("h3", "Records returned by this sweep"));
      box.append(element("p", "These are current-response results, separate from the stored-records table below. Candidate counts do not establish direct source matches or redeemability.", "note"));
      if (data.partial === true) box.append(element("p", "Some source coverage was unavailable or incomplete. See source reports.", "warning"));
      if (data.message) box.append(element("p", data.message, "note"));
      if (!candidates.length) box.append(element("p", "No candidate records returned. This does not prove that no public source exists.", "note"));
      for (const record of candidates) {
        const details = element("details");
        details.append(element("summary", `${text(record.referral_code)} — ${evidenceLabel(record)}`), recordDetails(record));
        box.append(details);
      }
      box.append(sourceReports(data.source_reports));
      box.hidden = false;
      // Read stored data back; never merge response-only discoveries into the DB table.
      await refresh();
    } catch (error) {
      status("sweepStatus", `Discovery request failed. Results and storage outcome are unconfirmed. ${error.message}`, "error");
    } finally {
      sweeping = false;
      byId("sweepBtn").disabled = false;
      byId("sweepBtn").textContent = "Run discovery sweep";
    }
  }

  byId("lookupForm").addEventListener("submit", (event) => { event.preventDefault(); lookup(); });
  byId("lookupInput").addEventListener("input", () => {
    // Editing invalidates any in-flight result even if its response races abort().
    ++lookupSequence;
    if (lookupController) lookupController.abort();
    lookupController = null;
    lookupBusy(false);
    byId("lookupResult").hidden = true;
    status("lookupStatus", "Input changed. Submit to look up this target.");
  });
  byId("targetBtn").addEventListener("click", () => {
    byId("lookupInput").value = "https://claude.ai/referral/PFQOnxQmRQ";
    lookup();
  });
  const sample1 = byId("sample1Btn");
  if (sample1) sample1.addEventListener("click", () => {
    byId("lookupInput").value = "https://claude.ai/referral/9wjIA9-Iug";
    lookup();
  });
  const sample2 = byId("sample2Btn");
  if (sample2) sample2.addEventListener("click", () => {
    byId("lookupInput").value = "https://claude.ai/referral/SE-Jaa--ig";
    lookup();
  });
  byId("sweepBtn").addEventListener("click", sweep);
  byId("refreshBtn").addEventListener("click", refresh);
  refresh();
})();
