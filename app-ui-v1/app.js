const sampleData = {
  lastRun: "2026-09-18 11:00 KST",
  dataMode: "샘플 화면",
  metrics: [["활성 관측 소스", "8"], ["사람 판정 대기", "12"], ["접속 실패", "4"], ["브리핑 연결", "0"]],
  sources: [["서울시의회", "L3", "관측 중"], ["25개 구의회", "L1", "7일 관측"], ["서울시 감사 결과", "L3", "그림자 평가"], ["시장·구청장 SNS", "L0", "보조 소스"]],
  cards: [],
  history: [],
  queue: []
};

async function loadData() {
  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error("latest data unavailable");
    return { ...sampleData, ...(await response.json()), dataMode: "실제 산출물" };
  } catch {
    return sampleData;
  }
}

function render(data) {
  document.getElementById("lastRun").textContent = data.lastRun;
  document.getElementById("dataMode").textContent = data.dataMode;
  document.getElementById("metrics").innerHTML = data.metrics.map(([label, value]) => `<div class="metric"><span>${label}</span><b>${value}</b></div>`).join("");
  const sourceFilter = document.getElementById("sourceFilter");
  const levelFilter = document.getElementById("levelFilter");
  const statusFilter = document.getElementById("statusFilter");
  [...new Set(data.sources.map(([name]) => name))].forEach(name => sourceFilter.insertAdjacentHTML("beforeend", `<option value="${name}">${name}</option>`));
  [...new Set(data.sources.map(([, level]) => level))].sort().forEach(level => levelFilter.insertAdjacentHTML("beforeend", `<option value="${level}">${level}</option>`));
  [...new Set((data.history || []).map(([, , , , status]) => status))].sort().forEach(status => statusFilter.insertAdjacentHTML("beforeend", `<option value="${status}">${status}</option>`));

  const update = () => {
    const source = sourceFilter.value;
    const level = levelFilter.value;
    const status = statusFilter.value;
    const visibleSources = data.sources.filter(([name, itemLevel]) => (!source || name === source) && (!level || itemLevel === level));
    document.getElementById("sources").innerHTML = visibleSources.map(([name, itemLevel, sourceStatus]) => `<div class="source"><span>${name}</span><span class="status">${itemLevel} · ${sourceStatus}</span></div>`).join("") || '<p class="muted">조건에 맞는 소스가 없습니다.</p>';
    const visibleCards = data.cards.filter(([, meta, , , cardStatus]) => (!source || meta.includes(source)) && (!status || cardStatus === status));
    document.getElementById("cards").innerHTML = visibleCards.map(([title, meta, body, url]) => `<article class="card"><h3>${title}</h3><small>${meta}</small><p>${body}</p>${url ? `<a class="source-link" href="${url}" target="_blank" rel="noreferrer">원문·근거 보기 ↗</a>` : ""}</article>`).join("") || '<p class="muted">조건에 맞는 검토 카드가 없습니다.</p>';
    const visibleHistory = (data.history || []).filter(([, , , , historyStatus]) => !status || historyStatus === status);
    document.getElementById("history").innerHTML = visibleHistory.map(([title, meta, question, report]) => `<article class="history-item"><div><h3>${title}</h3><small>${meta}</small></div><p>${question || "기록된 질문 없음"}</p>${report ? `<small class="history-source">${report}</small>` : ""}</article>`).join("") || '<p class="muted">조건에 맞는 검토 이력이 없습니다.</p>';
  };
  sourceFilter.addEventListener("change", update);
  levelFilter.addEventListener("change", update);
  statusFilter.addEventListener("change", update);
  update();
  document.getElementById("queue").innerHTML = data.queue.map(([name, queueStatus]) => `<div class="queue"><strong>${name}</strong><span class="muted">${queueStatus}</span></div>`).join("");
}

loadData().then(render);
