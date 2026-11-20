const ERROR_MESSAGES = {
  invalid_url: 'الرابط غير صالح. تحقق من الرابط وحاول مرة أخرى.',
  unsupported_link: 'هذا الرابط غير مدعوم. يدعم VideoPocket فيديوهات يوتيوب الفردية فقط (وليس القوائم أو البث المباشر أو الصفحات الأخرى).',
  unsupported_quality: 'الجودة المطلوبة غير مدعومة.',
  private_video: 'هذا الفيديو خاص أو يتطلب تسجيل دخول، ولا يمكن تنزيله.',
  bot_check: 'يوتيوب رفض مؤقتًا طلب الخادم (تحقق آلي من أنه ليس برنامجًا آليًا)، وهذا لا يعني أن الفيديو خاص. حاول مرة أخرى بعد قليل.',
  video_unavailable: 'هذا الفيديو غير متاح أو تم حذفه.',
  live_stream: 'لا يمكن تنزيل بث مباشر جارٍ. انتظر حتى ينتهي البث وجرّب رابط الفيديو المسجّل.',
  video_too_long: 'هذا الفيديو أطول من الحد المسموح به ضمن الموارد المتاحة حاليًا.',
  file_too_large: 'حجم ملف هذا الفيديو أكبر من الحد المسموح به.',
  timeout: 'استغرق تحليل الفيديو وقتًا طويلًا. حاول مرة أخرى.',
  download_timeout: 'استغرق التنزيل وقتًا طويلًا. حاول مرة أخرى.',
  analysis_failed: 'تعذر تحليل هذا الفيديو. حاول مرة أخرى.',
  download_failed: 'تعذر تنزيل هذا الفيديو. حاول مرة أخرى.',
  insufficient_disk_space: 'لا توجد مساحة تخزين كافية على الخادم حاليًا. حاول لاحقًا.',
  queue_full: 'الخادم مشغول بعدد كبير من طلبات التنزيل حاليًا. حاول بعد قليل.',
  file_expired: 'انتهت صلاحية هذا الملف. يرجى إعادة تجهيز التحميل.',
  file_not_ready: 'الملف غير جاهز بعد.',
  job_not_found: 'لم تعد هذه المهمة موجودة، على الأرجح بسبب إعادة تشغيل الخادم (نوم بعد فترة عدم نشاط). يرجى تجهيز التحميل من جديد.',
  interrupted_by_restart: 'تم إيقاف الخادم أثناء معالجة هذا الطلب. حاول مرة أخرى.',
  network_error: 'تعذر الاتصال بالخادم. تحقق من اتصالك بالشبكة وأن الخادم يعمل.',
  cancelled: 'تم إلغاء التنزيل.',
};

const STATUS_LABELS = {
  pending: 'في الانتظار...',
  fetching_info: 'جارٍ جلب المعلومات...',
  downloading: 'جارٍ تنزيل الفيديو...',
  merging: 'جارٍ دمج الصوت والصورة...',
};

const JOB_ID_STORAGE_KEY = 'videopocket_job_id';

const state = {
  analyzeStatus: 'idle', // idle | loading | result | error
  analyzeError: null,
  result: null,
  analyzedUrl: null,
  selectedQuality: null,
  job: null, // { id, status, progress, speed, eta, error, filename, expires_at }
  pollTimer: null,
};

const els = {
  form: document.getElementById('analyzeForm'),
  urlInput: document.getElementById('urlInput'),
  analyzeBtn: document.getElementById('analyzeBtn'),

  loadingBox: document.getElementById('loadingBox'),
  loadingText: document.getElementById('loadingText'),

  errorBox: document.getElementById('errorBox'),
  errorText: document.getElementById('errorText'),
  retryAnalyzeBtn: document.getElementById('retryAnalyzeBtn'),

  resultCard: document.getElementById('resultCard'),
  videoThumb: document.getElementById('videoThumb'),
  videoDuration: document.getElementById('videoDuration'),
  videoTitle: document.getElementById('videoTitle'),
  videoAuthor: document.getElementById('videoAuthor'),
  qualityGrid: document.getElementById('qualityGrid'),
  prepareBtn: document.getElementById('prepareBtn'),

  jobBox: document.getElementById('jobBox'),
  jobSpinner: document.getElementById('jobSpinner'),
  jobStatusText: document.getElementById('jobStatusText'),
  progressWrap: document.getElementById('progressWrap'),
  progressFill: document.getElementById('progressFill'),
  progressPercent: document.getElementById('progressPercent'),
  progressSpeedEta: document.getElementById('progressSpeedEta'),
  cancelJobBtn: document.getElementById('cancelJobBtn'),

  jobErrorBox: document.getElementById('jobErrorBox'),
  jobErrorText: document.getElementById('jobErrorText'),
  retryJobBtn: document.getElementById('retryJobBtn'),

  readyBox: document.getElementById('readyBox'),
  expiryNote: document.getElementById('expiryNote'),
  saveBtn: document.getElementById('saveBtn'),
};

