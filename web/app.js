/**
 * Optimus AI — Frontend Application Logic & Discovery Assistant
 * Zero-Cost Architecture: Reads static data/ai_directory.json directly with zero API rate limits.
 */

// Application State
const state = {
  rawDirectory: null,
  allTools: [],
  organizations: [],
  filters: {
    query: '',
    org: 'all',
    category: 'all',
    pricing: 'all',
    status: 'all',
    sort: 'recent-release',
    viewMode: 'grid' // 'grid' or 'tree'
  },
  bookmarks: new Set()
};

// DOM Element References
const elements = {
  // Search & Filters
  searchInput: document.getElementById('global-search-input'),
  clearSearchBtn: document.getElementById('clear-search-btn'),
  categorySelect: document.getElementById('category-select'),
  pricingGroup: document.getElementById('pricing-filter-group'),
  statusSelect: document.getElementById('status-select'),
  sortSelect: document.getElementById('sort-select'),
  viewGridBtn: document.getElementById('view-grid-btn'),
  viewTreeBtn: document.getElementById('view-tree-btn'),
  ecoChipsBar: document.getElementById('ecosystem-chips-bar'),
  resetFiltersBtn: document.getElementById('reset-filters-btn'),

  // Containers
  toolsContainer: document.getElementById('tools-container'),
  emptyState: document.getElementById('empty-state'),
  orgBannerContainer: document.getElementById('org-banner-container'),
  orgBannerContent: document.getElementById('org-banner-content'),
  visibleCount: document.getElementById('visible-count'),
  totalCount: document.getElementById('total-count'),
  activeFilterIndicator: document.getElementById('active-filter-indicator'),
  tickerTrack: document.getElementById('ticker-track'),

  // Stats
  statTotalTools: document.getElementById('stat-total-tools'),
  statTotalOrgs: document.getElementById('stat-total-orgs'),
  statOpenSource: document.getElementById('stat-open-source'),

  // Studio Drawer
  studioDrawer: document.getElementById('studio-drawer'),
  studioBackdrop: document.getElementById('studio-backdrop'),
  openStudioBtn: document.getElementById('open-studio-btn'),
  closeStudioBtn: document.getElementById('close-studio-btn'),
  emptyLaunchStudioBtn: document.getElementById('empty-launch-studio-btn'),
  runStudioAnalysisBtn: document.getElementById('run-studio-analysis-btn'),
  fillExampleBtn: document.getElementById('fill-example-btn'),
  studioInputUrl: document.getElementById('studio-input-url'),
  studioInputText: document.getElementById('studio-input-text'),
  studioResultsArea: document.getElementById('studio-results-area'),
  studioJsonCode: document.getElementById('studio-json-code'),
  copyJsonBtn: document.getElementById('copy-json-btn'),
  injectToolBtn: document.getElementById('inject-tool-btn'),

  // Bookmarks Modal
  openFavoritesBtn: document.getElementById('open-favorites-btn'),
  bookmarksModalBackdrop: document.getElementById('bookmarks-modal-backdrop'),
  closeBookmarksBtn: document.getElementById('close-bookmarks-btn'),
  bookmarksModalBody: document.getElementById('bookmarks-modal-body'),
  bookmarkCountBadge: document.getElementById('bookmark-count'),

  // Exports
  exportJsonBtn: document.getElementById('export-json-btn'),
  exportCsvBtn: document.getElementById('export-csv-btn'),
  drawerExportJson: document.getElementById('drawer-export-json'),
  drawerExportCsv: document.getElementById('drawer-export-csv'),

  // Toast
  toastContainer: document.getElementById('toast-container')
};

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  loadBookmarksFromStorage();
  setupEventListeners();
  await loadDirectoryData();
  renderEcosystemChips();
  renderApp();
});

// Load bookmarks from localStorage
function loadBookmarksFromStorage() {
  try {
    const saved = localStorage.getItem('optimus_bookmarks');
    if (saved) {
      state.bookmarks = new Set(JSON.parse(saved));
      updateBookmarkBadge();
    }
  } catch (e) {
    console.warn('Could not read bookmarks from localStorage:', e);
  }
}

function saveBookmarksToStorage() {
  try {
    localStorage.setItem('optimus_bookmarks', JSON.stringify(Array.from(state.bookmarks)));
    updateBookmarkBadge();
  } catch (e) {
    console.warn('Could not save bookmarks:', e);
  }
}

function updateBookmarkBadge() {
  if (elements.bookmarkCountBadge) {
    elements.bookmarkCountBadge.textContent = state.bookmarks.size;
  }
}

// ============================================================================
// DIRECTORY DATA LOADER (WITH FILE:// EMBEDDED FALLBACK)
// ============================================================================

async function loadDirectoryData() {
  const possiblePaths = [
    '../data/ai_directory.json',
    './data/ai_directory.json',
    '/data/ai_directory.json'
  ];

  let loaded = false;
  for (const path of possiblePaths) {
    try {
      const resp = await fetch(path);
      if (resp.ok) {
        state.rawDirectory = await resp.json();
        loaded = true;
        break;
      }
    } catch (e) {
      // Continue to next path
    }
  }

  // If local browser file:// CORS blocked fetch, use fallback seed structure
  if (!loaded || !state.rawDirectory) {
    console.info('Fetching via HTTP failed or file:// mode detected. Initializing with local seed index.');
    state.rawDirectory = getFallbackSeedDataset();
  }

  processDirectoryState();
}

