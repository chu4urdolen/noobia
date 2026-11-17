const agentsRoot = document.getElementById('agents');
const state = new Map();
let projectConversations = {};
async function json(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}
function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function displayTime(seconds) {
  if (!seconds) return '';
  return new Date(seconds * 1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
}
function renderEvents(agent, events) {
  const box = state.get(agent.id).feed;
  const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  const signature = JSON.stringify(events.map(e => [e.role,e.text,e.time,e.queued,e.final]));
  if (state.get(agent.id).signature === signature) return;
  state.get(agent.id).signature = signature;
  box.replaceChildren();
  if (!events.length) box.append(node('p','empty','No visible messages in this conversation yet.'));
  for (const event of events) {
    const fromForeman = event.role === 'noob' && event.text.startsWith('[Foreman Dushich] ');
    const item = node('article', `entry ${fromForeman ? 'foreman' : event.role}`);
    const prefix = fromForeman ? 'Foreman Dushich:' : event.role === 'noob' ? 'Noob:' : event.role === 'dushich' ? 'Dushich:' : event.role === 'aria' ? 'Aria:' : 'Banshee:';
    item.append(node('span','entry-name',prefix));
    if (event.final) item.append(node('span','final-tag','Final'));
    item.append(document.createTextNode(fromForeman ? event.text.slice(18) : event.text));
    item.append(node('span','entry-time',`${event.queued ? 'Queued · ' : ''}${displayTime(event.time)}`));
    box.append(item);
  }
  if (nearBottom) box.scrollTop = box.scrollHeight;
}
async function refresh(agent) {
  const panel = state.get(agent.id);
  try {
    const list = await json(`/api/conversations?agent=${encodeURIComponent(agent.id)}`);
    const selected = panel.select.value;
    panel.select.replaceChildren();
    for (const item of list) {
      const project = projectConversations[agent.id] === item.id ? 'PROJECT · ' : '';
      const status = item.active ? 'LIVE · ' : 'HISTORY · ';
      const date = item.updated ? ` · ${new Date(item.updated * 1000).toLocaleDateString()}` : '';
      const option = node('option','',item.new ? item.label : `${project}${status}${item.label}${date} · ${item.id.slice(0,8)}`);
      option.value = item.id;
      panel.select.append(option);
    }
    const preferred = list.find(x => x.id === panel.projectConversation) || list.find(x => x.id === selected) || list.find(x => x.active) || list[0];
    panel.projectConversation = null;
    if (preferred) panel.select.value = preferred.id;
    panel.badge.textContent = preferred?.active ? 'LIVE' : 'IDLE';
    panel.badge.classList.toggle('idle', !preferred?.active);
    if (preferred) {
      const events = await json(`/api/timeline?agent=${encodeURIComponent(agent.id)}&conversation=${encodeURIComponent(preferred.id)}`);
      renderEvents(agent, events);
    } else renderEvents(agent, []);
    if (panel.tokenText && preferred) {
      try {
        const tokenData = await json(`/api/tokens?agent=${encodeURIComponent(agent.id)}&conversation=${encodeURIComponent(preferred.id)}`);
        if (tokenData.available) {
          const fmt = v => (v === null || v === undefined) ? '—' : `${Number(Number(v).toFixed(2))}%`;
          const weekly = fmt(tokenData.weekly_remaining_percent);
          const hourly = fmt(tokenData.hourly_remaining_percent);
          const pct = tokenData.percent_remaining ?? 0;
          panel.tokenText.textContent = `${weekly} / ${hourly}`;
          panel.tokenFill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
          panel.tokenFill.className = 'token-fill' + (pct < 20 ? ' danger' : pct < 45 ? ' warning' : '');
        } else {
          panel.tokenText.textContent = 'Unavailable';
          panel.tokenFill.style.width = '0%';
          panel.tokenFill.className = 'token-fill';
        }
      } catch {
        panel.tokenText.textContent = '—';
        panel.tokenFill.style.width = '0%';
      }
    } else if (panel.tokenText) {
      panel.tokenText.textContent = '—';
      panel.tokenFill.style.width = '0%';
    }
    panel.notice.textContent = '';
    panel.notice.classList.remove('error');
  } catch (error) {
    panel.notice.textContent = error.message;
    panel.notice.classList.add('error');
  }
}
function addPanel(agent) {
  const panel = node('section','agent-panel');
  const head = node('div','panel-head');
  const titleWrap = node('div');
  titleWrap.append(node('p','panel-subtitle','CODING AGENT'),node('h2','panel-name',agent.name));
  const badge = node('span','panel-state idle','IDLE');
  head.append(titleWrap,badge);
  const row = node('div','conversation-row');
  const label = node('label','', 'Conversation');
  const select = node('select');
  label.htmlFor = `conversation-${agent.id}`;
  select.id = label.htmlFor;
  row.append(label,select);
  const feed = node('div','feed');
  let tokenRow = null;
  let tokenText = null;
  let tokenFill = null;
  if (agent.has_tokens) {
    tokenRow = node('div', 'token-row');
    const tokenMeta = node('div', 'token-meta');
    const tokenLabel = node('span', 'token-label', 'Weekly / Hourly');
    tokenText = node('span', 'token-value', '—');
    tokenMeta.append(tokenLabel, tokenText);
    const tokenTrack = node('div', 'token-track');
    tokenFill = node('div', 'token-fill');
    tokenTrack.append(tokenFill);
    tokenRow.append(tokenMeta, tokenTrack);
  }
  const notice = node('div','notice');
  panel.append(head,row);
  if (tokenRow) panel.append(tokenRow);
  panel.append(feed,notice);
  agentsRoot.append(panel);
  state.set(agent.id,{select,feed,badge,notice,tokenText,tokenFill,signature:'',projectConversation:projectConversations[agent.id] || null});
  select.addEventListener('change', () => refresh(agent));
  refresh(agent);
  setInterval(() => refresh(agent),3000);
}
async function refreshProjectChoices() {
  const latest = await json('/api/active-projects');
  for (const [agent, conversation] of Object.entries(latest)) {
    const panel = state.get(agent);
    if (panel && projectConversations[agent] !== conversation) panel.projectConversation = conversation;
  }
  projectConversations = latest;
}
Promise.all([json('/api/agents'), refreshProjectChoices()])
  .then(([agents]) => agents.forEach(addPanel))
  .catch(error => agentsRoot.append(node('p','empty',error.message)));
setInterval(() => refreshProjectChoices().catch(() => {}),4000);
