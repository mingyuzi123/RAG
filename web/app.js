const $ = (selector) => document.querySelector(selector);
const state = { examples: [], activeExample: null, config: null, keyAvailable: false };

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function message(text, isError = false) {
  const target = $('#form-message');
  target.textContent = text;
  target.classList.toggle('error', isError);
}

function setBusy(busy, label = '') {
  for (const id of ['compare-btn', 'search-btn']) $(`#${id}`).disabled = busy;
  $('#decompose-btn').disabled = busy || !state.keyAvailable;
  $('#ask-btn').disabled = busy || !state.keyAvailable;
  if (busy) message(label || '正在检索，请稍候…');
}

function showTab(name) {
  for (const button of document.querySelectorAll('.nav-item')) {
    button.classList.toggle('active', button.dataset.tab === name);
  }
  for (const section of document.querySelectorAll('.tab-section')) {
    section.classList.toggle('active', section.id === `${name}-tab`);
  }
  if (name === 'traces') loadTraces();
}

async function api(path, body) {
  const response = await fetch(path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  } : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`);
  return data;
}

function input() {
  const question = $('#question').value.trim();
  if (!question) throw new Error('请先输入一个问题。');
  const top_k = Number($('#top-k').value);
  const context_k = Number($('#context-k').value);
  if (!Number.isInteger(top_k) || top_k < 1 || top_k > 30) throw new Error('候选 Top K 需要在 1 到 30 之间。');
  if (!Number.isInteger(context_k) || context_k < 1 || context_k > top_k) throw new Error('上下文 K 需要在 1 到候选 Top K 之间。');
  const strategy = $('#strategy').value;
  const subqueries = strategy === 'decomposed' ? $('#subqueries').value.split(/\r?\n/).map(line => line.trim()).filter(Boolean) : [];
  if (strategy === 'decomposed' && (subqueries.length < 2 || subqueries.length > 4)) throw new Error('多查询覆盖需要填写 2–4 行子问题。');
  return { question, english_query: $('#english-query').value.trim(), strategy, subqueries, top_k, context_k };
}

function isGold(item) {
  return !!state.activeExample?.evidence?.some(anchor =>
    item.source_path === anchor.path && item.heading_path.includes(anchor.heading));
}

function candidateCard(item, contextK) {
  const gold = isGold(item);
  const card = el('article', `candidate${item.rank <= contextK ? ' in-context' : ''}${gold ? ' gold' : ''}`);
  const top = el('div', 'candidate-top');
  top.append(el('span', 'rank', `#${String(item.rank).padStart(2, '0')}`));
  if (item.rank <= contextK) top.append(el('span', 'chip', '进入上下文'));
  if (gold) top.append(el('span', 'chip gold', '标注证据'));
  if (item.retriever_ranks) {
    const ranks = Object.entries(item.retriever_ranks).map(([name, rank]) => `${name} #${rank}`).join(' · ');
    top.append(el('span', 'chip muted', ranks));
  }
  if (item.subquery_ranks) {
    const ranks = Object.entries(item.subquery_ranks).map(([name, rank]) => `${name.replace('query_', '子问题')} #${rank}`).join(' · ');
    top.append(el('span', 'chip muted', ranks));
  }
  const link = el('a', '', item.heading_path.join(' › '));
  link.href = item.source_url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  const snippet = el('p', '', item.text.replace(/\s+/g, ' ').slice(0, 180) + (item.text.length > 180 ? '…' : ''));
  const meta = el('div', 'candidate-meta', `${item.source_path.split('/').pop()} · L${item.start_line}–${item.end_line} · ${item.score}`);
  card.append(top, link, snippet, meta);
  return card;
}

function renderColumn(method, candidates, contextK) {
  const labels = { bm25: 'BM25 · 词语匹配', vector: 'E5 · 语义向量', hybrid: 'RRF · 排名融合', decomposed: '多查询 · 覆盖排序' };
  const column = el('div', 'result-col');
  column.dataset.method = method;
  const head = el('div', 'result-col-head');
  const title = el('h3');
  title.append(el('span', 'method-dot'), document.createTextNode(labels[method]));
  head.append(title, el('small', `${candidates.length} 个候选`));
  column.append(head);
  if (!candidates.length) column.append(el('p', 'muted', '未检索到候选。'));
  for (const item of candidates) column.append(candidateCard(item, contextK));
  return column;
}