function errorMessage(code) {
  return ERROR_MESSAGES[code] || ERROR_MESSAGES.analysis_failed;
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '';
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatSize(bytes) {
  if (!bytes) return null;
  const mb = bytes / (1024 * 1024);
  if (mb < 1024) return `${mb.toFixed(0)} م.ب تقريبًا`;
  return `${(mb / 1024).toFixed(1)} ج.ب تقريبًا`;
}

function formatSpeed(bytesPerSec) {
  if (!bytesPerSec) return null;
  const n = Number(bytesPerSec);
  if (Number.isNaN(n)) return null;
  const mbps = n / (1024 * 1024);
  return `${mbps.toFixed(1)} م.ب/ث`;
}

function formatEta(seconds) {
  if (seconds === null || seconds === undefined) return null;
  const n = Number(seconds);
  if (Number.isNaN(n)) return null;
  return `متبقٍ ${formatDuration(n)}`;
}

function hideAll() {
  els.loadingBox.classList.add('hidden');
  els.errorBox.classList.add('hidden');
  els.resultCard.classList.add('hidden');
  els.jobBox.classList.add('hidden');
  els.jobErrorBox.classList.add('hidden');
  els.readyBox.classList.add('hidden');
}

function renderAnalyzeState() {
  els.analyzeBtn.disabled = state.analyzeStatus === 'loading';
  els.analyzeBtn.textContent = state.analyzeStatus === 'loading' ? 'جارٍ التحليل...' : 'عرض الفيديو';

  if (state.analyzeStatus === 'loading') {
    hideAll();
    els.loadingBox.classList.remove('hidden');
    els.loadingText.textContent = 'جارٍ جلب معلومات الفيديو...';
    return;
  }

  if (state.analyzeStatus === 'error') {
    hideAll();
    els.errorBox.classList.remove('hidden');
    els.errorText.textContent = errorMessage(state.analyzeError);
    return;
  }

  if (state.analyzeStatus === 'result' && state.result) {
    hideAll();
    els.resultCard.classList.remove('hidden');
    const r = state.result;
    els.videoTitle.textContent = r.title || '';
    els.videoAuthor.textContent = r.author || '';
    const dur = formatDuration(r.duration);
    els.videoDuration.textContent = dur;
    els.videoDuration.classList.toggle('hidden', !dur);

    if (r.thumbnail) {
      els.videoThumb.onerror = () => els.videoThumb.classList.add('hidden');
      els.videoThumb.onload = () => els.videoThumb.classList.remove('hidden');
      els.videoThumb.src = r.thumbnail;
    } else {
      els.videoThumb.classList.add('hidden');
    }

    renderQualityGrid();
    return;
  }

  hideAll();
}

function renderQualityGrid() {
  const r = state.result;
  els.qualityGrid.innerHTML = '';
  (r.qualities || []).forEach((q) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'quality-chip' + (q.height === state.selectedQuality ? ' selected' : '');
    const sizeText = formatSize(q.approx_size_bytes);
    chip.innerHTML = `${q.height}p` + (sizeText ? `<span class="q-size">${sizeText}</span>` : '');
    chip.addEventListener('click', () => {
      state.selectedQuality = q.height;
      renderQualityGrid();
    });
    els.qualityGrid.appendChild(chip);
  });
}

