// ==UserScript==
// @name         Pinterest Grab & Download
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Quét toàn bộ pin ở trang Your Pins, copy link hoặc tải ảnh 736px
// @author       You
// @match        https://au.pinterest.com/zerxnosad/_pins/*
// @grant        GM_download
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  const panel = document.createElement('div');
  panel.style.cssText = `
    position: fixed;
    top: 10px;
    right: 10px;
    width: 270px;
    background: rgba(0,0,0,0.85);
    color: #fff;
    font-family: Consolas, Arial;
    font-size: 12px;
    padding: 12px;
    border-radius: 12px;
    z-index: 999999;
  `;
  panel.innerHTML = `
    <div style="font-weight:bold;margin-bottom:8px;">Pins Grabber</div>
    <div style="display:flex;gap:6px;margin-bottom:6px;">
      <button id="gl-scan">Scan</button>
      <button id="gl-copy">Copy</button>
      <button id="gl-download">Download</button>
      <button id="gl-clear">Clear</button>
    </div>
    <textarea id="gl-text" rows="8" style="width:100%;resize:vertical;font-size:11px;"></textarea>
    <div id="gl-status" style="margin-top:6px;color:#0f0;">Ready</div>
  `;
  document.body.appendChild(panel);

  const btnScan = panel.querySelector('#gl-scan');
  const btnCopy = panel.querySelector('#gl-copy');
  const btnDownload = panel.querySelector('#gl-download');
  const btnClear = panel.querySelector('#gl-clear');
  const textArea = panel.querySelector('#gl-text');
  const statusDiv = panel.querySelector('#gl-status');

  let pinQueue = [];
  let downloading = false;

  const PIN_REGEX = /https?:\/\/[^/]+\/pin\/(\d+)/;

  btnScan.addEventListener('click', () => {
    const links = [...document.querySelectorAll('a[href*="/pin/"]')];
    const unique = new Map();
    links.forEach(a => {
      const href = a.href || a.getAttribute('href');
      const normalized = normalizePinUrl(href);
      if (normalized) unique.set(normalized, true);
    });
    pinQueue = [...unique.keys()];
    textArea.value = pinQueue.join('\n');
    status(`Found ${pinQueue.length} pins. Ready to download.`);
  });

  btnCopy.addEventListener('click', () => {
    textArea.select();
    document.execCommand('copy');
    status('Copied to clipboard.');
  });

  btnClear.addEventListener('click', () => {
    textArea.value = '';
    pinQueue = [];
    status('Cleared.');
  });

  btnDownload.addEventListener('click', async () => {
    if (downloading) return;
    if (!pinQueue.length && textArea.value.trim()) {
      pinQueue = textArea.value.trim().split(/\s+/);
    }
    if (!pinQueue.length) {
      status('No links to process.');
      return;
    }
    downloading = true;
    status(`Downloading ${pinQueue.length} pins...`);
    for (let i = 0; i < pinQueue.length; i++) {
      const pinUrl = pinQueue[i];
      try {
        const imgUrl = await fetchPinImage(pinUrl);
        if (imgUrl) {
          await saveImage(imgUrl, pinUrl, i + 1);
          status(`Saved ${i + 1}/${pinQueue.length}`);
          await delay(1500);
        } else {
          status(`No image found for ${pinUrl}`);
        }
      } catch (err) {
        console.error(err);
        status(`Error: ${pinUrl}`);
      }
    }
    downloading = false;
    status('Done.');
  });

  function status(msg) {
    statusDiv.textContent = msg;
  }

  function normalizePinUrl(url) {
    if (!url) return null;
    const match = PIN_REGEX.exec(url);
    if (!match) return null;
    return `https://www.pinterest.com/pin/${match[1]}/`;
  }

  async function fetchPinImage(pinUrl) {
    const resp = await fetch(pinUrl, { credentials: 'include' });
    const html = await resp.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const imgs = doc.querySelectorAll('img.iFOUS5, img[elementtiming*="StoryPinImageBlock"], img[alt*="Story pin image"]');
    let best = null;
    imgs.forEach(img => {
      const srcset = img.getAttribute('srcset');
      if (srcset) {
        const parts = srcset.split(',').map(p => p.trim().split(' ')[0]);
        const candidate = parts.pop();
        if (candidate && candidate.includes('/736x/')) {
          best = candidate;
        } else if (!best) {
          best = candidate;
        }
      } else if (!best) {
        best = img.getAttribute('src');
      }
    });
    if (!best) {
      const meta = doc.querySelector('meta[property="og:image"]');
      best = meta?.content ?? null;
    }
    return best;
  }

  function saveImage(imageUrl, pinUrl, index) {
    const pinId = PIN_REGEX.exec(pinUrl)?.[1] ?? 'pin';
    const suffix = imageUrl.split('?')[0].split('.').pop() || 'jpg';
    const name = `pin_${pinId}_${index}.${suffix}`;
    return new Promise((resolve, reject) => {
      GM_download({
        url: imageUrl,
        name,
        onload: resolve,
        onerror: reject,
        ontimeout: reject,
      });
    });
  }

  const delay = ms => new Promise(res => setTimeout(res, ms));
})();