const $ = (selector) => document.querySelector(selector);
const state = { examples: [], activeExample: null, config: null, keyAvailable: false, evaluationLoaded: false, queryRewrite: null };

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
  $('#search-btn').disabled = busy;
  $('#compare-btn').disabled = busy || !state.config?.status.vector_ready;
  $('#decompose-btn').disabled = busy || !state.keyAvailable;
  $('#rewrite-btn').disabled = busy || !state.keyAvailable;
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
  if (name === 'evaluation' && !state.evaluationLoaded) loadEvaluations();
}

async function api(path, body) {
  const scenario = new URLSearchParams(window.location.search).get('scenario');
  const url = new URL(path, window.location.origin);
  if (scenario) url.searchParams.set('scenario', scenario);
  const response = await fetch(url, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  } : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(`${data.error || `请求失败 (${response.status})`}${data.request_id ? ` · 请求 ${data.request_id}` : ''}`);
  return data;
}

function fileBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1]);
    reader.onerror = () => reject(new Error('无法读取 PDF 文件。'));
    reader.readAsDataURL(file);
  });
}

function input(comparing = false) {
  const question = $('#question').value.trim();
  if (!question) throw new Error('请先输入一个问题。');
  const top_k = Number($('#top-k').value);
  const context_k = Number($('#context-k').value);
  if (!Number.isInteger(top_k) || top_k < 1 || top_k > 30) throw new Error('候选 Top K 需要在 1 到 30 之间。');
  if (!Number.isInteger(context_k) || context_k < 1 || context_k > top_k) throw new Error('上下文 K 需要在 1 到候选 Top K 之间。');
  const strategy = comparing ? 'hybrid' : $('#strategy').value;
  const context_policy = comparing ? 'top_k' : $('#context-policy').value;
  const subqueries = strategy === 'decomposed' ? $('#subqueries').value.split(/\r?\n/).map(line => line.trim()).filter(Boolean) : [];
  if (strategy === 'decomposed' && (subqueries.length < 2 || subqueries.length > 4)) throw new Error('多查询覆盖需要填写 2–4 行子问题。');
  const english_query = $('#english-query').value.trim();
  if (context_policy === 'targeted_window' && strategy !== 'hybrid') throw new Error('目标邻块规则当前需要混合 RRF 策略。');
  const query_metadata = state.queryRewrite?.question === question && state.queryRewrite.query === english_query
    ? state.queryRewrite.metadata : undefined;
  return { question, english_query, strategy, context_policy, subqueries, top_k, context_k,
    auto_rewrite: $('#auto-rewrite').checked, query_metadata };
}

function rememberQuery(question, query, metadata) {
  if (metadata.source !== 'auto' || $('#question').value.trim() !== question) return;
  $('#english-query').value = query;
  state.queryRewrite = { question, query, metadata };
}

function currentExample() {
  const question = $('#question').value.trim();
  if (state.activeExample?.question === question) return state.activeExample;
  return state.examples.find(example => example.question === question) || null;
}

function isGold(item) {
  return !!currentExample()?.evidence?.some(anchor =>
    item.source_path === anchor.path && item.heading_path.includes(anchor.heading));
}

function sourceLocation(item) {
  return item.page_number ? `第 ${item.page_number} 页` : `L${item.start_line}–${item.end_line}`;
}