function renderJobState() {
  if (!state.job) return;
  const job = state.job;

  if (['pending', 'fetching_info', 'downloading', 'merging'].includes(job.status)) {
    hideAll();
    els.jobBox.classList.remove('hidden');
    els.jobStatusText.textContent = STATUS_LABELS[job.status] || job.status;

    if (job.status === 'downloading' && job.progress !== null && job.progress !== undefined) {
      els.progressWrap.classList.remove('hidden');
      const pct = Math.max(0, Math.min(100, job.progress));
      els.progressFill.style.width = `${pct}%`;
      els.progressPercent.textContent = `${pct.toFixed(0)}%`;
      const speed = formatSpeed(job.speed);
      const eta = formatEta(job.eta);
      els.progressSpeedEta.textContent = [speed, eta].filter(Boolean).join(' · ');
    } else {
      els.progressWrap.classList.add('hidden');
    }
    return;
  }

  if (job.status === 'failed' || job.status === 'cancelled') {
    hideAll();
    els.jobErrorBox.classList.remove('hidden');
    els.jobErrorText.textContent = errorMessage(job.status === 'cancelled' ? 'cancelled' : job.error);
    return;
  }

  if (job.status === 'ready') {
    hideAll();
    els.readyBox.classList.remove('hidden');
    if (job.expires_at) {
      const expiryDate = new Date(job.expires_at * 1000);
      els.expiryNote.textContent = `هذا الملف صالح حتى ${expiryDate.toLocaleTimeString('ar', { hour: '2-digit', minute: '2-digit' })}.`;
    }
    return;
  }

  if (job.status === 'expired') {
    hideAll();
    els.jobErrorBox.classList.remove('hidden');
    els.jobErrorText.textContent = errorMessage('file_expired');
  }
}

function saveJobIdLocally(jobId) {
  try {
    localStorage.setItem(JOB_ID_STORAGE_KEY, jobId);
  } catch (e) {
    // localStorage unavailable; job recovery on refresh simply won't work
  }
}

function loadSavedJobId() {
  try {
    return localStorage.getItem(JOB_ID_STORAGE_KEY);
  } catch (e) {
    return null;
  }
}

function clearSavedJobId() {
  try {
    localStorage.removeItem(JOB_ID_STORAGE_KEY);
  } catch (e) {
    // ignore
  }
}

async function analyze() {
  if (state.analyzeStatus === 'loading') return;
  const url = els.urlInput.value.trim();
  if (!url) return;

  state.analyzeStatus = 'loading';
  state.result = null;
  state.selectedQuality = null;
  renderAnalyzeState();

  let data;
  try {
    const response = await fetch(`${API_BASE_URL}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    data = await response.json();
  } catch (err) {
    state.analyzeStatus = 'error';
    state.analyzeError = 'network_error';
    renderAnalyzeState();
    return;
  }

  if (data && data.success) {
    state.analyzeStatus = 'result';
    state.result = data;
    state.analyzedUrl = url;
    state.selectedQuality = data.default_quality;
  } else {
    state.analyzeStatus = 'error';
    state.analyzeError = (data && data.error) || 'analysis_failed';
  }
  renderAnalyzeState();
}

async function prepareDownload() {
  if (!state.analyzedUrl || !state.selectedQuality) return;

  els.prepareBtn.disabled = true;
  let data;
  try {
    const response = await fetch(`${API_BASE_URL}/api/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: state.analyzedUrl, quality: state.selectedQuality }),
    });
    data = await response.json();
  } catch (err) {
    els.prepareBtn.disabled = false;
    state.job = { status: 'failed', error: 'network_error' };
    renderJobState();
    return;
  }
  els.prepareBtn.disabled = false;

  if (!data || !data.success) {
    state.job = { status: 'failed', error: (data && data.error) || 'download_failed' };
    renderJobState();
    return;
  }

  state.job = { id: data.job_id, status: data.status };
  saveJobIdLocally(data.job_id);
  renderJobState();
  startPolling(data.job_id);
}

