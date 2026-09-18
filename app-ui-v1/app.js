const sampleData = {
  lastRun: "2026-09-18 11:00 KST",
  dataMode: "샘플 화면",
  metrics: [["활성 관측 소스", "8"], ["사람 판정 대기", "12"], ["접속 실패", "4"], ["브리핑 연결", "0"]],
  sources: [["서울시의회", "L3", "관측 중"], ["25개 구의회", "L1", "7일 관측"], ["서울시 감사 결과", "L3", "그림자 평가"], ["시장·구청장 SNS", "L0", "보조 소스"]],
  cards: [["국회대로 지하차도 및 상부공원화 사업 지연", "구의회 회의록 · 사실관계 확인 전", "회의록 원문과 사업 일정 자료의 대응을 확인해야 합니다."], ["수어통역서비스 지원 문제", "구의회 회의록 · 편집 검토", "대상 기관과 지원 범위를 추가 확인해야 합니다."]],
  queue: [["25개 구의회", "목록 표본 수집"], ["서울시 감사 결과", "사람 판정 80% 확인"], ["응답소 통계", "접속 재시험 대기"]]
};

async function loadData() {
  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error("latest data unavailable");
    const liveData = await response.json();
    return { ...sampleData, ...liveData, dataMode: "실제 산출물" };
  } catch {
    return sampleData;
  }
}

function render(data) {
  document.getElementById("lastRun").textContent = data.lastRun;
  document.getElementById("dataMode").textContent = data.dataMode;
  document.getElementById("metrics").innerHTML = data.metrics.map(([label, value]) => `<div class="metric"><span>${label}</span><b>${value}</b></div>`).join("");
  document.getElementById("sources").innerHTML = data.sources.map(([name, level, status]) => `<div class="source"><span>${name}</span><span class="status">${level} · ${status}</span></div>`).join("");
  document.getElementById("cards").innerHTML = data.cards.map(([title, meta, body]) => `<article class="card"><h3>${title}</h3><small>${meta}</small><p>${body}</p></article>`).join("");
  document.getElementById("queue").innerHTML = data.queue.map(([name, status]) => `<div class="queue"><strong>${name}</strong><span class="muted">${status}</span></div>`).join("");
}

loadData().then(render);
