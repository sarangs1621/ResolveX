/**
 * ResolveX — Autonomous Enterprise Resolution & Support Intelligence
 * Pure vector SVG icons, smooth state transitions, reactive triage & telemetry
 */

const AppState = {
  activeView: 'chat',
  sessionId: 'sess_' + Math.random().toString(36).substring(2, 10),
  currentUser: { role: 'customer', email: 'customer@example.com', token: '' },
  demoUsers: {},
  escalationsCache: [],
  selectedEscalationId: null,
  crmSubTab: 'conversations',
  activeKBFilename: 'billing.md',
  firstMessageSent: false,
};

// ---------------------------------------------------------------- Bootstrap & Lifecycle
document.addEventListener('DOMContentLoaded', async () => {
  await Promise.all([
    fetchEngineHealth(),
    fetchDemoPersonas(),
    syncEscalationBadge()
  ]);

  // Periodic background telemetry & escalation sync every 12 seconds
  setInterval(() => {
    syncEscalationBadge();
  }, 12000);
});

// ---------------------------------------------------------------- Navigation & View Routing
function navigateTo(viewName) {
  AppState.activeView = viewName;

  // Update sidebar active buttons
  document.querySelectorAll('.nav-item-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.getElementById(`nav-btn-${viewName}`);
  if (activeBtn) activeBtn.classList.add('active');

  // Update breadcrumb title
  const titleMap = {
    chat: 'Live Support Portal',
    escalations: 'Escalation Triage Desk',
    crm: 'CRM & Activity Explorer',
    kb: 'Knowledge Base Studio',
    telemetry: 'Telemetry & Ops Telemetry'
  };
  const crumb = document.getElementById('topbar-crumb-title');
  if (crumb) crumb.textContent = titleMap[viewName] || 'Workspace';

  // Toggle active view panel
  document.querySelectorAll('.view-panel-section').forEach(panel => panel.classList.remove('active-panel'));
  const activePanel = document.getElementById(`panel-${viewName}`);
  if (activePanel) activePanel.classList.add('active-panel');

  // View-specific data fetching
  if (viewName === 'escalations') loadEscalationQueue('open');
  if (viewName === 'crm') {
    if (AppState.crmSubTab === 'conversations') loadCRMConversations();
    else loadCRMTickets();
  }
  if (viewName === 'kb') loadKBArticleList();
  if (viewName === 'telemetry') loadTelemetryData();
}

function syncCurrentWorkspace() {
  navigateTo(AppState.activeView);
  fetchEngineHealth();
}

// ---------------------------------------------------------------- Engine Health & Telemetry
async function fetchEngineHealth() {
  try {
    const res = await fetch('/health');
    if (res.ok) {
      const data = await res.json();
      const statusLabel = document.getElementById('label-engine-status');
      if (statusLabel) statusLabel.textContent = `${data.model} Live`;
      const badge = document.getElementById('topbar-model-badge');
      if (badge) badge.textContent = data.model;
    }
  } catch (err) {
    console.warn('Health check warning:', err);
  }
}

async function syncEscalationBadge() {
  try {
    const res = await fetch('/escalations?status=open');
    if (res.ok) {
      const data = await res.json();
      const badge = document.getElementById('sidebar-esc-count');
      if (badge) {
        badge.textContent = data.length;
        badge.style.display = data.length > 0 ? 'inline-block' : 'none';
      }
    }
  } catch (err) {
    console.warn('Escalation sync warning:', err);
  }
}

// ---------------------------------------------------------------- Persona & RBAC Switcher
async function fetchDemoPersonas() {
  try {
    const res = await fetch('/auth/demo-users');
    if (res.ok) {
      const users = await res.json();
      users.forEach(u => {
        AppState.demoUsers[u.role] = u;
      });
      onPersonaSelect('customer');
    }
  } catch (err) {
    console.warn('Failed to load personas:', err);
  }
}

function onPersonaSelect(role) {
  if (AppState.demoUsers[role]) {
    const u = AppState.demoUsers[role];
    AppState.currentUser = { role: u.role, email: u.email, token: u.token };
    const emailField = document.getElementById('chat-sender-email');
    if (emailField) emailField.value = u.email;
  } else {
    AppState.currentUser = { role: role, email: `${role}@resolvex.ai`, token: '' };
  }
  const emailText = document.getElementById('dock-user-email-text');
  if (emailText) emailText.textContent = AppState.currentUser.email;
  const badge = document.getElementById('dock-user-badge');
  if (badge) badge.title = `Active Customer Persona: ${AppState.currentUser.email} (${AppState.currentUser.role})`;
}

function simulateAttachment() {
  const input = document.getElementById('chat-input-text');
  if (!input.value.includes('[Attached: system_diagnostic_log.txt]')) {
    input.value = input.value ? `${input.value} [Attached: system_diagnostic_log.txt]` : '[Attached: system_diagnostic_log.txt] ';
    input.focus();
  }
}

function getRequestHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (AppState.currentUser.token) {
    headers['Authorization'] = `Bearer ${AppState.currentUser.token}`;
  }
  return headers;
}

