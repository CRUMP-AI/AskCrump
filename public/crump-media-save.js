(() => {
  'use strict';

  if (window.__crumpMediaSaveLoaded) return;
  window.__crumpMediaSaveLoaded = true;

  function show(message, type = 'success') {
    if (window.showToast) window.showToast(message, type);
    else console[type === 'error' ? 'error' : 'log'](message);
  }

  async function api(path) {
    const response = await fetch(path, {credentials: 'include'});
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok || data.success === false) {
      const error = new Error(data.error || data.message || `Request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function fileStem(name) {
    return String(name || 'Ask-Crump').replace(/\.[^.]+$/, '').replace(/[^\w\- ()]+/g, '_').slice(0, 100) || 'Ask-Crump';
  }

  function isMedia(file) {
    const type = String(file?.type || '').toLowerCase();
    return type.startsWith('image/') || type.startsWith('video/');
  }

  async function signedFile(file) {
    if (!file?.id) throw new Error('That saved media item is missing its file ID.');
    const data = await api(`/api/files/${encodeURIComponent(file.id)}/signed`);
    if (!data.url) throw new Error('Crump could not prepare that media file.');
    return data;
  }

  async function androidAlbum(Media) {
    const response = await Media.getAlbums();
    let album = (response?.albums || []).find(item => String(item?.name || '').toLowerCase() === 'ask crump');
    if (album?.identifier) return album.identifier;
    await Media.createAlbum({name: 'Ask Crump'});
    const refreshed = await Media.getAlbums();
    album = (refreshed?.albums || []).find(item => String(item?.name || '').toLowerCase() === 'ask crump');
    if (!album?.identifier) throw new Error('Ask Crump could not prepare a Photos album.');
    return album.identifier;
  }

  async function saveNativeMedia(file) {
    const Media = window.CrumpNative?.Media;
    const Capacitor = window.CrumpNative?.Capacitor;
    if (!window.CrumpAPI?.isNative || !Media || !Capacitor) return false;
    const signed = await signedFile(file);
    const type = String(file.type || signed.mimeType || '').toLowerCase();
    const platform = Capacitor.getPlatform?.() || '';
    const options = {path: signed.url, fileName: fileStem(file.name || signed.name)};
    if (platform === 'android') options.albumIdentifier = await androidAlbum(Media);
    if (type.startsWith('video/')) {
      await Media.saveVideo(options);
      show('Video saved to Photos.', 'success');
    } else if (type.startsWith('image/')) {
      await Media.savePhoto(options);
      show('Image saved to Photos.', 'success');
    } else {
      return false;
    }
    return true;
  }

  async function shareMediaFile(file) {
    if (!navigator.share || !window.File) return false;
    try {
      const signed = await signedFile(file);
      const response = await fetch(signed.url, {cache: 'no-store'});
      if (!response.ok) throw new Error('Could not read that media file.');
      const blob = await response.blob();
      const name = file.name || signed.name || (String(blob.type).startsWith('video/') ? 'Ask-Crump-video.mp4' : 'Ask-Crump-image.png');
      const shareFile = new File([blob], name, {type: blob.type || file.type || 'application/octet-stream'});
      if (navigator.canShare && !navigator.canShare({files: [shareFile]})) return false;
      await navigator.share({files: [shareFile], title: name});
      return true;
    } catch (error) {
      if (error?.name === 'AbortError') return true;
      console.warn('Ask Crump media share fallback failed:', error);
      return false;
    }
  }

  function mobileLike() {
    return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '') ||
      Boolean(window.matchMedia?.('(pointer: coarse)').matches);
  }

  async function saveMedia(file) {
    if (!isMedia(file)) return false;
    try {
      if (await saveNativeMedia(file)) return true;
    } catch (error) {
      console.warn('Native Photos save failed; falling back:', error);
      show(error.message || 'Could not save directly to Photos. Opening another save option.', 'warning');
    }
    if (!mobileLike()) return false;
    return shareMediaFile(file);
  }

  function relabelMediaActions(root = document) {
    const imageLabel = window.CrumpAPI?.isNative ? 'Save to Photos' : 'Save';
    const videoLabel = window.CrumpAPI?.isNative ? 'Save to Photos' : 'Save video';
    root.querySelectorAll?.('.crump50-image-actions button').forEach(button => {
      if (['Download', 'Save'].includes(button.textContent?.trim())) button.textContent = imageLabel;
    });
    root.querySelectorAll?.('.crump50-lightbox-bar button').forEach(button => {
      if (['Download', 'Save'].includes(button.textContent?.trim())) button.textContent = imageLabel;
    });
    root.querySelectorAll?.('.crump53-video-result-actions a[download]').forEach(link => { link.textContent = videoLabel; });
  }

  function mediaFileFromHref(href, fallbackName = 'Ask-Crump-video.mp4') {
    try {
      const url = new URL(href, location.href);
      const match = url.pathname.match(/\/api\/files\/([0-9a-f-]{36})\/content$/i);
      if (!match) return null;
      return {id: match[1], name: fallbackName, type: 'video/mp4', url: url.pathname};
    } catch (_) {
      return null;
    }
  }

  document.addEventListener('click', event => {
    const link = event.target.closest?.('.crump53-video-result-actions a[download]');
    if (!link) return;
    const file = mediaFileFromHref(link.href, 'Ask-Crump-video.mp4');
    if (!file) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void (async () => {
      const handled = await saveMedia(file);
      if (!handled) window.location.assign(`${file.url}?download=1`);
    })();
  }, true);

  const observer = new MutationObserver(records => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) relabelMediaActions(node);
      }
    }
  });
  observer.observe(document.documentElement, {subtree: true, childList: true});
  relabelMediaActions();

  window.CrumpMediaSave = Object.freeze({saveMedia, relabelMediaActions});
  if (!window.__crumpLibrary57Loaded) window.CrumpLibrary57 = Object.freeze({saveMedia});
})();