function candidateCard(item, contextK) {
  const gold = isGold(item);
  const card = el('article', `candidate${item.rank <= contextK ? ' in-context' : ''}${gold ? ' gold' : ''}`);
  const top = el('div', 'candidate-top');
  top.append(el('span', 'rank', `#${String(item.rank).padStart(2, '0')}`));
  if (item.rank <= contextK) top.append(el('span', 'chip', '进入上下文'));
  if (gold) top.append(el('span', 'chip gold', item.page_number ? '标注页' : '标注章节'));
  if (item.retriever_ranks) {
    const ranks = Object.entries(item.retriever_ranks).map(([name, rank]) => `${name} #${rank}`).join(' · ');
    top.append(el('span', 'chip muted', ranks));
  }
  if (item.subquery_ranks) {
    const ranks = Object.entries(item.subquery_ranks).map(([name, rank]) => `${name.replace('query_', '子问题')} #${rank}`).join(' · ');
    top.append(el('span', 'chip muted', ranks));
  }
  if (item.context_origin) top.append(el('span', 'chip muted', item.context_origin));
  const link = el('a', '', item.heading_path.join(' › '));
  link.href = item.source_url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  const snippet = el('p', '', item.text.replace(/\s+/g, ' ').slice(0, 180) + (item.text.length > 180 ? '…' : ''));
  const meta = el('div', 'candidate-meta', `${item.source_path.split('/').pop()} · ${sourceLocation(item)} · ${item.score}`);
  card.append(top, link, snippet, meta);
  if (item.text.length > 180) {
    const detail = el('details', 'candidate-detail');
    detail.append(el('summary', '', '查看完整证据块'), el('pre', '', item.text));
    card.append(detail);
  }
  return card;
}

function renderColumn(method, candidates, contextK) {
  const labels = { bm25: 'BM25 · 词语匹配', vector: 'E5 · 语义向量', hybrid: 'RRF · 排名融合', decomposed: '多查询 · 覆盖排序', targeted_window: '条件合并 · 目标邻块' };
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
  const example = currentExample();
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
  summary.append(el('span', 'empty-icon', '⌁'), el('p', '', example?.evidence?.length ? goldContext.join(' · ') : `共查看 ${seen.size} 个不同知识块；浅紫色表示进入前 ${contextK} 上下文。`));
  $('#result-note').textContent = example?.id ? `${example.id} · 点击标题可查看原文` : '点击标题可查看原文';
}

function evaluationState(result) {
  return {
    context: ['前 3 齐', '标注证据均进入回答上下文'],
    candidate: ['只进前 10', `候选已集齐；前 3 仍缺 ${result.missing_context.join('、')}`],
    missing: ['候选未齐', `前 10 缺 ${result.missing_top.join('、')}`]
  }[result.state];
}

