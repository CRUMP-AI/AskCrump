(() => {
  'use strict';

  if (window.__crumpPrecisionImageEditLoaded) return;
  window.__crumpPrecisionImageEditLoaded = true;

  const MAX_OVERLAY_ITEMS = 12;
  const MAX_OVERLAY_SOURCE_PIXELS = 16_777_216;
  const MAX_LASSO_POINTS = 4096;
  const MIN_LASSO_AREA = 0.0001;

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
    modeButtons: {},
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
    invert: null,
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
    overlayCanvas: null,
    overlayContext: null,
    overlayGuide: null,
    overlays: [],
    activeOverlayId: '',
    overlayDrag: null,
    overlaySize: null,
    overlayOpacity: null,
    overlayColor: null,
    overlayRemove: null,
    lassoGuide: null,
    lassoPolygon: null,
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
    if (state.invert) state.invert.disabled = state.strokes.length === 0;
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
    state.mode = 'paint';
    state.modeButtons = {};
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
    state.invert = null;
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
    state.overlayCanvas = null;
    state.overlayContext = null;
    state.overlayGuide = null;
    state.overlays = [];
    state.activeOverlayId = '';
    state.overlayDrag = null;
    state.overlaySize = null;
    state.overlayOpacity = null;
    state.overlayColor = null;
    state.overlayRemove = null;
    state.lassoGuide = null;
    state.lassoPolygon = null;
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
    if (!canvas || !context || !stroke) return;
    if (stroke.mode === 'invert') {
      const inverted = document.createElement('canvas');
      inverted.width = canvas.width;
      inverted.height = canvas.height;
      const invertedContext = inverted.getContext('2d', {alpha: true});
      invertedContext.fillStyle = 'rgba(226, 196, 126, 1)';
      invertedContext.fillRect(0, 0, inverted.width, inverted.height);
      invertedContext.globalCompositeOperation = 'destination-out';
      invertedContext.drawImage(canvas, 0, 0);
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(inverted, 0, 0);
      return;
    }
    if (!stroke.points?.length) return;
    if (stroke.mode === 'lasso') {
      if (stroke.points.length < 3) return;
      context.save();
      context.globalCompositeOperation = 'source-over';
      context.fillStyle = 'rgba(226, 196, 126, 1)';
      context.beginPath();
      context.moveTo(stroke.points[0].x * canvas.width, stroke.points[0].y * canvas.height);
      stroke.points.slice(1).forEach(point => context.lineTo(point.x * canvas.width, point.y * canvas.height));
      context.closePath();
      context.fill();
      context.restore();
      return;
    }
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

  function polygonArea(points) {
    if (!Array.isArray(points) || points.length < 3) return 0;
    let area = 0;
    for (let index = 0; index < points.length; index += 1) {
      const current = points[index];
      const next = points[(index + 1) % points.length];
      area += (current.x * next.y) - (next.x * current.y);
    }
    return Math.abs(area) / 2;
  }

  function updateLassoGuide(points = []) {
    if (!state.lassoGuide || !state.lassoPolygon) return;
    const usablePoints = Array.isArray(points) ? points : [];
    state.lassoPolygon.setAttribute('points', usablePoints.map(point => `${point.x},${point.y}`).join(' '));
    state.lassoGuide.hidden = usablePoints.length < 2;
  }

  function selectionCoverage() {
    if (!state.context || !state.canvas) return 0;
    const pixels = state.context.getImageData(0, 0, state.canvas.width, state.canvas.height).data;
    let selectedWeight = 0;
    for (let index = 3; index < pixels.length; index += 4) selectedWeight += pixels[index];
    return selectedWeight / (255 * state.canvas.width * state.canvas.height);
  }

  function invertSelection() {
    const coverage = selectionCoverage();
    if (coverage <= 0) {
      setStatus('Brush or outline an area before inverting the selection.', 'error');
      return;
    }
    const invertedCoverage = 1 - coverage;
    if (invertedCoverage <= 0 || invertedCoverage > .9) {
      setStatus('The inverted area would be too broad. Outline more of the background, then try again.', 'error');
      return;
    }
    state.strokes.push({mode: 'invert', points: []});
    state.redoStrokes = [];
    redraw();
    setStatus('Selection inverted. The gold area is now the only area allowed to change.');
  }

  function hasLocalAdjustments() {
    return Object.values(state.adjustments).some(value => Number(value) !== 0);
  }

  function hasDeterministicOverlay() {
    return state.overlays.length > 0;
  }

  function localAdjustmentReady() {
    return hasLocalAdjustments() && selectionHasVisiblePixels();
  }

  function hasSavableLocalEdit() {
    return localAdjustmentReady() || hasDeterministicOverlay();
  }

  function updateLocalControls() {
    if (state.saveLocal) {
      state.saveLocal.disabled = !state.file?.id || !hasSavableLocalEdit();
    }
    if (state.compare) state.compare.disabled = !hasSavableLocalEdit();
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
    state.frame?.classList.toggle('has-local-preview', active || hasDeterministicOverlay());
    if (!active) {
      canvas.hidden = true;
      updateLocalControls();
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
    if (state.overlayCanvas) state.overlayCanvas.hidden = state.comparingOriginal || !hasDeterministicOverlay();
    updateOverlayGuide();
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

  function activeOverlay() {
    return state.overlays.find(item => item.id === state.activeOverlayId) || null;
  }

  function overlayBounds(item, context = state.overlayContext) {
    const canvas = state.overlayCanvas;
    if (!item || !canvas || !context) return null;
    if (item.type === 'image') {
      const width = Math.max(.02, Math.min(.95, Number(item.sizePercent || 25) / 100));
      const height = Math.max(.02, Math.min(.95, width * item.aspect * canvas.width / canvas.height));
      return {x: item.x - width / 2, y: item.y - height / 2, width, height};
    }
    const pixels = Math.max(12, Math.min(canvas.width, canvas.height) * Number(item.sizePercent || 8) / 100);
    context.font = `700 ${pixels}px Arial, sans-serif`;
    const measured = context.measureText(item.text);
    const width = Math.min(.96, Math.max(.02, (measured.width + pixels * .25) / canvas.width));
    const height = Math.min(.5, Math.max(.02, pixels * 1.35 / canvas.height));
    return {x: item.x - width / 2, y: item.y - height / 2, width, height, pixels};
  }

  function clampOverlay(item) {
    const bounds = overlayBounds(item);
    if (!bounds) return;
    item.x = Math.max(bounds.width / 2, Math.min(1 - bounds.width / 2, Number(item.x) || .5));
    item.y = Math.max(bounds.height / 2, Math.min(1 - bounds.height / 2, Number(item.y) || .5));
  }

  function updateOverlayGuide() {
    const guide = state.overlayGuide;
    const item = activeOverlay();
    const bounds = overlayBounds(item);
    if (!guide || !item || !bounds || state.comparingOriginal) {
      if (guide) guide.hidden = true;
      return;
    }
    guide.hidden = false;
    guide.style.left = `${bounds.x * 100}%`;
    guide.style.top = `${bounds.y * 100}%`;
    guide.style.width = `${bounds.width * 100}%`;
    guide.style.height = `${bounds.height * 100}%`;
    guide.setAttribute('aria-label', `${item.type === 'image' ? 'Image' : 'Text'} overlay selected`);
  }

  function updateOverlayControls() {
    const item = activeOverlay();
    if (state.overlaySize) {
      state.overlaySize.disabled = !item;
      state.overlaySize.min = item?.type === 'text' ? '2' : '5';
      state.overlaySize.max = item?.type === 'text' ? '24' : '90';
      state.overlaySize.value = String(item?.sizePercent || (item?.type === 'text' ? 8 : 25));
    }
    if (state.overlayOpacity) {
      state.overlayOpacity.disabled = !item;
      state.overlayOpacity.value = String(Math.round(Number(item?.opacity || 1) * 100));
    }
    if (state.overlayColor) {
      state.overlayColor.disabled = false;
      if (item?.type === 'text') state.overlayColor.value = item.color;
    }
    if (state.overlayRemove) state.overlayRemove.disabled = !item;
    updateOverlayGuide();
  }

  function renderOverlays() {
    const canvas = state.overlayCanvas;
    const context = state.overlayContext;
    if (!canvas || !context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    state.overlays.forEach(item => {
      const bounds = overlayBounds(item, context);
      if (!bounds) return;
      context.save();
      context.globalAlpha = Math.max(.1, Math.min(1, Number(item.opacity || 1)));
      if (item.type === 'image' && item.image) {
        context.drawImage(
          item.image,
          bounds.x * canvas.width,
          bounds.y * canvas.height,
          bounds.width * canvas.width,
          bounds.height * canvas.height,
        );
      } else if (item.type === 'text') {
        context.font = `700 ${bounds.pixels}px Arial, sans-serif`;
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.fillStyle = item.color;
        context.fillText(item.text, item.x * canvas.width, item.y * canvas.height);
      }
      context.restore();
    });
    canvas.hidden = state.comparingOriginal || !hasDeterministicOverlay();
    state.frame?.classList.toggle('has-exact-overlay', hasDeterministicOverlay());
    updateOverlayControls();
    updateLocalControls();
  }

  function selectOverlay(id) {
    state.activeOverlayId = String(id || '');
    updateOverlayControls();
  }

  function overlayAt(point) {
    return [...state.overlays].reverse().find(item => {
      const bounds = overlayBounds(item);
      return bounds && point.x >= bounds.x && point.x <= bounds.x + bounds.width
        && point.y >= bounds.y && point.y <= bounds.y + bounds.height;
    }) || null;
  }

  async function addImageOverlay(file) {
    if (state.overlays.length >= MAX_OVERLAY_ITEMS) {
      throw new Error('Remove an overlay before adding another. Precision Edit supports up to 12 at once.');
    }
    const type = String(file?.type || '').toLowerCase();
    if (!file || !['image/png', 'image/jpeg', 'image/webp'].includes(type)) {
      throw new Error('Choose a PNG, JPG, or WebP logo or image.');
    }
    if (Number(file.size || 0) <= 0 || Number(file.size || 0) > 8 * 1024 * 1024) {
      throw new Error('Use an overlay image between 1 byte and 8 MB.');
    }
    const objectUrl = URL.createObjectURL(file);
    let image;
    try {
      image = await loadImage(objectUrl);
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
    if (!image.naturalWidth || !image.naturalHeight
      || image.naturalWidth * image.naturalHeight > MAX_OVERLAY_SOURCE_PIXELS) {
      throw new Error('Use an overlay image below 16 megapixels.');
    }
    const item = {
      id: `overlay-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      type: 'image',
      image,
      aspect: image.naturalHeight / Math.max(1, image.naturalWidth),
      x: .5,
      y: .5,
      sizePercent: 25,
      opacity: 1,
    };
    state.overlays.push(item);
    selectOverlay(item.id);
    setComparingOriginal(false);
    setMode('place', state.modeButtons);
    clampOverlay(item);
    renderOverlays();
    setStatus('Exact image overlay added. Drag it into place, then adjust size or opacity.');
  }

  function addTextOverlay(value, color) {
    if (state.overlays.length >= MAX_OVERLAY_ITEMS) {
      throw new Error('Remove an overlay before adding another. Precision Edit supports up to 12 at once.');
    }
    const text = String(value || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    if (!text) throw new Error('Enter the exact text you want to place.');
    const item = {
      id: `overlay-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      type: 'text',
      text,
      color: /^#[0-9a-f]{6}$/i.test(String(color || '')) ? String(color) : '#ffffff',
      x: .5,
      y: .82,
      sizePercent: 8,
      opacity: 1,
    };
    state.overlays.push(item);
    selectOverlay(item.id);
    setComparingOriginal(false);
    setMode('place', state.modeButtons);
    clampOverlay(item);
    renderOverlays();
    setStatus('Exact text added. Drag it into place, then adjust size, color, or opacity.');
  }

  function overlayDataUrl() {
    return new Promise((resolve, reject) => {
      if (!state.overlayCanvas || !hasDeterministicOverlay()) {
        resolve('');
        return;
      }
      state.overlayCanvas.toBlob(blob => {
        if (!blob) {
          reject(new Error('The exact overlay could not be prepared.'));
          return;
        }
        if (blob.size > 2 * 1024 * 1024) {
          reject(new Error('The exact overlay is too complex. Use a smaller logo or less text.'));
          return;
        }
        const reader = new FileReader();
        reader.addEventListener('load', () => resolve(String(reader.result || '')), {once: true});
        reader.addEventListener('error', () => reject(new Error('The exact overlay could not be prepared.')), {once: true});
        reader.readAsDataURL(blob);
      }, 'image/png');
    });
  }

  function setMode(mode, buttons) {
    state.mode = ['paint', 'erase', 'lasso', 'move', 'place'].includes(mode) ? mode : 'paint';
    Object.entries(buttons).forEach(([value, button]) => {
      button.classList.toggle('is-active', state.mode === value);
      button.setAttribute('aria-pressed', String(state.mode === value));
    });
    if (state.canvas) state.canvas.dataset.mode = state.mode;
    setStatus({
      paint: 'Brush over what may change.',
      erase: 'Erase from the selected area.',
      lasso: 'Draw a closed outline around what may change.',
      move: 'Drag the enlarged image to reach a tiny detail.',
      place: 'Drag the selected exact overlay into place.',
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
      if (state.mode === 'place') {
        const point = pointFor(event);
        const item = overlayAt(point);
        selectOverlay(item?.id || '');
        if (item) {
          state.overlayDrag = {
            id: item.id,
            offsetX: point.x - item.x,
            offsetY: point.y - item.y,
          };
          canvas.classList.add('is-placing');
        }
        return;
      }
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
      if (state.mode === 'lasso') updateLassoGuide(state.activeStroke.points);
      else drawStroke(state.activeStroke);
      state.selectionDirty = true;
      updateHistoryControls();
    });
    canvas.addEventListener('pointermove', event => {
      if (state.overlayDrag) {
        event.preventDefault();
        const item = state.overlays.find(candidate => candidate.id === state.overlayDrag.id);
        if (!item) return;
        const point = pointFor(event);
        item.x = point.x - state.overlayDrag.offsetX;
        item.y = point.y - state.overlayDrag.offsetY;
        clampOverlay(item);
        renderOverlays();
        return;
      }
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
      if (state.activeStroke.mode === 'lasso') {
        if (state.activeStroke.points.length >= MAX_LASSO_POINTS) return;
        if (Math.hypot(point.x - previous.x, point.y - previous.y) < .002) return;
        state.activeStroke.points.push(point);
        updateLassoGuide(state.activeStroke.points);
        return;
      }
      state.activeStroke.points.push(point);
      const segment = {...state.activeStroke, points: [previous, point]};
      drawStroke(segment);
      state.selectionDirty = true;
    });
    const finish = event => {
      if (state.overlayDrag) {
        event?.preventDefault?.();
        if (event?.pointerId !== undefined) canvas.releasePointerCapture?.(event.pointerId);
        state.overlayDrag = null;
        canvas.classList.remove('is-placing');
        setStatus('Exact overlay position updated.');
        return;
      }
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
      const completedStroke = state.activeStroke;
      state.activeStroke = null;
      if (completedStroke.mode === 'lasso') {
        const cancelled = event?.type === 'pointercancel';
        const usable = !cancelled
          && completedStroke.points.length >= 3
          && polygonArea(completedStroke.points) >= MIN_LASSO_AREA;
        if (!usable && state.strokes.at(-1) === completedStroke) state.strokes.pop();
        updateLassoGuide();
        if (usable) drawStroke(completedStroke);
        state.selectionDirty = true;
        updateHistoryControls();
        scheduleLocalPreview();
        updateLocalControls();
        setStatus(
          usable
            ? 'Lasso selection ready. Add another area, erase, invert, undo, or continue.'
            : 'Draw a wider closed outline to create a lasso selection.',
          usable ? '' : 'error',
        );
        return;
      }
      state.selectionDirty = true;
      scheduleLocalPreview();
      updateLocalControls();
      setStatus('Selection ready. Add more, erase, invert, undo, or continue.');
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
            reject(new Error('This selection is too complex. Clear it and use fewer, broader selection actions.'));
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
    state.overlays = [];
    state.activeOverlayId = '';
    state.overlayDrag = null;

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
    heading.innerHTML = '<span>PRECISION EDIT</span><h2 id="crumpPrecisionTitle">Choose exactly what may change.</h2><p>Brush or outline the area yourself. Zoom in to isolate the smallest possible detail, then describe the visible change. Crump will not identify or label anyone’s race or ethnicity.</p>';
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
    controls.innerHTML = '<div class="crump-precision-control-head"><span>SELECTION</span><strong>Protect everything outside your selection.</strong></div>';

    const modeGroup = document.createElement('div');
    modeGroup.className = 'crump-precision-modes';
    modeGroup.setAttribute('role', 'group');
    modeGroup.setAttribute('aria-label', 'Selection tool');
    const paint = document.createElement('button'); paint.type = 'button'; paint.className = 'is-active'; paint.textContent = 'Brush'; paint.setAttribute('aria-pressed', 'true');
    const erase = document.createElement('button'); erase.type = 'button'; erase.textContent = 'Erase'; erase.setAttribute('aria-pressed', 'false');
    const lasso = document.createElement('button'); lasso.type = 'button'; lasso.textContent = 'Lasso'; lasso.setAttribute('aria-pressed', 'false');
    const move = document.createElement('button'); move.type = 'button'; move.textContent = 'Move'; move.setAttribute('aria-pressed', 'false');
    const place = document.createElement('button'); place.type = 'button'; place.textContent = 'Place'; place.setAttribute('aria-pressed', 'false');
    const modeButtons = {paint, erase, lasso, move, place};
    state.modeButtons = modeButtons;
    paint.addEventListener('click', () => setMode('paint', modeButtons));
    erase.addEventListener('click', () => setMode('erase', modeButtons));
    lasso.addEventListener('click', () => setMode('lasso', modeButtons));
    move.addEventListener('click', () => setMode('move', modeButtons));
    place.addEventListener('click', () => setMode('place', modeButtons));
    modeGroup.append(paint, erase, lasso, move, place);

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
    const invert = document.createElement('button'); invert.type = 'button'; invert.textContent = 'Invert'; invert.disabled = true;
    const clear = document.createElement('button'); clear.type = 'button'; clear.textContent = 'Clear'; clear.disabled = true;
    undo.addEventListener('click', () => {
      const stroke = state.strokes.pop();
      if (stroke) state.redoStrokes.push(stroke);
      redraw();
      setStatus('Last selection action removed.');
    });
    redo.addEventListener('click', () => {
      const stroke = state.redoStrokes.pop();
      if (stroke) state.strokes.push(stroke);
      redraw();
      setStatus('Selection action restored.');
    });
    invert.addEventListener('click', invertSelection);
    clear.addEventListener('click', () => {
      state.strokes = [];
      state.redoStrokes = [];
      redraw();
      setStatus('Selection cleared. Brush or outline what may change.');
    });
    state.undo = undo;
    state.redo = redo;
    state.clear = clear;
    state.invert = invert;
    history.append(undo, redo, invert, clear);

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

    const exactOverlay = document.createElement('section');
    exactOverlay.className = 'crump-precision-exact-overlay';
    exactOverlay.setAttribute('aria-labelledby', 'crumpPrecisionOverlayLabel');
    const overlayLabel = document.createElement('span');
    overlayLabel.id = 'crumpPrecisionOverlayLabel';
    overlayLabel.textContent = 'EXACT OVERLAY · NO AI OR CREDITS';
    const overlayCopy = document.createElement('small');
    overlayCopy.textContent = 'Place a rights-cleared logo, image, or exact text as pixels. Crump does not ask a model to redraw it, and the separate source is not saved.';
    const overlayActions = document.createElement('div');
    overlayActions.className = 'crump-precision-overlay-actions';
    const addOverlayImage = document.createElement('button');
    addOverlayImage.type = 'button';
    addOverlayImage.textContent = 'Add logo or image';
    const overlayImageInput = document.createElement('input');
    overlayImageInput.type = 'file';
    overlayImageInput.accept = 'image/png,image/jpeg,image/webp';
    overlayImageInput.hidden = true;
    overlayImageInput.setAttribute('aria-label', 'Exact overlay image');
    addOverlayImage.addEventListener('click', () => overlayImageInput.click());
    overlayImageInput.addEventListener('change', async () => {
      const file = overlayImageInput.files?.[0];
      overlayImageInput.value = '';
      if (!file) return;
      addOverlayImage.disabled = true;
      try {
        await addImageOverlay(file);
      } catch (error) {
        setStatus(error?.message || 'The exact overlay could not be added.', 'error');
      } finally {
        addOverlayImage.disabled = false;
      }
    });
    overlayActions.append(addOverlayImage, overlayImageInput);
    const overlayTextRow = document.createElement('div');
    overlayTextRow.className = 'crump-precision-overlay-text';
    const overlayText = document.createElement('input');
    overlayText.type = 'text';
    overlayText.maxLength = 80;
    overlayText.placeholder = 'Exact text';
    overlayText.setAttribute('aria-label', 'Exact overlay text');
    const overlayColor = document.createElement('input');
    overlayColor.type = 'color';
    overlayColor.value = '#ffffff';
    overlayColor.setAttribute('aria-label', 'Exact text color');
    const addOverlayText = document.createElement('button');
    addOverlayText.type = 'button';
    addOverlayText.textContent = 'Add text';
    addOverlayText.addEventListener('click', () => {
      try {
        addTextOverlay(overlayText.value, overlayColor.value);
        overlayText.value = '';
      } catch (error) {
        setStatus(error?.message || 'The exact text could not be added.', 'error');
        overlayText.focus({preventScroll: true});
      }
    });
    overlayTextRow.append(overlayText, overlayColor, addOverlayText);
    const overlayTuning = document.createElement('div');
    overlayTuning.className = 'crump-precision-overlay-tuning';
    const overlaySizeLabel = document.createElement('label');
    overlaySizeLabel.textContent = 'Selected size';
    const overlaySize = document.createElement('input');
    overlaySize.type = 'range'; overlaySize.min = '5'; overlaySize.max = '90'; overlaySize.step = '1'; overlaySize.value = '25'; overlaySize.disabled = true;
    overlaySize.setAttribute('aria-label', 'Selected overlay size');
    overlaySize.addEventListener('input', () => {
      const item = activeOverlay();
      if (!item) return;
      item.sizePercent = Number(overlaySize.value);
      clampOverlay(item);
      renderOverlays();
    });
    overlaySizeLabel.appendChild(overlaySize);
    const overlayOpacityLabel = document.createElement('label');
    overlayOpacityLabel.textContent = 'Opacity';
    const overlayOpacity = document.createElement('input');
    overlayOpacity.type = 'range'; overlayOpacity.min = '10'; overlayOpacity.max = '100'; overlayOpacity.step = '1'; overlayOpacity.value = '100'; overlayOpacity.disabled = true;
    overlayOpacity.setAttribute('aria-label', 'Selected overlay opacity');
    overlayOpacity.addEventListener('input', () => {
      const item = activeOverlay();
      if (!item) return;
      item.opacity = Number(overlayOpacity.value) / 100;
      renderOverlays();
    });
    overlayOpacityLabel.appendChild(overlayOpacity);
    overlayColor.addEventListener('input', () => {
      const item = activeOverlay();
      if (!item || item.type !== 'text') return;
      item.color = overlayColor.value;
      renderOverlays();
    });
    const removeOverlay = document.createElement('button');
    removeOverlay.type = 'button';
    removeOverlay.textContent = 'Remove selected';
    removeOverlay.disabled = true;
    removeOverlay.addEventListener('click', () => {
      const id = state.activeOverlayId;
      state.overlays = state.overlays.filter(item => item.id !== id);
      selectOverlay(state.overlays.at(-1)?.id || '');
      renderOverlays();
      setStatus(state.overlays.length ? 'Selected overlay removed.' : 'Exact overlays cleared.');
    });
    state.overlaySize = overlaySize;
    state.overlayOpacity = overlayOpacity;
    state.overlayColor = overlayColor;
    state.overlayRemove = removeOverlay;
    overlayTuning.append(overlaySizeLabel, overlayOpacityLabel, removeOverlay);
    exactOverlay.append(overlayLabel, overlayCopy, overlayActions, overlayTextRow, overlayTuning);

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
    controls.append(modeGroup, zoom, sizeLabel, history, boundary, appearance, local, exactOverlay, adjustment, status);
    workspace.append(stage, controls);

    const footer = document.createElement('footer');
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'crump-precision-cancel'; cancel.textContent = 'Cancel'; cancel.addEventListener('click', close);
    const saveLocal = document.createElement('button'); saveLocal.type = 'button'; saveLocal.className = 'crump-precision-save-local'; saveLocal.textContent = 'Save local edit'; saveLocal.disabled = true;
    state.saveLocal = saveLocal;
    saveLocal.addEventListener('click', async () => {
      if (!hasSavableLocalEdit()) {
        setStatus('Move a local adjustment inside a selection or add an exact overlay first.', 'error');
        return;
      }
      saveLocal.disabled = true;
      saveLocal.setAttribute('aria-busy', 'true');
      setStatus('Saving a private, provider-free image version…');
      try {
        const preparedMask = localAdjustmentReady() ? await maskDataUrl() : '';
        const preparedOverlay = await overlayDataUrl();
        const response = await fetch(`/api/files/${encodeURIComponent(state.file.id)}/image-adjust`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
          body: JSON.stringify({
            maskDataUrl: preparedMask,
            adjustments: state.adjustments,
            overlayDataUrl: preparedOverlay,
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
        setStatus('Brush or outline the specific area you want to change first.', 'error');
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
      canvas.setAttribute('aria-label', 'Brush or outline the area of the image Crump may edit');
      const base = document.createElement('img');
      base.src = sourceUrl;
      base.alt = file?.name ? `Image to edit: ${file.name}` : 'Image to edit';
      base.width = image.naturalWidth;
      base.height = image.naturalHeight;
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
      const overlayCanvas = document.createElement('canvas');
      overlayCanvas.className = 'crump-precision-exact-canvas';
      overlayCanvas.width = image.naturalWidth;
      overlayCanvas.height = image.naturalHeight;
      overlayCanvas.hidden = true;
      overlayCanvas.setAttribute('aria-hidden', 'true');
      const overlayGuide = document.createElement('div');
      overlayGuide.className = 'crump-precision-overlay-guide';
      overlayGuide.hidden = true;
      overlayGuide.setAttribute('aria-hidden', 'true');
      const lassoGuide = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      lassoGuide.classList.add('crump-precision-lasso-guide');
      lassoGuide.setAttribute('viewBox', '0 0 1 1');
      lassoGuide.setAttribute('preserveAspectRatio', 'none');
      lassoGuide.setAttribute('aria-hidden', 'true');
      lassoGuide.hidden = true;
      const lassoPolygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      lassoGuide.appendChild(lassoPolygon);
      const frame = document.createElement('div');
      frame.className = 'crump-precision-canvas-frame';
      frame.append(base, preview, overlayCanvas, overlayGuide, canvas, lassoGuide);
      stage.replaceChildren(frame);
      stage.classList.remove('is-loading');
      await new Promise(resolve => requestAnimationFrame(resolve));
      if (state.modal !== modal) return;
      state.canvas = canvas;
      state.context = canvas.getContext('2d', {alpha: true, willReadFrequently: true});
      state.frame = frame;
      state.previewCanvas = preview;
      state.previewContext = preview.getContext('2d', {alpha: true});
      state.previewSource = previewSourceContext.getImageData(0, 0, preview.width, preview.height);
      state.previewMask = previewMask;
      state.overlayCanvas = overlayCanvas;
      state.overlayContext = overlayCanvas.getContext('2d', {alpha: true});
      state.overlayGuide = overlayGuide;
      state.lassoGuide = lassoGuide;
      state.lassoPolygon = lassoPolygon;
      const stageStyle = getComputedStyle(stage);
      const stageWidth = Math.max(1,
        stage.clientWidth - (parseFloat(stageStyle.paddingLeft) || 0) - (parseFloat(stageStyle.paddingRight) || 0));
      const stageHeight = Math.max(1,
        stage.clientHeight - (parseFloat(stageStyle.paddingTop) || 0) - (parseFloat(stageStyle.paddingBottom) || 0));
      const baseMaxHeight = parseFloat(getComputedStyle(base).maxHeight);
      const availableHeight = Number.isFinite(baseMaxHeight) && baseMaxHeight > 0
        ? Math.min(stageHeight, baseMaxHeight)
        : stageHeight;
      const fitScale = Math.min(
        1,
        stageWidth / Math.max(1, image.naturalWidth),
        availableHeight / Math.max(1, image.naturalHeight),
      );
      state.fitWidth = Math.max(1, Math.round(image.naturalWidth * fitScale));
      state.fitHeight = Math.max(1, Math.round(image.naturalHeight * fitScale));
      frame.style.width = `${state.fitWidth}px`;
      frame.style.height = `${state.fitHeight}px`;
      zoomFit.disabled = false;
      wireCanvas(canvas);
      renderOverlays();
      updateZoomControls();
      use.disabled = false;
      updateLocalControls();
      setStatus('Brush or outline the smallest area that should change.');
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