function renderResults(groups, contextK) {
  const keys = Object.keys(groups);
  const columns = $('#result-columns');
  columns.replaceChildren();
  columns.classList.toggle('single', keys.length === 1);
  for (const key of keys) columns.append(renderColumn(key, groups[key], contextK));
  const summary = $('#comparison-summary');
  summary.classList.remove('empty');
  summary.replaceChildren();
  const seen = new Set(keys.flatMap(key => groups[key].map(item => item.id)));
  const goldContext = keys.map(key => `${key.toUpperCase()}：${groups[key].slice(0, contextK).filter(isGold).length} 个标注块进入前 ${contextK}`);
  summary.append(el('span', 'empty-icon', '⌁'), el('p', '', state.activeExample?.evidence?.length ? goldContext.join(' · ') : `共查看 ${seen.size} 个不同知识块；浅紫色表示进入前 ${contextK} 上下文。`));
  $('#result-note').textContent = state.activeExample?.id ? `${state.activeExample.id} · 点击标题可查看原文` : '点击标题可查看原文';
}

async function compare() {
  try {
    const payload = input();
    if (!payload.english_query) throw new Error('对比 BM25 与 E5 时，请提供英文关键词查询。');
    setBusy(true, '正在运行三路检索，首次使用 E5 可能需要加载模型…');
    const data = await api('/api/compare', payload);
    renderResults(data.strategies, payload.context_k);
    showTab('explore');
    message('对比完成。绿色边框标出评测集的预期证据章节。');
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}

async function search() {
  try {
    const payload = input();
    setBusy(true, '正在检索，请稍候…');
    const data = await api('/api/search', payload);
    renderResults({ [data.strategy]: data.candidates }, payload.context_k);
    showTab('explore');
    message('检索完成。查看排名、证据来源和进入上下文的块。');
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}

async function decompose() {
  try {
    const question = $('#question').value.trim();
    if (!question) throw new Error('请先输入要拆分的问题。');
    setBusy(true, '正在请求 DeepSeek 拆题…');
    const result = await api('/api/decompose', { question });
    $('#strategy').value = 'decomposed';
    $('#strategy').dispatchEvent(new Event('change'));
    $('#subqueries').value = result.subqueries.join('\n');
    message(`已生成两条子问题，本次用量 ${result.usage?.total_tokens ?? '未知'} tokens。请检查并修改后再检索。`);
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}

async function ask() {
  try {
    const payload = input();
    setBusy(true, '正在检索证据并请求 DeepSeek，可能需要几十秒…');
    const data = await api('/api/ask', payload);
    const trace = data.trace;
    renderResults({ [trace.strategy]: trace.candidates }, payload.context_k);
    const output = $('#answer-output');
    output.replaceChildren();
    output.append(el('div', 'answer-box', trace.result.answer));
    if (!trace.result.citation_numbers_valid) output.append(el('div', 'answer-warning', '未引用证据或引用编号超出范围。若回答明确拒答，未引用可能合理；请到请求记录中人工核验。'));
    const sources = el('div', 'source-list');
    for (const source of trace.result.sources) {
      const link = el('a', '', `[${source.number}] ${source.heading_path.join(' › ')}`);
      link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
      sources.append(link);
    }
    output.append(sources, el('p', 'key-hint', `请求 ID：${trace.request_id} · 用量：${trace.result.usage?.total_tokens ?? '未知'} tokens`));
    const reviewButton = el('button', 'button secondary', '核对回答与引用');
    reviewButton.type = 'button';
    reviewButton.addEventListener('click', () => showTab('traces'));
    output.append(reviewButton);
    showTab('answer');
    message('回答已保存到本地请求记录。引用编号有效不等于证据真正支持结论。');
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}

function reviewSelect(options, selected = '') {
  const select = el('select', 'review-select');
  for (const [value, label] of options) {
    const option = el('option', '', label);
    option.value = value;
    select.append(option);
  }
  select.value = selected;
  return select;
}

function verdictLabel(verdict) {
  return { pass: '通过', fail: '未通过', uncertain: '待确认' }[verdict] || verdict;
}

function reviewPanel(trace, example, previous) {
  const panel = el('div', 'review-panel');
  panel.append(el('h4', '', `人工核验 · ${example.id}`),
               el('p', 'muted', '先对照下方实际送入模型的证据，再判断答案要点与引用。编号有效只是格式检查。'));
  panel.append(el('div', 'review-answer', trace.result.answer || '（回答为空）'));
  const selected = new Set(trace.selected_chunk_ids);
  for (const item of trace.candidates.filter(candidate => selected.has(candidate.id))) {
    const detail = el('details', 'review-evidence');
    detail.append(el('summary', '', `[${trace.result.sources.find(source => source.chunk_id === item.id)?.number ?? '?'}] ${item.heading_path.join(' › ')} · ${item.source_path} L${item.start_line}–${item.end_line}`),
                  el('pre', '', item.text));
    panel.append(detail);
  }
  const pointInputs = [];
  for (const [index, point] of (example.expected_points || []).entries()) {
    const label = el('label', 'review-field', `要点 ${index + 1}：${point}`);
    const select = reviewSelect([
      ['', '请选择判断'], ['supported', '回答包含且证据支持'],
      ['unsupported', '回答包含但证据不支持'], ['missing', '回答缺失该要点']
    ], previous?.point_reviews?.[index]?.verdict);
    label.append(select); panel.append(label); pointInputs.push(select);
  }
  if (example.answerability === 'unanswerable') {
    panel.append(el('p', 'review-prompt', '这题在固定文档中没有标注答案。请检查模型是否明确表示资料不足，是否编造了具体事实。'));
  }
  const citationLabel = el('label', 'review-field', '主要断言的引用是否真的提供支持？');
  const citation = reviewSelect([
    ['', '请选择判断'], ['supported', '支持'], ['unsupported', '不支持或误引'],
    ['unclear', '无法判断'], ['not_applicable', '没有需要核验的断言']
  ], previous?.citation_verdict);
  citationLabel.append(citation);
  const refusalLabel = el('label', 'review-field', '模型是否拒答？');
  const refusal = reviewSelect([
    ['', '请选择判断'], ['not_applicable', '没有拒答'],
    ['appropriate', '已拒答且合理'], ['inappropriate', '拒答不合理或应拒却编造']
  ], previous?.refusal_verdict);
  refusalLabel.append(refusal);
  const noteLabel = el('label', 'review-field', '判断依据 / 需复查的断言');
  const note = el('textarea', 'review-note');
  note.rows = 3; note.maxLength = 2000; note.value = previous?.note || '';
  noteLabel.append(note);
  const save = el('button', 'button primary', '保存人工核验');
  save.type = 'button';
  const status = el('p', 'review-status', previous ? `上次结果：${verdictLabel(previous.verdict)}` : '尚未核验');
  save.addEventListener('click', async () => {
    if (pointInputs.some(select => !select.value) || !citation.value || !refusal.value) {
      status.textContent = '请完成每项判断后保存。'; return;
    }
    save.disabled = true;
    try {
      const { review } = await api('/api/review', {
        request_id: trace.request_id,
        point_verdicts: pointInputs.map(select => select.value),
        citation_verdict: citation.value, refusal_verdict: refusal.value, note: note.value
      });
      status.textContent = `已保存 · ${verdictLabel(review.verdict)} · ${new Date(review.timestamp).toLocaleString('zh-CN')}`;
    } catch (error) { status.textContent = `保存失败：${error.message}`; }
    finally { save.disabled = false; }
  });
  panel.append(citationLabel, refusalLabel, noteLabel, save, status);
  return panel;
}

async function loadTraces() {
  const box = $('#trace-list');
  try {
    const { traces, reviews } = await api('/api/traces');
    box.replaceChildren();
    if (!traces.length) { box.append(el('p', 'muted', '还没有问答记录。检索实验可先在上方运行；配置 DeepSeek 密钥后再生成回答。')); return; }
    for (const trace of traces) {
      const card = el('article', 'trace-item');
      const head = el('div', 'trace-item-head');
      head.append(el('b', '', trace.strategy.toUpperCase()), el('span', '', new Date(trace.timestamp).toLocaleString('zh-CN')));
      card.append(head, el('p', '', trace.question), el('small', '', `状态 ${trace.status || 'completed'} · 候选 ${trace.candidates.length} · 上下文 ${trace.selected_chunk_ids.length} · 引用编号 ${trace.result.citation_numbers_valid ? '有效' : '待检查'}`));
      const detail = el('details');
      detail.append(el('summary', '', '查看完整请求'), el('pre', '', JSON.stringify(trace, null, 2)));
      card.append(detail);
      const example = state.examples.find(item => item.question === trace.question);
      if (example && trace.status === 'completed') {
        const reviewDetail = el('details', 'review-detail');
        const previous = reviews?.[trace.request_id];
        reviewDetail.append(el('summary', '', previous ? `人工核验：${verdictLabel(previous.verdict)}` : '人工核验本次回答'),
                            reviewPanel(trace, example, previous));
        card.append(reviewDetail);
      }
      box.append(card);
    }
  } catch (error) { box.replaceChildren(el('p', 'muted', error.message)); }
}

async function initialize() {
  for (const button of document.querySelectorAll('.nav-item')) button.addEventListener('click', () => showTab(button.dataset.tab));
  $('#compare-btn').addEventListener('click', compare);
  $('#search-btn').addEventListener('click', search);
  $('#decompose-btn').addEventListener('click', decompose);
  $('#ask-btn').addEventListener('click', ask);
  $('#refresh-traces').addEventListener('click', loadTraces);
  $('#strategy').addEventListener('change', () => { $('#subquery-field').hidden = $('#strategy').value !== 'decomposed'; });
  $('#strategy').dispatchEvent(new Event('change'));
  $('#sample-select').addEventListener('change', event => {
    const item = state.examples.find(example => example.id === event.target.value);
    state.activeExample = item || null;
    if (item) { $('#question').value = item.question; $('#english-query').value = item.english_query; $('#subqueries').value = (item.subqueries || []).join('\n'); }
  });
  $('#question').addEventListener('input', () => { state.activeExample = null; $('#sample-select').value = ''; });
  $('#english-query').addEventListener('input', () => { state.activeExample = null; $('#sample-select').value = ''; });
  $('#subqueries').addEventListener('input', () => { state.activeExample = null; $('#sample-select').value = ''; });
  try {
    const config = await api('/api/config');
    state.config = config;
    state.keyAvailable = config.status.deepseek_key_set;
    state.examples = config.examples;
    $('#scenario-name').textContent = config.ui.title;
    $('#scenario-icon').textContent = (config.ui.title || 'R').slice(0, 1).toUpperCase();
    $('#scenario-badge').textContent = config.ui.badge || config.ui.title;
    $('#scenario-subtitle').textContent = config.ui.subtitle || '从问题到证据，逐步检查每个知识块为什么被选中。';
    $('#scenario-version').textContent = config.status.source_commit.slice(0, 8) + ' · 固定资料';
    document.documentElement.style.setProperty('--accent', config.ui.accent || '#635bff');
    document.title = `RAG Lab · ${config.ui.title}`;
    if (config.ui.metric) {
      $('#metric-label').textContent = config.ui.metric.label;
      $('#metric-value').textContent = config.ui.metric.value;
      $('#metric-caption').textContent = config.ui.metric.caption;
      $('#metric-note').textContent = config.ui.metric.note;
      $('#metric-fill').style.width = `${Math.max(0, Math.min(100, config.ui.metric.percent))}%`;
    }
    for (const item of config.examples) {
      const option = el('option', '', `${item.id} · ${item.question}`);
      option.value = item.id; $('#sample-select').append(option);
    }
    const ready = config.status.keyword_ready && config.status.vector_ready;
    $('#status-dot').classList.toggle('ready', ready);
    $('#status-line').textContent = ready ? 'BM25 与 E5 索引已就绪' : '索引未齐，请先运行建库命令';
    $('#key-hint').textContent = config.status.deepseek_key_set ? 'DeepSeek 密钥已从本地环境变量读取。' : '未检测到 DeepSeek 密钥；检索实验仍可使用。';
    $('#ask-btn').disabled = !state.keyAvailable;
    $('#decompose-btn').disabled = !state.keyAvailable;
    if (config.examples.length) {
      const preferred = config.examples.find(item => item.id === 'C07') || config.examples[0];
      $('#sample-select').value = preferred.id;
      $('#sample-select').dispatchEvent(new Event('change'));
    }
  } catch (error) { message(`初始化失败：${error.message}`, true); }
}

initialize();