// ---------------------------------------------------------------- Live Support Portal (Chat)
function submitQuickPrompt(promptText) {
  const input = document.getElementById('chat-input-text');
  input.value = promptText;
  onChatSubmit(new Event('submit'));
}

function clearChatThread() {
  AppState.sessionId = 'sess_' + Math.random().toString(36).substring(2, 10);
  const container = document.getElementById('chat-messages-container');
  container.innerHTML = `
    <div class="chat-hero-stage" id="chat-hero-greeting">
      <div class="hero-sparkle-prism">
        <svg class="svg-icon icon-lg" viewBox="0 0 24 24">
          <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>
        </svg>
      </div>
      <h2 class="hero-headline">How can ResolveX assist you today?</h2>
      <p class="hero-caption">
        Conversation cleared. Ask questions about billing, track shipments, check account quotas, or test human escalation.
      </p>
    </div>
  `;
  AppState.firstMessageSent = false;
}

async function onChatSubmit(event) {
  if (event) event.preventDefault();
  const input = document.getElementById('chat-input-text');
  const message = input.value.trim();
  if (!message) return;

  const email = document.getElementById('chat-sender-email').value.trim() || 'customer@example.com';
  const channel = document.getElementById('chat-channel-select').value || 'web';

  // Hide hero on first message
  if (!AppState.firstMessageSent) {
    const hero = document.getElementById('chat-hero-greeting');
    if (hero) hero.style.display = 'none';
    AppState.firstMessageSent = true;
  }

  // Append user bubble
  appendChatTurn('user', message);
  input.value = '';

  // Show thinking placeholder
  const placeholder = appendThinkingTurn();

  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: getRequestHeaders(),
      body: JSON.stringify({
        message: message,
        customer_email: email,
        channel: channel,
        session_id: AppState.sessionId
      })
    });

    if (placeholder && placeholder.parentNode) {
      placeholder.parentNode.removeChild(placeholder);
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      appendChatTurn('assistant', `<div style="display: inline-flex; align-items: center; gap: 8px; color: var(--accent-rose);"><svg class="svg-icon icon-sm" viewBox="0 0 24 24"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg><span>Service exception: ${escapeHtml(err.detail || 'Failed to process inquiry.')}</span></div>`);
      return;
    }

    const data = await res.json();
    appendChatTurn('assistant', data.answer, data);
    syncEscalationBadge();
  } catch (err) {
    if (placeholder && placeholder.parentNode) placeholder.parentNode.removeChild(placeholder);
    appendChatTurn('assistant', `<div style="display: inline-flex; align-items: center; gap: 8px; color: var(--accent-rose);"><svg class="svg-icon icon-sm" viewBox="0 0 24 24"><line x1="1" y1="1" x2="23" y2="23"/><path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/><path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/><path d="M10.71 5.05A16 16 0 0 1 22.58 9"/><path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg><span>Connection error: ${escapeHtml(err.message)}</span></div>`);
  }
}