async function loadEvaluations() {
  const target = $('#evaluation-content');
  try {
    const dashboard = await api('/api/evaluations');
    target.replaceChildren();
    if (!dashboard.strategies.length) {
      target.append(el('p', 'muted', '这个场景还没有固定评测报告。'));
      state.evaluationLoaded = true;
      return;
    }
    const summary = el('div', 'evaluation-summary');
    for (const method of dashboard.strategies) {
      const card = el('div', 'evaluation-method');
      card.append(el('strong', '', method.label),
                  el('span', '', `候选前 ${method.top_k}：${method.candidate_hits}/${method.question_count}`),
                  el('span', '', `上下文前 ${method.context_k}：${method.context_hits}/${method.question_count}`));
      summary.append(card);
    }
    const legend = el('p', 'evaluation-legend', '红：候选前 10 没集齐证据，先查召回。黄：候选齐了但前 3 没齐，查排序或选块。绿：前 3 已齐，继续核验回答与引用。');
    const scroll = el('div', 'evaluation-table-wrap');
    const table = el('table', 'evaluation-table');
    const thead = el('thead');
    const heading = el('tr');
    heading.append(el('th', '', '评测题'));
    for (const method of dashboard.strategies) heading.append(el('th', '', method.label));
    thead.append(heading); table.append(thead);
    const tbody = el('tbody');
    for (const question of dashboard.questions) {
      const row = el('tr');
      const first = el('td');
      const open = el('button', 'evaluation-question', question.id);
      open.type = 'button';
      const example = state.examples.find(item => item.id === question.id);
      open.addEventListener('click', () => {
        $('#sample-select').value = question.id;
        $('#sample-select').dispatchEvent(new Event('change'));
        showTab('explore');
        message(`已载入 ${question.id}。运行三路对比，查看各块为何进入或错过上下文。`);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
      first.append(open, el('small', '', example?.question || ''));
      if (question.caveat) first.append(el('small', 'evaluation-caveat', `标注复核：${question.caveat}`));
      row.append(first);
      for (const method of dashboard.strategies) {
        const result = question.results[method.id];
        const [label, detail] = evaluationState(result);
        const cell = el('td', `evaluation-state ${result.state}`);
        cell.append(el('strong', '', label), el('small', '', detail));
        row.append(cell);
      }
      tbody.append(row);
    }
    table.append(tbody); scroll.append(table);
    target.append(summary, legend, scroll);
    state.evaluationLoaded = true;
  } catch (error) { target.replaceChildren(el('p', 'answer-warning', `读取评测报告失败：${error.message}`)); }
}

async function compare() {
  try {
    const payload = input(true);
    setBusy(true, '正在运行三路检索，首次使用 E5 可能需要加载模型…');
    const data = await api('/api/compare', payload);
    rememberQuery(payload.question, data.english_query, data.query_metadata);
    renderResults(data.strategies, payload.context_k);
    showTab('explore');
    message(`对比完成。检索词来源：${querySource(data.query_metadata)}。绿色边框标出与标注位置匹配的块。`);
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}

async function search() {
  try {
    const payload = input();
    setBusy(true, '正在检索，请稍候…');
    const data = await api('/api/search', payload);
    rememberQuery(payload.question, data.english_query, data.query_metadata);
    renderResults({ [data.strategy]: data.candidates }, payload.context_k);
    showTab('explore');
    message(`检索完成。检索词来源：${querySource(data.query_metadata)}。`);
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

async function rewrite() {
  try {
    const question = $('#question').value.trim();
    if (!question) throw new Error('请先输入一个问题。');
    setBusy(true, '正在生成英文检索词…');
    const { query, ...metadata } = await api('/api/rewrite', { question });
    rememberQuery(question, query, { source: 'auto', ...metadata });
    message(`英文词已生成：${query}。本次用量 ${metadata.usage?.total_tokens ?? '未知'} tokens。`);
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}

async function ask() {
  try {
    const payload = input();
    setBusy(true, '正在检索证据并请求 DeepSeek，可能需要几十秒…');
    const data = await api('/api/ask', payload);
    rememberQuery(payload.question, data.english_query, data.query_metadata);
    const trace = data.trace;
    renderResults({ [trace.context_policy === 'targeted_window' ? 'targeted_window' : trace.strategy]: trace.context_policy === 'targeted_window' ? trace.selected_chunks : trace.candidates }, payload.context_k);
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
    message(`回答已保存。检索词来源：${querySource(data.query_metadata)}。请核对引用与结论。`);
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}

function querySource(metadata) {
  return { auto: 'DeepSeek 自动生成', manual: '人工填写', original_question: '原问题' }[metadata.source];
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
    detail.append(el('summary', '', `[${trace.result.sources.find(source => source.chunk_id === item.id)?.number ?? '?'}] ${item.heading_path.join(' › ')} · ${item.source_path} ${sourceLocation(item)}`),
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
      card.append(head, el('p', '', trace.question), el('small', '', `状态 ${trace.status || 'completed'}${trace.failure_stage ? ` · 失败环节 ${trace.failure_stage}` : ''} · 候选 ${trace.candidates.length} · 上下文 ${trace.selected_chunk_ids.length} · 引用编号 ${trace.result.citation_numbers_valid ? '有效' : '待检查'}`));
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
  $('#rewrite-btn').addEventListener('click', rewrite);
  $('#ask-btn').addEventListener('click', ask);
  $('#refresh-traces').addEventListener('click', loadTraces);
  $('#scenario-select').addEventListener('change', event => {
    const url = new URL(window.location.href);
    url.searchParams.set('scenario', event.target.value);
    window.location.assign(url);
  });
  $('#open-local-btn').addEventListener('click', () => {
    $('#scenario-select').value = 'local-docs';
    $('#scenario-select').dispatchEvent(new Event('change'));
  });
  $('#import-btn').addEventListener('click', async () => {
    const file = $('#import-file').files?.[0];
    const target = $('#import-message');
    if (!file) { target.textContent = '请先选择 .md、.mdx 或 .pdf 文件。'; return; }
    const isPdf = /\.pdf$/i.test(file.name);
    if ((!isPdf && !/\.mdx?$/i.test(file.name)) || file.size > (isPdf ? 8 : 1) * 1024 * 1024) {
      target.textContent = '仅支持不超过 1 MB 的 Markdown/MDX，或不超过 8 MB 的文本型 PDF。'; return;
    }
    const button = $('#import-btn');
    button.disabled = true;
    target.textContent = '正在导入、切块并建立索引…';
    try {
      const result = await api('/api/import', {
        filename: file.name, content: isPdf ? null : await file.text(),
        pdf_base64: isPdf ? await fileBase64(file) : null,
        replace: $('#replace-file').checked
      });
      const sparse = result.sparse_pages?.length ? `；第 ${result.sparse_pages.join('、')} 页文字不足，可能需要 OCR` : '';
      sessionStorage.setItem('raglab-import-result', result.vector_error
        ? `已导入 ${file.name}，BM25 索引就绪；E5 建库失败：${result.vector_error}${sparse}`
        : `已导入 ${file.name}，共 ${result.chunks} 个知识块，BM25 与 E5 索引已更新${sparse}。`);
      window.location.hash = 'sources';
      window.location.reload();
    } catch (error) { target.textContent = `导入失败：${error.message}`; }
    finally { button.disabled = false; }
  });
  $('#strategy').addEventListener('change', () => { $('#subquery-field').hidden = $('#strategy').value !== 'decomposed'; });
  $('#strategy').dispatchEvent(new Event('change'));
  $('#sample-select').addEventListener('change', event => {
    const item = state.examples.find(example => example.id === event.target.value);
    state.activeExample = item || null;
    state.queryRewrite = null;
    if (item) { $('#question').value = item.question; $('#english-query').value = item.english_query; $('#subqueries').value = (item.subqueries || []).join('\n'); }
  });
  $('#question').addEventListener('input', () => { if (state.queryRewrite) $('#english-query').value = ''; state.activeExample = null; state.queryRewrite = null; $('#sample-select').value = ''; });
  $('#english-query').addEventListener('input', () => { state.queryRewrite = null; });
  $('#subqueries').addEventListener('input', () => { state.activeExample = null; $('#sample-select').value = ''; });
  try {
    const config = await api('/api/config');
    state.config = config;
    state.keyAvailable = config.status.deepseek_key_set;
    state.examples = config.examples;
    $('#compare-btn').disabled = !config.status.vector_ready;
    $('#compare-btn').title = config.status.vector_ready ? '' : '三路对比需要 E5 向量索引';
    $('#strategy').value = config.retrieval.strategy;
    $('#strategy').dispatchEvent(new Event('change'));
    $('#top-k').value = config.retrieval.top_k;
    $('#context-k').value = config.retrieval.context_k;
    $('#context-policy').value = config.retrieval.context_policy;
    $('#auto-rewrite').checked = config.retrieval.auto_rewrite;
    $('#rewrite-btn').disabled = !state.keyAvailable;
    const scenarioSelect = $('#scenario-select');
    scenarioSelect.replaceChildren();
    for (const scenario of config.scenarios) {
      const option = el('option', '', `${scenario.name} · ${scenario.version}`);
      option.value = scenario.id;
      scenarioSelect.append(option);
    }
    scenarioSelect.value = config.scenario_id;
    const sourceList = $('#source-list');
    sourceList.replaceChildren();
    for (const document of config.documents) {
      const row = el('div', 'source-doc');
      const label = el('a', '', document.name);
      label.href = document.url;
      label.target = '_blank';
      label.rel = 'noopener noreferrer';
      row.append(label, el('small', '', document.path),
                 el('span', document.available ? 'source-ready' : 'source-missing',
                    document.available ? '本地资料已就绪' : '本地资料缺失'));
      if (document.sparse_pages?.length) row.append(el('small', '', `第 ${document.sparse_pages.join('、')} 页文字不足，可能需要 OCR`));
      sourceList.append(row);
    }
    $('#source-count').textContent = `${config.documents.length} 篇 · ${config.status.source_commit.slice(0, 8)}`;
    const local = config.scenario_id === 'local-docs';
    $('#source-intro').textContent = local
      ? '下列文档只保存在本机。每次添加或替换都会生成新的资料版本和独立索引。'
      : '下列文档来自固定版本的官方仓库。切换知识库会同时切换资料、索引、题集与请求记录。';
    $('#query-source-tag').textContent = local ? '基于本地文档' : '基于固定版本文档';
    $('#open-local-btn').hidden = local;
    $('#import-panel').hidden = !local;
    $('#source-guide').textContent = local
      ? '可导入 Markdown/MDX 或可复制文字的 PDF。PDF 引用会跳到原文件页码；扫描页会提示 OCR。相同文件名可勾选替换，旧版本保留在本机。'
      : '这套官方资料固定在一个 Git 提交上。请切换到“我的本地文档”导入自己的资料，避免改动当前实验基线。';
    $('#scenario-name').textContent = config.ui.title;
    $('#scenario-icon').textContent = (config.ui.title || 'R').slice(0, 1).toUpperCase();
    $('#scenario-badge').textContent = config.ui.badge || config.ui.title;
    $('#scenario-subtitle').textContent = config.ui.subtitle || '从问题到证据，逐步检查每个知识块为什么被选中。';
    $('#question').placeholder = config.ui.question_placeholder || '请输入文档相关问题';
    $('#english-query').placeholder = config.ui.english_placeholder || 'English keywords for BM25';
    const learning = $('#learning-points');
    learning.replaceChildren();
    for (const point of (config.ui.learning_points || [])) {
      const row = el('li');
      row.append(el('span', 'check', '✓'), document.createTextNode(point));
      learning.append(row);
    }
    $('#scenario-version').textContent = config.status.source_commit.slice(0, 8) + (local ? ' · 本地资料' : ' · 固定资料');
    document.documentElement.style.setProperty('--accent', config.ui.accent || '#635bff');
    document.title = `RAG Lab · ${config.ui.title}`;
    if (config.ui.metric) {
      $('#metric-label').textContent = config.ui.metric.label;
      $('#metric-value').textContent = config.ui.metric.value;
      $('#metric-caption').textContent = config.ui.metric.caption;
      $('#metric-note').textContent = config.ui.metric.note;
      $('#metric-fill').style.width = `${Math.max(0, Math.min(100, config.ui.metric.percent))}%`;
    } else if (local) {
      $('#metric-label').textContent = '我的文档';
      $('#metric-value').textContent = String(config.documents.length);
      $('#metric-caption').textContent = '篇已导入';
      $('#metric-note').textContent = '自定义场景尚无固定评测集；请先导入资料，再逐题检查检索和引用。';
      $('#metric-fill').style.width = config.documents.length ? '100%' : '0%';
    }
    for (const item of config.examples) {
      const option = el('option', '', `${item.id} · ${item.question}`);
      option.value = item.id; $('#sample-select').append(option);
    }
    const ready = config.status.keyword_ready && config.status.vector_ready;
    $('#status-dot').classList.toggle('ready', ready);
    $('#status-line').textContent = ready ? 'BM25 与 E5 索引已就绪'
      : config.status.keyword_ready ? 'BM25 已就绪，可选建 E5 索引'
      : (local && !config.documents.length ? '尚未导入本地文档' : '索引未就绪，请先运行建库命令');
    $('#key-hint').textContent = config.status.deepseek_key_set ? 'DeepSeek 密钥已从本地环境变量读取。' : '未检测到 DeepSeek 密钥；检索实验仍可使用。';
    $('#ask-btn').disabled = !state.keyAvailable;
    $('#decompose-btn').disabled = !state.keyAvailable;
    if (config.examples.length) {
      const preferred = config.examples.find(item => item.id === config.ui.default_example) || config.examples[0];
      $('#sample-select').value = preferred.id;
      $('#sample-select').dispatchEvent(new Event('change'));
    }
    if (window.location.hash === '#sources') showTab('sources');
    const importResult = sessionStorage.getItem('raglab-import-result');
    if (importResult) { $('#import-message').textContent = importResult; sessionStorage.removeItem('raglab-import-result'); }
  } catch (error) { message(`初始化失败：${error.message}`, true); }
}

initialize();
