"use strict";
const token = document.querySelector('meta[name="lessonproof-token"]').content;
const view = document.querySelector("#view");
const labels = {ready:"待确认步骤",blocked:"材料待补齐",queued:"排队中",verifying_sources:"核对课程来源",running:"正在隔离试跑",reviewing:"AI 正在审阅",needs_review:"发现待处理问题",awaiting_approval:"待教师审核",approved:"已审核",delivered:"已交付",error:"本次未完成",interrupted:"试跑已中断"};
const activePhases = ["queued","verifying_sources","running","reviewing"];
const samples = [
  {id:"numpy-data",icon:"▥",type:"01 · 数据分析",title:"数组数据读取与统计",text:"从一份 CSV 开始，确认学生能得到正确的数组和统计结果。",footer:"Software Carpentry · 3 步"},
  {id:"expected-index-error",icon:"[!]",type:"02 · 教学预期报错",title:"读懂列表越界的错误信息",text:"有些错误正是教学的一部分。看看 AI 能不能保留这个练习。",footer:"Software Carpentry · 2 步"},
  {id:"pandas-error-version",icon:"⇄",type:"03 · 历史版本问题",title:"缺失值与整数转换",text:"代码能跑，讲义却可能过时。寻找一处真实的版本变化。",footer:"Data Carpentry · 3 步"}
];
let currentJob = null, currentTab = "lesson", timer = null, pageGeneration = 0, busy = false, toastTimer;
let detailDraft = {scope:"", checks:{}, reason:"", open:{}};
const e = escapeLessonHTML;
const date = value => new Date(value).toLocaleString("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false});
const color = phase => ["needs_review","awaiting_approval","blocked"].includes(phase) ? "amber" : ["error","interrupted"].includes(phase) ? "red" : phase === "ready" ? "gray" : "";
const badge = (text, kind="") => `<span class="badge ${kind}">${e(text)}</span>`;
const button = (text, action, kind="secondary", extra="") => `<button class="btn ${kind}" data-action="${action}" ${busy?"disabled":""} ${extra}>${text}</button>`;

async function request(path, options) {
  try { return await fetch(path, options); }
  catch { throw new Error("连接不到本地工作台。请重新启动工作台后刷新页面。"); }
}

async function api(path, body, raw=false) {
  const response = await request(path, {method:body === undefined ? "GET" : "POST",headers:{"X-LessonProof-Token":token,...(body === undefined ? {} : {"Content-Type":raw?"application/zip":"application/json"})},body:body === undefined ? undefined : raw ? body : JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "操作未完成");
  return result;
}
function toast(message) {
  const element = document.querySelector("#toast");
  element.textContent = message; element.classList.add("visible");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => element.classList.remove("visible"), 6500);
}
async function download(path, filename) {
  const response = await request(path,{headers:{"X-LessonProof-Token":token}});
  if (!response.ok) throw new Error((await response.json()).error);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const markdown = renderLesson;
function rows(jobs, deliveries=false) {
  if (!jobs.length) return `<div class="empty"><span class="empty-icon" aria-hidden="true">▤</span><div>${deliveries?"交付好的课程，会保存在这里。":"这里会留下每一次试跑。"}<p>${deliveries?"完成试跑、教师审核并生成交付包后，即可查看和下载。":"选一套课程，开始你的第一次课前检查。"}</p></div></div>`;
  return jobs.map(job => `<div class="job-row"><div><a href="#job/${job.id}"><h3>${e(job.title)}</h3></a><small>版本 ${job.revision+1} · ${job.id.slice(0,8)}</small></div>${badge(labels[job.phase]||job.phase,color(job.phase))}<time>${date(job.created_at)}</time><a href="#job/${job.id}">查看 →</a></div>`).join("");
}
function renderHome(jobs, deliveries=false) {
  view.innerHTML=`<div class="page"><div class="page-heading"><div><p class="eyebrow">${deliveries?"COURSE DELIVERY":"READY BEFORE CLASS"}</p><h1>${deliveries?"每一份交付，都有据可查。":"把问题留在课前。"}</h1><p>${deliveries?"查看教师批准的课程版本、交付文件和回读结果。":"导入课程，让 AI 沿着学生的路径走一遍。"}</p></div>${button('<span class="plus">+</span> 导入课程',"upload","primary")}</div>
  ${deliveries ? "" : `<section class="hero"><div><div class="eyebrow">从这三节小课开始</div><h2>一节课，一次有依据的试跑。</h2><p>读材料、看结果、审修订。你负责教学判断，<br>LessonProof 帮你把每一步的证据留好。</p><span class="hero-tag">公开课程来源 · 独立验收标准 · 教师审核</span></div><div class="hero-art" aria-hidden="true"><div class="art-page back"></div><div class="art-page"><i></i><i></i><i></i><i></i></div><div class="art-check">✓</div></div></section>
  <div class="section-heading"><h2>选一套课程，开始试跑</h2><span>3 套公开课程 · 每次生成独立副本</span></div><section class="samples">${samples.map(sample=>`<article class="sample-card"><div class="sample-top"><span class="course-icon" aria-hidden="true">${sample.icon}</span><span class="sample-type">${sample.type}</span></div><h3>${sample.title}</h3><p>${sample.text}</p><div class="sample-footer"><small>${sample.footer}</small><button data-action="sample" data-sample="${sample.id}">开始试跑 <span aria-hidden="true">↗</span></button></div></article>`).join("")}</section>`}
  <div class="section-heading"><h2>${deliveries?"已交付课程":"最近的试跑"}</h2><span>${jobs.length} 条记录</span></div><section class="list-card">${rows(jobs,deliveries)}</section><p class="footnote">${deliveries?"交付记录保存在本机。打开记录可下载课程包，并切换到课程阅读页核对内容。":"支持导入符合课程包格式的 ZIP（16 MiB 以内）。讲义、Notebook、数据和验收标准放在包内；点击“导入课程”查看格式说明。"}</p></div>`;
}
function workflow(job) {
  const positions={blocked:0,ready:1,queued:1,verifying_sources:1,running:1,reviewing:2,needs_review:2,awaiting_approval:3,approved:3,delivered:4,error:1,interrupted:1};
  const pos=positions[job.phase]??0;
  return '<div class="workflow" aria-label="课程处理进度">'+["材料检查","课程试跑","问题修订","教师审核","课程交付"].map((label,i)=>`${i?'<span class="workflow-line" aria-hidden="true"></span>':""}<span class="workflow-item ${i<pos?"done":i===pos?"current":""}"><i>${i<pos?"✓":i+1}</i>${label}</span>`).join("")+"</div>";
}
function statusPanel(job) {
  const messages={ready:["材料齐了，确认步骤后开始。","请阅读讲义和步骤，特别留意用于教学的预期报错。"],blocked:["先把材料补齐。","下方列出材料检查发现的问题，修正课程包后重新导入。"],queued:["已加入本地试跑队列。","同一时间执行一份课程，保证本地模型与运行环境稳定。"],verifying_sources:["正在核对课程来源。","从 GitHub 读取固定版本，核对原始文件的校验值。"],running:["正在沿着课程步骤试跑。","代码在隔离环境中执行，每一步都会保留结果和错误记录。"],reviewing:["结果已返回，AI 正在核对讲义。","代码结果与教学说明分别检查，教学预期报错会被保留。"],needs_review:["有些地方，需要你看一眼。","先阅读具体问题和修改对照，再决定是否采用 AI 修订。"],awaiting_approval:["检查完成，等待你的教学判断。","结果符合验收标准，AI 未发现材料矛盾。请完成教师复核。"],approved:["这个版本已经审核通过。","生成课程交付包后，会逐文件回读，并存入本地 Git 归档。"],delivered:["课程已交付，回读一致。","现在可以从学生视角阅读，也可以下载课程包交给学生。"],error:["这次试跑尚未完成。",job.error||"已有证据已保存，可以查看后重新试跑。"],interrupted:["上次试跑中断了。",job.error]};
  const [title,text]=messages[job.phase]||[job.phase,""];
  return `<section class="status-panel ${color(job.phase)}"><span class="status-symbol" aria-hidden="true">${activePhases.includes(job.phase)?'<span class="spinner"></span>':["needs_review","blocked","error"].includes(job.phase)?"!":"✓"}</span><div><h2>${e(title)}</h2><p>${e(job.phase==="awaiting_approval"&&job.review_decision?"运行结果符合标准，你已记录无需修改的复核意见。请完成最终审核。":text)}</p></div>${job.phase==="delivered"?`<a class="btn secondary" href="/student/${job.id}" target="_blank" rel="noopener">学生视角 ↗</a>`:""}</section>`;
}
function lessonTab(job) {
  const steps=job.preflight.steps||[];
  return `<div class="info-box">下面的讲义和代码来自当前课程副本。运行时仅提供学生材料；验收标准独立保存。</div><article class="lesson-text">${markdown(job.lesson||"")}</article><h3 class="section-subtitle">确认试跑步骤</h3>${(job.notebook?.cells||[]).filter(cell=>cell.cell_type==="code").map(cell=>`<details class="code-step"><summary><span>${e(cell.id)}</span>${badge(steps.find(step=>step.id===cell.id)?.expected_outcome==="error"?"教学预期报错":"正常执行",steps.find(step=>step.id===cell.id)?.expected_outcome==="error"?"amber":"gray")}</summary><pre>${e(Array.isArray(cell.source)?cell.source.join(""):cell.source)}</pre></details>`).join("")}<details class="code-step"><summary><span>独立验收标准 · 教师可核对</span>${badge("已固定")}</summary><pre>${e(JSON.stringify(job.contract,null,2))}</pre></details>`;
}
function issuesTab(job) {
  const run=job.runs.at(-1);
  if (!run?.ai) return `<div class="empty"><div><h3>试跑后，在这里核对问题。</h3><p>AI 会把讲义与实际结果放在一起检查，并提供可定位的原文和修改建议。</p></div></div>`;
  const ai=run.ai, stale=run.version_hash!==job.version_hash;
  let html = stale?'<div class="info-box">以下为上一版本的审阅结果。当前修订版需要重新试跑。</div>':"";
  if(job.review_decision)html+=`<div class="info-box">教师已复核：${e(job.review_decision.reason)}</div>`;
  if (!ai.findings.length) html+=`<div class="good-result"><span class="large-check" aria-hidden="true">✓</span><h3>AI 未发现讲义与结果矛盾</h3><p>这是辅助审阅结论，交付前还需要你的教师审核。</p></div>`;
  html+=`<p class="result-summary">${e(ai.summary)}</p>`;
  if(job.last_diff)html+=`<details class="code-step"><summary>查看已采用的修订对照</summary><pre>${e(job.last_diff)}</pre></details>`;
  html+=ai.findings.map((finding,i)=>`<article class="finding"><h3>${i+1}. 步骤 ${e(finding.step_id)}</h3><p>${e(finding.explanation)}</p><blockquote>${e(finding.evidence_quote)}</blockquote></article>`).join("");
  if (ai.patches.length) html+=`<h3 class="section-subtitle">建议修改 · ${ai.patches.length} 处</h3><p class="muted small">确认后保存新版本，并按照原来的标准重新试跑。</p>${ai.patches.map(patch=>`<article class="patch"><header>${e(patch.file)}${patch.cell_id?" · "+e(patch.cell_id):""}</header><pre class="before">− ${e(patch.old_text)}</pre><pre class="after">+ ${e(patch.new_text)}</pre><p class="patch-reason">${e(patch.reason)}</p></article>`).join("")}`;
  if (ai.patches.length&&!stale&&job.phase==="needs_review") html+=`<label class="check-label"><input type="checkbox" data-enables="apply">我已阅读修改对照，同意采用这些修订。</label><div class="section-heading">${button("采用修订并复测","apply","primary","disabled")}</div>`;
  const failures=run.assessment?.findings.filter(f=>f.status!=="passed")||[];
  if(failures.length)html+=`<h3 class="section-subtitle">验收未通过项</h3><pre class="code-block">${e(JSON.stringify(failures,null,2))}</pre>`;
  if(run.sources?.some(source=>!source.matched))html+='<div class="error-box">部分课程来源尚未核验通过。请在“运行证据”中查看原因，网络恢复后重新试跑。</div>';
  if(!stale&&job.phase==="needs_review"&&run.assessment?.status==="passed"&&run.sources?.every(source=>source.matched))html+=`<details class="code-step"><summary>教师复核：认为这是 AI 误报？</summary><div class="review-form"><label for="review-reason">说明为什么无需修改（至少 10 字）</label><textarea id="review-reason" rows="3" maxlength="1000" placeholder="请结合讲义和运行证据说明你的判断。"></textarea><p class="footnote">意见会与当前版本一起保存。此操作不会跳过执行验收，之后仍需最终审核。</p>${button("记录复核意见","resolve","secondary","disabled")}</div></details>`;
  return html;
}
function evidenceTab(job) {
  if (!job.runs.length) return '<div class="empty"><div>试跑后会留下真实的运行记录。<p>包含环境版本、各步骤的输出、来源核验及 AI 调用记录。</p></div></div>';
  return [...job.runs].reverse().map((run,index)=>`<section><div class="section-heading"><h3>版本 ${run.revision+1} · ${index===0?"最近一次":"历史试跑"}</h3><span>${date(run.started_at)}</span></div>${run.error?`<div class="error-box">${e(run.error)}</div>`:""}<table class="record-table"><tbody><tr><th>实际运行环境</th><td>Python ${e(run.execution?.python||"尚未取得")} ${e(Object.entries(run.execution?.packages||{}).map(([k,v])=>`${k} ${v}`).join(" · "))}</td></tr><tr><th>课程执行耗时</th><td>${run.elapsed_ms?(run.elapsed_ms/1000).toFixed(2)+" 秒":"—"}</td></tr><tr><th>执行验收</th><td>${badge({passed:"符合标准",failed:"结果不符",inconclusive:"证据不足"}[run.assessment?.status]||"尚未判定",run.assessment?.status==="passed"?"":"amber")}</td></tr><tr><th>AI 审阅</th><td>${badge(run.ai_status==="completed"?"已完成":"尚未完成",run.ai_status==="completed"?"":"amber")}</td></tr><tr><th>隔离范围</th><td>网络隔离 · 输入只读 · 临时目录独立</td></tr></tbody></table>
  ${(run.execution?.steps||[]).map(step=>{const passed=run.assessment?.findings.find(f=>f.step_id===step.id)?.status==="passed";return `<article class="evidence-step"><header><span class="mono">${e(step.id)}</span>${badge(step.outcome==="error"?(passed?"教学预期报错":"执行异常"):(passed?"符合标准":"待核对"),passed?"":"amber")}</header><pre class="code-block">${e(step.outcome==="error"?`${step.error_type}: ${step.error_message}\n${step.stdout}`:step.stdout||"此步骤没有输出")}</pre>${step.stderr?`<details class="code-step"><summary>查看错误定位</summary><pre>${e(step.stderr)}</pre></details>`:""}</article>`}).join("")}
  <h3 class="section-subtitle">真实系统调用</h3><table class="record-table"><thead><tr><th>连接</th><th>操作</th><th>耗时</th><th>结果</th></tr></thead><tbody>${(run.calls||[]).map(call=>`<tr><td>${e(call.system)}</td><td>${e(call.method)}</td><td>${(call.elapsed_ms/1000).toFixed(2)} 秒</td><td>${badge(call.ok?"已完成":"未完成",call.ok?"":"amber")}</td></tr>`).join("")}</tbody></table><details class="code-step"><summary>查看来源与文件校验</summary><pre>${e(JSON.stringify(run.sources||[],null,2))}</pre></details><p class="footnote">耗时来自本次运行；尚未用于计算人工效率提升。完整请求、响应和文件校验值可下载证据包核对。</p></section>`).join('<div class="separator"></div>');
}
function deliveryTab(job) {
  return `${job.delivery?`<div class="good-result"><span class="large-check" aria-hidden="true">✓</span><h3>交付内容与审核版本一致</h3><p>课程 ZIP 与本地 Git 归档均已逐文件回读。</p></div><div class="section-heading">${button("下载课程包","download-course","primary")}<a class="btn secondary" href="/student/${job.id}" target="_blank" rel="noopener">学生视角 ↗</a></div><details class="code-step"><summary>查看交付回执与版本</summary><pre>${e(JSON.stringify(job.delivery,null,2))}</pre></details>`:'<div class="info-box">教师审核通过后，可生成课程交付包、保存本地 Git 版本，并从课程阅读页回读核对。</div>'}<h3 class="section-subtitle">处理记录</h3><ol class="history">${[...job.history].reverse().map(item=>`<li><p>${e(item.detail)}</p><time>${date(item.at)} · 版本 ${item.revision+1}</time></li>`).join("")}</ol>`;
}
function nextStep(job) {
  const run=job.runs.at(-1),canRun=!activePhases.includes(job.phase)&&job.phase!=="blocked"&&job.integrity_ok;
  let action="";
  if(job.integrity_ok===false)action=`<p>材料版本已发生变化，请导入完整课程包后重新检查。</p>${button("重新导入课程","upload","primary")}`;
  else if(job.phase==="awaiting_approval")action=`<label class="check-label"><input type="checkbox" data-enables="approve">我已核对讲义、运行结果及修订，确认适合交给学生。</label>${button("审核通过","approve","primary","disabled")}`;
  else if(job.phase==="approved")action=`<p>将当前审核版本打包，并验证归档内容。</p>${button("生成交付包","deliver","primary")}`;
  else if(job.phase==="delivered")action=`<p>课程已经准备好，可以下载后用于教学。</p>${button("下载课程包","download-course","primary")}`;
  else if(job.phase==="needs_review"&&run?.ai?.patches?.length)action=`<p>先核对具体问题和修改内容，再采用修订并复测。</p>${button("查看修改建议","show-issues","primary")}`;
  else if(canRun)action=`<label class="check-label"><input type="checkbox" data-enables="run">我已确认步骤、输入数据与教学预期报错。</label>${button(job.runs.length?"重新试跑":"确认并开始试跑","run","primary","disabled")}`;
  else action='<p>任务正在本地处理。离开本页不会中断试跑。</p>';
  return `<section class="side-panel next-step" aria-label="下一步操作"><h2>下一步</h2>${action}</section>`;
}
function aside(job) {
  const environment=job.preflight.declared_environment;
  return `<aside class="detail-aside"><section class="side-panel"><h2>这次试跑</h2><dl><div><dt>课程版本</dt><dd>版本 ${job.revision+1}</dd></div><div><dt>步骤数量</dt><dd>${job.preflight.steps?.length||0} 步</dd></div><div><dt>AI 模型</dt><dd>Qwen3 · 本地 4B</dd></div><div><dt>Python 环境</dt><dd>${e(environment?.python||"待确认")}</dd></div><div><dt>验收标准</dt><dd>${badge("原标准已固定")}</dd></div></dl><details><summary>核对验收标准指纹</summary><p class="hash mono">${e(job.contract_sha256)}</p></details><div class="separator"></div><p>每次修订都会保存新版本。教师审核绑定具体版本，修改后须重新试跑。</p>${job.runs.length?button("下载完整证据","download-evidence","secondary"):""}</section></aside>`;
}
function rememberDetail() {
  if(view.dataset.detailScope!==detailDraft.scope)return;
  view.querySelectorAll("[data-enables]").forEach(input=>detailDraft.checks[input.dataset.enables]=input.checked);
  const reason=view.querySelector("#review-reason");if(reason)detailDraft.reason=reason.value;
  const panel=view.querySelector("#detail-panel");
  if(panel)detailDraft.open[panel.getAttribute("aria-labelledby")]=[...panel.querySelectorAll("details")].map(item=>item.open);
}
function syncActions() {
  view.querySelectorAll("[data-action]").forEach(target=>{
    const checkbox=view.querySelector(`[data-enables="${target.dataset.action}"]`);
    target.disabled=busy||(checkbox?!checkbox.checked:target.dataset.action==="resolve"?(view.querySelector("#review-reason")?.value.trim().length||0)<10:false);
  });
}
function renderJob(job) {
  rememberDetail();
  const scope=[job.id,job.version_hash,job.phase,job.runs.at(-1)?.id,job.integrity_ok].join(":");
  if(scope!==detailDraft.scope)detailDraft={scope,checks:{},reason:"",open:{}};
  view.dataset.detailScope=scope;
  currentJob=job;
  view.innerHTML=`<div class="page"><a class="back" href="#home">← 返回工作台</a><div class="page-heading"><div><h1 class="detail-title">${e(job.title)}</h1><div class="detail-meta"><span>版本 ${job.revision+1}</span><span>创建于 ${date(job.created_at)}</span>${badge(labels[job.phase]||job.phase,color(job.phase))}</div></div>${button("刷新","refresh","secondary")}</div>${workflow(job)}${statusPanel(job)}${job.integrity_ok===false?'<div class="error-box">课程文件在工作台外发生变化。请重新导入，以新的材料版本开始检查。</div>':""}${job.preflight.material_status!=="ready"?`<div class="error-box">${job.preflight.findings.map(f=>`<p>${e(f.file||"课程包")}：${e(f.message)}</p>`).join("")}</div><section class="side-panel">${button("重新导入课程","upload","primary")}</section>`:`<div class="detail-grid"><section class="panel"><div class="tabs" role="tablist" aria-label="试跑详情">${[["lesson","讲义与步骤"],["issues","问题与修订"],["evidence","运行证据"],["delivery","交付记录"]].map(([id,label])=>`<button role="tab" id="tab-${id}" aria-controls="detail-panel" aria-selected="${currentTab===id}" tabindex="${currentTab===id?0:-1}" class="tab ${currentTab===id?"active":""}" data-tab="${id}">${label}</button>`).join("")}</div><div class="tab-content" id="detail-panel" role="tabpanel" aria-labelledby="tab-${currentTab}">${({lesson:lessonTab,issues:issuesTab,evidence:evidenceTab,delivery:deliveryTab})[currentTab](job)}</div></section>${nextStep(job)}${aside(job)}</div>`}</div>`;
  view.querySelectorAll("[data-enables]").forEach(input=>input.checked=!!detailDraft.checks[input.dataset.enables]);
  const reason=view.querySelector("#review-reason");if(reason)reason.value=detailDraft.reason;
  view.querySelectorAll("#detail-panel details").forEach((item,index)=>item.open=!!detailDraft.open[`tab-${currentTab}`]?.[index]);
  syncActions();
}
function renderConnections(state) {
  const card=(title,stateText,description,ok)=>`<article class="connection-card"><header><h2>${title}</h2>${badge(stateText,ok?"":"amber")}</header><p>${description}</p></article>`;
  view.innerHTML=`<div class="page"><div class="page-heading"><div><p class="eyebrow">WORKSPACE CONNECTIONS</p><h1>让材料、运行与结果连起来。</h1><p>这里区分已接通的本地能力和需要账号的下一步连接。</p></div>${button("重新检查","refresh","secondary")}</div><section class="connection-grid">${card("本地 AI · Ollama",state.ollama&&state.model_installed?"已连接":"待启动",`使用本机已有的 <code>${e(state.model)}</code>。请求和响应会留在每次试跑的证据包中。${state.ollama?"":"请先启动 Ollama，再刷新本页。"}`,state.ollama&&state.model_installed)}${card("隔离课程环境",state.runtime_prepared?"文件已就绪":"待准备","Python 3.11.15，提供标准库、NumPy 1.26.4 和 pandas 2.2.3 三套环境。每次执行会实际校验环境版本。",state.runtime_prepared)}${card("GitHub · 公开课程来源","试跑时联网核验","读取来源固定提交的文件，核对原始文件 SHA-256。联网失败会如实记录并阻止交付。",true)}${card("本地 Git · 课程归档","交付时写入并回读","审核后建立独立的课程归档，并逐文件读取核对。课程包和学生阅读页保存在本机。",true)}${card("华为云 AgentArts","待账号接入","目前使用本地模型完成真实试跑与审阅。取得开发账号后，再接入 AgentArts 并记录平台调用证据。",false)}${card("教学平台","待授权接入","当前交付到本地课程包与阅读页。取得教学平台账号和权限后，再验证远程写入、发布与回读。",false)}</section><div class="info-box connect-note">本轮可以完整验证课程检查、AI 修订、教师审核和本地交付。真实课堂节省了多少时间，需要后续人工对照试用；页面不预填效果数字。</div></div>`;
}
async function route(reset=true) {
  rememberDetail();
  const previousJob=currentJob;
  clearTimeout(timer); currentJob=null;
  if(reset) {window.scrollTo(0,0);detailDraft={scope:"",checks:{},reason:"",open:{}};}
  const generation=++pageGeneration, hash=location.hash.slice(1)||"home";
  const page=hash.startsWith("job/")?"job":hash;
  document.querySelectorAll("[data-nav]").forEach(link=>{const selected=link.dataset.nav===(page==="job"?"home":page);link.classList.toggle("active",selected);if(selected)link.setAttribute("aria-current","page");else link.removeAttribute("aria-current");});
  document.querySelector("#breadcrumb").textContent="教学空间 / "+({home:"工作台",job:"课程试跑",deliveries:"交付记录",connections:"环境与连接"}[page]||"工作台");
  view.innerHTML='<div class="loading-page"><span class="spinner" aria-hidden="true"></span>正在读取工作空间…</div>';
  try {
    if(page==="job") {
      const job=await api("/api/jobs/"+hash.slice(4)); if(generation!==pageGeneration)return;
      if(reset||previousJob?.id!==job.id)currentTab=job.phase==="needs_review"?"issues":job.phase==="delivered"?"delivery":"lesson";renderJob(job);poll(job.id,generation);
    }else if(page==="connections") {const state=await api("/api/status");if(generation===pageGeneration)renderConnections(state);}
    else {const jobs=await api("/api/jobs");if(generation===pageGeneration)renderHome(page==="deliveries"?jobs.filter(job=>job.delivery):jobs,page==="deliveries");}
  }catch(error){if(generation===pageGeneration)view.innerHTML=`<div class="page"><div class="error-box">${e(error.message)}</div>${button("刷新页面","reload","primary")} <a class="btn secondary" href="#home">返回工作台</a></div>`;}
}
function poll(id,generation) {
  if(!currentJob||!activePhases.includes(currentJob.phase))return;
  timer=setTimeout(async()=>{
    try{const job=await api("/api/jobs/"+id);if(generation!==pageGeneration)return;
      if(job.phase!==currentJob.phase||job.updated_at!==currentJob.updated_at){if(job.phase==="needs_review")currentTab="issues";renderJob(job);}poll(id,generation);
    }catch(error){toast(error.message);if(generation===pageGeneration)timer=setTimeout(()=>poll(id,generation),4000);}
  },1800);
}
view.addEventListener("change",syncActions);
view.addEventListener("input",event=>{if(event.target.id==="review-reason")syncActions();});
view.addEventListener("keydown",event=>{
  if(event.target.getAttribute("role")!=="tab"||!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
  event.preventDefault();const tabs=[...view.querySelectorAll('[role="tab"]')],index=tabs.indexOf(event.target);
  const next=event.key==="Home"?0:event.key==="End"?tabs.length-1:(index+(event.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;
  currentTab=tabs[next].dataset.tab;renderJob(currentJob);document.querySelector(`#tab-${currentTab}`).focus();
});
view.addEventListener("click",async event=>{
  const tab=event.target.closest("[data-tab]");if(tab){currentTab=tab.dataset.tab;renderJob(currentJob);document.querySelector(`#tab-${currentTab}`).focus();return;}
  const target=event.target.closest("[data-action]");if(!target||busy)return;
  const action=target.dataset.action;
  if(action==="reload"){location.reload();return;}
  if(action==="upload"){document.querySelector("#import-dialog").showModal();return;}
  if(action==="show-issues"){currentTab="issues";renderJob(currentJob);return;}
  if(action==="refresh"){await route(false);return;}
  const generation=pageGeneration, jobSnapshot=currentJob, originalText=target.textContent;
  busy=true;syncActions();view.setAttribute("aria-busy","true");
  target.textContent=action==="sample"?"正在创建…":action.startsWith("download-")?"正在准备下载…":action==="deliver"?"正在打包并核对…":"正在提交…";
  try {
    if(action==="sample") {const job=await api("/api/jobs",{sample:target.dataset.sample});if(generation===pageGeneration)location.hash="job/"+job.id;else toast("课程已创建，可从工作台打开");}
    else if(action.startsWith("download-")) {const evidence=action==="download-evidence";await download(`/api/jobs/${jobSnapshot.id}/${evidence?"evidence.zip":"course.zip"}`,evidence?"LessonProof-运行证据.zip":"LessonProof-课程包.zip");toast("下载已开始");}
    else {
      const id=jobSnapshot.id,body={version_hash:jobSnapshot.version_hash,confirmed:true};
      if(action==="resolve")body.reason=document.querySelector("#review-reason").value;
      const result=await api(`/api/jobs/${id}/${action}`,body);
      if(action==="apply") {await api(`/api/jobs/${id}/run`,{version_hash:result.version_hash,confirmed:true});toast("修订已保存，正在使用原标准复测");}
      else if(action==="approve")toast("已审核当前课程版本");
      else if(action==="deliver")toast("交付完成，逐文件回读一致");
      const job=await api("/api/jobs/"+id);if(generation===pageGeneration){if(action==="deliver")currentTab="delivery";renderJob(job);poll(id,generation);}
    }
  }catch(error){toast(error.message);if(jobSnapshot&&generation===pageGeneration&&!action.startsWith("download-")){try{const job=await api("/api/jobs/"+jobSnapshot.id);renderJob(job);poll(job.id,generation);}catch{ /* The original error remains visible; saved revisions stay on disk. */ }}}
  finally{busy=false;view.removeAttribute("aria-busy");if(target.isConnected)target.textContent=originalText;syncActions();}
});
document.querySelector("#choose-file").addEventListener("click",()=>document.querySelector("#upload").click());
document.querySelector("#import-dialog").addEventListener("click",event=>{const box=event.currentTarget.getBoundingClientRect();if(event.target===event.currentTarget&&(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom))event.currentTarget.close();});
document.querySelector("#upload").addEventListener("change",async event=>{
  const file=event.target.files[0];if(!file)return;
  if(busy){event.target.value="";return;}
  const generation=pageGeneration;
  busy=true;syncActions();document.querySelector("#import-dialog").close();
  try{if(!file.name.toLowerCase().endsWith(".zip"))throw new Error("请选择 ZIP 格式的课程包");if(file.size>16*1024*1024)throw new Error("课程 ZIP 上限为 16 MiB");toast("正在读取课程包…");const job=await api("/api/upload",file,true);if(generation===pageGeneration)location.hash="job/"+job.id;toast(generation!==pageGeneration?"课程已导入，可从工作台查看":job.phase==="blocked"?"课程已导入，请补齐列出的材料":"课程已导入，材料检查通过");}catch(error){toast(error.message);}finally{busy=false;syncActions();event.target.value="";}
});
window.addEventListener("hashchange",()=>route());
document.querySelector(".skip").addEventListener("click",event=>{event.preventDefault();document.querySelector("#content").focus();});
route();
