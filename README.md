<p align="center">
  <img src="images/header.svg" alt="Vibbo for Home Assistant" width="100%">
</p>

<p align="center">
  <a href="https://github.com/NicolasBonduel/hass-vibbo-feed/releases"><img src="https://img.shields.io/github/v/release/NicolasBonduel/hass-vibbo-feed?style=for-the-badge&color=486FDD&label=Latest%20Release" alt="Latest Release"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-486FDD?style=for-the-badge" alt="HACS"></a>
  <a href="https://github.com/NicolasBonduel/hass-vibbo-feed/blob/main/LICENSE"><img src="https://img.shields.io/github/license/NicolasBonduel/hass-vibbo-feed?style=for-the-badge&color=486FDD" alt="License"></a>
  <a href="https://github.com/NicolasBonduel/hass-vibbo-feed/stargazers"><img src="https://img.shields.io/github/stars/NicolasBonduel/hass-vibbo-feed?style=for-the-badge&color=486FDD" alt="Stars"></a>
</p>

<p align="center">
  A <a href="https://www.home-assistant.io">Home Assistant</a> integration for <a href="https://vibbo.no">Vibbo</a> — the Norwegian housing cooperative platform.<br>
  Get news, posts, and announcements from your building directly in your HA dashboard.
</p>

---

## ✨ Features

|      | Feature                 | Description                                                                        |
| ---- | ----------------------- | ---------------------------------------------------------------------------------- |
| 🔄   | **Live Sensor**   | Polls the Vibbo activity feed on a configurable interval (default 30 min)          |
| 🗂️ | **Lovelace Card** | Beautiful `vibbo-feed-card` that renders news and posts with links to vibbo.no   |
| 🔐   | **Session Login** | Paste your browser's Vibbo session once a year; HA asks for a new one when it expires |
| 📰   | **News & Posts**  | Supports both**News** (from the board) and **Posts** (from neighbours) |

---

## 📦 Installation

### HACS (Recommended)

1. Open **HACS** in your Home Assistant instance.
2. Go to **Integrations** → **⋮** (top-right) → **Custom repositories**.
3. Add this repository URL:
   ```
   https://github.com/NicolasBonduel/hass-vibbo-feed
   ```
4. Select **Integration** as the category.
5. Search for **Vibbo** and click **Install**.
6. **Restart** Home Assistant.

### Manual

1. Download the [latest release](https://github.com/NicolasBonduel/hass-vibbo-feed/releases).
2. Copy the `custom_components/vibbo` folder into your HA `config/custom_components/` directory.
3. Restart Home Assistant.

---

## ⚙️ Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Vibbo**.
3. Paste your **Vibbo session** (see below).
4. If you belong to multiple organizations, **select** which borettslag to add.

The integration discovers your organizations from the session automatically.

### Copying your Vibbo session

OBOS login now requires SMS, an identity check and a password, so the integration
reuses the session from your browser instead of logging in itself.

1. Log in at [vibbo.no](https://vibbo.no) in a desktop browser.
2. Open the developer tools (<kbd>F12</kbd>), go to the **Network** tab and reload the page.
3. Right-click any request to `vibbo.no` → **Copy** → **Copy as cURL**.
4. Paste the whole command into Home Assistant. Only the `sesid` and `sesid.sig` cookies are kept.

A pasted `Cookie` header, or `sesid=…; sesid.sig=…` copied from
**Application → Cookies** (Chrome) / **Storage → Cookies** (Firefox), works too.
The cookies are `HttpOnly`, so a console snippet or bookmarklet cannot read them.

The session lasts about a year. When it expires, Home Assistant shows a
**Re-authenticate** prompt for the integration; paste a fresh session there.

---

## 🗂️ Lovelace Card

The card is **auto-registered** when the integration loads. Just add it to any dashboard:

```yaml
type: custom:vibbo-feed-card
entity: sensor.vibbo_feed
title: Vibbo
max_items: 5
truncate: 350
```

You can also add the card through the **UI card picker** — search for *Vibbo Feed*.

### Card Options

| Option        | Type   | Default        | Description                                |
| :------------ | :----- | :------------- | :----------------------------------------- |
| `entity`    | string | *(required)* | The Vibbo Feed sensor entity               |
| `title`     | string | `Vibbo`      | Card header text (set empty to hide)       |
| `max_items` | number | `5`          | Maximum number of items to display         |
| `truncate`  | number | `350`        | Truncate body text at this character count |

---

## 📊 Sensor

The integration creates a `sensor.vibbo_feed` entity:

| Attribute                   | Description                                                           |
| :-------------------------- | :-------------------------------------------------------------------- |
| **state**             | Title of the latest feed item (truncated to 50 chars)                 |
| **items**             | Full list of activity items (same structure as the Vibbo GraphQL API) |
| **organization_slug** | Your building's URL slug, used by the card for links                  |

---

## 🧪 Development

Run the tests with [uv](https://docs.astral.sh/uv/):

```sh
uv run --no-project --python 3.13 --with-requirements requirements_test.txt pytest
```
