const chat = document.getElementById('foreman-chat');
const projectsRoot = document.getElementById('projects');
const helpRoot = document.getElementById('help-requests');
const foremanState = document.getElementById('foreman-state');
const notice = document.getElementById('home-notice');
const labels = {aria:'Aria', banshee:'Banshee', dushich_solo:'Dushich Solo'};

function element(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
}

function render(data) {
  foremanState.textContent = data.enabled ? (data.busy ? 'Enabled · thinking…' : 'Enabled') : 'Disabled';
  chat.replaceChildren();
  if (!data.chat.length) chat.append(element('p', 'empty', 'Foreman has not spoken yet.'));
  for (const message of data.chat) {
    const entry = element('article', `entry ${message.role === 'foreman' ? 'dushich' : 'noob'}`);
    entry.append(element('strong', 'entry-name', message.role === 'foreman' ? 'Foreman Dushich:' : 'Noob:'));
    entry.append(document.createTextNode(message.text));
    chat.append(entry);
  }

  projectsRoot.replaceChildren();
  for (const [agent, label] of Object.entries(labels)) {
    const group = element('section', 'project-group');
    group.append(element('h3', '', label));
    const assigned = data.projects.filter(project => project.agent === agent);
    if (!assigned.length) group.append(element('p', 'empty', 'No projects assigned.'));
    for (const project of assigned) {
      const item = element('article', 'project-choice');
      const selected = data.selected[agent] === project.project_name ? ' · current' : '';
      item.append(element('strong', '', project.project_name + selected));
      item.append(element('small', '', project.description || 'No description'));
      item.append(element('small', '', project.conversation_id ? `Conversation ${project.conversation_id.slice(0, 8)}` : 'No conversation linked'));
      group.append(item);
    }
    projectsRoot.append(group);
  }
  const unassigned = data.projects.filter(project => !project.agent);
  if (unassigned.length) {
    const group = element('section', 'project-group');
    group.append(element('h3', '', 'Unassigned'));
    for (const project of unassigned) group.append(element('p', '', project.project_name));
    projectsRoot.append(group);
  }

  helpRoot.replaceChildren();
  const pending = data.flags.filter(flag => !flag.response);
  if (!pending.length) helpRoot.append(element('p', 'empty', 'No human help requested.'));
  for (const flag of pending) {
    const card = element('article', 'help-card');
    card.append(element('strong', '', flag.project_name || 'Project'));
    card.append(element('p', '', flag.request || 'Help requested'));
    helpRoot.append(card);
  }
  notice.textContent = data.error || '';
  notice.classList.toggle('error', !!data.error);
}

async function refresh() {
  try {
    const response = await fetch('/api/foreman');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    render(data);
  } catch (error) {
    notice.textContent = error.message;
    notice.classList.add('error');
  }
}

refresh();
setInterval(refresh, 4000);
