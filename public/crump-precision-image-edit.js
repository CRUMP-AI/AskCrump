(() => {
  'use strict';

  if (window.__crumpPrecisionImageEditLoaded) return;
  window.__crumpPrecisionImageEditLoaded = true;

  const state = {
    modal: null,
    returnFocus: null,
    file: null,
    sourceUrl: '',
    canvas: null,
    context: null,
    strokes: [],
    activeStroke: null,
    mode: 'paint',
    brushPercent: 4,
    status: null,
    undo: null,
    clear: null,
  };

  const focusableSelector = 'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function show(message, tone = 'info') {
    window.showToast?.(message, tone);
  }

  function setStatus(message, tone = '') {
    if (!state.status) return;
    state.status.textContent = message;
    state.status.dataset.tone = tone;
  }

  function updateHistoryControls() {
    if (state.undo) state.undo.disabled = state.strokes.length === 0;
    if (state.clear) state.clear.disabled = state.strokes.length === 0;
  }

  function close() {
    const modal = state.modal;
    if (!modal) return;
    const backdrop = modal.closest('.crump-precision-backdrop');
    if (backdrop) backdrop.remove();
    else modal.remove();
    state.modal = null;
    state.file = null;
    state.sourceUrl = '';
    state.canvas = null;
    state.context = null;
    state.strokes = [];
    state.activeStroke = null;
    state.status = null;
    state.undo = null;
    state.clear = null;
    document.body.classList.remove('crump-precision-open');
    const target = state.returnFocus;
    state.returnFocus = null;
    if (target?.isConnected) requestAnimationFrame(() => target.focus({preventScroll: true}));
  }

  async function signedSource(file, fallback = '') {
    if (String(fallback || '').startsWith('blob:') || String(fallback || '').startsWith('data:')) {
      return String(fallback);
    }
    if (file?.id) {
      const response = await fetch(`/api/files/${encodeURIComponent(file.id)}/signed`, {
        credentials: 'same-origin',
        headers: {'Accept': 'application/json'},
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.url) throw new Error(data.error || 'This private image could not be opened for editing.');
      return String(data.url);
    }
    if (fallback) return String(fallback);
    throw new Error('This image is not available for editing.');
  }

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      if (!url.startsWith('blob:') && !url.startsWith('data:')) image.crossOrigin = 'anonymous';
      image.decoding = 'async';
      image.addEventListener('load', () => resolve(image), {once: true});
      image.addEventListener('error', () => reject(new Error('This image could not be decoded for Precision Edit.')), {once: true});
      image.src = url;
    });
  }

  function pointFor(event) {
    const rect = state.canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width))),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(1, rect.height))),
    };
  }

  function drawStroke(stroke) {
    const canvas = state.canvas;
    const context = state.context;
    if (!canvas || !context || !stroke?.points?.length) return;
    const width = Math.max(2, Math.min(canvas.width, canvas.height) * stroke.brushPercent / 100);
    context.save();
    context.globalCompositeOperation = stroke.mode === 'erase' ? 'destination-out' : 'source-over';
    context.strokeStyle = 'rgba(226, 196, 126, .72)';
    context.fillStyle = 'rgba(226, 196, 126, .72)';
    context.lineWidth = width;
    context.lineCap = 'round';
    context.lineJoin = 'round';
    const first = stroke.points[0];
    context.beginPath();
    context.arc(first.x * canvas.width, first.y * canvas.height, width / 2, 0, Math.PI * 2);
    context.fill();
    if (stroke.points.length > 1) {
      context.beginPath();
      context.moveTo(first.x * canvas.width, first.y * canvas.height);
      stroke.points.slice(1).forEach(point => context.lineTo(point.x * canvas.width, point.y * canvas.height));
      context.stroke();
    }
    context.restore();
  }

  function redraw() {
    if (!state.canvas || !state.context) return;
    state.context.clearRect(0, 0, state.canvas.width, state.canvas.height);
    state.strokes.forEach(drawStroke);
    updateHistoryControls();
  }

  function setMode(mode, paint, erase) {
    state.mode = mode === 'erase' ? 'erase' : 'paint';
    paint.classList.toggle('is-active', state.mode === 'paint');
    erase.classList.toggle('is-active', state.mode === 'erase');
    paint.setAttribute('aria-pressed', String(state.mode === 'paint'));
    erase.setAttribute('aria-pressed', String(state.mode === 'erase'));
    setStatus(state.mode === 'paint' ? 'Brush over what may change.' : 'Erase from the selected area.');
  }

  function wireCanvas(canvas) {
    canvas.addEventListener('pointerdown', event => {
      if (event.button !== undefined && event.button !== 0) return;
      event.preventDefault();
      canvas.setPointerCapture?.(event.pointerId);
      state.activeStroke = {
        mode: state.mode,
        brushPercent: state.brushPercent,
        points: [pointFor(event)],
      };
      state.strokes.push(state.activeStroke);
      drawStroke(state.activeStroke);
      updateHistoryControls();
    });
    canvas.addEventListener('pointermove', event => {
      if (!state.activeStroke) return;
      event.preventDefault();
      const point = pointFor(event);
      const previous = state.activeStroke.points[state.activeStroke.points.length - 1];
      state.activeStroke.points.push(point);
      const segment = {...state.activeStroke, points: [previous, point]};
      drawStroke(segment);
    });
    const finish = event => {
      if (!state.activeStroke) return;
      event?.preventDefault?.();
      if (event?.pointerId !== undefined) canvas.releasePointerCapture?.(event.pointerId);
      state.activeStroke = null;
      setStatus('Selection ready. Add more, erase, undo, or continue.');
    };
    canvas.addEventListener('pointerup', finish);
    canvas.addEventListener('pointercancel', finish);
  }

  function maskDataUrl() {
    return new Promise((resolve, reject) => {
      state.canvas.toBlob(blob => {
        if (!blob) {
          reject(new Error('The selected area could not be prepared.'));
          return;
        }
        const reader = new FileReader();
        reader.addEventListener('load', () => {
          const value = String(reader.result || '');
          if (value.length > 2_900_000) {
            reject(new Error('This selection is too complex. Clear it and use fewer, broader brush strokes.'));
            return;
          }
          resolve(value);
        }, {once: true});
        reader.addEventListener('error', () => reject(new Error('The selected area could not be prepared.')), {once: true});
        reader.readAsDataURL(blob);
      }, 'image/png');
    });
  }

  function selectionHasVisiblePixels() {
    if (!state.context || !state.canvas || !state.strokes.length) return false;
    const pixels = state.context.getImageData(0, 0, state.canvas.width, state.canvas.height).data;
    const stride = Math.max(4, Math.floor((state.canvas.width * state.canvas.height) / 200_000) * 4);
    for (let index = 3; index < pixels.length; index += stride) {
      if (pixels[index] > 0) return true;
    }
    return false;
  }

  function trapKeyboard(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab' || !state.modal) return;
    const focusable = [...state.modal.querySelectorAll(focusableSelector)].filter(node => node.getClientRects().length);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function open({file, url = ''} = {}) {
    if (!file?.id && !url) throw new Error('This image is not available for Precision Edit.');
    close();
    state.returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    state.file = file;
    state.strokes = [];
    state.mode = 'paint';
    state.brushPercent = 4;

    const backdrop = document.createElement('div');
    backdrop.className = 'crump-precision-backdrop';
    backdrop.addEventListener('mousedown', event => { if (event.target === backdrop) close(); });
    const modal = document.createElement('section');
    modal.className = 'crump-precision-editor';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'crumpPrecisionTitle');
    modal.addEventListener('keydown', trapKeyboard);
    state.modal = modal;

    const header = document.createElement('header');
    const heading = document.createElement('div');
    heading.innerHTML = '<span>PRECISION EDIT</span><h2 id="crumpPrecisionTitle">Choose exactly what may change.</h2><p>Paint the area yourself. Crump will not identify or label anyone’s race or ethnicity.</p>';
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'crump-precision-close';
    closeButton.setAttribute('aria-label', 'Close Precision Edit');
    closeButton.textContent = '×';
    closeButton.addEventListener('click', close);
    header.append(heading, closeButton);

    const workspace = document.createElement('div');
    workspace.className = 'crump-precision-workspace';
    const stage = document.createElement('div');
    stage.className = 'crump-precision-stage is-loading';
    stage.innerHTML = '<div class="crump-precision-loading"><span></span><strong>Opening your private image…</strong></div>';
    const controls = document.createElement('aside');
    controls.className = 'crump-precision-controls';
    controls.innerHTML = '<div class="crump-precision-control-head"><span>SELECTION</span><strong>Protect everything outside the brush.</strong></div>';

    const modeGroup = document.createElement('div');
    modeGroup.className = 'crump-precision-modes';
    modeGroup.setAttribute('role', 'group');
    modeGroup.setAttribute('aria-label', 'Selection tool');
    const paint = document.createElement('button'); paint.type = 'button'; paint.className = 'is-active'; paint.textContent = 'Brush'; paint.setAttribute('aria-pressed', 'true');
    const erase = document.createElement('button'); erase.type = 'button'; erase.textContent = 'Erase'; erase.setAttribute('aria-pressed', 'false');
    paint.addEventListener('click', () => setMode('paint', paint, erase));
    erase.addEventListener('click', () => setMode('erase', paint, erase));
    modeGroup.append(paint, erase);

    const sizeLabel = document.createElement('label');
    sizeLabel.className = 'crump-precision-size';
    const sizeCopy = document.createElement('span'); sizeCopy.textContent = 'Brush size';
    const sizeValue = document.createElement('b'); sizeValue.textContent = '4%';
    const size = document.createElement('input'); size.type = 'range'; size.min = '1'; size.max = '14'; size.step = '1'; size.value = '4'; size.setAttribute('aria-label', 'Brush size');
    size.addEventListener('input', () => { state.brushPercent = Number(size.value); sizeValue.textContent = `${size.value}%`; });
    sizeLabel.append(sizeCopy, sizeValue, size);

    const history = document.createElement('div');
    history.className = 'crump-precision-history';
    const undo = document.createElement('button'); undo.type = 'button'; undo.textContent = 'Undo'; undo.disabled = true;
    const clear = document.createElement('button'); clear.type = 'button'; clear.textContent = 'Clear'; clear.disabled = true;
    undo.addEventListener('click', () => { state.strokes.pop(); redraw(); setStatus('Last brush stroke removed.'); });
    clear.addEventListener('click', () => { state.strokes = []; redraw(); setStatus('Selection cleared. Brush over what may change.'); });
    state.undo = undo;
    state.clear = clear;
    history.append(undo, clear);

    const boundary = document.createElement('div');
    boundary.className = 'crump-precision-boundary';
    boundary.innerHTML = '<span aria-hidden="true">✓</span><p><strong>Outside-selection lock</strong><small>Ask Crump restores protected pixels after the AI edit, so they do not drift.</small></p>';
    const appearance = document.createElement('p');
    appearance.className = 'crump-precision-appearance';
    appearance.textContent = 'For a person, you may request warmth, complexion, lighting, hair, clothing, or another visible detail inside your selection. Skin tone is not a race label.';
    const status = document.createElement('div');
    status.className = 'crump-precision-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.textContent = 'Brush over the smallest area that should change.';
    state.status = status;
    controls.append(modeGroup, sizeLabel, history, boundary, appearance, status);
    workspace.append(stage, controls);

    const footer = document.createElement('footer');
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'crump-precision-cancel'; cancel.textContent = 'Cancel'; cancel.addEventListener('click', close);
    const use = document.createElement('button'); use.type = 'button'; use.className = 'crump-precision-use'; use.textContent = 'Use this selection'; use.disabled = true;
    use.addEventListener('click', async () => {
      if (!selectionHasVisiblePixels()) {
        setStatus('Brush over the specific area you want to change first.', 'error');
        return;
      }
      use.disabled = true;
      use.setAttribute('aria-busy', 'true');
      setStatus('Preparing the protected edit boundary…');
      try {
        const dataUrl = await maskDataUrl();
        window.CrumpImageStudio?.applyPrecisionSelection?.({
          file: state.file,
          maskDataUrl: dataUrl,
          width: state.canvas.width,
          height: state.canvas.height,
        });
        close();
      } catch (error) {
        setStatus(error?.message || 'The selected area could not be prepared.', 'error');
        use.disabled = false;
        use.removeAttribute('aria-busy');
      }
    });
    footer.append(cancel, use);
    modal.append(header, workspace, footer);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    document.body.classList.add('crump-precision-open');
    closeButton.focus({preventScroll: true});

    try {
      const sourceUrl = await signedSource(file, url);
      if (state.modal !== modal) return;
      state.sourceUrl = sourceUrl;
      const image = await loadImage(sourceUrl);
      if (state.modal !== modal) return;
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      canvas.setAttribute('aria-label', 'Paint the area of the image Crump may edit');
      const base = document.createElement('img');
      base.src = sourceUrl;
      base.alt = file?.name ? `Image to edit: ${file.name}` : 'Image to edit';
      const frame = document.createElement('div');
      frame.className = 'crump-precision-canvas-frame';
      frame.append(base, canvas);
      stage.replaceChildren(frame);
      stage.classList.remove('is-loading');
      state.canvas = canvas;
      state.context = canvas.getContext('2d', {alpha: true, willReadFrequently: true});
      wireCanvas(canvas);
      use.disabled = false;
      setStatus('Brush over the smallest area that should change.');
    } catch (error) {
      if (state.modal !== modal) return;
      stage.classList.remove('is-loading');
      stage.innerHTML = '<div class="crump-precision-load-error"><strong>Image unavailable</strong><p>Your original is safe. Close this window and try again.</p></div>';
      setStatus(error?.message || 'This image could not be opened.', 'error');
      show(error?.message || 'Precision Edit could not open this image.', 'error');
    }
  }

  window.CrumpPrecisionImageEditor = Object.freeze({open, close});
})();