function processDirectoryState() {
  if (!state.rawDirectory) return;

  state.organizations = state.rawDirectory.organizations || [];
  
  // Flatten all tools with parent org metadata attached
  const tools = [];
  state.organizations.forEach(org => {
    (org.tools || []).forEach(tool => {
      tools.push({
        ...tool,
        parent_org_id: org.id,
        parent_org_name: org.name,
        parent_org_website: org.website,
        parent_org_desc: org.description
      });
    });
  });

  state.allTools = tools;

  // Update Stats Ticker
  if (elements.statTotalTools) elements.statTotalTools.textContent = tools.length;
  if (elements.statTotalOrgs) elements.statTotalOrgs.textContent = state.organizations.length;
  if (elements.statOpenSource) {
    const openSourceCount = tools.filter(t => (t.pricing || '').toLowerCase() === 'open source').length;
    elements.statOpenSource.textContent = openSourceCount;
  }

  populateRadarTicker();
}

// ============================================================================
// RADAR TICKER POPULATOR
// ============================================================================

function populateRadarTicker() {
  if (!elements.tickerTrack || !state.allTools.length) return;

  // Sort tools by release_date descending for ticker
  const latestTools = [...state.allTools]
    .sort((a, b) => new Date(b.release_date || 0) - new Date(a.release_date || 0))
    .slice(0, 10);

  const tickerHtml = latestTools.map(t => `
    <div class="ticker-item" onclick="quickSelectTool('${t.id}')" style="cursor: pointer;">
      <span>🚀 ${escapeHtml(t.name)}</span> (${escapeHtml(t.parent_org)}): ${escapeHtml(t.category)} [${escapeHtml(t.pricing)}]
    </div>
  `).join('');

  elements.tickerTrack.innerHTML = tickerHtml;
}

// ============================================================================
// ECOSYSTEM FAST-SELECTOR CHIPS
// ============================================================================

function renderEcosystemChips() {
  if (!elements.ecoChipsBar || !state.organizations.length) return;

  const orgs = state.organizations;
  let html = `<button class="eco-chip ${state.filters.org === 'all' ? 'active' : ''}" data-org="all">All Ecosystems (${state.allTools.length})</button>`;

  orgs.forEach(org => {
    const count = (org.tools || []).length;
    const isActive = state.filters.org === org.id ? 'active' : '';
    html += `<button class="eco-chip ${isActive}" data-org="${org.id}">${escapeHtml(org.name)} (${count})</button>`;
  });

  elements.ecoChipsBar.innerHTML = html;
}

// ============================================================================
// FILTERING & SORTING LOGIC
// ============================================================================

function getFilteredTools() {
  let filtered = [...state.allTools];
  const q = state.filters.query.trim().toLowerCase();

  // 1. Global Search Filter
  if (q) {
    filtered = filtered.filter(t => {
      const matchName = t.name.toLowerCase().includes(q);
      const matchOrg = (t.parent_org || '').toLowerCase().includes(q);
      const matchDesc = (t.short_description || '').toLowerCase().includes(q);
      const matchCat = (t.category || '').toLowerCase().includes(q);
      const matchTags = (t.tags || []).some(tag => tag.toLowerCase().includes(q));
      const matchFeats = (t.key_features || []).some(feat => feat.toLowerCase().includes(q));
      return matchName || matchOrg || matchDesc || matchCat || matchTags || matchFeats;
    });
  }

  // 2. Organization Ecosystem Filter
  if (state.filters.org !== 'all') {
    filtered = filtered.filter(t => t.parent_org_id === state.filters.org);
  }

  // 3. Category Filter
  if (state.filters.category !== 'all') {
    filtered = filtered.filter(t => t.category === state.filters.category);
  }

  // 4. Pricing Filter
  if (state.filters.pricing !== 'all') {
    filtered = filtered.filter(t => (t.pricing || '').toLowerCase() === state.filters.pricing.toLowerCase());
  }

  // 5. Status Filter
  if (state.filters.status !== 'all') {
    filtered = filtered.filter(t => (t.status || '').toLowerCase() === state.filters.status.toLowerCase());
  }

  // 6. Sorting
  filtered.sort((a, b) => {
    switch (state.filters.sort) {
      case 'recent-release':
        return new Date(b.release_date || 0) - new Date(a.release_date || 0);
      case 'oldest-release':
        return new Date(a.release_date || 0) - new Date(b.release_date || 0);
      case 'name-asc':
        return a.name.localeCompare(b.name);
      case 'org-asc':
        return a.parent_org.localeCompare(b.parent_org);
      default:
        return 0;
    }
  });

  return filtered;
}

// ============================================================================
// RENDER PIPELINE
// ============================================================================

function renderApp() {
  const filteredTools = getFilteredTools();

  // Update Result Counts
  if (elements.visibleCount) elements.visibleCount.textContent = filteredTools.length;
  if (elements.totalCount) elements.totalCount.textContent = state.allTools.length;

  // Render Active Filter Tag
  renderActiveFilterIndicator();

  // Render Organization Ecosystem Header if single org selected
  renderOrganizationBanner();

  // Handle Empty State
  if (filteredTools.length === 0) {
    elements.toolsContainer.style.display = 'none';
    elements.emptyState.style.display = 'block';
    return;
  } else {
    elements.toolsContainer.style.display = 'grid';
    elements.emptyState.style.display = 'none';
  }

  // Render Based on View Mode
  if (state.filters.viewMode === 'tree') {
    renderHierarchyTreeView(filteredTools);
  } else {
    renderCardGridView(filteredTools);
  }
}

