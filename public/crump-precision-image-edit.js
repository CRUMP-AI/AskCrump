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
    redoStrokes: [],
    selectionDirty: true,
    hasSelection: false,
    activeStroke: null,
    mode: 'paint',
    brushPercent: 4,
    stage: null,
    frame: null,
    fitWidth: 0,
    fitHeight: 0,
    zoom: 1,
    zoomValue: null,
    zoomOut: null,
    zoomIn: null,
    panStart: null,
    instruction: null,
    status: null,
    undo: null,
    redo: null,
    clear: null,
    previewCanvas: null,
    previewContext: null,
    previewSource: null,
    previewMask: null,
    previewRequest: 0,
    adjustments: {warmth: 0, exposure: 0, saturation: 0},
    adjustmentInputs: {},
    saveLocal: null,
    compare: null,
    comparingOriginal: false,
  };

  const focusableSelector = 'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

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
    if (state.redo) state.redo.disabled = state.redoStrokes.length === 0;
    if (state.clear) state.clear.disabled = state.strokes.length === 0;
    updateLocalControls();
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
    state.redoStrokes = [];
    state.selectionDirty = true;
    state.hasSelection = false;
    state.activeStroke = null;
    state.stage = null;
    state.frame = null;
    state.fitWidth = 0;
    state.fitHeight = 0;
    state.zoom = 1;
    state.zoomValue = null;
    state.zoomOut = null;
    state.zoomIn = null;
    state.panStart = null;
    state.instruction = null;
    state.status = null;
    state.undo = null;
    state.redo = null;
    state.clear = null;
    if (state.previewRequest) cancelAnimationFrame(state.previewRequest);
    state.previewCanvas = null;
    state.previewContext = null;
    state.previewSource = null;
    state.previewMask = null;
    state.previewRequest = 0;
    state.adjustments = {warmth: 0, exposure: 0, saturation: 0};
    state.adjustmentInputs = {};
    state.saveLocal = null;
    state.compare = null;
    state.comparingOriginal = false;
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
    context.strokeStyle = 'rgba(226, 196, 126, 1)';
    context.fillStyle = 'rgba(226, 196, 126, 1)';
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
    state.selectionDirty = true;
    updateHistoryControls();
    scheduleLocalPreview();
  }

  function hasLocalAdjustments() {
    return Object.values(state.adjustments).some(value => Number(value) !== 0);
  }

  function updateLocalControls() {
    if (state.saveLocal) {
      state.saveLocal.disabled = !state.file?.id || !hasLocalAdjustments() || !selectionHasVisiblePixels();
    }
    if (state.compare) state.compare.disabled = !hasLocalAdjustments() || !selectionHasVisiblePixels();
  }

  function clampChannel(value) {
    return Math.max(0, Math.min(255, Math.round(value)));
  }

  function renderLocalPreview() {
    state.previewRequest = 0;
    const canvas = state.previewCanvas;
    const context = state.previewContext;
    const source = state.previewSource;
    const mask = state.previewMask;
    if (!canvas || !context || !source || !mask || !state.canvas) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    const active = hasLocalAdjustments() && selectionHasVisiblePixels();
    state.frame?.classList.toggle('has-local-preview', active);
    if (!active) {
      canvas.hidden = true;
      return;
    }
    const maskContext = mask.getContext('2d', {alpha: true, willReadFrequently: true});
    maskContext.clearRect(0, 0, mask.width, mask.height);
    maskContext.drawImage(state.canvas, 0, 0, mask.width, mask.height);
    const maskPixels = maskContext.getImageData(0, 0, mask.width, mask.height).data;
    const output = context.createImageData(canvas.width, canvas.height);
    const sourcePixels = source.data;
    const exposure = 2 ** (Number(state.adjustments.exposure || 0) / 100);
    const saturation = 1 + (Number(state.adjustments.saturation || 0) / 100);
    const warmth = Number(state.adjustments.warmth || 0) / 100;
    const redFactor = 1 + (warmth * .35);
    const blueFactor = 1 - (warmth * .35);
    for (let index = 0; index < sourcePixels.length; index += 4) {
      const selected = maskPixels[index + 3] / 255;
      if (!selected) continue;
      let red = sourcePixels[index] * exposure;
      let green = sourcePixels[index + 1] * exposure;
      let blue = sourcePixels[index + 2] * exposure;
      const luminance = (.2126 * red) + (.7152 * green) + (.0722 * blue);
      red = (luminance + ((red - luminance) * saturation)) * redFactor;
      green = luminance + ((green - luminance) * saturation);
      blue = (luminance + ((blue - luminance) * saturation)) * blueFactor;
      output.data[index] = clampChannel(red);
      output.data[index + 1] = clampChannel(green);
      output.data[index + 2] = clampChannel(blue);
      output.data[index + 3] = Math.round(sourcePixels[index + 3] * selected);
    }
    context.putImageData(output, 0, 0);
    canvas.hidden = state.comparingOriginal;
    updateLocalControls();
  }

  function scheduleLocalPreview() {
    if (state.previewRequest || !state.previewCanvas) return;
    state.previewRequest = requestAnimationFrame(renderLocalPreview);
  }

  function setComparingOriginal(value) {
    state.comparingOriginal = Boolean(value);
    state.frame?.classList.toggle('is-comparing-original', state.comparingOriginal);
    if (state.compare) {
      state.compare.setAttribute('aria-pressed', String(state.comparingOriginal));
      state.compare.textContent = state.comparingOriginal ? 'Show edit' : 'Show original';
    }
    if (state.previewCanvas) state.previewCanvas.hidden = state.comparingOriginal || !hasLocalAdjustments();
    setStatus(state.comparingOriginal ? 'Showing the untouched original.' : 'Showing the local adjustment preview.');
  }

  function resetLocalAdjustments() {
    state.adjustments = {warmth: 0, exposure: 0, saturation: 0};
    Object.values(state.adjustmentInputs).forEach(({input, value}) => {
      input.value = '0';
      value.textContent = '0';
    });
    setComparingOriginal(false);
    scheduleLocalPreview();
    updateLocalControls();
    setStatus('Local adjustments reset. Your selection is unchanged.');
  }

  function setMode(mode, buttons) {
    state.mode = ['paint', 'erase', 'move'].includes(mode) ? mode : 'paint';
    Object.entries(buttons).forEach(([value, button]) => {
      button.classList.toggle('is-active', state.mode === value);
      button.setAttribute('aria-pressed', String(state.mode === value));
    });
    if (state.canvas) state.canvas.dataset.mode = state.mode;
    setStatus({
      paint: 'Brush over what may change.',
      erase: 'Erase from the selected area.',
      move: 'Drag the enlarged image to reach a tiny detail.',
    }[state.mode]);
  }

  function updateZoomControls() {
    if (state.zoomValue) state.zoomValue.textContent = `${Math.round(state.zoom * 100)}%`;
    if (state.zoomOut) state.zoomOut.disabled = !state.frame || state.zoom <= 1;
    if (state.zoomIn) state.zoomIn.disabled = !state.frame || state.zoom >= 4;
  }

  function setZoom(nextZoom) {
    if (!state.frame || !state.stage || !state.fitWidth || !state.fitHeight) return;
    const stage = state.stage;
    const centerX = (stage.scrollLeft + stage.clientWidth / 2) / Math.max(1, stage.scrollWidth);
    const centerY = (stage.scrollTop + stage.clientHeight / 2) / Math.max(1, stage.scrollHeight);
    state.zoom = Math.max(1, Math.min(4, Number(nextZoom) || 1));
    state.frame.style.width = `${Math.round(state.fitWidth * state.zoom)}px`;
    state.frame.style.height = `${Math.round(state.fitHeight * state.zoom)}px`;
    state.frame.classList.toggle('is-zoomed', state.zoom > 1);
    updateZoomControls();
    requestAnimationFrame(() => {
      stage.scrollLeft = Math.max(0, centerX * stage.scrollWidth - stage.clientWidth / 2);
      stage.scrollTop = Math.max(0, centerY * stage.scrollHeight - stage.clientHeight / 2);
    });
  }

  function wireCanvas(canvas) {
    canvas.addEventListener('pointerdown', event => {
      if (event.button !== undefined && event.button !== 0) return;
      event.preventDefault();
      canvas.setPointerCapture?.(event.pointerId);
      if (state.mode === 'move') {
        state.panStart = {
          clientX: event.clientX,
          clientY: event.clientY,
          scrollLeft: state.stage?.scrollLeft || 0,
          scrollTop: state.stage?.scrollTop || 0,
        };
        canvas.classList.add('is-panning');
        return;
      }
      state.activeStroke = {
        mode: state.mode,
        brushPercent: state.brushPercent,
        points: [pointFor(event)],
      };
      state.redoStrokes = [];
      state.strokes.push(state.activeStroke);
      drawStroke(state.activeStroke);
      state.selectionDirty = true;
      updateHistoryControls();
    });
    canvas.addEventListener('pointermove', event => {
      if (state.panStart && state.stage) {
        event.preventDefault();
        state.stage.scrollLeft = state.panStart.scrollLeft - (event.clientX - state.panStart.clientX);
        state.stage.scrollTop = state.panStart.scrollTop - (event.clientY - state.panStart.clientY);
        return;
      }
      if (!state.activeStroke) return;
      event.preventDefault();
      const point = pointFor(event);
      const previous = state.activeStroke.points[state.activeStroke.points.length - 1];
      state.activeStroke.points.push(point);
      const segment = {...state.activeStroke, points: [previous, point]};
      drawStroke(segment);
      state.selectionDirty = true;
    });
    const finish = event => {
      if (state.panStart) {
        event?.preventDefault?.();
        if (event?.pointerId !== undefined) canvas.releasePointerCapture?.(event.pointerId);
        state.panStart = null;
        canvas.classList.remove('is-panning');
        return;
      }
      if (!state.activeStroke) return;
      event?.preventDefault?.();
      if (event?.pointerId !== undefined) canvas.releasePointerCapture?.(event.pointerId);
      state.activeStroke = null;
      state.selectionDirty = true;
      scheduleLocalPreview();
      updateLocalControls();
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
    if (!state.context || !state.canvas || !state.strokes.length) {
      state.hasSelection = false;
      state.selectionDirty = false;
      return false;
    }
    if (!state.selectionDirty) return state.hasSelection;
    const pixels = state.context.getImageData(0, 0, state.canvas.width, state.canvas.height).data;
    const stride = Math.max(4, Math.floor((state.canvas.width * state.canvas.height) / 200_000) * 4);
    for (let index = 3; index < pixels.length; index += stride) {
      if (pixels[index] > 0) {
        state.hasSelection = true;
        state.selectionDirty = false;
        return true;
      }
    }
    state.hasSelection = false;
    state.selectionDirty = false;
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
    state.redoStrokes = [];
    state.selectionDirty = true;
    state.hasSelection = false;
    state.mode = 'paint';
    state.brushPercent = 4;
    state.zoom = 1;
    state.adjustments = {warmth: 0, exposure: 0, saturation: 0};
    state.comparingOriginal = false;

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
    heading.innerHTML = '<span>PRECISION EDIT</span><h2 id="crumpPrecisionTitle">Choose exactly what may change.</h2><p>Paint the area yourself. Zoom in to isolate the smallest possible detail, then describe the visible change. Crump will not identify or label anyone’s race or ethnicity.</p>';
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
    state.stage = stage;
    const controls = document.createElement('aside');
    controls.className = 'crump-precision-controls';
    controls.innerHTML = '<div class="crump-precision-control-head"><span>SELECTION</span><strong>Protect everything outside the brush.</strong></div>';

    const modeGroup = document.createElement('div');
    modeGroup.className = 'crump-precision-modes';
    modeGroup.setAttribute('role', 'group');
    modeGroup.setAttribute('aria-label', 'Selection tool');
    const paint = document.createElement('button'); paint.type = 'button'; paint.className = 'is-active'; paint.textContent = 'Brush'; paint.setAttribute('aria-pressed', 'true');
    const erase = document.createElement('button'); erase.type = 'button'; erase.textContent = 'Erase'; erase.setAttribute('aria-pressed', 'false');
    const move = document.createElement('button'); move.type = 'button'; move.textContent = 'Move'; move.setAttribute('aria-pressed', 'false');
    const modeButtons = {paint, erase, move};
    paint.addEventListener('click', () => setMode('paint', modeButtons));
    erase.addEventListener('click', () => setMode('erase', modeButtons));
    move.addEventListener('click', () => setMode('move', modeButtons));
    modeGroup.append(paint, erase, move);

    const zoom = document.createElement('div');
    zoom.className = 'crump-precision-zoom';
    zoom.setAttribute('role', 'group');
    zoom.setAttribute('aria-label', 'Image zoom');
    const zoomOut = document.createElement('button'); zoomOut.type = 'button'; zoomOut.textContent = '−'; zoomOut.setAttribute('aria-label', 'Zoom out'); zoomOut.disabled = true;
    const zoomValue = document.createElement('b'); zoomValue.textContent = '100%'; zoomValue.setAttribute('aria-live', 'polite');
    const zoomIn = document.createElement('button'); zoomIn.type = 'button'; zoomIn.textContent = '+'; zoomIn.setAttribute('aria-label', 'Zoom in'); zoomIn.disabled = true;
    const zoomFit = document.createElement('button'); zoomFit.type = 'button'; zoomFit.textContent = 'Fit'; zoomFit.setAttribute('aria-label', 'Fit image to screen'); zoomFit.disabled = true;
    zoomOut.addEventListener('click', () => setZoom(state.zoom - .5));
    zoomIn.addEventListener('click', () => setZoom(state.zoom + .5));
    zoomFit.addEventListener('click', () => setZoom(1));
    state.zoomOut = zoomOut;
    state.zoomIn = zoomIn;
    state.zoomValue = zoomValue;
    zoom.append(zoomOut, zoomValue, zoomIn, zoomFit);

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
    const redo = document.createElement('button'); redo.type = 'button'; redo.textContent = 'Redo'; redo.disabled = true;
    const clear = document.createElement('button'); clear.type = 'button'; clear.textContent = 'Clear'; clear.disabled = true;
    undo.addEventListener('click', () => {
      const stroke = state.strokes.pop();
      if (stroke) state.redoStrokes.push(stroke);
      redraw();
      setStatus('Last brush stroke removed.');
    });
    redo.addEventListener('click', () => {
      const stroke = state.redoStrokes.pop();
      if (stroke) state.strokes.push(stroke);
      redraw();
      setStatus('Brush stroke restored.');
    });
    clear.addEventListener('click', () => {
      state.strokes = [];
      state.redoStrokes = [];
      redraw();
      setStatus('Selection cleared. Brush over what may change.');
    });
    state.undo = undo;
    state.redo = redo;
    state.clear = clear;
    history.append(undo, redo, clear);

    const boundary = document.createElement('div');
    boundary.className = 'crump-precision-boundary';
    boundary.innerHTML = '<span aria-hidden="true">✓</span><p><strong>Outside-selection lock</strong><small>Ask Crump restores protected pixels after the AI edit, so they do not drift.</small></p>';
    const appearance = document.createElement('p');
    appearance.className = 'crump-precision-appearance';
    appearance.textContent = 'For a person, you may request warmth, complexion, lighting, hair, clothing, or another visible detail inside your selection. Skin tone is not a race label.';

    const local = document.createElement('section');
    local.className = 'crump-precision-local';
    local.setAttribute('aria-labelledby', 'crumpPrecisionLocalLabel');
    const localLabel = document.createElement('span');
    localLabel.id = 'crumpPrecisionLocalLabel';
    localLabel.textContent = 'LOCAL ADJUSTMENTS · NO AI OR CREDITS';
    const localCopy = document.createElement('small');
    localCopy.textContent = 'Preview and save warmth, exposure, or saturation only inside your manual selection. The saved file is generated deterministically from your private original.';
    const sliders = document.createElement('div');
    sliders.className = 'crump-precision-sliders';
    const sliderDefinitions = [
      ['warmth', 'Warmth'],
      ['exposure', 'Exposure'],
      ['saturation', 'Saturation'],
    ];
    sliderDefinitions.forEach(([key, label]) => {
      const row = document.createElement('label');
      const copy = document.createElement('span'); copy.textContent = label;
      const value = document.createElement('b'); value.textContent = '0';
      const input = document.createElement('input');
      input.type = 'range'; input.min = '-30'; input.max = '30'; input.step = '1'; input.value = '0';
      input.setAttribute('aria-label', `${label} adjustment`);
      input.addEventListener('input', () => {
        state.adjustments[key] = Number(input.value);
        value.textContent = Number(input.value) > 0 ? `+${input.value}` : input.value;
        setComparingOriginal(false);
        scheduleLocalPreview();
        updateLocalControls();
      });
      state.adjustmentInputs[key] = {input, value};
      row.append(copy, value, input);
      sliders.appendChild(row);
    });
    const localActions = document.createElement('div');
    localActions.className = 'crump-precision-local-actions';
    const compare = document.createElement('button'); compare.type = 'button'; compare.textContent = 'Show original'; compare.disabled = true; compare.setAttribute('aria-pressed', 'false');
    const reset = document.createElement('button'); reset.type = 'button'; reset.textContent = 'Reset';
    compare.addEventListener('click', () => setComparingOriginal(!state.comparingOriginal));
    reset.addEventListener('click', resetLocalAdjustments);
    state.compare = compare;
    localActions.append(compare, reset);
    local.append(localLabel, localCopy, sliders, localActions);

    const adjustment = document.createElement('section');
    adjustment.className = 'crump-precision-adjustment';
    adjustment.setAttribute('aria-labelledby', 'crumpPrecisionAdjustmentLabel');
    const adjustmentLabel = document.createElement('span');
    adjustmentLabel.id = 'crumpPrecisionAdjustmentLabel';
    adjustmentLabel.textContent = 'GUIDED CHANGE · OPTIONAL';
    const presets = document.createElement('div');
    presets.className = 'crump-precision-presets';
    const instruction = document.createElement('textarea');
    instruction.rows = 3;
    instruction.maxLength = 900;
    instruction.placeholder = 'Describe only what should change inside the highlighted area…';
    instruction.setAttribute('aria-label', 'Edit instruction');
    state.instruction = instruction;
    [
      ['Natural retouch', 'Even the selected complexion naturally while preserving skin texture, facial features, lighting, age, and identity.'],
      ['Warmer', 'Make the selected skin tone subtly warmer while preserving natural texture, facial features, lighting, age, and identity.'],
      ['Cooler', 'Make the selected skin tone subtly cooler while preserving natural texture, facial features, lighting, age, and identity.'],
      ['Slightly deeper', 'Make the selected skin tone slightly deeper while preserving natural texture, facial features, lighting, age, and identity.'],
      ['Slightly lighter', 'Make the selected skin tone slightly lighter while preserving natural texture, facial features, lighting, age, and identity.'],
    ].forEach(([label, value]) => {
      const preset = document.createElement('button');
      preset.type = 'button';
      preset.textContent = label;
      preset.addEventListener('click', () => {
        instruction.value = value;
        instruction.focus({preventScroll: true});
        setStatus(`${label} guidance added. Review it before continuing.`);
      });
      presets.appendChild(preset);
    });
    const adjustmentBoundary = document.createElement('small');
    adjustmentBoundary.textContent = 'These controls adjust visible tone—not race or ethnicity. No person is identified or classified.';
    adjustment.append(adjustmentLabel, presets, instruction, adjustmentBoundary);
    const status = document.createElement('div');
    status.className = 'crump-precision-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.textContent = 'Brush over the smallest area that should change.';
    state.status = status;
    controls.append(modeGroup, zoom, sizeLabel, history, boundary, appearance, local, adjustment, status);
    workspace.append(stage, controls);

    const footer = document.createElement('footer');
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'crump-precision-cancel'; cancel.textContent = 'Cancel'; cancel.addEventListener('click', close);
    const saveLocal = document.createElement('button'); saveLocal.type = 'button'; saveLocal.className = 'crump-precision-save-local'; saveLocal.textContent = 'Save local edit'; saveLocal.disabled = true;
    state.saveLocal = saveLocal;
    saveLocal.addEventListener('click', async () => {
      if (!selectionHasVisiblePixels() || !hasLocalAdjustments()) {
        setStatus('Select an area and move at least one local adjustment first.', 'error');
        return;
      }
      saveLocal.disabled = true;
      saveLocal.setAttribute('aria-busy', 'true');
      setStatus('Saving a private, provider-free image version…');
      try {
        const preparedMask = await maskDataUrl();
        const response = await fetch(`/api/files/${encodeURIComponent(state.file.id)}/image-adjust`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
          body: JSON.stringify({
            maskDataUrl: preparedMask,
            adjustments: state.adjustments,
            chatId: window.currentChatId || null,
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.file?.id) throw new Error(data.error || 'The local image edit could not be saved.');
        const savedFile = data.file;
        close();
        show('Local edit saved to Files. No AI provider or Crump Credits were used.', 'success');
        requestAnimationFrame(() => window.CrumpFileTools?.open?.(savedFile, false));
      } catch (error) {
        setStatus(error?.message || 'The local image edit could not be saved.', 'error');
        saveLocal.disabled = false;
        saveLocal.removeAttribute('aria-busy');
      }
    });
    const use = document.createElement('button'); use.type = 'button'; use.className = 'crump-precision-use'; use.textContent = 'Continue with AI edit'; use.disabled = true;
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
          instruction: String(state.instruction?.value || '').trim(),
        });
        close();
      } catch (error) {
        setStatus(error?.message || 'The selected area could not be prepared.', 'error');
        use.disabled = false;
        use.removeAttribute('aria-busy');
      }
    });
    footer.append(cancel, saveLocal, use);
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
      canvas.className = 'crump-precision-mask';
      canvas.setAttribute('aria-label', 'Paint the area of the image Crump may edit');
      const base = document.createElement('img');
      base.src = sourceUrl;
      base.alt = file?.name ? `Image to edit: ${file.name}` : 'Image to edit';
      const previewScale = Math.min(1, 1200 / Math.max(image.naturalWidth, image.naturalHeight));
      const preview = document.createElement('canvas');
      preview.className = 'crump-precision-preview';
      preview.width = Math.max(1, Math.round(image.naturalWidth * previewScale));
      preview.height = Math.max(1, Math.round(image.naturalHeight * previewScale));
      preview.hidden = true;
      preview.setAttribute('aria-hidden', 'true');
      const previewSource = document.createElement('canvas');
      previewSource.width = preview.width;
      previewSource.height = preview.height;
      const previewSourceContext = previewSource.getContext('2d', {alpha: true, willReadFrequently: true});
      previewSourceContext.drawImage(image, 0, 0, preview.width, preview.height);
      const previewMask = document.createElement('canvas');
      previewMask.width = preview.width;
      previewMask.height = preview.height;
      const frame = document.createElement('div');
      frame.className = 'crump-precision-canvas-frame';
      frame.append(base, preview, canvas);
      stage.replaceChildren(frame);
      stage.classList.remove('is-loading');
      state.canvas = canvas;
      state.context = canvas.getContext('2d', {alpha: true, willReadFrequently: true});
      state.frame = frame;
      state.previewCanvas = preview;
      state.previewContext = preview.getContext('2d', {alpha: true});
      state.previewSource = previewSourceContext.getImageData(0, 0, preview.width, preview.height);
      state.previewMask = previewMask;
      const fitted = frame.getBoundingClientRect();
      state.fitWidth = fitted.width;
      state.fitHeight = fitted.height;
      frame.style.width = `${Math.round(fitted.width)}px`;
      frame.style.height = `${Math.round(fitted.height)}px`;
      zoomFit.disabled = false;
      wireCanvas(canvas);
      updateZoomControls();
      use.disabled = false;
      updateLocalControls();
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