async function fetchJobStatus(jobId) {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`);
  return response.json();
}

function startPolling(jobId) {
  stopPolling();
  state.pollTimer = setInterval(async () => {
    let data;
    try {
      data = await fetchJobStatus(jobId);
    } catch (err) {
      return; // transient network hiccup; keep polling
    }

    if (!data || !data.success) {
      state.job = { status: 'failed', error: (data && data.error) || 'job_not_found' };
      stopPolling();
      clearSavedJobId();
      renderJobState();
      return;
    }

    state.job = {
      id: data.job_id,
      status: data.status,
      progress: data.progress,
      speed: data.speed,
      eta: data.eta,
      error: data.error,
      filename: data.filename,
      expires_at: data.expires_at,
    };
    renderJobState();

    if (['ready', 'failed', 'cancelled', 'expired'].includes(data.status)) {
      stopPolling();
      if (data.status !== 'ready') clearSavedJobId();
    }
  }, 1500);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function cancelJob() {
  if (!state.job || !state.job.id) return;
  els.cancelJobBtn.disabled = true;
  try {
    await fetch(`${API_BASE_URL}/api/jobs/${state.job.id}/cancel`, { method: 'POST' });
  } catch (err) {
    // ignore; polling will reflect eventual state
  }
  els.cancelJobBtn.disabled = false;
}

function saveFile() {
  if (!state.job || !state.job.id) return;
  const url = `${API_BASE_URL}/api/jobs/${state.job.id}/file`;
  const link = document.createElement('a');
  link.href = url;
  link.download = state.job.filename || 'videopocket.mp4';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  clearSavedJobId();
}

function retryAfterJobError() {
  stopPolling();
  state.job = null;
  clearSavedJobId();
  renderAnalyzeState();
}

els.form.addEventListener('submit', (e) => {
  e.preventDefault();
  analyze();
});

els.retryAnalyzeBtn.addEventListener('click', () => {
  state.analyzeStatus = 'idle';
  renderAnalyzeState();
});

els.prepareBtn.addEventListener('click', prepareDownload);
els.cancelJobBtn.addEventListener('click', cancelJob);
els.retryJobBtn.addEventListener('click', retryAfterJobError);
els.saveBtn.addEventListener('click', saveFile);

// Resume a job after a page refresh, as long as it is still valid.
(async function resumeSavedJob() {
  const savedId = loadSavedJobId();
  if (!savedId) return;

  let data;
  try {
    data = await fetchJobStatus(savedId);
  } catch (err) {
    return;
  }

  if (!data || !data.success) {
    clearSavedJobId();
    state.job = { status: 'failed', error: (data && data.error) || 'job_not_found' };
    renderJobState();
    return;
  }

  state.job = {
    id: data.job_id,
    status: data.status,
    progress: data.progress,
    speed: data.speed,
    eta: data.eta,
    error: data.error,
    filename: data.filename,
    expires_at: data.expires_at,
  };
  renderJobState();

  if (['pending', 'fetching_info', 'downloading', 'merging'].includes(data.status)) {
    startPolling(savedId);
  } else if (data.status !== 'ready') {
    clearSavedJobId();
  }
})();

renderAnalyzeState();

// --- PWA: install prompt (Android/Chromium), iOS instructions, service worker ---
//
// Installing VideoPocket only makes the interface itself open faster/offline
// as an app shell. It does NOT make downloading new videos work offline —
// analysis and downloads always require the server to be reachable.

const installEls = {
  installBtn: document.getElementById('installBtn'),
  iosInstallPopover: document.getElementById('iosInstallPopover'),
  iosInstallClose: document.getElementById('iosInstallClose'),
};

function isStandalone() {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  );
}

function isIOS() {
  const ua = window.navigator.userAgent || '';
  const isAppleTouch = /iPad|iPhone|iPod/.test(ua);
  const isIPadOS = ua.includes('Macintosh') && 'ontouchend' in document;
  return isAppleTouch || isIPadOS;
}

let deferredInstallPrompt = null;

function showInstallButton() {
  if (isStandalone()) return;
  installEls.installBtn.classList.remove('hidden');
}

function hideInstallButton() {
  installEls.installBtn.classList.add('hidden');
}

function showIosInstallPopover() {
  installEls.iosInstallPopover.classList.remove('hidden');
}

function hideIosInstallPopover() {
  installEls.iosInstallPopover.classList.add('hidden');
}

if (!isStandalone()) {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    showInstallButton();
  });

  if (isIOS()) {
    showInstallButton();
  }
}

window.addEventListener('appinstalled', () => {
  deferredInstallPrompt = null;
  hideInstallButton();
});

installEls.installBtn.addEventListener('click', async () => {
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    const choice = await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    if (choice && choice.outcome === 'accepted') {
      hideInstallButton();
    }
    return;
  }

  if (isIOS()) {
    showIosInstallPopover();
  }
});

installEls.iosInstallClose.addEventListener('click', hideIosInstallPopover);
installEls.iosInstallPopover.addEventListener('click', (e) => {
  if (e.target === installEls.iosInstallPopover) hideIosInstallPopover();
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('service-worker.js').catch(() => {
      // Service worker registration failure must never block Analyze/Download.
    });
  });
}