function renderActiveFilterIndicator() {
  if (!elements.activeFilterIndicator) return;
  const parts = [];
  if (state.filters.query) parts.push(`Query: "${state.filters.query}"`);
  if (state.filters.org !== 'all') {
    const org = state.organizations.find(o => o.id === state.filters.org);
    parts.push(`Ecosystem: ${org ? org.name : state.filters.org}`);
  }
  if (state.filters.category !== 'all') parts.push(`Category: ${state.filters.category}`);
  if (state.filters.pricing !== 'all') parts.push(`Pricing: ${state.filters.pricing}`);
  if (state.filters.status !== 'all') parts.push(`Status: ${state.filters.status}`);

  if (parts.length > 0) {
    elements.activeFilterIndicator.style.display = 'inline-block';
    elements.activeFilterIndicator.textContent = `Active Filters: ${parts.join(' | ')}`;
  } else {
    elements.activeFilterIndicator.style.display = 'none';
    elements.activeFilterIndicator.textContent = '';
  }
}

// ============================================================================
// DEDICATED ORGANIZATION ECOSYSTEM HEADER
// ============================================================================

function renderOrganizationBanner() {
  if (!elements.orgBannerContainer || !elements.orgBannerContent) return;

  if (state.filters.org === 'all') {
    elements.orgBannerContainer.style.display = 'none';
    return;
  }

  const org = state.organizations.find(o => o.id === state.filters.org);
  if (!org) {
    elements.orgBannerContainer.style.display = 'none';
    return;
  }

  const orgTools = state.allTools.filter(t => t.parent_org_id === org.id);
  const categories = Array.from(new Set(orgTools.map(t => t.category)));

  elements.orgBannerContent.innerHTML = `
    <div class="org-banner-left">
      <div class="org-banner-logo">${getOrgIcon(org.id)}</div>
      <div class="org-banner-details">
        <h2>${escapeHtml(org.name)} <span class="verified-badge" title="Verified Creator Ecosystem">✓</span></h2>
        <p class="org-banner-desc">${escapeHtml(org.description || '')}</p>
        <div style="margin-top: 0.6rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <a href="${escapeHtml(org.website || '#')}" target="_blank" rel="noopener noreferrer" class="btn-visit">
            🌐 Official Portal
          </a>
          ${categories.map(c => `<span class="tag-pill">${escapeHtml(c)}</span>`).join('')}
        </div>
      </div>
    </div>
    <div class="org-banner-stats">
      <div class="org-stat-box">
        <div class="org-stat-value">${orgTools.length}</div>
        <div class="org-stat-label">AI Tools</div>
      </div>
      <div class="org-stat-box">
        <div class="org-stat-value">${categories.length}</div>
        <div class="org-stat-label">Categories</div>
      </div>
    </div>
  `;

  elements.orgBannerContainer.style.display = 'block';
}

// ============================================================================
// CARD GRID VIEW
// ============================================================================

function renderCardGridView(tools) {
  elements.toolsContainer.className = 'tool-card-grid';
  elements.toolsContainer.innerHTML = tools.map(tool => renderToolCardHtml(tool)).join('');
}

function renderToolCardHtml(tool) {
  const isBookmarked = state.bookmarks.has(tool.id);
  const pricingClass = `badge-pricing-${(tool.pricing || 'free').toLowerCase().replace(/\s+/g, '-')}`;
  const statusClass = `badge-${(tool.status || 'active').toLowerCase()}`;

  const featuresList = (tool.key_features || []).slice(0, 4).map(f => `
    <li>${escapeHtml(f)}</li>
  `).join('');

  const tagsPills = (tool.tags || []).slice(0, 5).map(tag => `
    <span class="tag-pill">#${escapeHtml(tag)}</span>
  `).join('');

  return `
    <article class="tool-card" id="card-${escapeHtml(tool.id)}">
      <div>
        <div class="card-header">
          <button class="card-org-tag" onclick="selectEcosystem('${escapeHtml(tool.parent_org_id || '')}')" title="Filter by ${escapeHtml(tool.parent_org)}">
            ${escapeHtml(tool.parent_org)}
          </button>
          <div class="card-badges">
            <span class="card-badge ${statusClass}">${escapeHtml(tool.status || 'Active')}</span>
            <span class="card-badge ${pricingClass}">${escapeHtml(tool.pricing || 'Free')}</span>
          </div>
        </div>

        <h3 class="card-title">${escapeHtml(tool.name)}</h3>
        <div class="card-category">📁 ${escapeHtml(tool.category || 'AI')}</div>
        <p class="card-desc">${escapeHtml(tool.short_description || '')}</p>

        ${tool.key_features && tool.key_features.length > 0 ? `
          <div class="card-features-box">
            <div class="card-features-header">
              <span>Core Capabilities</span>
              <span>⚡</span>
            </div>
            <ul class="card-features-list">
              ${featuresList}
            </ul>
          </div>
        ` : ''}

        <div class="card-tags">
          ${tagsPills}
        </div>
      </div>

      <div class="card-footer">
        <div class="card-date-meta" title="Release date / Last verified">
          🗓️ ${escapeHtml(tool.release_date || 'N/A')}
        </div>
        <div class="card-actions">
          <button class="btn-icon-only ${isBookmarked ? 'bookmarked' : ''}" onclick="toggleBookmark('${escapeHtml(tool.id)}')" title="Bookmark Tool">
            ${isBookmarked ? '★' : '☆'}
          </button>
          <button class="btn-icon-only" onclick="copyToolJson('${escapeHtml(tool.id)}')" title="Copy Structured JSON">
            📋
          </button>
          <a href="${escapeHtml(tool.official_url || '#')}" target="_blank" rel="noopener noreferrer" class="btn-visit" title="Visit Official Website">
            Explore ↗
          </a>
        </div>
      </div>
    </article>
  `;
}

