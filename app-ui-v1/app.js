const sampleData = {
  lastRun: "미확인",
  dataMode: "데이터 확인 중",
  metrics: [],
  sources: [],
  cards: [],
  pending: [],
  pendingGroups: [],
  history: [],
  editorialBrief: { candidates: [] },
  sourceExploration: { sources: [], clues: [] }
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

function renderDiscoveryItem(item) {
  const evidence = (item.evidence || []).find(row => row.type === "publisher_article")
    || (item.evidence || [])[0] || {};
  const assessed = item.source_context_status === "BODY_READ";
  const typeLabels = {
    INCIDENT: "사건 보도", POLICY_ANNOUNCEMENT: "정책 발표",
    PROMOTION: "홍보성 보도", OPINION: "주장·의견", OTHER: "기타"
  };
  const claimLabels = {
    OBSERVED_EVENT: "기사에 기록된 사건", ATTRIBUTED_CLAIM: "인용된 주장",
    ANNOUNCEMENT: "발표 내용", UNCLEAR: "사실 성격 미확인"
  };
  const badge = assessed ? "본문 판정 · 사실 미검증" : "본문 확인 전";
  const failureLabels = {
    NO_TITLE_MATCH: "동일 기사 원문 주소 미확인",
    BODY_TOO_SHORT: "기사 본문 추출 부족",
    NOT_HTML: "본문 형식 미지원",
    MODEL_NOT_RUN: "내용 판정 미실행",
    NAVER_CREDENTIALS_MISSING: "뉴스 검색 연결 필요"
  };
  const pendingReason = failureLabels[item.context_failure] || "본문 접근·판정 미완료";
  return `<article class="item-card">
    <div class="item-head"><h3>${esc(item.headline || "제목 미상")}</h3><span class="status-badge">${badge}</span></div>
    <p class="item-meta">${esc(item.source || "출처 미상")}${assessed ? " · " + esc(typeLabels[item.document_type] || "유형 확인 필요") + " · " + esc(claimLabels[item.claim_type] || "사실 성격 미확인") : ""}</p>
    ${assessed
      ? `<p class="item-question"><strong>기사 내용</strong> ${esc(item.what_happened || "요약 확인 필요")}</p>
         ${item.citizen_relevance ? `<p class="item-question"><strong>시민 관련성</strong> ${esc(item.citizen_relevance)}</p>` : ""}
         ${item.editorial_question ? `<p class="item-question"><strong>검토할 질문</strong> ${esc(item.editorial_question)}</p>` : ""}
         <p class="item-question"><strong>먼저 확인</strong> ${esc(item.first_check || "기사의 주장과 사실 구분")}</p>
         ${item.counterpossibility ? `<p class="item-question"><strong>다른 가능성</strong> ${esc(item.counterpossibility)}</p>` : ""}`
      : `<p class="item-question">${esc(item.observed_signal || "검색 결과에서 제목을 확인했습니다.")} 본문을 확인하지 못해 내용 판단을 보류합니다. <strong>사유</strong> ${esc(pendingReason)}</p>`}
    ${evidence.url ? `<div class="item-actions"><a href="${esc(evidence.url)}" target="_blank" rel="noreferrer">원문 확인 ↗</a></div>` : ""}
  </article>`;
}
function renderSourceExploration(exploration = {}) {
  const sources = exploration.sources || [];
  const clues = exploration.clues || [];
  if (!sources.length) return '<p class="empty">저장된 소스 탐색 현황이 없습니다.</p>';
  const safeLink = url => /^https?:\/\//i.test(url || "")
    ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">원문 확인 ↗</a>` : "";
  return sources.map(source => {
    const related = clues.filter(item => item.source_id === source.source_id);
    const observed = source.observed === null || source.observed === undefined
      ? "수집 건수 미확인" : `읽은 항목 ${esc(source.observed)}건`;
    return `<details class="exploration-source">
      <summary>
        <span><strong>${esc(source.source)}</strong><small>${esc(source.stage)} · ${esc(source.collected_at)} · ${observed}</small></span>
        <span class="status-badge">${esc(source.status)}</span>
      </summary>
      <div class="exploration-body">
        <p>${esc(source.reason)}</p>
        ${safeLink(source.url)}
        ${related.length ? `<div class="exploration-clues"><h3>저장된 검토·보류 단서 ${related.length}건</h3>
          ${related.map(item => `<article class="exploration-clue">
            <div class="item-head"><h4>${esc(item.title || "사안명 미확인")}</h4><span class="status-badge">${esc(item.status)}</span></div>
            <p class="item-meta">${esc(item.date || "문서일 미확인")}</p>
            ${item.excerpt ? `<p>${esc(item.excerpt)}</p>` : ""}
            <p><strong>이 단계에 머문 이유</strong> ${esc(item.reason)}</p>
            <p><strong>다음 확인</strong> ${esc(item.next_step)}</p>
            ${safeLink(item.url)}
          </article>`).join("")}</div>` : ""}
      </div>
    </details>`;
  }).join("");
}

function renderEditorialItem(item) {
  const evidence = (item.evidence || [])[0] || {};
  const list = (values = []) => values.length
    ? `<ul class="editorial-list">${values.map(value => `<li>${esc(value)}</li>`).join("")}</ul>`
    : "";
  return `<article class="item-card editorial-card">
    <div class="item-head"><h3>${esc(item.title || item.seed_event)}</h3><span class="status-badge">${esc(item.editorial_status || item.status || "편집 후보")}</span></div>
    <p class="item-meta">${esc(item.source || item.topic || "출처 미상")}</p>
    ${item.seed_event ? `<p class="item-question"><strong>출발 사건</strong> ${esc(item.seed_event)}</p>` : ""}
    ${item.structural_question ? `<p class="item-question"><strong>서울 전체로 확장할 질문</strong> ${esc(item.structural_question)}</p>` : ""}
    ${item.scope_hypothesis ? `<p class="item-question"><strong>확장 가설</strong> ${esc(item.scope_hypothesis)}</p>` : ""}
    ${item.selection_reason ? `<p class="item-question"><strong>선정 이유</strong> ${esc(item.selection_reason)}</p>` : ""}
    ${item.citizen_question ? `<p class="item-question"><strong>시민 질문</strong> ${esc(item.citizen_question)}</p>` : ""}
    ${item.citizen_questions ? `<p class="item-question"><strong>시민 질문</strong></p>${list(item.citizen_questions)}` : ""}
    ${item.conflict_groups ? `<p class="item-question"><strong>이해관계 집단</strong></p>${list(item.conflict_groups)}` : ""}
    ${item.reporting_paths ? `<p class="item-question"><strong>취재 경로</strong></p>${list(item.reporting_paths)}` : ""}
    ${item.uncommon_angle ? `<p class="item-question"><strong>다른 각도</strong> ${esc(item.uncommon_angle)}</p>` : ""}
    ${item.title_options ? `<p class="item-question"><strong>제목 후보</strong></p>${list(item.title_options)}` : ""}
    ${evidence.url ? `<div class="item-actions"><a href="${esc(evidence.url)}" target="_blank" rel="noreferrer">근거 원문 보기 ↗</a></div>` : ""}
  </article>`;
}

function renderV4(data = {}) {
  const items = data.proposals || [];
  const node = document.getElementById("editorialV4");
  const gaps = document.getElementById("editorialV4Gaps");
  if (node) node.innerHTML = items.length ? items.map(item => `
    <article class="item-card editorial-card">
      <div class="item-head"><h3>${esc(item.title)}</h3><span class="status-badge">기획 질문 · 미검증</span></div>
      <p class="item-meta">${esc(item.source)} · ${esc(item.date || "날짜 미상")}</p>
      <p class="item-question"><strong>주제</strong> ${esc(item.subject)}</p>
      <p class="item-question"><strong>선정 이유</strong> ${esc(item.why_now)}</p>
      <p class="item-question"><strong>시민 질문</strong> ${esc(item.citizen_question)}</p>
      <p class="item-question"><strong>뜻밖의 질문</strong> ${esc(item.uncommon_question)}</p>
      <p class="item-question"><strong>가를 첫 취재</strong> ${esc(item.decisive_test || item.first_check)}</p>
      <details><summary>반론·제작 경로</summary>
        <p class="item-question"><strong>다른 설명</strong> ${esc(item.counterhypothesis)}</p>
        ${item.editorial_risk ? `<p class="item-question"><strong>오판 위험</strong> ${esc(item.editorial_risk)}</p>` : ""}
        <p class="item-question"><strong>방송 장면</strong> ${esc(item.scene_path)}</p>
      </details>
      <p class="item-meta">원문 단서: ${esc(item.anchor_quote)} · ${esc(item.claim_status)}</p>
      <div class="item-actions">
        ${item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noreferrer">원문 확인 ↗</a>` : ""}
        <a href="https://github.com/onetym77-bit/news-item-radar/actions/workflows/review-editorial-v4.yml" target="_blank" rel="noreferrer">검토 판정 ↗</a>
        <span class="item-meta">판정 ID: ${esc(item.id)}</span>
      </div>
    </article>`).join("") : '<p class="empty">이번 회차에 검토 기준을 통과한 새 기획 질문이 없습니다. 수량을 맞추기 위해 채우지 않습니다.</p>';
  if (gaps) {
    const holds = (data.holds || []).filter(x => x.verdict !== "SKIP").slice(0, 6).map(x => `<p><strong>${esc(x.source)}</strong> · ${esc(x.headline)} — ${esc(x.reason)}</p>`);
    const missing = (data.source_gaps || []).map(x => `<p><strong>${esc(x.source)}</strong> · ${esc(x.reason)}</p>`);
    gaps.innerHTML = [...holds, ...missing].join("") || '<p>보류 기록이 없습니다.</p>';
  }
}

function render(data) {
  renderV4(data.editorialV4);
  document.getElementById("lastRun").textContent = data.lastRun || "미확인";
  document.getElementById("dataMode").textContent = data.dataMode;
  const sourceExplorationNode = document.getElementById("sourceExploration");
  if (sourceExplorationNode) sourceExplorationNode.innerHTML = renderSourceExploration(data.sourceExploration);
  const briefNode = document.getElementById("editorialBrief");
  if (briefNode) {
    const candidates = (data.editorialBrief && data.editorialBrief.candidates) || [];
    briefNode.innerHTML = candidates.length
      ? candidates.map(renderEditorialItem).join("")
      : '<p class="empty">본문 맥락과 시민에게 의미 있는 질문을 검토해 승격한 후보가 아직 없습니다.</p>';
  }
  const discoveryNode = document.getElementById("discoverySignals");
  if (discoveryNode) {
    const signals = (data.editorialBrief && data.editorialBrief.discovery_signals) || [];
    discoveryNode.innerHTML = signals.length
      ? signals.map(renderDiscoveryItem).join("")
      : '<p class="empty">현재 검증할 새 신호가 없습니다.</p>';
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
