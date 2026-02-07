/* ───────────────────────────── Card ───────────────────────────── */

class VibboFeedCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  /* ── HA lifecycle ─────────────────────────────────────────────── */

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('Please define an entity');
    }
    this._config = {
      title: '',
      max_items: 5,
      truncate: 350,
      ...config,
    };
  }

  static getConfigElement() {
    return document.createElement('vibbo-feed-card-editor');
  }

  static getStubConfig() {
    return {
      entity: 'sensor.vibbo_feed',
      title: 'Vibbo',
      max_items: 5,
      truncate: 350,
    };
  }

  getCardSize() {
    return this._config ? Math.max(this._config.max_items * 2, 3) : 6;
  }

  /* ── Helpers ──────────────────────────────────────────────────── */

  _truncate(text, len) {
    if (!text) return 'Ingen tekst';
    return text.length <= len ? text : text.substring(0, len).trimEnd() + '…';
  }

  _esc(text) {
    if (!text) return '';
    const el = document.createElement('span');
    el.textContent = text;
    return el.innerHTML;
  }

  _fmtDate(iso) {
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now - d;
      const locale = this._hass?.language || 'en';

      if (diffMs >= 0 && diffMs < 7 * 24 * 60 * 60 * 1000) {
        const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
        const dayDiff = Math.round((startOfToday - startOfDay) / (24 * 60 * 60 * 1000));

        if (dayDiff <= 1) {
          return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(-dayDiff, 'day');
        }

        return new Intl.DateTimeFormat(locale, { weekday: 'long' }).format(d);
      }

      return new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit' }).format(d);
    } catch {
      return '';
    }
  }

  /* ── Render ──────────────────────────────────────────────────── */

  _render() {
    if (!this._hass || !this._config) return;

    const entity = this._hass.states[this._config.entity];
    if (!entity) {
      this.shadowRoot.innerHTML = `
        <ha-card>
          <div class="card-content">
            <p class="error">Entity not found: ${this._esc(this._config.entity)}</p>
          </div>
        </ha-card>`;
      return;
    }

    const items = (entity.attributes.items || []).slice(0, this._config.max_items);
    const orgSlug = entity.attributes.organization_slug || '';
    const trunc = this._config.truncate;

    let body = '';

    if (items.length === 0) {
      body = '<p class="empty">Ingen data funnet.</p>';
    } else {
      items.forEach((entry, idx) => {
        const item = entry.item;
        if (!item) return;

        const date = this._fmtDate(item.createdAt || entry.happenedAt);
        let icon, url, meta, text;

        const thumbs = item.thumbsUpCount || 0;
        const comments = item.commentsCount || 0;
        const stats = `👍 ${thumbs}  ·  💬 ${comments}`;

        if (item.__typename === 'News') {
          icon = item.pinned ? '📌' : '📢';
          url = orgSlug
            ? `https://vibbo.no/${orgSlug}/nyheter/${item.slug}`
            : '#';
          meta = `${date}  ·  Styret  ·  ${stats}`;
          text = this._truncate(item.ingress, trunc);
        } else if (item.__typename === 'Post') {
          icon = '💬';
          url = orgSlug
            ? `https://vibbo.no/${orgSlug}/oppslag/${item.slug}`
            : '#';
          const author = item.updatedBy?.firstName || 'Ukjent';
          const cat = item.category?.label;
          meta = `${date}  ·  ${this._esc(author)}${cat ? ` · ${this._esc(cat)}` : ''}  ·  ${stats}`;
          text = this._truncate(item.body, trunc);
        } else {
          return;
        }

        // Build topic tags (News only)
        const topics = (item.topics || [])
          .map(t => `<span class="tag">${this._esc(t.title)}</span>`)
          .join('');

        body += `
          <div class="item">
            <div class="item-title">
              <span class="icon">${icon}</span>
              <a href="${this._esc(url)}" target="_blank" rel="noopener noreferrer">
                ${this._esc(item.title)}
              </a>
            </div>
            <div class="meta">${meta}</div>
            ${topics ? `<div class="tags">${topics}</div>` : ''}
            <div class="body">${this._esc(text)}</div>
          </div>`;

        if (idx < items.length - 1) {
          body += '<hr>';
        }
      });
    }

    const titleText = this._config.title
      ? `<span class="title">${this._esc(this._config.title)}</span>`
      : '';
    const headerHtml = `
      <div class="card-header${this._config.title ? '' : ' no-title'}">
        ${titleText}
        <button class="refresh-btn" title="Oppdater">
          <ha-icon icon="mdi:refresh"></ha-icon>
        </button>
      </div>`;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --vibbo-spacing: 12px;
        }
        ha-card { overflow: hidden; }
        .card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px 0;
          font-size: 1.2em;
          font-weight: 500;
          color: var(--ha-card-header-color, var(--primary-text-color));
        }
        .card-header .title { flex: 1; }
        .card-header.no-title {
          justify-content: flex-end;
          padding: 8px 12px 0;
        }
        .refresh-btn {
          background: none;
          border: none;
          cursor: pointer;
          color: var(--secondary-text-color);
          padding: 4px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          transition: color 0.2s;
          --mdc-icon-size: 20px;
        }
        .refresh-btn:hover { color: var(--primary-color); }
        .refresh-btn.spinning ha-icon {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          100% { transform: rotate(360deg); }
        }
        .card-content { padding: 0 16px 16px; }
        .item { padding: var(--vibbo-spacing) 0; }

        .item-title {
          display: flex;
          align-items: baseline;
          gap: 6px;
          font-weight: 600;
          font-size: 1em;
          line-height: 1.4;
        }
        .item-title .icon { flex-shrink: 0; }
        .item-title a {
          color: var(--primary-text-color);
          text-decoration: none;
        }
        .item-title a:hover {
          text-decoration: underline;
          color: var(--primary-color);
        }

        .meta {
          font-size: 0.8em;
          color: var(--secondary-text-color);
          margin-top: 2px;
          padding-left: 26px;
        }
        .tags {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
          padding-left: 26px;
          margin-top: 4px;
        }
        .tag {
          font-size: 0.7em;
          padding: 1px 8px;
          border-radius: 10px;
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          opacity: 0.8;
        }
        .body {
          font-size: 0.9em;
          color: var(--primary-text-color);
          margin-top: 6px;
          padding-left: 26px;
          line-height: 1.5;
          opacity: 0.85;
        }

        hr {
          border: none;
          border-top: 1px solid var(--divider-color, #e0e0e0);
          margin: 0;
        }

        .empty, .error {
          color: var(--secondary-text-color);
          font-style: italic;
          padding: 16px 0;
        }
        .error { color: var(--error-color, #db4437); }
      </style>

      <ha-card>
        ${headerHtml}
        <div class="card-content">
          ${body}
        </div>
      </ha-card>`;

    // Wire up refresh button
    const btn = this.shadowRoot.querySelector('.refresh-btn');
    if (btn) {
      btn.addEventListener('click', () => {
        btn.classList.add('spinning');
        this._hass.callService('homeassistant', 'update_entity', {
          entity_id: this._config.entity,
        }).finally(() => {
          setTimeout(() => btn.classList.remove('spinning'), 1000);
        });
      });
    }
  }
}

/* ───────────────────────── Visual Editor ───────────────────────── */

// Schema-driven editor using ha-form (same pattern as Mushroom cards).
// ha-form + selectors gives us the native HA entity picker with type-to-search.
const EDITOR_SCHEMA = [
  { name: 'entity', selector: { entity: { domain: ['sensor'] } } },
  { name: 'title', selector: { text: {} } },
  {
    type: 'grid',
    name: '',
    schema: [
      { name: 'max_items', selector: { number: { min: 1, max: 50, mode: 'box' } } },
      { name: 'truncate', selector: { number: { min: 50, max: 2000, mode: 'box' } } },
    ],
  },
];

const EDITOR_LABELS = {
  entity: 'Entity',
  title: 'Title',
  max_items: 'Max items',
  truncate: 'Truncate text at (characters)',
};

class VibboFeedCardEditor extends HTMLElement {
  constructor() {
    super();
    this._rendered = false;
  }

  // Trigger lazy loading of HA form components (Mushroom / auto-entities pattern).
  // Built-in card classes are already registered; calling getConfigElement()
  // on them forces HA to import their editors which register ha-form, ha-entity-picker, etc.
  connectedCallback() {
    if (!customElements.get('ha-form') || !customElements.get('hui-card-features-editor')) {
      customElements.get('hui-tile-card')?.getConfigElement();
    }
    if (!customElements.get('ha-entity-picker')) {
      customElements.get('hui-entities-card')?.getConfigElement();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered && this._config) this._render();
    if (this._form) this._form.hass = hass;
  }

  setConfig(config) {
    this._config = { ...config };
    if (!this._rendered && this._hass) this._render();
    if (this._form) this._form.data = this._config;
  }

  _emit() {
    this.dispatchEvent(
      new CustomEvent('config-changed', {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      }),
    );
  }

  async _render() {
    this._rendered = true;
    this.innerHTML = '';

    // Wait for ha-form to be registered (with 5 s timeout)
    if (!customElements.get('ha-form')) {
      try {
        await Promise.race([
          customElements.whenDefined('ha-form'),
          new Promise((_, reject) => setTimeout(reject, 5000)),
        ]);
      } catch {
        this.innerHTML = '<p style="padding:16px">Loading editor…</p>';
        return;
      }
    }

    const form = document.createElement('ha-form');
    form.hass = this._hass;
    form.data = this._config;
    form.schema = EDITOR_SCHEMA;
    form.computeLabel = (s) => EDITOR_LABELS[s.name] || s.name;
    form.addEventListener('value-changed', (e) => {
      e.stopPropagation();
      // ha-form returns the full updated data object
      this._config = { ...this._config, ...e.detail.value };
      this._emit();
    });

    this.appendChild(form);
    this._form = form;
  }
}

/* ───────────────────────── Registration ───────────────────────── */

if (!customElements.get('vibbo-feed-card')) {
  customElements.define('vibbo-feed-card', VibboFeedCard);
}
if (!customElements.get('vibbo-feed-card-editor')) {
  customElements.define('vibbo-feed-card-editor', VibboFeedCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'vibbo-feed-card')) {
  window.customCards.push({
    type: 'vibbo-feed-card',
    name: 'Vibbo Feed',
    description: 'Displays the latest news and posts from your Vibbo community.',
    preview: true,
    documentationURL: 'https://github.com/NicolasBonduel/hass-vibbo-feed',
  });
}


