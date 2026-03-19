"""Add new technology fingerprints to technologies.json"""
import json

db = json.load(open('detection/technologies.json', encoding='utf-8'))

new_techs = {
  # AD TECH
  "Google Publisher Tag": {
    "categories": ["Advertising"],
    "website": "https://developers.google.com/publisher-tag",
    "implies": [],
    "patterns": {
      "scripts": ["securepubads.g.doubleclick.net/tag/js/gpt.js", "googletagservices.com/tag/js/gpt.js"],
      "html": ["googletag.cmd", "googletag.pubads()", "GPT_ERRORS_URL"],
    }
  },
  "Prebid.js": {
    "categories": ["Advertising"],
    "website": "https://prebid.org",
    "implies": [],
    "patterns": {
      "scripts": ["prebid.js", "prebid.min.js"],
      "html": ["pbjs.que", "var pbjs", "pbjs ="],
    }
  },
  "Yandex Advertising": {
    "categories": ["Advertising"],
    "website": "https://yandex.ru/adv",
    "implies": [],
    "patterns": {
      "scripts": ["yandex.ru/ads/system/context.js", "yandex.ru/ads/system/"],
      "html": ["Ya.adfoxCode", "yandex_rtb"],
    }
  },
  "Yandex Header Bidding": {
    "categories": ["Advertising"],
    "website": "https://yandex.ru/adv",
    "implies": [],
    "patterns": {
      "scripts": ["yandex.ru/ads/system/header-bidding.js"],
      "html": ["YandexAdfoxBidder"],
    }
  },
  "ADFOX": {
    "categories": ["Advertising"],
    "website": "https://adfox.yandex.ru",
    "implies": [],
    "patterns": {
      "scripts": ["adfox.yandex.ru", "yastatic.net/pcode/adfox"],
      "html": ["Ya.adfoxCode", "ADFOX"],
    }
  },
  "Facebook Ads": {
    "categories": ["Advertising"],
    "website": "https://www.facebook.com/business",
    "implies": [],
    "patterns": {
      "scripts": ["connect.facebook.net/en_US/fbevents.js", "connect.facebook.net/"],
      "html": ["fbq('init'", "_fbq"],
    }
  },
  "Criteo": {
    "categories": ["Advertising"],
    "website": "https://www.criteo.com",
    "implies": [],
    "patterns": {
      "scripts": ["static.criteo.net/", "cas.criteo.com/"],
      "html": ["window.criteo_q", "Criteo.DisplayAd"],
    }
  },
  "Outbrain": {
    "categories": ["Advertising"],
    "website": "https://www.outbrain.com",
    "implies": [],
    "patterns": {
      "scripts": ["widgets.outbrain.com/outbrain.js"],
      "html": ["outbrain-widget", "data-ob-mark"],
    }
  },
  "Taboola": {
    "categories": ["Advertising"],
    "website": "https://www.taboola.com",
    "implies": [],
    "patterns": {
      "scripts": ["cdn.taboola.com/libtrc/", "trc.taboola.com/"],
      "html": ["_taboola.push", "window._taboola"],
    }
  },
  "Google AdSense": {
    "categories": ["Advertising"],
    "website": "https://www.google.com/adsense",
    "implies": [],
    "patterns": {
      "scripts": ["pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"],
      "html": ["adsbygoogle.push", "(adsbygoogle = window.adsbygoogle"],
    }
  },
  "RTB House": {
    "categories": ["Advertising"],
    "website": "https://www.rtbhouse.com",
    "implies": [],
    "patterns": {
      "scripts": ["creativecdn.com/", "rtbhouse.com/"],
      "html": ["rtbhouse.com"],
    }
  },
  "myTarget": {
    "categories": ["Advertising"],
    "website": "https://target.my.com",
    "implies": [],
    "patterns": {
      "scripts": ["top-fwz1.mail.ru/counter", "target.my.com/"],
      "html": ["_tmr.push", "_tmr = window._tmr"],
    }
  },

  # MAPS
  "Google Maps": {
    "categories": ["Mapping"],
    "website": "https://maps.google.com",
    "implies": [],
    "patterns": {
      "scripts": ["maps.googleapis.com/maps/api/js", "maps.google.com/maps/api/js"],
      "html": ["google.maps.Map", "initMap()", "GMaps"],
    }
  },
  "Mapbox": {
    "categories": ["Mapping"],
    "website": "https://www.mapbox.com",
    "implies": [],
    "patterns": {
      "scripts": ["api.mapbox.com/mapbox-gl-js/", "api.tiles.mapbox.com/"],
      "html": ["mapboxgl.Map", "mapbox-gl", "mapboxgl.accessToken"],
    }
  },
  "MapLibre GL": {
    "categories": ["Mapping"],
    "website": "https://maplibre.org",
    "implies": [],
    "patterns": {
      "scripts": ["unpkg.com/maplibre-gl", "cdn.jsdelivr.net/npm/maplibre-gl"],
      "html": ["maplibregl.Map", "maplibre-gl", "new maplibregl"],
    }
  },
  "Leaflet": {
    "categories": ["Mapping"],
    "website": "https://leafletjs.com",
    "implies": [],
    "patterns": {
      "scripts": ["leaflet.js", "leaflet.min.js", "unpkg.com/leaflet"],
      "html": ["L.map(", "L.tileLayer(", "leaflet-map"],
    }
  },
  "Yandex Maps": {
    "categories": ["Mapping"],
    "website": "https://yandex.ru/maps",
    "implies": [],
    "patterns": {
      "scripts": ["api-maps.yandex.ru/", "api.maps.yandex.ru/"],
      "html": ["ymaps.ready(", "new ymaps.Map"],
    }
  },
  "2GIS Maps": {
    "categories": ["Mapping"],
    "website": "https://2gis.ru",
    "implies": [],
    "patterns": {
      "scripts": ["maps.api.2gis.ru/", "2gis.ru/api/"],
      "html": ["DG.map(", "2gis.ru/api"],
    }
  },

  # JS FRAMEWORKS
  "Astro": {
    "categories": ["JavaScript Framework", "Static Site Generator"],
    "website": "https://astro.build",
    "implies": [],
    "patterns": {
      "html": ["astro-island", "data-astro-cid-", "<astro-", "astro:content"],
      "headers": {"x-astro-version": ""},
    }
  },
  "Remix": {
    "categories": ["JavaScript Framework"],
    "website": "https://remix.run",
    "implies": [],
    "patterns": {
      "html": ["__remixContext", "__remixRouteModules", "data-remix-"],
    }
  },
  "SvelteKit": {
    "categories": ["JavaScript Framework"],
    "website": "https://kit.svelte.dev",
    "implies": ["Svelte"],
    "patterns": {
      "html": ["__sveltekit_", "data-sveltekit-", "sveltekit:nonce"],
      "scripts": ["/_app/immutable/entry/"],
    }
  },
  "Preact": {
    "categories": ["JavaScript Framework"],
    "website": "https://preactjs.com",
    "implies": [],
    "patterns": {
      "scripts": ["preact.min.js", "preact.module.js"],
      "html": ["preact/", "__preact_"],
    }
  },
  "Alpine.js": {
    "categories": ["JavaScript Framework"],
    "website": "https://alpinejs.dev",
    "implies": [],
    "patterns": {
      "scripts": ["alpinejs.min.js", "cdn.jsdelivr.net/npm/alpinejs"],
      "html": ["x-data=", "Alpine.js"],
    }
  },
  "htmx": {
    "categories": ["JavaScript Framework"],
    "website": "https://htmx.org",
    "implies": [],
    "patterns": {
      "scripts": ["htmx.min.js"],
      "html": ["hx-get=", "hx-post=", "hx-target="],
    }
  },
  "Ember.js": {
    "categories": ["JavaScript Framework"],
    "website": "https://emberjs.com",
    "implies": [],
    "patterns": {
      "scripts": ["ember.min.js", "ember.prod.js"],
      "html": ["data-ember-action", "ember-view", "__ember"],
    }
  },

  # UI LIBRARIES
  "Material UI": {
    "categories": ["UI Library"],
    "website": "https://mui.com",
    "implies": ["React"],
    "patterns": {
      "html": ["MuiButton-", "MuiTypography-", "MuiBox-"],
    }
  },
  "Ant Design": {
    "categories": ["UI Library"],
    "website": "https://ant.design",
    "implies": ["React"],
    "patterns": {
      "html": ["ant-btn", "ant-input", "ant-layout", "ant-table"],
    }
  },
  "Chakra UI": {
    "categories": ["UI Library"],
    "website": "https://chakra-ui.com",
    "implies": ["React"],
    "patterns": {
      "html": ["data-chakra-component", "chakra-button", "chakra-stack"],
    }
  },
  "Radix UI": {
    "categories": ["UI Library"],
    "website": "https://www.radix-ui.com",
    "implies": ["React"],
    "patterns": {
      "html": ["data-radix-", "radix-ui"],
    }
  },
  "Bulma": {
    "categories": ["CSS Framework"],
    "website": "https://bulma.io",
    "implies": [],
    "patterns": {
      "html": ["class=\"column is-", "class=\"columns\"", "class=\"hero is-"],
    }
  },

  # JS LIBRARIES
  "Lodash": {
    "categories": ["JavaScript Library"],
    "website": "https://lodash.com",
    "implies": [],
    "patterns": {
      "scripts": ["lodash.min.js", "lodash.js"],
      "html": ["_.debounce", "_.throttle", "_.merge("],
    }
  },
  "Moment.js": {
    "categories": ["JavaScript Library"],
    "website": "https://momentjs.com",
    "implies": [],
    "patterns": {
      "scripts": ["moment.min.js", "cdn.jsdelivr.net/npm/moment"],
      "html": ["moment(", "moment.utc(", "moment.locale("],
    }
  },
  "Day.js": {
    "categories": ["JavaScript Library"],
    "website": "https://day.js.org",
    "implies": [],
    "patterns": {
      "scripts": ["dayjs/dayjs.min.js", "cdn.jsdelivr.net/npm/dayjs", "unpkg.com/dayjs"],
      "html": ["dayjs(", "dayjs.extend(", "dayjs.locale("],
    }
  },
  "D3.js": {
    "categories": ["JavaScript Library"],
    "website": "https://d3js.org",
    "implies": [],
    "patterns": {
      "scripts": ["d3.v5.min.js", "d3.v6.min.js", "d3.v7.min.js", "d3.min.js"],
      "html": ["d3.select(", "d3.json(", "d3.scaleLinear"],
    }
  },
  "Chart.js": {
    "categories": ["JavaScript Library"],
    "website": "https://www.chartjs.org",
    "implies": [],
    "patterns": {
      "scripts": ["chart.min.js", "chart.js", "cdn.jsdelivr.net/npm/chart.js"],
      "html": ["new Chart(", "Chart.register("],
    }
  },
  "Swiper": {
    "categories": ["JavaScript Library"],
    "website": "https://swiperjs.com",
    "implies": [],
    "patterns": {
      "scripts": ["swiper.min.js", "swiper-bundle.min.js"],
      "html": ["swiper-container", "swiper-slide", "new Swiper("],
    }
  },
  "GSAP": {
    "categories": ["JavaScript Library"],
    "website": "https://greensock.com/gsap/",
    "implies": [],
    "patterns": {
      "scripts": ["gsap.min.js", "cdn.jsdelivr.net/npm/gsap"],
      "html": ["gsap.to(", "gsap.from(", "TweenMax"],
    }
  },
  "Axios": {
    "categories": ["JavaScript Library"],
    "website": "https://axios-http.com",
    "implies": [],
    "patterns": {
      "scripts": ["axios.min.js", "cdn.jsdelivr.net/npm/axios"],
      "html": ["axios.get(", "axios.post(", "axios({"],
    }
  },
  "Socket.io": {
    "categories": ["JavaScript Library"],
    "website": "https://socket.io",
    "implies": [],
    "patterns": {
      "scripts": ["socket.io/socket.io.js", "/socket.io/"],
      "html": ["io.connect(", "socket.on(", "socket.emit("],
    }
  },
  "three.js": {
    "categories": ["JavaScript Library"],
    "website": "https://threejs.org",
    "implies": [],
    "patterns": {
      "scripts": ["three.min.js", "cdn.jsdelivr.net/npm/three"],
      "html": ["THREE.Scene(", "THREE.PerspectiveCamera", "THREE.WebGLRenderer"],
    }
  },
  "Redux": {
    "categories": ["JavaScript Library"],
    "website": "https://redux.js.org",
    "implies": [],
    "patterns": {
      "scripts": ["redux.min.js"],
      "html": ["createStore(", "combineReducers(", "__redux__"],
    }
  },
  "Vuex": {
    "categories": ["JavaScript Library"],
    "website": "https://vuex.vuejs.org",
    "implies": ["Vue.js"],
    "patterns": {
      "scripts": ["vuex.min.js"],
      "html": ["new Vuex.Store(", "store.commit("],
    }
  },

  # ANALYTICS
  "Gemius": {
    "categories": ["Analytics"],
    "website": "https://www.gemius.com",
    "implies": [],
    "patterns": {
      "scripts": ["gemius_pending.js", "gemiusAudience", "gemius.pl/"],
      "html": ["gemius_hit(", "pp_gemius_"],
    }
  },
  "comScore": {
    "categories": ["Analytics"],
    "website": "https://www.comscore.com",
    "implies": [],
    "patterns": {
      "scripts": ["sb.scorecardresearch.com/beacon.js"],
      "html": ["COMSCORE.beacon", "_comscore.push"],
    }
  },
  "LiveInternet": {
    "categories": ["Analytics"],
    "website": "https://www.liveinternet.ru",
    "implies": [],
    "patterns": {
      "scripts": ["counter.yadro.ru/hit", "www.liveinternet.ru/click"],
      "html": ["liveinternet.ru/click", "counter.yadro.ru"],
    }
  },
  "Rambler Top100": {
    "categories": ["Analytics"],
    "website": "https://top100.rambler.ru",
    "implies": [],
    "patterns": {
      "scripts": ["top100.rambler.ru/top100/", "cnt.rambler.ru/"],
      "html": ["rambler_id", "top100.rambler.ru"],
    }
  },
  "Calltouch": {
    "categories": ["Analytics"],
    "website": "https://calltouch.ru",
    "implies": [],
    "patterns": {
      "scripts": ["mod.calltouch.ru/", "calltouch.ru/"],
      "html": ["calltouch_params", "_ct.push"],
    }
  },
  "Callibri": {
    "categories": ["Analytics"],
    "website": "https://callibri.ru",
    "implies": [],
    "patterns": {
      "scripts": ["callibri.ru/calltracking"],
      "html": ["callibri"],
    }
  },

  # SEO / WEBMASTER
  "Yandex Webmaster": {
    "categories": ["SEO"],
    "website": "https://webmaster.yandex.ru",
    "implies": [],
    "patterns": {
      "html": ["yandex-verification", "yandex_webmaster"],
      "meta_tags": {"yandex-verification": ".*"},
    }
  },
  "Google Search Console": {
    "categories": ["SEO"],
    "website": "https://search.google.com/search-console",
    "implies": [],
    "patterns": {
      "html": ["google-site-verification"],
      "meta_tags": {"google-site-verification": ".*"},
    }
  },
  "Schema.org": {
    "categories": ["SEO"],
    "website": "https://schema.org",
    "implies": [],
    "patterns": {
      "html": ["itemtype=\"https://schema.org/", "schema.org/Product", "application/ld+json"],
    }
  },
  "Open Graph": {
    "categories": ["SEO"],
    "website": "https://ogp.me",
    "implies": [],
    "patterns": {
      "html": ["property=\"og:title\"", "property=\"og:description\"", "property='og:"],
    }
  },

  # TAG MANAGERS
  "Tealium": {
    "categories": ["Tag Manager"],
    "website": "https://tealium.com",
    "implies": [],
    "patterns": {
      "scripts": ["tags.tiqcdn.com/utag/", "utag.js"],
      "html": ["utag_data", "utag.view("],
    }
  },
  "Adobe Launch": {
    "categories": ["Tag Manager"],
    "website": "https://business.adobe.com",
    "implies": [],
    "patterns": {
      "scripts": ["assets.adobedtm.com/", "launch-"],
      "html": ["_satellite.pageBottom", "_satellite.track"],
    }
  },

  # CMS
  "Bitrix": {
    "categories": ["CMS"],
    "website": "https://www.1c-bitrix.ru",
    "implies": ["PHP"],
    "patterns": {
      "html": ["/bitrix/js/", "BX.ready", "/bitrix/cache/"],
      "cookies": ["BITRIX_SM_", "BX_LOGIN_NEED_SECURE_"],
      "scripts": ["/bitrix/js/", "/bitrix/cache/"],
    }
  },
  "TYPO3": {
    "categories": ["CMS"],
    "website": "https://typo3.org",
    "implies": ["PHP"],
    "patterns": {
      "html": ["typo3/", "TYPO3"],
      "meta_generator": "TYPO3",
      "headers": {"X-Powered-By": "TYPO3"},
      "cookies": ["fe_typo_user"],
    }
  },
  "OpenCart": {
    "categories": ["E-commerce"],
    "website": "https://www.opencart.com",
    "implies": ["PHP"],
    "patterns": {
      "html": ["/catalog/view/theme/", "opencart"],
      "cookies": ["OCSESSID"],
    }
  },
  "Hugo": {
    "categories": ["Static Site Generator"],
    "website": "https://gohugo.io",
    "implies": [],
    "patterns": {
      "html": ["/hugo/"],
      "meta_generator": "Hugo",
    }
  },
  "Jekyll": {
    "categories": ["Static Site Generator"],
    "website": "https://jekyllrb.com",
    "implies": [],
    "patterns": {
      "html": ["jekyll"],
      "meta_generator": "Jekyll",
    }
  },
  "Eleventy": {
    "categories": ["Static Site Generator"],
    "website": "https://www.11ty.dev",
    "implies": [],
    "patterns": {
      "meta_generator": "Eleventy",
      "html": ["eleventy-navigation"],
    }
  },

  # CDN / HOSTING
  "Cloudflare CDN": {
    "categories": ["CDN"],
    "website": "https://www.cloudflare.com",
    "implies": [],
    "patterns": {
      "headers": {
        "cf-ray": "",
        "cf-cache-status": "",
      }
    }
  },
  "BunnyCDN": {
    "categories": ["CDN"],
    "website": "https://bunny.net",
    "implies": [],
    "patterns": {
      "headers": {"bunnycdn-cache-status": ""},
      "scripts": ["b-cdn.net/"],
    }
  },
  "Vercel Edge": {
    "categories": ["CDN"],
    "website": "https://vercel.com",
    "implies": [],
    "patterns": {
      "headers": {
        "x-vercel-id": "",
        "x-vercel-cache": "",
      }
    }
  },

  # WEB SERVERS
  "OpenResty": {
    "categories": ["Web Server"],
    "website": "https://openresty.org",
    "implies": [],
    "patterns": {
      "headers": {"server": "openresty"},
    }
  },
  "Caddy": {
    "categories": ["Web Server"],
    "website": "https://caddyserver.com",
    "implies": [],
    "patterns": {
      "headers": {"server": "Caddy"},
    }
  },
  "Tengine": {
    "categories": ["Web Server"],
    "website": "https://tengine.taobao.org",
    "implies": [],
    "patterns": {
      "headers": {"server": "Tengine"},
    }
  },
  "uWSGI": {
    "categories": ["Web Server"],
    "website": "https://uwsgi-docs.readthedocs.io",
    "implies": [],
    "patterns": {
      "headers": {"x-powered-by": "uWSGI"},
    }
  },

  # SECURITY
  "HSTS": {
    "categories": ["Security"],
    "website": "",
    "implies": [],
    "patterns": {
      "headers": {"strict-transport-security": ""},
    }
  },
  "Content Security Policy": {
    "categories": ["Security"],
    "website": "",
    "implies": [],
    "patterns": {
      "headers": {"content-security-policy": ""},
    }
  },
  "X-Frame-Options": {
    "categories": ["Security"],
    "website": "",
    "implies": [],
    "patterns": {
      "headers": {"x-frame-options": ""},
    }
  },

  # PAYMENTS (RU)
  "YooKassa": {
    "categories": ["Payment"],
    "website": "https://yookassa.ru",
    "implies": [],
    "patterns": {
      "scripts": ["yookassa.ru/", "yookassa.js"],
      "html": ["YooMoneyCheckout", "yookassa.ru"],
    }
  },
  "Robokassa": {
    "categories": ["Payment"],
    "website": "https://www.robokassa.ru",
    "implies": [],
    "patterns": {
      "scripts": ["robokassa.ru/"],
      "html": ["robokassa.ru", "Robokassa"],
    }
  },
  "CloudPayments": {
    "categories": ["Payment"],
    "website": "https://cloudpayments.ru",
    "implies": [],
    "patterns": {
      "scripts": ["widget.cloudpayments.ru/"],
      "html": ["CloudPayments", "cp.createPaymentForm"],
    }
  },

  # CHAT / SUPPORT (RU)
  "JivoChat": {
    "categories": ["Live Chat"],
    "website": "https://www.jivochat.ru",
    "implies": [],
    "patterns": {
      "scripts": ["code.jivosite.com/", "app.jivosite.com/widget/"],
      "html": ["jivosite.com", "jivochat"],
    }
  },
  "Carrotquest": {
    "categories": ["Live Chat"],
    "website": "https://www.carrotquest.io",
    "implies": [],
    "patterns": {
      "scripts": ["carrotquest.io/", "cdn.carrotquest.app/"],
      "html": ["carrotquest.track", "carrotquest.identify"],
    }
  },
  "Usedesk": {
    "categories": ["Customer Support"],
    "website": "https://usedesk.ru",
    "implies": [],
    "patterns": {
      "scripts": ["widget.usedesk.ru/"],
      "html": ["usedesk"],
    }
  },

  # SOCIAL (RU)
  "VKontakte": {
    "categories": ["Social"],
    "website": "https://vk.com",
    "implies": [],
    "patterns": {
      "scripts": ["vk.com/js/api/openapi.js", "vk.com/js/"],
      "html": ["VK.init(", "vk_ads", "vk.com/js/api"],
    }
  },
  "OK.ru": {
    "categories": ["Social"],
    "website": "https://ok.ru",
    "implies": [],
    "patterns": {
      "scripts": ["ok.ru/connect.js", "ok.ru/social.js"],
      "html": ["OK.CONNECT.insertShareWidget"],
    }
  },
  "myTarget Pixel": {
    "categories": ["Advertising"],
    "website": "https://target.my.com",
    "implies": [],
    "patterns": {
      "scripts": ["top-fwz1.mail.ru/counter", "target.my.com/"],
      "html": ["_tmr.push", "_tmr = window._tmr"],
    }
  },

  # MOBILE / PWA
  "PWA": {
    "categories": ["Mobile"],
    "website": "",
    "implies": [],
    "patterns": {
      "html": ["site.webmanifest", "serviceWorker.register"],
      "scripts": ["service-worker.js", "sw.js"],
    }
  },
  "AMP": {
    "categories": ["Mobile"],
    "website": "https://amp.dev",
    "implies": [],
    "patterns": {
      "html": ["<html amp", "cdn.ampproject.org/v0.js"],
      "scripts": ["cdn.ampproject.org/"],
    }
  },

  # BUILD TOOLS
  "Parcel": {
    "categories": ["Build Tool"],
    "website": "https://parceljs.org",
    "implies": [],
    "patterns": {
      "scripts": ["/parcel-"],
      "html": ["parcelRequire"],
    }
  },

  # HOSTING (RU)
  "Selectel": {
    "categories": ["Hosting"],
    "website": "https://selectel.ru",
    "implies": [],
    "patterns": {
      "scripts": ["s3.selectel.ru/", "storage.selectel.ru/"],
    }
  },
  "TimeWeb": {
    "categories": ["Hosting"],
    "website": "https://timeweb.com",
    "implies": [],
    "patterns": {
      "scripts": ["timeweb.cloud/"],
      "html": ["timeweb.com"],
    }
  },
  "REG.RU": {
    "categories": ["Hosting"],
    "website": "https://www.reg.ru",
    "implies": [],
    "patterns": {
      "html": ["reg.ru", "hosting.reg.ru"],
      "headers": {"server": "nginx/reg.ru"},
    }
  },
}

added = 0
skipped = 0
for name, data in new_techs.items():
    if name not in db:
        db[name] = data
        added += 1
        print(f"  + {name}")
    else:
        skipped += 1

print(f"\nAdded: {added}, Skipped (already exist): {skipped}")
print(f"Total techs now: {len(db)}")

with open('detection/technologies.json', 'w', encoding='utf-8') as f:
    json.dump(db, f, indent=2, ensure_ascii=False)
print("Saved!")