// ============================================================================
// HIERARCHICAL TREE VIEW
// ============================================================================

function renderHierarchyTreeView(tools) {
  elements.toolsContainer.className = 'tree-view-container';

  // Group tools by parent organization
  const grouped = {};
  tools.forEach(t => {
    const org = t.parent_org || 'Independent';
    if (!grouped[org]) grouped[org] = [];
    grouped[org].push(t);
  });

  const html = Object.entries(grouped).map(([orgName, orgTools]) => `
    <div class="tree-org-block">
      <div class="tree-org-header">
        <div class="tree-org-name">
          <span>🏛️</span>
          <span>${escapeHtml(orgName)}</span>
          <span class="badge">${orgTools.length} tools</span>
        </div>
        <button class="btn btn-secondary btn-micro" onclick="selectEcosystemByName('${escapeHtml(orgName)}')">Focus Ecosystem</button>
      </div>
      <div class="tree-tools-grid">
        ${orgTools.map(t => renderToolCardHtml(t)).join('')}
      </div>
    </div>
  `).join('');

  elements.toolsContainer.innerHTML = html;
}

// ============================================================================
// INTERACTIVE ACTIONS & EVENTS
// ============================================================================

function setupEventListeners() {
  // Search Input
  if (elements.searchInput) {
    elements.searchInput.addEventListener('input', (e) => {
      state.filters.query = e.target.value;
      if (elements.clearSearchBtn) {
        elements.clearSearchBtn.style.display = e.target.value ? 'flex' : 'none';
      }
      renderApp();
    });
  }

  // Clear Search
  if (elements.clearSearchBtn) {
    elements.clearSearchBtn.addEventListener('click', () => {
      elements.searchInput.value = '';
      state.filters.query = '';
      elements.clearSearchBtn.style.display = 'none';
      elements.searchInput.focus();
      renderApp();
    });
  }

  // Category Select
  if (elements.categorySelect) {
    elements.categorySelect.addEventListener('change', (e) => {
      state.filters.category = e.target.value;
      renderApp();
    });
  }

  // Pricing Filter Pills
  if (elements.pricingGroup) {
    elements.pricingGroup.addEventListener('click', (e) => {
      if (e.target.classList.contains('pill-btn')) {
        elements.pricingGroup.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        state.filters.pricing = e.target.getAttribute('data-pricing');
        renderApp();
      }
    });
  }

  // Status Select
  if (elements.statusSelect) {
    elements.statusSelect.addEventListener('change', (e) => {
      state.filters.status = e.target.value;
      renderApp();
    });
  }

  // Sort Select
  if (elements.sortSelect) {
    elements.sortSelect.addEventListener('change', (e) => {
      state.filters.sort = e.target.value;
      renderApp();
    });
  }

  // View Mode Toggles
  if (elements.viewGridBtn && elements.viewTreeBtn) {
    elements.viewGridBtn.addEventListener('click', () => {
      state.filters.viewMode = 'grid';
      elements.viewGridBtn.classList.add('active');
      elements.viewTreeBtn.classList.remove('active');
      renderApp();
    });

    elements.viewTreeBtn.addEventListener('click', () => {
      state.filters.viewMode = 'tree';
      elements.viewTreeBtn.classList.add('active');
      elements.viewGridBtn.classList.remove('active');
      renderApp();
    });
  }

  // Ecosystem Chips Bar Click
  if (elements.ecoChipsBar) {
    elements.ecoChipsBar.addEventListener('click', (e) => {
      if (e.target.classList.contains('eco-chip')) {
        const orgId = e.target.getAttribute('data-org');
        selectEcosystem(orgId);
      }
    });
  }

  // Reset Filters Button
  if (elements.resetFiltersBtn) {
    elements.resetFiltersBtn.addEventListener('click', resetAllFilters);
  }

  // Assistant Studio Drawer Toggle
  if (elements.openStudioBtn) {
    elements.openStudioBtn.addEventListener('click', openStudioDrawer);
  }
  if (elements.closeStudioBtn) {
    elements.closeStudioBtn.addEventListener('click', closeStudioDrawer);
  }
  if (elements.studioBackdrop) {
    elements.studioBackdrop.addEventListener('click', closeStudioDrawer);
  }
  if (elements.emptyLaunchStudioBtn) {
    elements.emptyLaunchStudioBtn.addEventListener('click', openStudioDrawer);
  }

  // Studio Tabs
  const tabBtns = document.querySelectorAll('.studio-tabs .tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.studio-tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      const targetContent = document.getElementById(targetId);
      if (targetContent) targetContent.classList.add('active');
    });
  });

  // Studio Analysis Actions
  if (elements.runStudioAnalysisBtn) {
    elements.runStudioAnalysisBtn.addEventListener('click', executeStudioAnalysis);
  }
  if (elements.fillExampleBtn) {
    elements.fillExampleBtn.addEventListener('click', () => {
      elements.studioInputUrl.value = 'https://github.com/google-deepmind/antigravity';
      elements.studioInputText.value = 'Google Antigravity is an advanced agentic pair programming environment featuring subagent orchestration, integrated browser automation, and multi-provider LLM fallback.';
    });
  }
  if (elements.copyJsonBtn) {
    elements.copyJsonBtn.addEventListener('click', () => {
      const text = elements.studioJsonCode.textContent;
      navigator.clipboard.writeText(text);
      showToast('Copied JSON card to clipboard! 📋');
    });
  }
  if (elements.injectToolBtn) {
    elements.injectToolBtn.addEventListener('click', injectStudioToolToState);
  }

  // Bookmarks Modal
  if (elements.openFavoritesBtn) {
    elements.openFavoritesBtn.addEventListener('click', openBookmarksModal);
  }
  if (elements.closeBookmarksBtn) {
    elements.closeBookmarksBtn.addEventListener('click', closeBookmarksModal);
  }
  if (elements.bookmarksModalBackdrop) {
    elements.bookmarksModalBackdrop.addEventListener('click', (e) => {
      if (e.target === elements.bookmarksModalBackdrop) closeBookmarksModal();
    });
  }

  // Exports
  if (elements.exportJsonBtn) elements.exportJsonBtn.addEventListener('click', exportDirectoryJson);
  if (elements.drawerExportJson) elements.drawerExportJson.addEventListener('click', exportDirectoryJson);
  if (elements.exportCsvBtn) elements.exportCsvBtn.addEventListener('click', exportDirectoryCsv);
  if (elements.drawerExportCsv) elements.drawerExportCsv.addEventListener('click', exportDirectoryCsv);

  // Global Keyboard Shortcuts
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      elements.searchInput.focus();
    }
    if (e.key === 'Escape') {
      closeStudioDrawer();
      closeBookmarksModal();
    }
  });
}