function appendChatTurn(role, content, meta = null) {
  const container = document.getElementById('chat-messages-container');
  const turn = document.createElement('div');
  turn.className = `chat-bubble-turn turn-${role}`;

  // SVG Avatars (Zero Emojis)
  const avatarSvg = role === 'user' ? `
    <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
      <circle cx="12" cy="8" r="5"/>
      <path d="M20 21a8 8 0 1 0-16 0"/>
    </svg>
  ` : `
    <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
    </svg>
  `;

  // Clean formatting
  let formattedBody = escapeHtml(content)
    .replace(/\*\*(.*?)\*\*/g, '<strong style="color: white;">$1</strong>')
    .replace(/`(.*?)`/g, '<code style="background: rgba(0,0,0,0.35); padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #A5B4FC;">$1</code>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n- /g, '<br>• ');

  let richWidgetHtml = '';
  let metadataHtml = '';

  if (role === 'assistant' && meta) {
    const conf = meta.confidence !== undefined ? (meta.confidence * 100).toFixed(0) : 'N/A';
    const isEscalated = meta.escalated;
    const confClass = isEscalated ? 'tag-confidence-low' : 'tag-confidence-high';
    const confIcon = isEscalated ? `
      <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    ` : `
      <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
    `;
    const confLabel = isEscalated ? `Escalated (${conf}%)` : `Confidence ${conf}%`;

    // Rich Interactive Business Tool Cards
    if (meta.tool_calls && meta.tool_calls.length > 0) {
      for (const tc of meta.tool_calls) {
        const data = extractToolData(tc);
        if (tc.tool === 'track_shipment' && data) {
          const isDelivered = data.status === 'delivered';
          richWidgetHtml += `
            <div class="rich-widget-card">
              <div class="widget-header-strip">
                <span class="widget-badge-tag" style="color: var(--accent-indigo);">
                  <svg class="svg-icon icon-sm" viewBox="0 0 24 24"><rect width="16" height="12" x="1" y="3" rx="2"/><path d="M17 8h4l3 3v4h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
                  <span>${escapeHtml(data.carrier || 'Carrier')} Tracking</span>
                </span>
                <span class="telemetry-tag tag-confidence-high" style="font-size: 10px; text-transform: uppercase;">
                  ${escapeHtml(data.status || 'In Transit')}
                </span>
              </div>
              <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;">
                <div>
                  <span style="font-size: 11px; color: var(--text-tertiary); display: block;">Tracking Reference</span>
                  <span style="font-family: var(--font-mono); font-size: 13.5px; font-weight: 700; color: var(--text-pure);">${escapeHtml(data.tracking_number || tc.input?.tracking_number || 'FEDEX-992147')}</span>
                </div>
                <div style="text-align: right;">
                  <span style="font-size: 11px; color: var(--text-tertiary); display: block;">Estimated Delivery</span>
                  <span style="font-size: 12px; font-weight: 600; color: var(--accent-cyan);">${escapeHtml(data.estimated_delivery || 'On Schedule')}</span>
                </div>
              </div>
              <div class="tracking-progress-bar">
                <div class="progress-track-bg"></div>
                <div class="progress-track-fill" style="width: ${isDelivered ? '100%' : '65%'};"></div>
                <div class="progress-step-node active" title="Dispatched">✓</div>
                <div class="progress-step-node active" title="In Transit">●</div>
                <div class="progress-step-node ${isDelivered ? 'active' : ''}" title="Out for delivery">○</div>
                <div class="progress-step-node ${isDelivered ? 'active' : ''}" title="Delivered">○</div>
              </div>
              <div style="font-size: 11.5px; color: var(--text-secondary); background: rgba(0,0,0,0.3); padding: 8px 12px; border-radius: 6px; margin-top: 6px;">
                <strong style="color: var(--text-pure);">Route:</strong> ${escapeHtml(data.origin || 'Memphis')} → ${escapeHtml(data.destination || 'Destination')}
                ${data.checkpoints && data.checkpoints.length > 0 ? `<br><strong style="color: var(--text-pure);">Latest Checkpoint:</strong> ${escapeHtml(data.checkpoints[data.checkpoints.length - 1].activity)} (${escapeHtml(data.checkpoints[data.checkpoints.length - 1].location)})` : ''}
              </div>
            </div>
          `;
        } else if (tc.tool === 'create_support_ticket' && data) {
          richWidgetHtml += `
            <div class="rich-widget-card" style="border-left: 3px solid var(--accent-rose);">
              <div class="widget-header-strip">
                <span class="widget-badge-tag" style="color: var(--accent-rose);">
                  <svg class="svg-icon icon-sm" viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>
                  <span>Formal Support Ticket Filed</span>
                </span>
                <span class="telemetry-tag tag-confidence-low" style="font-size: 10px; text-transform: uppercase;">
                  ${escapeHtml(data.priority || 'Urgent')} Priority
                </span>
              </div>
              <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <div>
                  <span style="font-size: 11px; color: var(--text-tertiary); display: block;">Ticket Reference</span>
                  <span style="font-family: var(--font-mono); font-size: 14px; font-weight: 700; color: var(--accent-indigo);">${escapeHtml(data.ticket_ref)}</span>
                </div>
                <div style="text-align: right;">
                  <span style="font-size: 11px; color: var(--text-tertiary); display: block;">SLA Guarantee</span>
                  <span style="font-size: 12px; font-weight: 600; color: var(--accent-emerald);">&lt; 4 Hours Response</span>
                </div>
              </div>
              <p style="font-size: 12px; color: var(--text-secondary); margin-top: 8px; border-top: 1px solid var(--border-subtle); padding-top: 8px;">
                Routed to human engineering support. A dedicated support agent will contact <strong>${escapeHtml(data.customer_email || 'you')}</strong> shortly.
              </p>
            </div>
          `;
        } else if (tc.tool === 'check_order_status' && data) {
          richWidgetHtml += `
            <div class="rich-widget-card" style="border-left: 3px solid var(--accent-cyan);">
              <div class="widget-header-strip">
                <span class="widget-badge-tag" style="color: var(--accent-cyan);">
                  <svg class="svg-icon icon-sm" viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                  <span>Order ${escapeHtml(data.order_id)}</span>
                </span>
                <span class="telemetry-tag tag-confidence-high" style="font-size: 10px;">
                  ${escapeHtml(data.status || 'Verified')}
                </span>
              </div>
              <div style="display: flex; justify-content: space-between; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">
                <span>Total Amount:</span>
                <strong style="color: var(--text-pure);">${data.total_amount ? '$' + Number(data.total_amount).toFixed(2) : '$149.99'}</strong>
              </div>
              <div style="font-size: 11.5px; color: var(--text-tertiary);">
                Order Date: ${escapeHtml(data.order_date || 'Recent')} • Customer: ${escapeHtml(data.customer_email || 'Verified')}
              </div>
            </div>
          `;
        }
      }
    }

    let sourcesHtml = '';
    if (meta.sources && meta.sources.length > 0) {
      meta.sources.forEach(src => {
        sourcesHtml += `
          <span class="telemetry-tag tag-source-chip" onclick="openKBArticleFromChat('${src}')" title="View documentation source">
            <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <span>${src}</span>
          </span>
        `;
      });
    }

    let toolsHtml = '';
    if (meta.tool_calls && meta.tool_calls.length > 0) {
      const count = meta.tool_calls.length;
      toolsHtml = `
        <span class="telemetry-tag tag-tools-chip" onclick='openToolModal(${JSON.stringify(meta.tool_calls)})' title="Inspect execution details">
          <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <span>${count} Tool${count > 1 ? 's' : ''}</span>
        </span>
      `;
    }

    let csatHtml = '';
    if (meta.conversation_id) {
      csatHtml = `
        <span class="csat-rating-capsule">
          <button class="btn-csat-vote" onclick="rateInteraction(${meta.conversation_id}, 'positive', this)" title="Accurate response">
            <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
              <path d="M7 10v12"/>
              <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h3"/>
            </svg>
          </button>
          <button class="btn-csat-vote" onclick="rateInteraction(${meta.conversation_id}, 'negative', this)" title="Inaccurate response">
            <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
              <path d="M17 14V2"/>
              <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3"/>
            </svg>
          </button>
        </span>
      `;
    }

    metadataHtml = `
      <div class="assistant-telemetry-bar">
        <span class="telemetry-tag ${confClass}">${confIcon} <span>${confLabel}</span></span>
        ${sourcesHtml}
        ${toolsHtml}
        ${csatHtml}
      </div>
    `;
  }

  turn.innerHTML = `
    <div class="bubble-avatar-disc">${avatarSvg}</div>
    <div class="bubble-envelope">
      <div class="bubble-card">
        ${formattedBody}
        ${richWidgetHtml}
      </div>
      ${metadataHtml}
    </div>
  `;

  container.appendChild(turn);
  container.scrollTop = container.scrollHeight;
}

function extractToolData(tc) {
  if (!tc || !tc.result_preview) return null;
  if (typeof tc.result_preview === 'object') return tc.result_preview;
  try {
    return JSON.parse(tc.result_preview);
  } catch (e) {
    try {
      const jsonStr = tc.result_preview
        .replace(/'/g, '"')
        .replace(/True/g, 'true')
        .replace(/False/g, 'false')
        .replace(/None/g, 'null');
      return JSON.parse(jsonStr);
    } catch (e2) {
      return null;
    }
  }
}

function appendThinkingTurn() {
  const container = document.getElementById('chat-messages-container');
  const turn = document.createElement('div');
  turn.className = 'chat-bubble-turn turn-assistant';
  turn.innerHTML = `
    <div class="bubble-avatar-disc">
      <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
      </svg>
    </div>
    <div class="bubble-envelope">
      <div class="bubble-card" style="color: var(--text-tertiary); font-style: italic; display: flex; align-items: center; gap: 8px;">
        <span class="live-dot" style="background: var(--accent-indigo);"></span>
        <span>Calling tools & retrieving policy chunks...</span>
      </div>
    </div>
  `;
  container.appendChild(turn);
  container.scrollTop = container.scrollHeight;
  return turn;
}

async function rateInteraction(convId, feedback, btn) {
  try {
    const res = await fetch(`/conversations/${convId}/feedback`, {
      method: 'POST',
      headers: getRequestHeaders(),
      body: JSON.stringify({ feedback: feedback })
    });
    if (res.ok) {
      btn.classList.add('voted');
    }
  } catch (err) {
    console.warn('CSAT submission error:', err);
  }
}

function openKBArticleFromChat(filename) {
  navigateTo('kb');
  selectKBArticle(filename);
}

// ---------------------------------------------------------------- VIEW 2: Escalations Desk
async function loadEscalationQueue(status = 'open') {
  const container = document.getElementById('escalation-inbox-cards');
  container.innerHTML = `<div style="text-align: center; color: var(--text-tertiary); padding: 24px;">Loading tickets...</div>`;

  try {
    const res = await fetch(`/escalations?status=${status}`);
    const data = await res.json();
    AppState.escalationsCache = data;

    if (!data || data.length === 0) {
      container.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-tertiary); padding: 48px 24px; text-align: center; gap: 12px;">
          <div style="width: 44px; height: 44px; border-radius: 50%; background: rgba(16, 185, 129, 0.12); display: flex; align-items: center; justify-content: center; color: var(--accent-emerald); border: 1px solid rgba(16, 185, 129, 0.25);">
            <svg class="svg-icon" viewBox="0 0 24 24">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
          <span style="font-size: 13.5px; font-weight: 600; color: var(--text-primary);">Triage Queue Clear</span>
          <span style="font-size: 12px; color: var(--text-tertiary);">All customer inquiries handled with high confidence!</span>
        </div>
      `;
      document.getElementById('escalation-detail-pane').innerHTML = `
        <div style="text-align: center; margin: auto; color: var(--text-tertiary); font-size: 13px;">
          Select an escalation ticket to review details and dispatch human resolution.
        </div>
      `;
      return;
    }

    container.innerHTML = data.map(esc => {
      const confPct = ((esc.confidence || 0) * 100).toFixed(0);
      const isSelected = esc.id === AppState.selectedEscalationId;
      const timeStr = new Date(esc.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      return `
        <div class="ticket-row-item ${isSelected ? 'selected' : ''}" onclick="selectEscalationTicket(${esc.id})">
          <div class="ticket-user-header">
            <span class="ticket-email-label">${escapeHtml(esc.customer)}</span>
            <span style="font-size: 11px; color: var(--text-dim);">${timeStr}</span>
          </div>
          <div class="ticket-snippet-text">${escapeHtml(esc.question)}</div>
          <div style="display: flex; gap: 6px; align-items: center; margin-top: 4px;">
            <span class="telemetry-tag ${esc.status === 'resolved' ? 'tag-confidence-high' : 'tag-confidence-low'}" style="padding: 1px 7px; font-size: 10px;">
              ${esc.status === 'resolved' ? 'Resolved' : `${confPct}% Conf`}
            </span>
          </div>
        </div>
      `;
    }).join('');

    if (!AppState.selectedEscalationId && data.length > 0) {
      selectEscalationTicket(data[0].id);
    } else if (AppState.selectedEscalationId) {
      renderEscalationDetail(AppState.selectedEscalationId);
    }

  } catch (err) {
    container.innerHTML = `<div style="color: var(--accent-rose); padding: 20px;">Error: ${err.message}</div>`;
  }
}

function filterEscalations(status) {
  document.getElementById('filter-btn-open').classList.toggle('active', status === 'open');
  document.getElementById('filter-btn-all').classList.toggle('active', status === 'all');
  loadEscalationQueue(status);
}

function selectEscalationTicket(escId) {
  AppState.selectedEscalationId = escId;
  document.querySelectorAll('.ticket-row-item').forEach(c => c.classList.remove('selected'));
  renderEscalationDetail(escId);
}

function renderEscalationDetail(escId) {
  const detailPane = document.getElementById('escalation-detail-pane');
  const esc = AppState.escalationsCache.find(e => e.id === escId);
  if (!esc) return;

  const isResolved = esc.status === 'resolved';
  const timeStr = new Date(esc.ts * 1000).toLocaleString();
  const confPct = ((esc.confidence || 0) * 100).toFixed(0);

  detailPane.innerHTML = `
    <div class="ticket-inspect-card">
      <div class="inspect-header-line">
        <div>
          <span style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: var(--text-tertiary); letter-spacing: 0.05em;">Interaction #${esc.conversation_id || esc.id}</span>
          <h2 style="font-family: var(--font-display); font-size: 1.15rem; color: var(--text-pure); margin-top: 2px;">
            ${escapeHtml(esc.customer)}
          </h2>
          <span style="font-size: 12px; color: var(--text-tertiary);">${timeStr}</span>
        </div>
        <div>
          <span class="telemetry-tag ${isResolved ? 'tag-confidence-high' : 'tag-confidence-low'}">
            ${isResolved ? `
              <svg class="svg-icon icon-sm" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
              <span>Resolved</span>
            ` : `
              <svg class="svg-icon icon-sm" viewBox="0 0 24 24"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              <span>Low Confidence (${confPct}%)</span>
            `}
          </span>
        </div>
      </div>

      <div>
        <span style="font-size: 11.5px; font-weight: 700; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 6px; display: block;">Customer Inquired:</span>
        <div class="quote-inquiry-container">
          ${escapeHtml(esc.question)}
        </div>
      </div>

      ${esc.draft_answer ? `
        <div class="ai-reasoning-draft">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <svg class="svg-icon icon-sm" style="color: var(--accent-indigo);" viewBox="0 0 24 24">
                <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>
              </svg>
              <span style="font-size: 11.5px; font-weight: 700; text-transform: uppercase; color: var(--accent-indigo); letter-spacing: 0.04em;">AI Generated Draft</span>
            </div>
            ${!isResolved ? `<button class="btn-luxury-action" style="padding: 3px 8px; font-size: 11px;" onclick="approveDraftAnswer(${esc.id}, '${escapeQuote(esc.draft_answer)}')">Approve Draft</button>` : ''}
          </div>
          <p style="font-size: 13px; line-height: 1.6; color: #CBD5E1;">${escapeHtml(esc.draft_answer)}</p>
        </div>
      ` : ''}

      ${isResolved && esc.human_response ? `
        <div style="background: rgba(16, 185, 129, 0.1); border-left: 3px solid var(--accent-emerald); padding: 14px 18px; border-radius: 4px;">
          <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--accent-emerald);">Agent Resolution:</span>
          <p style="font-size: 13px; color: var(--text-pure); margin-top: 4px;">${escapeHtml(esc.human_response)}</p>
        </div>
      ` : ''}

      ${!isResolved ? `
        <div class="agent-compose-area">
          <span style="font-size: 12px; font-weight: 700; text-transform: uppercase; color: var(--text-secondary);">Compose Human Agent Reply:</span>
          <textarea class="agent-response-textarea" id="human-reply-input-${esc.id}" placeholder="Type your response to the customer..."></textarea>
          <div style="display: flex; gap: 10px; justify-content: flex-end;">
            <button class="btn-send-dock" onclick="resolveWithHumanReply(${esc.id})">
              Send Response & Resolve
            </button>
          </div>
        </div>
      ` : ''}
    </div>
  `;
}

async function approveDraftAnswer(escId, draftText) {
  try {
    const res = await fetch(`/escalations/${escId}/respond`, {
      method: 'POST',
      headers: getRequestHeaders(),
      body: JSON.stringify({ response: draftText || "Approved by Support Lead", status: 'resolved' })
    });
    if (res.ok) {
      loadEscalationQueue('open');
      syncEscalationBadge();
    }
  } catch (err) {
    alert(`Failed to approve draft: ${err.message}`);
  }
}

async function resolveWithHumanReply(escId) {
  const input = document.getElementById(`human-reply-input-${escId}`);
  const reply = input ? input.value.trim() : '';
  if (!reply) {
    alert('Please enter a response message.');
    return;
  }
  try {
    const res = await fetch(`/escalations/${escId}/respond`, {
      method: 'POST',
      headers: getRequestHeaders(),
      body: JSON.stringify({ response: reply, status: 'resolved' })
    });
    if (res.ok) {
      loadEscalationQueue('open');
      syncEscalationBadge();
    }
  } catch (err) {
    alert(`Resolution failed: ${err.message}`);
  }
}

// ---------------------------------------------------------------- VIEW 3: CRM & Activity
function switchCRMSubTab(subTab) {
  AppState.crmSubTab = subTab;
  const convTable = document.getElementById('crm-table-conversations-card');
  const tickTable = document.getElementById('crm-table-tickets-card');

  if (subTab === 'conversations') {
    convTable.style.display = 'block';
    tickTable.style.display = 'none';
    loadCRMConversations();
  } else {
    convTable.style.display = 'none';
    tickTable.style.display = 'block';
    loadCRMTickets();
  }
}

async function loadCRMConversations(search = '') {
  const tbody = document.getElementById('crm-conversations-tbody');
  tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-tertiary); padding: 24px;">Loading interactions...</td></tr>`;

  try {
    const url = search ? `/conversations?search=${encodeURIComponent(search)}` : '/conversations?limit=50';
    const res = await fetch(url);
    const data = await res.json();

    if (!data || data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-tertiary); padding: 24px;">No customer interactions logged.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.map(c => {
      const timeStr = new Date(c.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const confPct = ((c.confidence || 0) * 100).toFixed(0);
      const tools = c.tool_calls ? JSON.parse(c.tool_calls) : [];

      return `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 12px; color: var(--text-tertiary);">#${c.id}</td>
          <td style="color: var(--text-secondary);">${timeStr}</td>
          <td><strong style="color: var(--text-pure);">${escapeHtml(c.customer)}</strong></td>
          <td><span class="telemetry-tag tag-source-chip">${c.channel}</span></td>
          <td style="max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(c.question)}">
            ${escapeHtml(c.question)}
          </td>
          <td>
            <span class="telemetry-tag ${c.confidence >= 0.7 ? 'tag-confidence-high' : 'tag-confidence-low'}">
              ${confPct}%
            </span>
          </td>
          <td>
            <span style="font-size: 11.5px; font-weight: 600; color: ${c.escalated ? 'var(--accent-rose)' : 'var(--accent-emerald)'};">
              ${c.escalated ? 'Held for Human' : 'Auto-Resolved'}
            </span>
          </td>
          <td>
            ${c.feedback ? (c.feedback === 'positive' ? `
              <span class="telemetry-tag tag-confidence-high" style="padding: 2px 7px;">
                <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
                  <path d="M7 10v12"/>
                  <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h3"/>
                </svg>
              </span>
            ` : `
              <span class="telemetry-tag tag-confidence-low" style="padding: 2px 7px;">
                <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
                  <path d="M17 14V2"/>
                  <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3"/>
                </svg>
              </span>
            `) : '<span style="color: var(--text-dim);">—</span>'}
          </td>
          <td>
            ${tools.length > 0 ? `
              <button class="btn-luxury-action" style="padding: 2px 8px; font-size: 11px;" onclick='openToolModal(${JSON.stringify(tools)})'>
                <svg class="svg-icon icon-sm" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="3"/>
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                </svg>
                <span>${tools.length}</span>
              </button>
            ` : '<span style="color: var(--text-dim);">—</span>'}
          </td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" style="color: var(--accent-rose); padding: 20px;">Error: ${err.message}</td></tr>`;
  }
}

function onCRMSearch(query) {
  if (AppState.crmSubTab === 'conversations') {
    loadCRMConversations(query);
  }
}

async function loadCRMTickets() {
  const tbody = document.getElementById('crm-tickets-tbody');
  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-tertiary); padding: 24px;">Loading support tickets...</td></tr>`;

  try {
    const res = await fetch('/tickets');
    const tickets = await res.json();

    if (!tickets || tickets.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-tertiary); padding: 24px;">No support tickets created yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = tickets.map(t => {
      const createdStr = new Date(t.created_at * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });
      const priorityColor = t.priority === 'urgent' ? 'var(--accent-rose)' : (t.priority === 'high' ? 'var(--accent-amber)' : 'var(--text-tertiary)');

      return `
        <tr>
          <td style="font-family: var(--font-mono); font-weight: 700; color: var(--accent-indigo);">${t.ticket_ref}</td>
          <td style="color: var(--text-secondary);">${createdStr}</td>
          <td><strong style="color: var(--text-pure);">${escapeHtml(t.customer_email)}</strong></td>
          <td><span style="color: ${priorityColor}; font-weight: 700; text-transform: uppercase; font-size: 11px;">${t.priority}</span></td>
          <td style="max-width: 300px;">${escapeHtml(t.issue_description)}</td>
          <td>
            <span class="telemetry-tag ${t.status === 'resolved' ? 'tag-confidence-high' : 'tag-confidence-low'}">
              ${t.status}
            </span>
          </td>
          <td>
            ${t.status !== 'resolved' ? `
              <button class="btn-luxury-action" style="padding: 2px 8px; font-size: 11px;" onclick="resolveTicketStatus('${t.ticket_ref}')">
                Resolve
              </button>
            ` : `
              <span style="color: var(--accent-emerald); display: inline-flex; align-items: center;">
                <svg class="svg-icon icon-sm" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
              </span>
            `}
          </td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" style="color: var(--accent-rose); padding: 20px;">Error: ${err.message}</td></tr>`;
  }
}

async function resolveTicketStatus(ticketRef) {
  try {
    const res = await fetch(`/tickets/${ticketRef}`, {
      method: 'PATCH',
      headers: getRequestHeaders(),
      body: JSON.stringify({ status: 'resolved' })
    });
    if (res.ok) {
      loadCRMTickets();
    }
  } catch (err) {
    alert(`Update failed: ${err.message}`);
  }
}

// ---------------------------------------------------------------- VIEW 4: Knowledge Base Studio
async function loadKBArticleList() {
  const container = document.getElementById('kb-sidebar-articles-list');
  container.innerHTML = `<span style="font-size: 12px; color: var(--text-tertiary);">Loading...</span>`;

  try {
    const res = await fetch('/kb');
    const articles = await res.json();

    if (!articles || articles.length === 0) {
      container.innerHTML = `<span style="font-size: 12px; color: var(--text-tertiary);">No articles found.</span>`;
      return;
    }

    container.innerHTML = articles.map(art => `
      <div class="kb-tile-item ${art.filename === AppState.activeKBFilename ? 'active' : ''}" onclick="selectKBArticle('${art.filename}')">
        <div style="font-family: var(--font-display); font-weight: 600; font-size: 13px; color: var(--text-pure);">${art.title}</div>
        <div style="font-size: 11px; color: var(--text-dim); margin-top: 2px;">
          ${art.filename} • ${(art.size_bytes / 1024).toFixed(1)} KB
        </div>
      </div>
    `).join('');

    if (AppState.activeKBFilename) {
      loadKBArticleContent(AppState.activeKBFilename);
    }
  } catch (err) {
    container.innerHTML = `<span style="color: var(--accent-rose);">Error: ${err.message}</span>`;
  }
}

async function selectKBArticle(filename) {
  AppState.activeKBFilename = filename;
  const input = document.getElementById('kb-active-filename');
  if (input) input.value = filename;
  loadKBArticleList();
}

async function loadKBArticleContent(filename) {
  try {
    const res = await fetch(`/kb/${filename}`);
    if (res.ok) {
      const data = await res.json();
      const editor = document.getElementById('kb-markdown-editor');
      editor.value = data.content;
      renderKBMarkdown(data.content);
    }
  } catch (err) {
    console.warn('Error loading article:', err);
  }
}

function renderKBMarkdown(content) {
  const preview = document.getElementById('kb-markdown-preview');
  let html = escapeHtml(content)
    .replace(/^# (.*$)/gim, '<h1 style="font-size: 1.4rem; color: #FFFFFF; margin: 12px 0 8px;">$1</h1>')
    .replace(/^## (.*$)/gim, '<h2 style="font-size: 1.2rem; color: #E2E8F0; margin: 12px 0 6px;">$1</h2>')
    .replace(/^### (.*$)/gim, '<h3 style="font-size: 1.05rem; color: #CBD5E1; margin: 8px 0 4px;">$1</h3>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong style="color: white;">$1</strong>')
    .replace(/`(.*?)`/gim, '<code style="background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #A5B4FC;">$1</code>')
    .replace(/\n\n/gim, '<br><br>')
    .replace(/^\- (.*$)/gim, '<li>$1</li>');
  preview.innerHTML = html;
}

async function saveActiveArticle() {
  const filename = document.getElementById('kb-active-filename').value.trim();
  const content = document.getElementById('kb-markdown-editor').value;

  if (!filename) {
    alert('Please enter a filename.');
    return;
  }

  try {
    const res = await fetch(`/kb/${filename}`, {
      method: 'POST',
      headers: getRequestHeaders(),
      body: JSON.stringify({ content: content })
    });
    if (res.ok) {
      const data = await res.json();
      alert(`Article saved! Indexed ${data.chunk_count} chunks.`);
      AppState.activeKBFilename = filename;
      loadKBArticleList();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(`Save failed: ${err.detail || res.statusText}`);
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function deleteActiveArticle() {
  const filename = document.getElementById('kb-active-filename').value.trim();
  if (!confirm(`Delete ${filename}?`)) return;

  try {
    const res = await fetch(`/kb/${filename}`, {
      method: 'DELETE',
      headers: getRequestHeaders()
    });
    if (res.ok) {
      AppState.activeKBFilename = 'billing.md';
      loadKBArticleList();
    }
  } catch (err) {
    alert(`Delete failed: ${err.message}`);
  }
}

async function reindexKnowledgeBase() {
  try {
    const res = await fetch('/kb/reindex', { method: 'POST', headers: getRequestHeaders() });
    if (res.ok) {
      const data = await res.json();
      alert(`BM25 Index Refreshed! Total active chunks: ${data.total_chunks}`);
    }
  } catch (err) {
    alert(`Reindex error: ${err.message}`);
  }
}

function promptNewArticle() {
  const name = prompt('New article filename (e.g. shipping.md):', 'new_guide.md');
  if (name) {
    AppState.activeKBFilename = name;
    document.getElementById('kb-active-filename').value = name;
    document.getElementById('kb-markdown-editor').value = `# ${name.replace('.md', '').toUpperCase()}\n\nWrite documentation here...`;
    renderKBMarkdown(document.getElementById('kb-markdown-editor').value);
  }
}

// ---------------------------------------------------------------- VIEW 5: Telemetry & Ops
async function loadTelemetryData() {
  try {
    const [analyticsRes, metricsRes] = await Promise.all([
      fetch('/analytics'),
      fetch('/metrics')
    ]);

    if (analyticsRes.ok) {
      const a = await analyticsRes.json();
      document.getElementById('telemetry-total-interactions').textContent = a.total_conversations;
      document.getElementById('telemetry-auto-rate').textContent = `${a.automation_rate}%`;

      // Render channel traffic bars
      const chanBox = document.getElementById('chart-channel-container');
      const channels = a.channel_distribution || {};
      const maxChan = Math.max(...Object.values(channels), 1);
      chanBox.innerHTML = Object.entries(channels).map(([chan, count]) => {
        const pct = ((count / maxChan) * 100).toFixed(0);
        return `
          <div class="telemetry-bar-row">
            <span class="telemetry-key-label">${chan.toUpperCase()}</span>
            <div class="telemetry-track-line">
              <div class="telemetry-fill-gradient" style="width: ${pct}%;"></div>
            </div>
            <span class="telemetry-val-counter">${count}</span>
          </div>
        `;
      }).join('');
    }

    if (metricsRes.ok) {
      const m = await metricsRes.json();
      document.getElementById('telemetry-avg-latency').textContent = `${m.latency.avg_ms} ms`;
      document.getElementById('telemetry-uptime').textContent = `${m.uptime_seconds}s`;

      // Render tool execution bars
      const toolBox = document.getElementById('chart-tools-container');
      const tools = m.tool_executions || {};
      const maxTool = Math.max(...Object.values(tools), 1);
      toolBox.innerHTML = Object.entries(tools).map(([tool, count]) => {
        const pct = ((count / maxTool) * 100).toFixed(0);
        return `
          <div class="telemetry-bar-row">
            <span class="telemetry-key-label">${tool}</span>
            <div class="telemetry-track-line">
              <div class="telemetry-fill-gradient" style="width: ${pct}%; background: linear-gradient(90deg, var(--accent-teal), #3B82F6);"></div>
            </div>
            <span class="telemetry-val-counter">${count}</span>
          </div>
        `;
      }).join('');
    }

    await loadTelemetryAlerts();
  } catch (err) {
    console.warn('Telemetry load warning:', err);
  }
}

async function loadTelemetryAlerts() {
  const container = document.getElementById('telemetry-alerts-feed');
  try {
    const res = await fetch('/notifications');
    const notifs = await res.json();

    if (!notifs || notifs.length === 0) {
      container.innerHTML = `<div style="color: var(--text-tertiary); font-size: 12px; padding: 12px 0;">No escalation webhook alerts dispatched yet.</div>`;
      return;
    }

    container.innerHTML = notifs.map(n => {
      const timeStr = new Date(n.ts * 1000).toLocaleTimeString();
      return `
        <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-subtle); padding: 10px 14px; border-radius: var(--radius-xs); display: flex; justify-content: space-between; align-items: center; font-size: 12.5px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <svg class="svg-icon icon-sm" style="color: var(--accent-rose);" viewBox="0 0 24 24">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <strong style="color: var(--accent-rose);">${escapeHtml(n.customer)}</strong>
            <span style="color: var(--text-tertiary); margin-left: 4px;">"${escapeHtml(n.question.substring(0, 75))}..."</span>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <span class="telemetry-tag tag-confidence-low" style="padding: 1px 6px; font-size: 10px;">${(n.confidence * 100).toFixed(0)}% Conf</span>
            <span style="font-size: 11px; color: var(--text-dim);">${timeStr}</span>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = `<div style="color: var(--accent-rose);">Alert feed error: ${err.message}</div>`;
  }
}

// ---------------------------------------------------------------- Tool Inspector Modal
function openToolModal(toolCalls) {
  const modal = document.getElementById('modal-tool-inspector');
  const codeElem = document.getElementById('modal-json-content');
  codeElem.textContent = JSON.stringify(toolCalls, null, 2);
  modal.classList.add('active');
}

function closeToolModal(event) {
  const modal = document.getElementById('modal-tool-inspector');
  modal.classList.remove('active');
}

// ---------------------------------------------------------------- Sanitization
function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeQuote(text) {
  if (!text) return '';
  return String(text).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
