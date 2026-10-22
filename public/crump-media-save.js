(() => {
  'use strict';

  if (window.__crumpMediaSaveLoaded) return;
  window.__crumpMediaSaveLoaded = true;

  const activeOperations = new Set();
  let operationSequence = 0;

  function show(message, type = 'success') {
    if (window.showToast) window.showToast(message, type);
    else console[type === 'error' ? 'error' : 'log'](message);
  }

  function abortError() {
    const error = new Error('That private media delivery was cancelled after the account changed.');
    error.name = 'AbortError';
    return error;
  }

  function currentAuthenticatedUserId() {
    const currentUserId = String(window.currentUser?.id || '').trim();
    if (!currentUserId) return '';
    const boundaryUserId = window.CrumpAuthBoundary?.authenticatedUserId;
    if (typeof boundaryUserId === 'function' && String(boundaryUserId() || '').trim() !== currentUserId) return '';
    const productUserId = window.CrumpProductLoader?.authenticatedUserId;
    if (typeof productUserId === 'function' && String(productUserId() || '').trim() !== currentUserId) return '';
    return currentUserId;
  }

  function deliveryMayProceed(operation) {
    if (!operation || operation.controller.signal.aborted || operation.signal?.aborted) return false;
    if (!activeOperations.has(operation)) return false;
    if (operation.userId !== currentAuthenticatedUserId()) return false;
    if (operation.fileId !== String(operation.file?.id || '').trim()) return false;
    if (typeof operation.shouldProceed !== 'function') return true;
    try { return operation.shouldProceed() === true; }
    catch (_) { return false; }
  }

  function assertDeliveryCurrent(operation) {
    if (!deliveryMayProceed(operation)) throw abortError();
  }

  function beginOperation(file, {signal = null, shouldProceed = null} = {}) {
    const userId = currentAuthenticatedUserId();
    const fileId = String(file?.id || '').trim();
    if (!userId || !fileId) throw abortError();
    const operation = {
      token: ++operationSequence,
      userId,
      fileId,
      file: {...file, id: fileId},
      controller: new AbortController(),
      signal,
      shouldProceed,
      detachSignal: null,
    };
    if (signal) {
      const abortOperation = () => operation.controller.abort();
      if (signal.aborted) abortOperation();
      else {
        signal.addEventListener('abort', abortOperation, {once: true});
        operation.detachSignal = () => signal.removeEventListener('abort', abortOperation);
      }
    }
    activeOperations.add(operation);
    try {
      assertDeliveryCurrent(operation);
    } catch (error) {
      finishOperation(operation);
      throw error;
    }
    return operation;
  }

  function finishOperation(operation) {
    operation?.detachSignal?.();
    activeOperations.delete(operation);
  }

  function abort() {
    [...activeOperations].forEach(operation => {
      operation.controller.abort();
      finishOperation(operation);
    });
  }

  async function api(path, operation) {
    assertDeliveryCurrent(operation);
    const response = await fetch(path, {
      credentials: 'include',
      cache: 'no-store',
      signal: operation.controller.signal,
    });
    assertDeliveryCurrent(operation);
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    assertDeliveryCurrent(operation);
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

  async function signedFile(operation) {
    const data = await api(`/api/files/${encodeURIComponent(operation.fileId)}/signed`, operation);
    assertDeliveryCurrent(operation);
    if (!data.url) throw new Error('Crump could not prepare that media file.');
    return data;
  }

  async function androidAlbum(Media, operation) {
    assertDeliveryCurrent(operation);
    const response = await Media.getAlbums();
    assertDeliveryCurrent(operation);
    let album = (response?.albums || []).find(item => String(item?.name || '').toLowerCase() === 'ask crump');
    if (album?.identifier) return album.identifier;
    await Media.createAlbum({name: 'Ask Crump'});
    assertDeliveryCurrent(operation);
    const refreshed = await Media.getAlbums();
    assertDeliveryCurrent(operation);
    album = (refreshed?.albums || []).find(item => String(item?.name || '').toLowerCase() === 'ask crump');
    if (!album?.identifier) throw new Error('Ask Crump could not prepare a Photos album.');
    return album.identifier;
  }

  async function saveNativeMedia(operation) {
    const Media = window.CrumpNative?.Media;
    const Capacitor = window.CrumpNative?.Capacitor;
    if (!window.CrumpAPI?.isNative || !Media || !Capacitor) return false;
    const signed = await signedFile(operation);
    assertDeliveryCurrent(operation);
    const file = operation.file;
    const type = String(file.type || signed.mimeType || '').toLowerCase();
    const platform = Capacitor.getPlatform?.() || '';
    const options = {path: signed.url, fileName: fileStem(file.name || signed.name)};
    if (platform === 'android') options.albumIdentifier = await androidAlbum(Media, operation);
    assertDeliveryCurrent(operation);
    if (type.startsWith('video/')) {
      await Media.saveVideo(options);
      assertDeliveryCurrent(operation);
      show('Video saved to Photos.', 'success');
    } else if (type.startsWith('image/')) {
      await Media.savePhoto(options);
      assertDeliveryCurrent(operation);
      show('Image saved to Photos.', 'success');
    } else {
      return false;
    }
    return true;
  }

  async function shareMediaFile(operation) {
    if (!navigator.share || !window.File) return false;
    try {
      const signed = await signedFile(operation);
      assertDeliveryCurrent(operation);
      const response = await fetch(signed.url, {
        cache: 'no-store',
        credentials: 'omit',
        signal: operation.controller.signal,
      });
      assertDeliveryCurrent(operation);
      if (!response.ok) throw new Error('Could not read that media file.');
      const blob = await response.blob();
      assertDeliveryCurrent(operation);
      const file = operation.file;
      const name = file.name || signed.name || (String(blob.type).startsWith('video/') ? 'Ask-Crump-video.mp4' : 'Ask-Crump-image.png');
      const shareFile = new File([blob], name, {type: blob.type || file.type || 'application/octet-stream'});
      if (navigator.canShare && !navigator.canShare({files: [shareFile]})) return false;
      assertDeliveryCurrent(operation);
      await navigator.share({files: [shareFile], title: name});
      if (!deliveryMayProceed(operation)) throw abortError();
      return true;
    } catch (error) {
      if (!deliveryMayProceed(operation)) throw abortError();
      if (error?.name === 'AbortError') return true;
      console.warn('Ask Crump media share fallback failed:', error);
      return false;
    }
  }

  function mobileLike() {
    return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '') ||
      Boolean(window.matchMedia?.('(pointer: coarse)').matches);
  }

  function fallbackDownload(operation) {
    assertDeliveryCurrent(operation);
    const file = operation.file;
    const link = document.createElement('a');
    link.href = `/api/files/${encodeURIComponent(operation.fileId)}/content?download=1`;
    link.download = file.name || 'Ask-Crump-media';
    link.hidden = true;
    document.body.appendChild(link);
    if (!deliveryMayProceed(operation)) {
      link.remove();
      throw abortError();
    }
    link.click();
    link.remove();
    return true;
  }

  async function saveMedia(file, deliveryOptions = {}) {
    if (!isMedia(file)) return false;
    const operation = beginOperation(file, deliveryOptions);
    try {
      try {
        if (await saveNativeMedia(operation)) return true;
      } catch (error) {
        if (!deliveryMayProceed(operation)) throw abortError();
        console.warn('Native Photos save failed; falling back:', error);
        show(error.message || 'Could not save directly to Photos. Opening another save option.', 'warning');
      }
      assertDeliveryCurrent(operation);
      if (mobileLike() && await shareMediaFile(operation)) return true;
      assertDeliveryCurrent(operation);
      if (deliveryOptions.fallback === true) return fallbackDownload(operation);
      return false;
    } finally {
      finishOperation(operation);
    }
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
      return {id: match[1], name: fallbackName, type: 'video/mp4'};
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
    void saveMedia(file, {
      fallback: true,
      shouldProceed: () => link.isConnected && mediaFileFromHref(link.href)?.id === file.id,
    }).catch(error => {
      if (error?.name !== 'AbortError') show(error?.message || 'Crump could not save that media file.', 'error');
    });
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

  window.CrumpAuthBoundary?.register?.('media-save', abort);
  if (!window.CrumpAuthBoundary?.register) {
    window.addEventListener('crump:authentication-required', abort);
  }
  window.CrumpMediaSave = Object.freeze({saveMedia, relabelMediaActions, abort});
})();