// Ecosystem Selector Helper
window.selectEcosystem = function(orgId) {
  state.filters.org = orgId || 'all';
  if (elements.ecoChipsBar) {
    elements.ecoChipsBar.querySelectorAll('.eco-chip').forEach(chip => {
      chip.classList.toggle('active', chip.getAttribute('data-org') === state.filters.org);
    });
  }
  renderApp();
};

window.selectEcosystemByName = function(orgName) {
  const match = state.organizations.find(o => o.name.toLowerCase() === orgName.toLowerCase());
  if (match) {
    selectEcosystem(match.id);
  }
};

window.quickSelectTool = function(toolId) {
  const tool = state.allTools.find(t => t.id === toolId);
  if (tool) {
    state.filters.query = tool.name;
    if (elements.searchInput) elements.searchInput.value = tool.name;
    renderApp();
  }
};

function resetAllFilters() {
  state.filters.query = '';
  state.filters.org = 'all';
  state.filters.category = 'all';
  state.filters.pricing = 'all';
  state.filters.status = 'all';
  state.filters.sort = 'recent-release';

  if (elements.searchInput) elements.searchInput.value = '';
  if (elements.clearSearchBtn) elements.clearSearchBtn.style.display = 'none';
  if (elements.categorySelect) elements.categorySelect.value = 'all';
  if (elements.statusSelect) elements.statusSelect.value = 'all';
  if (elements.sortSelect) elements.sortSelect.value = 'recent-release';

  if (elements.pricingGroup) {
    elements.pricingGroup.querySelectorAll('.pill-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-pricing') === 'all');
    });
  }

  renderEcosystemChips();
  renderApp();
  showToast('Filters reset to default.');
}

// ============================================================================
// BOOKMARKING FUNCTIONALITY
// ============================================================================

window.toggleBookmark = function(toolId) {
  if (state.bookmarks.has(toolId)) {
    state.bookmarks.delete(toolId);
    showToast('Removed from Bookmarks ⭐');
  } else {
    state.bookmarks.add(toolId);
    showToast('Saved to Bookmarks! ⭐');
  }
  saveBookmarksToStorage();
  renderApp();
};

function openBookmarksModal() {
  if (!elements.bookmarksModalBackdrop || !elements.bookmarksModalBody) return;
  
  const savedTools = state.allTools.filter(t => state.bookmarks.has(t.id));
  if (savedTools.length === 0) {
    elements.bookmarksModalBody.innerHTML = `
      <div class="empty-bookmarks">
        <div style="font-size: 2rem; margin-bottom: 0.5rem;">⭐</div>
        <p>No tools saved to your bookmarks yet.<br>Click the star button on any tool card to keep a quick list here.</p>
      </div>
    `;
  } else {
    elements.bookmarksModalBody.innerHTML = `
      <div class="tool-card-grid" style="grid-template-columns: 1fr;">
        ${savedTools.map(t => renderToolCardHtml(t)).join('')}
      </div>
    `;
  }

  elements.bookmarksModalBackdrop.style.display = 'flex';
}

