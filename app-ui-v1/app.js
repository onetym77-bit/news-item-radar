const sampleData = {
  lastRun: "미확인",
  dataMode: "데이터 확인 중",
  metrics: [],
  sources: [],
  cards: [],
  pending: [],
  pendingGroups: [],
  history: [],
  editorialBrief: { candidates: [] }
};

const esc = (value = "") => String(value).replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

async function loadData() {
  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error("데이터 없음");
    return { ...sampleData, ...(await response.json()), dataMode: "실제 산출물" };
  } catch {
    return sampleData;
  }
}

function groupBySource(items, sourceIndex = 1) {
  const groups = new Map();
  items.forEach(item => {
    const source = item[sourceIndex] || "출처 미상";
    if (!groups.has(source)) groups.set(source, []);
    groups.get(source).push(item);
  });
  return [...groups.entries()];
}

function renderItem([title, source, date, question, url, status]) {
  return `
    <article class="item-card">
      <div class="item-head"><h3>${esc(title)}</h3><span class="status-badge">${esc(status === "PENDING" ? "판정 대기" : status)}</span></div>
      <p class="item-meta">${esc(source)} · ${esc(date)}</p>
      <p class="item-question">${esc(question || "확인할 질문이 아직 정리되지 않았습니다.")}</p>
      <div class="item-actions">
        ${url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">원문 보기 ↗</a>` : ""}
        <a class="decision-link" href="https://github.com/onetym77-bit/news-item-radar/actions/workflows/review-item.yml" target="_blank" rel="noreferrer">판정 처리</a>
      </div>
    </article>`;
}

function renderGroups(items, emptyText) {
  if (!items.length) return `<p class="empty">${emptyText}</p>`;
  return groupBySource(items).map(([source, sourceItems]) => `
    <section class="source-group">
      <div class="source-group-head"><h3>${esc(source)}</h3><span>${sourceItems.length}건</span></div>
      ${sourceItems.map(renderItem).join("")}
    </section>`).join("");
}

function render(data) {
  document.getElementById("lastRun").textContent = data.lastRun || "미확인";
  document.getElementById("dataMode").textContent = data.dataMode;
  const briefNode = document.getElementById("editorialBrief");
  if (briefNode) {
    const candidates = (data.editorialBrief && data.editorialBrief.candidates) || [];
    briefNode.innerHTML = candidates.length ? candidates.map(item => {
      const evidence = (item.evidence || [])[0] || {};
      return `<article class="item-card editorial-card"><div class="item-head"><h3>${esc(item.title)}</h3><span class="status-badge">편집 후보</span></div><p class="item-meta">${esc(item.source || "출처 미상")}</p><p class="item-question"><strong>선정 이유</strong> ${esc(item.selection_reason)}</p><p class="item-question"><strong>시민 질문</strong> ${esc(item.citizen_question)}</p><p class="item-question"><strong>다른 각도</strong> ${esc(item.uncommon_angle)}</p>${evidence.url ? `<div class="item-actions"><a href="${esc(evidence.url)}" target="_blank" rel="noreferrer">근거 원문 보기 ↗</a></div>` : ""}</article>`; }).join("") : '<p class="empty">현재 기준을 충족한 편집 후보가 없습니다.</p>';
  }
  document.getElementById("metrics").innerHTML = (data.metrics || []).map(([label, value]) =>
    `<div class="metric"><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join("");

  const observationNode = document.getElementById("observations");
  if (observationNode) {
    const observations = data.observations || [];
    observationNode.innerHTML = observations.length ? observations.map(item => {
      const [title, source, date, question, url, status] = item;
      return `<article class="item-card"><div class="item-head"><h3>${esc(title)}</h3><span class="status-badge">${esc(status)}</span></div><p class="item-meta">${esc(source)} · ${esc(date)}</p><p class="item-question">${esc(question)}</p>${url ? `<div class="item-actions"><a href="${esc(url)}" target="_blank" rel="noreferrer">공식 목록 보기 ↗</a></div>` : ""}</article>`;
    }).join("") : '<p class="empty">추가 확인이 필요한 관측이 없습니다.</p>';
  }

  const sourceFilter = document.getElementById("sourceFilter");
  const levelFilter = document.getElementById("levelFilter");
  const statusFilter = document.getElementById("statusFilter");
  const sourceRows = data.sources || [];
  const dataSources = [...new Set([...(data.pending || []).map(([, source]) => source), ...(data.cards || []).map(([, source]) => source), ...(data.observations || []).map(([, source]) => source)])];
  [...new Set([...sourceRows.map(([name]) => name), ...dataSources])].filter(Boolean).sort().forEach(name =>
    sourceFilter.insertAdjacentHTML("beforeend", `<option value="${esc(name)}">${esc(name)}</option>`));
  [...new Set(sourceRows.map(([, level]) => level).filter(Boolean))].sort().forEach(level =>
    levelFilter.insertAdjacentHTML("beforeend", `<option value="${esc(level)}">${esc(level)}</option>`));
  const statuses = [...new Set([...(data.pending || []).map(([, , , , , status]) => status), ...(data.history || []).map(([, status]) => status)])].filter(Boolean);
  statuses.forEach(status => statusFilter.insertAdjacentHTML("beforeend",
    `<option value="${esc(status)}">${esc(status)}</option>`));

  const update = () => {
    const source = sourceFilter.value;
    const level = levelFilter.value;
    const status = statusFilter.value;
    const allowedSources = new Set([
      ...sourceRows
        .filter(([name, itemLevel]) => (!source || name === source) && (!level || itemLevel === level))
        .map(([name]) => name),
      ...dataSources.filter(name => !source || name === source),
    ]);
    const pending = (data.pending || []).filter(([, itemSource, , , , itemStatus]) =>
      allowedSources.has(itemSource) && (!status || itemStatus === status));
    const cards = (data.cards || []).filter(([, itemSource, , , , itemStatus]) =>
      allowedSources.has(itemSource) && (!status || itemStatus === status));

    document.getElementById("pending").innerHTML = renderGroups(pending, "현재 판정 대기 항목이 없습니다.");
    document.getElementById("pendingCount").textContent = `${pending.length}건`;
    document.getElementById("cards").innerHTML = renderGroups(cards, "현재 최신 검토 카드가 없습니다.");

    const history = (data.history || []).filter(([, historyStatus]) => !status || historyStatus === status);
    document.getElementById("history").innerHTML = history.length
      ? history.map(([title, historyStatus, date, question, report]) => `
        <article class="history-item"><div class="item-head"><h3>${esc(title)}</h3><span class="status-badge">${esc(historyStatus)}</span></div>
        <p class="item-meta">${esc(date)}</p><p class="item-question">${esc(question || "기록된 질문 없음")}</p>
        ${report ? `<p class="history-source">${esc(report)}</p>` : ""}</article>`).join("")
      : '<p class="empty">검토 이력이 없습니다.</p>';

    document.getElementById("sources").innerHTML = sourceRows
      .filter(([name, itemLevel]) => (!source || name === source) && (!level || itemLevel === level))
      .map(([name, itemLevel, role]) => `<div class="source-row"><span>${esc(name)}</span><small>${esc(itemLevel)} · ${esc(role)}</small></div>`).join("")
      || '<p class="empty">조건에 맞는 소스가 없습니다.</p>';
  };

  sourceFilter.addEventListener("change", update);
  levelFilter.addEventListener("change", update);
  statusFilter.addEventListener("change", update);
  update();
}

loadData().then(render);