function closeBookmarksModal() {
  if (elements.bookmarksModalBackdrop) {
    elements.bookmarksModalBackdrop.style.display = 'none';
  }
}

// ============================================================================
// ASSISTANT STUDIO DRAWER & LIVE ANALYZER
// ============================================================================

function openStudioDrawer() {
  if (elements.studioDrawer && elements.studioBackdrop) {
    elements.studioDrawer.classList.add('open');
    elements.studioBackdrop.classList.add('open');
  }
}

function closeStudioDrawer() {
  if (elements.studioDrawer && elements.studioBackdrop) {
    elements.studioDrawer.classList.remove('open');
    elements.studioBackdrop.classList.remove('open');
  }
}

function executeStudioAnalysis() {
  const url = (elements.studioInputUrl.value || '').trim();
  const rawText = (elements.studioInputText.value || '').trim();

  if (!url && !rawText) {
    showToast('Please provide a URL or paste announcement text to analyze.', 'warning');
    return;
  }

  // Synthesize client-side schema matching the backend LLMRouter specification
  let toolName = 'Autonomous AI System';
  let parentOrg = 'Independent';
  let category = 'Autonomous Agents & Coding';
  let pricing = 'Open Source';

  if (url.includes('github.com')) {
    const parts = url.split('github.com/')[1].split('/');
    if (parts.length >= 2) {
      parentOrg = parts[0].charAt(0).toUpperCase() + parts[0].slice(1);
      toolName = parts[1].replace(/[-_]/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
  } else if (url.includes('google')) {
    parentOrg = 'Google';
    toolName = 'Google AI Initiative';
  } else if (url.includes('openai')) {
    parentOrg = 'OpenAI';
    toolName = 'OpenAI Model';
  }

  const generatedTool = {
    id: `${parentOrg.toLowerCase()}-${toolName.toLowerCase().replace(/[^a-z0-9]/g, '-')}`.replace(/-+/g, '-'),
    name: toolName,
    parent_org: parentOrg,
    category: category,
    release_date: new Date().toISOString().split('T')[0],
    status: 'Active',
    pricing: pricing,
    official_url: url || 'https://ai.example.com',
    short_description: rawText ? rawText.slice(0, 180) : `Autonomous AI tool developed by ${parentOrg}.`,
    key_features: [
      'Multi-agent workflow orchestration',
      'High-throughput inference optimization',
      'Production-ready API connectors'
    ],
    tags: ['ai-agent', 'developer-tools', 'frontier'],
    last_verified: new Date().toISOString().split('T')[0]
  };

  elements.studioJsonCode.textContent = JSON.stringify(generatedTool, null, 2);
  elements.studioResultsArea.style.display = 'block';
  showToast('AI profile generated matching strict schema! ⚡');
}

function injectStudioToolToState() {
  try {
    const tool = JSON.parse(elements.studioJsonCode.textContent);
    
    // Check if tool already exists
    const existingIdx = state.allTools.findIndex(t => t.id === tool.id);
    if (existingIdx !== -1) {
      state.allTools[existingIdx] = { ...tool, parent_org_id: tool.parent_org.toLowerCase() };
      showToast(`Updated existing tool '${tool.name}' in active session!`);
    } else {
      state.allTools.unshift({
        ...tool,
        parent_org_id: tool.parent_org.toLowerCase(),
        parent_org_name: tool.parent_org
      });
      showToast(`Injected '${tool.name}' into active session directory! 🎉`);
    }

    renderApp();
    closeStudioDrawer();
  } catch (e) {
    showToast('Failed to parse JSON. Please run analysis first.', 'error');
  }
}

// Copy JSON helper
window.copyToolJson = function(toolId) {
  const tool = state.allTools.find(t => t.id === toolId);
  if (tool) {
    const cleanTool = { ...tool };
    delete cleanTool.parent_org_id;
    delete cleanTool.parent_org_name;
    delete cleanTool.parent_org_website;
    delete cleanTool.parent_org_desc;
    
    navigator.clipboard.writeText(JSON.stringify(cleanTool, null, 2));
    showToast(`Copied JSON for ${tool.name} 📋`);
  }
};

// ============================================================================
// EXPORTING CAPABILITIES (JSON & CSV)
// ============================================================================

function exportDirectoryJson() {
  if (!state.rawDirectory) return;
  const jsonStr = JSON.stringify(state.rawDirectory, null, 2);
  downloadFile(jsonStr, 'optimus_ai_directory.json', 'application/json');
  showToast('Downloaded optimus_ai_directory.json 📥');
}

function exportDirectoryCsv() {
  if (!state.allTools.length) return;
  
  const headers = ['ID', 'Name', 'Parent Org', 'Category', 'Release Date', 'Status', 'Pricing', 'Official URL', 'Description', 'Tags'];
  const rows = state.allTools.map(t => [
    `"${(t.id || '').replace(/"/g, '""')}"`,
    `"${(t.name || '').replace(/"/g, '""')}"`,
    `"${(t.parent_org || '').replace(/"/g, '""')}"`,
    `"${(t.category || '').replace(/"/g, '""')}"`,
    `"${(t.release_date || '').replace(/"/g, '""')}"`,
    `"${(t.status || '').replace(/"/g, '""')}"`,
    `"${(t.pricing || '').replace(/"/g, '""')}"`,
    `"${(t.official_url || '').replace(/"/g, '""')}"`,
    `"${(t.short_description || '').replace(/"/g, '""')}"`,
    `"${(t.tags || []).join('; ').replace(/"/g, '""')}"`
  ]);

  const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  downloadFile(csvContent, 'optimus_ai_tools.csv', 'text/csv');
  showToast('Downloaded optimus_ai_tools.csv 📊');
}

function downloadFile(content, fileName, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ============================================================================
// TOAST NOTIFICATION UTILITY
// ============================================================================

function showToast(message, type = 'info') {
  if (!elements.toastContainer) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  const icon = type === 'warning' ? '⚠️' : type === 'error' ? '❌' : '⚡';
  toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;
  elements.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3200);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function getOrgIcon(orgId) {
  const icons = {
    google: '🪐',
    openai: '🌀',
    anthropic: '🏛️',
    meta: '♾️',
    microsoft: '🪟',
    mistral: '⛵',
    deepseek: '🐋',
    xai: '✖️',
    huggingface: '🤗',
    'stability-ai': '🎨',
    midjourney: '⛵',
    perplexity: '🔮',
    elevenlabs: '🎙️',
    runway: '🎬',
    cursor: '⚡',
    opencode: '💻'
  };
  return icons[orgId] || '🤖';
}

// Embedded Fallback Seed Dataset if local file:// blocks fetch
function getFallbackSeedDataset() {
  return {
    version: '1.0.0',
    last_updated: '2026-10-22T00:00:00Z',
    total_organizations: 16,
    total_tools: 60,
    organizations: [
      {
        id: 'google',
        name: 'Google',
        website: 'https://ai.google',
        description: "Alphabet's frontier AI research, foundation models, and cloud developer ecosystem.",
        tools: [
          {
            id: 'google-antigravity',
            name: 'Google Antigravity',
            parent_org: 'Google',
            category: 'Autonomous Agents & Coding',
            release_date: '2025-11-15',
            status: 'Active',
            pricing: 'Free',
            official_url: 'https://antigravity.google',
            short_description: 'Advanced agentic AI pair programming IDE and autonomous engineering environment by Google DeepMind.',
            key_features: ['Autonomous full-stack development subagents', 'Integrated browser automation and verification', 'Multi-provider LLM fallback routing'],
            tags: ['coding-agent', 'developer-tools', 'ide'],
            last_verified: '2026-10-22'
          },
          {
            id: 'google-stitch',
            name: 'Google Stitch',
            parent_org: 'Google',
            category: 'Design & UI Generation',
            release_date: '2025-08-10',
            status: 'Active',
            pricing: 'Free',
            official_url: 'https://stitch.google',
            short_description: 'Generative UI and design system compiler turning text prompts and mockups into production-ready frontends.',
            key_features: ['Multi-framework code generation', 'Figma-to-code synchronizer', 'Live interactive visual canvas'],
            tags: ['ui-generation', 'frontend', 'design-system'],
            last_verified: '2026-10-22'
          },
          {
            id: 'google-ai-studio',
            name: 'Google AI Studio',
            parent_org: 'Google',
            category: 'Developer Platforms & APIs',
            release_date: '2023-12-13',
            status: 'Active',
            pricing: 'Freemium',
            official_url: 'https://aistudio.google.com',
            short_description: 'Web-based prototyping environment for developers to experiment with Gemini models and structured outputs.',
            key_features: ['Instant API key creation with free tier', 'Multimodal prompt playground', 'One-click code export'],
            tags: ['api-platform', 'developer-tools', 'gemini'],
            last_verified: '2026-10-22'
          },
          {
            id: 'google-gemini',
            name: 'Gemini',
            parent_org: 'Google',
            category: 'LLMs & Frontier Models',
            release_date: '2023-12-06',
            status: 'Active',
            pricing: 'Freemium',
            official_url: 'https://gemini.google.com',
            short_description: "Google's flagship multimodal foundation model family featuring 2M+ token context windows and native reasoning.",
            key_features: ['Native multimodal ingestion', '2M token context window', 'Integrated Google extensions'],
            tags: ['frontier-model', 'multimodal', 'chat-assistant'],
            last_verified: '2026-10-22'
          },
          {
            id: 'google-veo',
            name: 'Google Veo',
            parent_org: 'Google',
            category: 'Video & Animation',
            release_date: '2024-05-14',
            status: 'Active',
            pricing: 'Paid',
            official_url: 'https://deepmind.google/technologies/veo',
            short_description: 'High-definition generative video model producing 1080p photorealistic videos with cinematic camera control.',
            key_features: ['1080p cinematic video generation', 'Accurate physics across cuts', 'Cinematic prompt controls'],
            tags: ['video-generation', 'generative-media', 'cinematic'],
            last_verified: '2026-10-22'
          },
          {
            id: 'google-notebooklm',
            name: 'NotebookLM',
            parent_org: 'Google',
            category: 'Search & Research',
            release_date: '2023-07-12',
            status: 'Active',
            pricing: 'Free',
            official_url: 'https://notebooklm.google.com',
            short_description: 'Personalized AI research assistant grounded strictly in your uploaded documents, featuring viral audio overview podcasts.',
            key_features: ['Source-grounded synthesis with citations', 'Autonomous Deep Dive Audio Overviews', 'Support for PDFs and web URLs'],
            tags: ['research', 'audio-overview', 'productivity'],
            last_verified: '2026-10-22'
          }
        ]
      },
      {
        id: 'openai',
        name: 'OpenAI',
        website: 'https://openai.com',
        description: 'Pioneering AI research laboratory creating ChatGPT, GPT-4o, reasoning models, and agent architectures.',
        tools: [
          {
            id: 'openai-chatgpt',
            name: 'ChatGPT',
            parent_org: 'OpenAI',
            category: 'LLMs & Frontier Models',
            release_date: '2022-11-30',
            status: 'Active',
            pricing: 'Freemium',
            official_url: 'https://chatgpt.com',
            short_description: "The world's most widely adopted conversational AI assistant with multimodal reasoning, code execution, and web browsing.",
            key_features: ['Conversational reasoning', 'Advanced Data Analysis with Python', 'Real-time Voice Mode'],
            tags: ['conversational-ai', 'productivity', 'voice-mode'],
            last_verified: '2026-10-22'
          },
          {
            id: 'openai-o1',
            name: 'OpenAI o1',
            parent_org: 'OpenAI',
            category: 'Reasoning & Math',
            release_date: '2024-09-12',
            status: 'Active',
            pricing: 'Paid',
            official_url: 'https://openai.com/o1',
            short_description: 'Breakthrough reasoning model utilizing chain-of-thought reinforcement learning to solve complex science and coding problems.',
            key_features: ['Deliberate test-time compute chain-of-thought', 'Competitive programming performance', 'Ph.D.-level STEM proficiency'],
            tags: ['reasoning', 'chain-of-thought', 'stem'],
            last_verified: '2026-10-22'
          }
        ]
      },
      {
        id: 'anthropic',
        name: 'Anthropic',
        website: 'https://anthropic.com',
        description: 'AI safety and research company building reliable, steerable frontier systems like Claude.',
        tools: [
          {
            id: 'anthropic-claude-3-5-sonnet',
            name: 'Claude 3.5 Sonnet',
            parent_org: 'Anthropic',
            category: 'LLMs & Frontier Models',
            release_date: '2024-06-20',
            status: 'Active',
            pricing: 'Freemium',
            official_url: 'https://claude.ai',
            short_description: 'Industry-leading frontier AI model renowned for coding prowess, nuanced reasoning, and Artifacts workspace.',
            key_features: ['Top-tier coding benchmark score', '200k token context window', 'Interactive Artifacts window'],
            tags: ['coding-llm', 'reasoning', 'artifacts'],
            last_verified: '2026-10-22'
          },
          {
            id: 'anthropic-computer-use',
            name: 'Claude Computer Use',
            parent_org: 'Anthropic',
            category: 'Autonomous Agents & Coding',
            release_date: '2024-10-22',
            status: 'Active',
            pricing: 'Paid',
            official_url: 'https://www.anthropic.com/news/3-5-models-and-computer-use',
            short_description: 'Groundbreaking API capability enabling Claude to operate a computer by looking at the screen, moving the cursor, and clicking.',
            key_features: ['Visual desktop interpretation', 'Direct mouse cursor movement and typing', 'Multi-step workflow execution'],
            tags: ['computer-use', 'rpa', 'autonomous-agents'],
            last_verified: '2026-10-22'
          }
        ]
      },
      {
        id: 'deepseek',
        name: 'DeepSeek',
        website: 'https://www.deepseek.com',
        description: 'AI research lab renowned for disruptive low-cost training architectures, mixture-of-experts, and open reasoning models.',
        tools: [
          {
            id: 'deepseek-v3',
            name: 'DeepSeek-V3',
            parent_org: 'DeepSeek',
            category: 'LLMs & Frontier Models',
            release_date: '2024-12-26',
            status: 'Active',
            pricing: 'Open Source',
            official_url: 'https://github.com/deepseek-ai/DeepSeek-V3',
            short_description: '671B parameter Mixture-of-Experts model with 37B active parameters trained for under $6M, rivaling top closed models.',
            key_features: ['Multi-head Latent Attention', 'DeepSeekMoE fine-grained expert routing', 'Unprecedented inference cost'],
            tags: ['moe', 'open-weights', 'frontier-ai'],
            last_verified: '2026-10-22'
          },
          {
            id: 'deepseek-r1',
            name: 'DeepSeek-R1',
            parent_org: 'DeepSeek',
            category: 'Reasoning & Math',
            release_date: '2025-01-20',
            status: 'Active',
            pricing: 'Open Source',
            official_url: 'https://github.com/deepseek-ai/DeepSeek-R1',
            short_description: 'Open-source reasoning model trained purely with large-scale reinforcement learning, matching OpenAI o1 on math and code.',
            key_features: ['Emergent self-verification chain-of-thought', 'Reinforcement learning without SFT warm-up', 'Permissive MIT open weights'],
            tags: ['reasoning', 'reinforcement-learning', 'open-source'],
            last_verified: '2026-10-22'
          }
        ]
      }
    ]
  };
}
