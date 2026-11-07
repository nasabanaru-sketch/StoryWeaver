/**
 * StoryWeaver Live — Workbench Application Logic (workbench.js)
 */

(function () {
  'use strict';

  // State Management
  const wbState = {
    // Presets & Config
    presets: [],
    currentSceneId: '',
    config: {},
    workflows: [],
    currentWorkflow: 'storyweaver_anime_api.json',

    // Face / Person Image
    faceBlob: null,
    faceImageFilename: '',
    isCroppedImage: false,
    sessionId: '',
    vlmData: null,
    vlmExtraction: null,
    cameraStream: null,
    cameraActive: false,
    pendingCroppedFilename: '',
    pendingCroppedBase64: '',
    capturedFacesList: [],

    // Audio / Voice
    audioBlob: null,
    audioAnalysis: null,
    isRecording: false,
    audioContext: null,
    audioRecorderNode: null,
    audioChunks: [],
    recStartTime: 0,
    recTimerInterval: null,
    analyserNode: null,
    meterAnimFrame: null,

    // 3-Point Calibration
    baselineData: null,
    isRecordingCalib: false,
    calibRecordingMode: null,
    calibSession: null,

    // Status Timer
    statusTimerInterval: null,
    statusStartTime: 0,

    // FD Prompt Option
    fdOption: 'B', // 'B' (表情専念) or 'A' (外見包含)

    // Generation Results & History
    history: [],
    lastResult: null,

    // Predefined Expression Templates (README §3.2)
    expressionPresets: {
      BURNING: 'shouting, fierce determination, intense eyes, open mouth, battle cry, dynamic expression',
      JOYFUL: 'confident smile, bright expressive eyes, joyful and energetic expression',
      EMOTIONAL: 'tearful eyes, emotional expression, biting lip, dramatic sorrow, desperate look',
      COOL: 'calm and composed expression, sharp gaze, cool determination, slight smirk'
    }
  };

  const DEFAULT_QWEN_SYSTEM_PROMPT = `What is the emotion of the speaker and does the speaker whisper or shout?`;

  // DOM Elements
  const el = {
    // Status
    statusPill: document.getElementById('wb-status-pill'),
    statusText: document.getElementById('wb-status-text'),
    elapsedTimer: document.getElementById('wb-elapsed-timer'),
    vramVal: document.getElementById('wb-vram-val'),
    errorBanner: document.getElementById('wb-error-banner'),
    errorMsg: document.getElementById('wb-error-msg'),
    btnCloseError: document.getElementById('btn-close-error'),

    // Scene
    sceneSelect: document.getElementById('wb-scene-select'),
    btnLoadScene: document.getElementById('wb-btn-load-scene'),
    sceneId: document.getElementById('wb-scene-id'),
    sceneName: document.getElementById('wb-scene-name'),
    sceneScript: document.getElementById('wb-scene-script'),
    scenePrompt: document.getElementById('wb-scene-prompt'),
    sceneNegPrompt: document.getElementById('wb-scene-neg-prompt'),
    btnSaveCurrentScene: document.getElementById('wb-btn-save-current-scene'),
    btnAddScene: document.getElementById('wb-btn-add-scene'),
    btnDeleteScene: document.getElementById('wb-btn-delete-scene'),

    // Face
    faceDropzone: document.getElementById('face-dropzone'),
    faceFileInput: document.getElementById('face-file-input'),
    facePreviewImg: document.getElementById('face-preview-img'),
    facePlaceholder: document.getElementById('face-placeholder'),
    currentFaceLabel: document.getElementById('wb-current-face-label'),
    autoCropCheck: document.getElementById('wb-auto-crop-check'),
    btnToggleCamera: document.getElementById('wb-btn-toggle-camera'),
    cameraPanel: document.getElementById('wb-camera-panel'),
    selectCamera: document.getElementById('wb-select-camera'),
    cameraViewfinder: document.getElementById('wb-camera-viewfinder'),
    cameraVideo: document.getElementById('wb-camera-video'),
    cameraCanvas: document.getElementById('wb-camera-canvas'),
    cameraCropPreview: document.getElementById('wb-camera-crop-preview'),
    guideOverlay: document.getElementById('wb-guide-overlay'),
    cameraLiveActions: document.getElementById('wb-camera-live-actions'),
    cameraReviewActions: document.getElementById('wb-camera-review-actions'),
    btnCaptureCrop: document.getElementById('wb-btn-capture-crop'),
    btnRetakeCamera: document.getElementById('wb-btn-retake-camera'),
    btnUseCropped: document.getElementById('wb-btn-use-cropped'),
    btnRefreshCaptured: document.getElementById('wb-btn-refresh-captured'),
    capturedFacesGrid: document.getElementById('wb-captured-faces-grid'),
    btnAnalyzeFace: document.getElementById('wb-btn-analyze-face'),
    faceAnalysisBadge: document.getElementById('face-analysis-badge'),
    vlmTimeVal: document.getElementById('vlm-time-val'),
    vlmVramVal: document.getElementById('vlm-vram-val'),
    attrFace: document.getElementById('attr-face'),
    attrGender: document.getElementById('attr-gender'),
    attrHairLen: document.getElementById('attr-hair-len'),
    attrBangs: document.getElementById('attr-bangs'),
    attrForehead: document.getElementById('attr-forehead'),
    attrGlasses: document.getElementById('attr-glasses'),
    attrBeard: document.getElementById('attr-beard'),
    vlmRawJson: document.getElementById('vlm-raw-json'),
    inputGender: document.getElementById('wb-input-gender'),
    inputTraits: document.getElementById('wb-input-traits'),
    inputNegbias: document.getElementById('wb-input-negbias'),

    // Audio & 3-Point Calibration
    calibDetails: document.getElementById('wb-calib-details'),
    badgeNormal: document.getElementById('wb-badge-normal'),
    badgePower: document.getElementById('wb-badge-power'),
    badgeWhisper: document.getElementById('wb-badge-whisper'),
    calibUpdatedAt: document.getElementById('wb-calib-updated-at'),
    btnReanalyzeAfterCalib: document.getElementById('wb-btn-reanalyze-after-calib'),
    calibChips: document.getElementById('wb-calib-chips'),
    calibProgress: document.getElementById('wb-calib-progress'),
    rawFeaturesGrid: document.getElementById('wb-raw-features-grid'),
    audioFileInput: document.getElementById('wb-audio-file-input'),
    selectMic: document.getElementById('wb-select-mic'),
    btnMicToggle: document.getElementById('wb-btn-mic-toggle'),
    recLabel: document.getElementById('wb-rec-label'),
    recTimer: document.getElementById('wb-rec-timer'),
    levelFill: document.getElementById('wb-level-fill'),
    audioPlayer: document.getElementById('wb-audio-player'),
    audioInfo: document.getElementById('wb-audio-info'),
    btnAnalyzeAudio: document.getElementById('wb-btn-analyze-audio'),
    audioBadge: document.getElementById('wb-audio-badge'),
    resSenseEmo: document.getElementById('res-sense-emo'),
    resRmsDb: document.getElementById('res-rms-db'),
    resVerdict: document.getElementById('res-verdict'),
    resRecognizedText: document.getElementById('res-recognized-text'),
    selectEmotionMode: document.getElementById('wb-select-emotion-mode'),
    btnSaveMode: document.getElementById('wb-btn-save-mode'),
    audioCalibChip: document.getElementById('wb-audio-calib-chip'),

    // Qwen2-Audio Hybrid Controls & Results
    qwenPromptDetails: document.getElementById('wb-qwen-prompt-details'),
    qwenSystemPrompt: document.getElementById('wb-qwen-system-prompt'),
    qwenCustomInstruction: document.getElementById('wb-qwen-custom-instruction'),
    btnResetQwenPrompt: document.getElementById('wb-btn-reset-qwen-prompt'),
    qwenResultsCard: document.getElementById('wb-qwen-results-card'),
    qwenNuanceBadge: document.getElementById('wb-qwen-nuance-badge'),
    qwenTimeVal: document.getElementById('wb-qwen-time-val'),
    qwenVramVal: document.getElementById('wb-qwen-vram-val'),
    qwenPerceptionEn: document.getElementById('wb-qwen-perception-en'),
    qwenSemanticBridgeEn: document.getElementById('wb-qwen-semantic-bridge-en'),
    qwenDeltasGrid: document.getElementById('wb-qwen-deltas-grid'),
    qwenTop1Card: document.getElementById('wb-qwen-top1-card'),
    qwenTop1ScoreWrap: document.getElementById('wb-qwen-top1-score-wrap'),
    qwenTop1Score: document.getElementById('wb-qwen-top1-score'),
    qwenTop1Icon: document.getElementById('wb-qwen-top1-icon'),
    qwenTop1Name: document.getElementById('wb-qwen-top1-name'),
    qwenTop2Card: document.getElementById('wb-qwen-top2-card'),
    qwenTop2Rank: document.getElementById('wb-qwen-top2-rank'),
    qwenTop2ScoreWrap: document.getElementById('wb-qwen-top2-score-wrap'),
    qwenTop2Score: document.getElementById('wb-qwen-top2-score'),
    qwenTop2Icon: document.getElementById('wb-qwen-top2-icon'),
    qwenTop2Name: document.getElementById('wb-qwen-top2-name'),
    qwenE8List: document.getElementById('wb-qwen-e8-list'),
    btnQwenUnload: document.getElementById('wb-btn-qwen-unload'),

    detailed12Card: document.getElementById('wb-detailed-12-card'),
    top1Card: document.getElementById('wb-top1-card'),
    top1ScoreWrap: document.getElementById('wb-top1-score-wrap'),
    top1Score: document.getElementById('wb-top1-score'),
    top1Icon: document.getElementById('wb-top1-icon'),
    top1Name: document.getElementById('wb-top1-name'),
    top2Card: document.getElementById('wb-top2-card'),
    top2Rank: document.getElementById('wb-top2-rank'),
    top2ScoreWrap: document.getElementById('wb-top2-score-wrap'),
    top2Score: document.getElementById('wb-top2-score'),
    top2Icon: document.getElementById('wb-top2-icon'),
    top2Name: document.getElementById('wb-top2-name'),
    f7Grid: document.getElementById('wb-f7-grid'),
    e12List: document.getElementById('wb-e12-list'),
    burningSlider: document.getElementById('wb-burning-slider'),
    thresholdValText: document.getElementById('wb-threshold-val-text'),
    btnSaveThreshold: document.getElementById('wb-btn-save-threshold'),
    scriptFinal: document.getElementById('wb-script-final'),
    btnRestoreSceneScript: document.getElementById('wb-btn-restore-scene-script'),
    btnApplyRecognizedScript: document.getElementById('wb-btn-apply-recognized-script'),
    inputExpression: document.getElementById('wb-input-expression'),

    // Prompts & Generation
    workflowSelect: document.getElementById('wb-workflow-select'),
    colPosFd: document.getElementById('wb-col-pos-fd'),
    fdDisabledBadge: document.getElementById('wb-fd-disabled-badge'),
    autoAssembleToggle: document.getElementById('wb-auto-assemble-toggle'),
    btnManualAssemble: document.getElementById('wb-btn-manual-assemble'),
    btnStartGenerate: document.getElementById('wb-btn-start-generate'),
    qualityPrompt: document.getElementById('wb-quality-prompt'),
    baseNegative: document.getElementById('wb-base-negative'),
    promptPosBase: document.getElementById('wb-prompt-pos-base'),
    promptNegBase: document.getElementById('wb-prompt-neg-base'),
    promptPosFd: document.getElementById('wb-prompt-pos-fd'),
    btnFdModeB: document.getElementById('wb-btn-fd-mode-b'),
    btnFdModeA: document.getElementById('wb-btn-fd-mode-a'),

    // Results & Preview
    generatedImage: document.getElementById('wb-generated-image'),
    imagePlaceholder: document.getElementById('wb-image-placeholder'),
    genSpinner: document.getElementById('wb-gen-spinner'),
    genSpinnerText: document.getElementById('wb-gen-spinnerText'),
    btnDownloadResult: document.getElementById('wb-btn-download-result'),
    savedPathText: document.getElementById('wb-saved-path-text'),
    cardSceneTitle: document.getElementById('wb-card-scene-title'),
    cardScriptText: document.getElementById('wb-card-script-text'),
    historyList: document.getElementById('wb-history-list'),
    btnClearHistory: document.getElementById('wb-btn-clear-history'),
    toastContainer: document.getElementById('toast-container')
  };

  // Toast Helper
  function showToast(msg, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = msg;
    el.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  // Error Banner Helper
  function showError(msg) {
    if (!msg) {
      el.errorBanner.classList.add('hidden');
      return;
    }
    el.errorMsg.textContent = msg;
    el.errorBanner.classList.remove('hidden');
  }

  // Status Indicator
  function setStatus(stateCode, customText = '') {
    el.statusPill.setAttribute('data-state', stateCode);
    if (stateCode === 'idle') {
      el.statusText.textContent = customText || '待機中 (IDLE)';
      stopStatusTimer();
    } else if (stateCode === 'analyzing_face') {
      el.statusText.textContent = customText || '人物画像分析中 (ANALYZING FACE)';
      startStatusTimer();
    } else if (stateCode === 'recording_audio') {
      el.statusText.textContent = customText || '音声録音中 (RECORDING AUDIO)';
      startStatusTimer();
    } else if (stateCode === 'analyzing_audio') {
      el.statusText.textContent = customText || '音声分析中 (ANALYZING AUDIO)';
      startStatusTimer();
    } else if (stateCode === 'generating_image') {
      el.statusText.textContent = customText || '画像生成中 (GENERATING IMAGE)';
      startStatusTimer();
    }
  }

  function startStatusTimer() {
    wbState.statusStartTime = Date.now();
    clearInterval(wbState.statusTimerInterval);
    wbState.statusTimerInterval = setInterval(() => {
      const elapsed = ((Date.now() - wbState.statusStartTime) / 1000).toFixed(1);
      el.elapsedTimer.textContent = `${elapsed}s`;
    }, 100);
  }

  function stopStatusTimer() {
    clearInterval(wbState.statusTimerInterval);
  }

  // -------------------------------------------------------------------------
  // 1. Initial Load & Config / Presets
  // -------------------------------------------------------------------------
  async function init() {
    setupEventListeners();
    await loadConfig();
    await loadWorkflows();
    await loadPresets();
    await loadWbBaselineStatus();
    await populateMicDevices();
    await populateCameraDevices();
    await loadCapturedFacesList();
    triggerAutoAssemble();
  }

  async function loadWorkflows() {
    if (!el.workflowSelect) return;
    try {
      const res = await fetch('/api/workflows');
      if (!res.ok) return;
      const data = await res.json();
      wbState.workflows = data.workflows || [];
      wbState.currentWorkflow = data.current_workflow || wbState.config.WORKFLOW_PATH || 'storyweaver_anime_api.json';

      el.workflowSelect.innerHTML = '';
      wbState.workflows.forEach(wf => {
        const opt = document.createElement('option');
        opt.value = wf.filename;
        opt.textContent = wf.exists === false ? `${wf.label} (${wf.filename} - 未配置)` : `${wf.label} (${wf.filename})`;
        if (wf.exists === false) opt.disabled = true;
        if (wf.filename === wbState.currentWorkflow) opt.selected = true;
        el.workflowSelect.appendChild(opt);
      });
      updateWorkflowFdUiState();
    } catch (e) {
      console.warn('workflows load error:', e);
    }
  }

  function isCurrentWorkflowHasFd() {
    const selectedWf = el.workflowSelect ? el.workflowSelect.value : wbState.currentWorkflow;
    const wfObj = wbState.workflows.find(w => w.filename === selectedWf);
    if (wfObj) return Boolean(wfObj.has_fd);
    return selectedWf !== 'storyweaver_anime_nofd_api.json';
  }

  function updateWorkflowFdUiState() {
    const hasFd = isCurrentWorkflowHasFd();
    if (el.promptPosFd) {
      el.promptPosFd.disabled = !hasFd;
    }
    if (el.btnFdModeB) {
      el.btnFdModeB.disabled = !hasFd;
    }
    if (el.btnFdModeA) {
      el.btnFdModeA.disabled = !hasFd;
    }
    if (el.colPosFd) {
      el.colPosFd.classList.toggle('fd-disabled', !hasFd);
    }
    if (el.fdDisabledBadge) {
      el.fdDisabledBadge.classList.toggle('hidden', hasFd);
    }
  }

  function updateEmotionModeUI() {
    const mode = el.selectEmotionMode ? el.selectEmotionMode.value : 'standard';
    if (el.qwenPromptDetails) {
      el.qwenPromptDetails.style.display = (mode === 'qwen2_audio_hybrid') ? 'block' : 'none';
    }
    if (el.btnAnalyzeAudio) {
      const span = el.btnAnalyzeAudio.querySelector('span');
      if (span) {
        if (mode === 'qwen2_audio_hybrid') {
          span.textContent = '🎙 Qwen2-Audio ハイブリッド分析をスタート';
        } else if (mode === 'detailed_12') {
          span.textContent = '🎙 音声分析をスタート (SenseVoice / 12-Emo)';
        } else {
          span.textContent = '🎙 音声分析をスタート (SenseVoice 従来)';
        }
      }
    }
  }

  async function loadConfig() {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        wbState.config = await res.json();
        const thresh = wbState.config.BURNING_DB_THRESHOLD ?? -12.0;
        el.burningSlider.value = thresh;
        el.thresholdValText.innerHTML = `<strong>${thresh.toFixed(1)}</strong> dBFS`;
        if (wbState.config.emotion_mode && el.selectEmotionMode) {
          el.selectEmotionMode.value = wbState.config.emotion_mode;
        }
      }
      if (el.qwenSystemPrompt && !el.qwenSystemPrompt.value) {
        el.qwenSystemPrompt.value = DEFAULT_QWEN_SYSTEM_PROMPT;
      }
      updateEmotionModeUI();
    } catch (e) {
      console.warn('config load error:', e);
    }
  }

  async function loadPresets() {
    try {
      const res = await fetch('/api/presets');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      wbState.presets = data.scenes || [];
      renderSceneSelect();
      if (wbState.presets.length > 0) {
        selectScene(wbState.presets[0].id);
      }
    } catch (e) {
      console.error('presets load error:', e);
      showError('プリセットの読み込みに失敗しました: ' + e.message);
    }
  }

  function renderSceneSelect() {
    el.sceneSelect.innerHTML = '';
    wbState.presets.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = `${s.name} (${s.id})`;
      el.sceneSelect.appendChild(opt);
    });
  }

  function selectScene(sceneId) {
    const scene = wbState.presets.find(s => s.id === sceneId);
    if (!scene) return;
    wbState.currentSceneId = scene.id;
    el.sceneSelect.value = scene.id;
    el.sceneId.value = scene.id;
    el.sceneName.value = scene.name;
    el.sceneScript.value = scene.script_text;
    el.scenePrompt.value = scene.scene_prompt;
    if (el.sceneNegPrompt) {
      el.sceneNegPrompt.value = scene.scene_neg_prompt || '';
    }

    // 連動
    if (!el.scriptFinal.value) {
      el.scriptFinal.value = scene.script_text;
    }
    el.cardSceneTitle.textContent = scene.name;
    el.cardScriptText.textContent = el.scriptFinal.value || scene.script_text;

    triggerAutoAssemble();
  }

  // -------------------------------------------------------------------------
  // B. Scene CRUD Operations
  // -------------------------------------------------------------------------
  async function savePresetsToServer() {
    try {
      const res = await fetch('/api/presets', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenes: wbState.presets })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('プリセット (presets.json) を保存しました', 'success');
    } catch (e) {
      showError('プリセット保存に失敗しました: ' + e.message);
    }
  }

  function handleSaveCurrentScene() {
    const id = el.sceneId.value.trim();
    const name = el.sceneName.value.trim();
    if (!id || !name) {
      showError('シーンIDとシーン名は必須です');
      return;
    }
    let idx = wbState.presets.findIndex(s => s.id === id);
    const updated = {
      id: id,
      name: name,
      script_text: el.sceneScript.value.trim(),
      scene_prompt: el.scenePrompt.value.trim(),
      scene_neg_prompt: el.sceneNegPrompt ? el.sceneNegPrompt.value.trim() : ''
    };
    if (idx >= 0) {
      wbState.presets[idx] = updated;
    } else {
      wbState.presets.push(updated);
    }
    renderSceneSelect();
    selectScene(id);
    savePresetsToServer();
  }

  function handleAddNewScene() {
    const newId = `scene_${String(wbState.presets.length + 1).padStart(2, '0')}`;
    const newScene = {
      id: newId,
      name: '新規シーン',
      script_text: 'セリフを入力してください',
      scene_prompt: 'fantasy anime, dynamic pose, vibrant colors',
      scene_neg_prompt: ''
    };
    wbState.presets.push(newScene);
    renderSceneSelect();
    selectScene(newId);
    savePresetsToServer();
  }

  function handleDeleteScene() {
    const id = el.sceneId.value.trim();
    if (!id) return;
    if (wbState.presets.length <= 1) {
      showError('これ以上シーンを削除できません');
      return;
    }
    if (!confirm(`シーン「${el.sceneName.value} (${id})」を削除しますか？`)) return;
    wbState.presets = wbState.presets.filter(s => s.id !== id);
    renderSceneSelect();
    if (wbState.presets.length > 0) {
      selectScene(wbState.presets[0].id);
    }
    savePresetsToServer();
  }

  // -------------------------------------------------------------------------
  // C. Face Image, Camera Capture, Cropped Selection & VLM Analysis
  // -------------------------------------------------------------------------
  function updateCurrentFaceLabel(label) {
    if (el.currentFaceLabel) {
      el.currentFaceLabel.textContent = `入力画像: ${label}`;
    }
  }

  async function setFaceImageFile(file) {
    if (!file) return;
    showError('');

    const autoCrop = el.autoCropCheck ? el.autoCropCheck.checked : true;
    if (autoCrop) {
      try {
        const formData = new FormData();
        formData.append('face_image', file, file.name || 'upload.jpg');
        const res = await fetch('/api/capture_cropped_face', {
          method: 'POST',
          body: formData
        });
        if (res.ok) {
          const data = await res.json();
          if (data.image_filename && data.cropped_image_base64) {
            const dataUrl = `data:image/jpeg;base64,${data.cropped_image_base64}`;
            const blobRes = await fetch(dataUrl);
            const croppedBlob = await blobRes.blob();
            wbState.faceBlob = croppedBlob;
            wbState.faceImageFilename = data.image_filename;
            wbState.isCroppedImage = true;
            el.facePreviewImg.src = dataUrl;
            el.facePreviewImg.classList.remove('hidden');
            el.facePlaceholder.classList.add('hidden');
            updateCurrentFaceLabel(`${data.image_filename} (自動クロップ済)`);
            showToast(`「${file.name}」を頭髪〜肩に自動クロップしてセットしました`, 'success');
            await loadCapturedFacesList();
            return;
          }
        }
      } catch (e) {
        console.warn('auto_crop upload preview fallback:', e);
      }
    }

    wbState.faceBlob = file;
    wbState.faceImageFilename = file.name;
    wbState.isCroppedImage = false;
    const url = URL.createObjectURL(file);
    el.facePreviewImg.src = url;
    el.facePreviewImg.classList.remove('hidden');
    el.facePlaceholder.classList.add('hidden');
    updateCurrentFaceLabel(`${file.name} (生画像)`);
  }

  // ① カメラで撮影してクロップ機能
  async function populateCameraDevices() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices || !el.selectCamera) return;
      const devices = await navigator.mediaDevices.enumerateDevices();
      const cams = devices.filter(d => d.kind === 'videoinput');
      el.selectCamera.innerHTML = '';
      cams.forEach((c, idx) => {
        const opt = document.createElement('option');
        opt.value = c.deviceId;
        opt.textContent = c.label || `カメラ ${idx + 1}`;
        el.selectCamera.appendChild(opt);
      });
    } catch (e) {
      console.warn('camera enumeration error:', e);
    }
  }

  async function toggleWorkbenchCamera() {
    if (wbState.cameraActive) {
      stopWorkbenchCamera();
    } else {
      await startWorkbenchCamera();
    }
  }

  async function startWorkbenchCamera() {
    stopWorkbenchCameraStream();
    wbState.pendingCroppedFilename = '';
    wbState.pendingCroppedBase64 = '';

    const camId = el.selectCamera ? el.selectCamera.value : '';
    const constraints = {
      video: camId
        ? { deviceId: { exact: camId }, width: { ideal: 1280 }, height: { ideal: 960 } }
        : { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false
    };

    try {
      wbState.cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
      try {
        wbState.cameraStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      } catch (e2) {
        showError('カメラへのアクセスに失敗しました: ' + e2.message);
        return;
      }
    }

    await populateCameraDevices();
    el.cameraVideo.srcObject = wbState.cameraStream;
    await el.cameraVideo.play();

    wbState.cameraActive = true;
    el.cameraPanel.classList.remove('hidden');
    el.btnToggleCamera.textContent = '✕ カメラを閉じる';
    resetWorkbenchCameraReview();
  }

  function stopWorkbenchCameraStream() {
    if (wbState.cameraStream) {
      wbState.cameraStream.getTracks().forEach(t => t.stop());
      wbState.cameraStream = null;
    }
  }

  function stopWorkbenchCamera() {
    stopWorkbenchCameraStream();
    wbState.cameraActive = false;
    if (el.cameraPanel) el.cameraPanel.classList.add('hidden');
    if (el.btnToggleCamera) el.btnToggleCamera.textContent = '📷 カメラを起動';
  }

  function resetWorkbenchCameraReview() {
    wbState.pendingCroppedFilename = '';
    wbState.pendingCroppedBase64 = '';
    if (el.cameraViewfinder) el.cameraViewfinder.classList.remove('cropped-mode');
    if (el.cameraVideo) el.cameraVideo.classList.remove('hidden');
    if (el.guideOverlay) el.guideOverlay.classList.remove('hidden');
    if (el.cameraCropPreview) el.cameraCropPreview.classList.add('hidden');
    if (el.cameraLiveActions) el.cameraLiveActions.classList.remove('hidden');
    if (el.cameraReviewActions) el.cameraReviewActions.classList.add('hidden');
  }

  async function handleCaptureAndCrop() {
    if (!wbState.cameraStream || !el.cameraVideo) return;
    const video = el.cameraVideo;
    const canvas = el.cameraCanvas;
    canvas.width = video.videoWidth || 768;
    canvas.height = video.videoHeight || 1024;
    const ctx = canvas.getContext('2d');

    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    el.btnCaptureCrop.disabled = true;
    canvas.toBlob(async (blob) => {
      try {
        if (!blob) throw new Error('カメラフレームの取得に失敗しました');
        const formData = new FormData();
        formData.append('face_image', blob, 'wb_capture.jpg');

        const res = await fetch('/api/capture_cropped_face', {
          method: 'POST',
          body: formData
        });
        if (!res.ok) {
          const errJson = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
          throw new Error(errJson.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        wbState.pendingCroppedFilename = data.image_filename;
        wbState.pendingCroppedBase64 = data.cropped_image_base64;

        const dataUrl = `data:image/jpeg;base64,${data.cropped_image_base64}`;
        el.cameraCropPreview.src = dataUrl;
        el.cameraViewfinder.classList.add('cropped-mode');
        el.cameraVideo.classList.add('hidden');
        el.guideOverlay.classList.add('hidden');
        el.cameraCropPreview.classList.remove('hidden');
        el.cameraLiveActions.classList.add('hidden');
        el.cameraReviewActions.classList.remove('hidden');

        await loadCapturedFacesList();
        showToast('頭髪〜肩にクロップしました。確認してセットしてください', 'info');
      } catch (e) {
        console.error('capture_cropped_face error:', e);
        showError('撮影クロップ処理に失敗しました: ' + e.message);
      } finally {
        el.btnCaptureCrop.disabled = false;
      }
    }, 'image/jpeg', 0.95);
  }

  async function handleUsePendingCropped() {
    if (!wbState.pendingCroppedFilename || !wbState.pendingCroppedBase64) return;
    await selectCapturedFace(wbState.pendingCroppedFilename, `data:image/jpeg;base64,${wbState.pendingCroppedBase64}`);
    stopWorkbenchCamera();
  }

  // ② 撮影済みクロップ画像リストから選択機能
  async function loadCapturedFacesList() {
    if (!el.capturedFacesGrid) return;
    try {
      const res = await fetch('/api/captured_faces');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      wbState.capturedFacesList = data.faces || [];
      renderCapturedFacesGrid();
    } catch (e) {
      console.warn('captured_faces load error:', e);
      el.capturedFacesGrid.innerHTML = '<div class="wb-captured-empty">一覧の取得に失敗しました</div>';
    }
  }

  function renderCapturedFacesGrid() {
    if (!el.capturedFacesGrid) return;
    if (!wbState.capturedFacesList || wbState.capturedFacesList.length === 0) {
      el.capturedFacesGrid.innerHTML = '<div class="wb-captured-empty">撮影済みクロップ画像はまだありません</div>';
      return;
    }

    el.capturedFacesGrid.innerHTML = '';
    wbState.capturedFacesList.forEach(item => {
      const div = document.createElement('div');
      const isSelected = (wbState.faceImageFilename === item.image_filename);
      div.className = `wb-captured-thumb-item${isSelected ? ' selected' : ''}`;
      div.title = `${item.image_filename} (${item.created_at || ''})`;
      div.innerHTML = `<img src="${item.url}" alt="${item.image_filename}" loading="lazy">`;
      div.addEventListener('click', () => {
        selectCapturedFace(item.image_filename, item.url);
      });
      el.capturedFacesGrid.appendChild(div);
    });
  }

  async function selectCapturedFace(filename, previewUrl) {
    try {
      const res = await fetch(previewUrl || `/api/captured_faces/${filename}`);
      const blob = res.ok ? await res.blob() : null;
      wbState.faceBlob = blob;
      wbState.faceImageFilename = filename;
      wbState.isCroppedImage = true;

      el.facePreviewImg.src = previewUrl || `/api/captured_faces/${filename}`;
      el.facePreviewImg.classList.remove('hidden');
      el.facePlaceholder.classList.add('hidden');
      updateCurrentFaceLabel(`${filename} (クロップ済)`);
      renderCapturedFacesGrid();
      showError('');
      showToast(`クロップ画像「${filename}」を入力にセットしました`, 'success');
    } catch (e) {
      console.error('selectCapturedFace error:', e);
      showError('クロップ画像のセットに失敗しました: ' + e.message);
    }
  }

  async function loadTestFace(filename) {
    try {
      const res = await fetch(`/test_assets/faces/${filename}`);
      if (!res.ok) {
        throw new Error(`test_asset fetch HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const file = new File([blob], filename, { type: blob.type || 'image/jpeg' });
      await setFaceImageFile(file);
    } catch (e) {
      // サーバー経由で直接画像取得できない場合、ファイル名のみ保持
      wbState.faceBlob = null;
      wbState.faceImageFilename = filename;
      wbState.isCroppedImage = false;
      el.facePreviewImg.classList.add('hidden');
      el.facePlaceholder.classList.remove('hidden');
      el.facePlaceholder.innerHTML = `<span class="dropzone-icon">🖼</span><p>テスト画像指定: <strong>${filename}</strong></p>`;
      updateCurrentFaceLabel(`${filename} (テスト画像)`);
      renderCapturedFacesGrid();
      showToast(`画像指定: ${filename}`, 'info');
    }
  }

  async function handleAnalyzeFace() {
    if (!wbState.faceBlob && !wbState.faceImageFilename) {
      showError('分析対象の人物画像をセットしてください');
      return;
    }

    showError('');
    setStatus('analyzing_face', 'ComfyUI /free 解放中 ➔ VLM外見抽出中...');
    el.btnAnalyzeFace.disabled = true;

    try {
      const formData = new FormData();
      if (wbState.faceBlob) {
        formData.append('face_image', wbState.faceBlob, wbState.faceImageFilename || 'face.jpg');
      } else if (wbState.faceImageFilename.startsWith('sw_crop_')) {
        const capRes = await fetch(`/api/captured_faces/${wbState.faceImageFilename}`);
        if (!capRes.ok) throw new Error(`クロップ画像の取得に失敗しました (${wbState.faceImageFilename})`);
        const blob = await capRes.blob();
        formData.append('face_image', blob, wbState.faceImageFilename);
      } else {
        // テスト画像からBlob取得試行
        const testRes = await fetch(`/test_assets/faces/${wbState.faceImageFilename}`);
        const blob = await testRes.blob();
        formData.append('face_image', blob, wbState.faceImageFilename);
      }

      const res = await fetch('/api/analyze_face', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(errJson.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      wbState.vlmData = data;
      wbState.sessionId = data.session_id;

      // クロップ後のプレビュー画像が返ってきた場合はプレビュー更新
      if (data.cropped_image_base64) {
        el.facePreviewImg.src = `data:image/jpeg;base64,${data.cropped_image_base64}`;
        el.facePreviewImg.classList.remove('hidden');
        el.facePlaceholder.classList.add('hidden');
      }

      // 画面反映
      el.faceAnalysisBadge.textContent = '分析完了';
      el.faceAnalysisBadge.className = 'badge-mini ready';
      if (data.vlm_metrics) {
        el.vlmTimeVal.textContent = `${data.vlm_metrics.wall_time_ms} ms`;
        el.vlmVramVal.textContent = `${data.vlm_metrics.vram_used_mb} MB`;
        el.vramVal.textContent = `${data.vlm_metrics.vram_used_mb} MB`;
      }

      // 属性表示
      const ext = data.vlm_extraction || {};
      wbState.vlmExtraction = ext;
      el.attrFace.textContent = data.face_detected ? 'True' : 'False';
      el.attrGender.textContent = ext.gender_tag || data.gender_tag || '--';
      el.attrHairLen.textContent = ext.hair_length || '--';
      el.attrBangs.textContent = ext.has_bangs !== undefined ? String(ext.has_bangs) : '--';
      el.attrForehead.textContent = ext.exposed_forehead !== undefined ? String(ext.exposed_forehead) : '--';
      el.attrGlasses.textContent = ext.glasses || '--';
      el.attrBeard.textContent = ext.facial_hair || '--';

      el.vlmRawJson.textContent = JSON.stringify(data, null, 2);

      // プロンプト部品への自動反映（手直し可能）
      el.inputGender.value = data.gender_tag || '1boy';
      el.inputTraits.value = data.physical_traits || '';
      el.inputNegbias.value = data.negative_hair_bias || '';

      showToast('人物画像の外見特徴を抽出しました！', 'success');
      triggerAutoAssemble();
    } catch (e) {
      console.error('analyze_face error:', e);
      showError('画像分析に失敗しました: ' + e.message);
    } finally {
      el.btnAnalyzeFace.disabled = false;
      setStatus('idle');
    }
  }

  // -------------------------------------------------------------------------
  // D. Audio Input, 3-Point Calibration, Recording, & Emotion Analysis
  // -------------------------------------------------------------------------
  const WB_CALIB_META = {
    normal: { num: '①', name: '棒読み（基準）', btnDefault: '① 棒読み録音' },
    power: { num: '②', name: '張った声（上限）', btnDefault: '② 張り声録音' },
    whisper: { num: '③', name: 'ささやき声（吐息）', btnDefault: '③ ささやき録音' }
  };

  async function loadWbBaselineStatus() {
    try {
      const res = await fetch('/api/voice_emo_baseline');
      if (!res.ok) return;
      const data = await res.json();
      wbState.baselineData = data.baseline || {};
      renderWbBaselineStatus();
      if (wbState.audioAnalysis && wbState.audioAnalysis.raw_features) {
        renderWbRawFeatures(wbState.audioAnalysis.raw_features, wbState.baselineData);
      }
    } catch (e) {
      console.warn('workbench baseline load error:', e);
    }
  }

  function renderWbBaselineStatus() {
    const b = wbState.baselineData || {};
    const count = b.samples_count || 0;
    const anchors = b.anchors || {};
    const st = b.anchors_status || {
      normal: count > 0,
      power: Boolean(anchors.power),
      whisper: Boolean(anchors.whisper)
    };

    const setBadge = (elBadge, label, isReg, isReq) => {
      if (!elBadge) return;
      if (isReg) {
        elBadge.textContent = `${label}: 登録済 ✓`;
        elBadge.className = 'wb-vc-badge registered';
      } else if (isReq) {
        elBadge.textContent = `${label}: 未登録`;
        elBadge.className = 'wb-vc-badge unregistered';
      } else {
        elBadge.textContent = `${label}: オプション`;
        elBadge.className = 'wb-vc-badge optional';
      }
    };

    setBadge(el.badgeNormal, '①棒読み', st.normal, true);
    setBadge(el.badgePower, '②張り声', st.power, false);
    setBadge(el.badgeWhisper, '③ささやき', st.whisper, false);

    if (el.audioCalibChip) {
      if (st.normal) {
        const f0 = b.f0_median_hz !== undefined ? `${Number(b.f0_median_hz).toFixed(0)}Hz` : '--';
        const rms = b.rms_p90_db !== undefined ? `${Number(b.rms_p90_db).toFixed(1)}dB` : '--';
        el.audioCalibChip.textContent = `基準: 棒読み登録済 ✓ (${f0} / ${rms})`;
        el.audioCalibChip.className = 'badge-mini ready';
      } else {
        el.audioCalibChip.textContent = '基準: 未測定（標準初期値使用中）';
        el.audioCalibChip.className = 'badge-mini';
      }
    }

    if (el.calibUpdatedAt) {
      if (b.calibrated_at) {
        const d = new Date(b.calibrated_at);
        el.calibUpdatedAt.textContent = `最終更新: ${d.toLocaleString('ja-JP')}`;
      } else {
        el.calibUpdatedAt.textContent = '最終更新: 標準初期値 (未登録)';
      }
    }

    if (el.calibChips) {
      el.calibChips.innerHTML = '';
      const baseKeys = [
        ['rms_p90_db', 'RMS(dB)', 2],
        ['f0_median_hz', 'F0(Hz)', 1],
        ['hnr_db', 'HNR(dB)', 2],
        ['breath_ratio', 'Breath', 4],
        ['jitter', 'Jitter', 4],
        ['shimmer', 'Shimmer', 3]
      ];
      baseKeys.forEach(([k, label, dig]) => {
        if (b[k] !== undefined) {
          const sp = document.createElement('span');
          sp.className = 'wb-b-chip';
          sp.textContent = `①${label}: ${Number(b[k]).toFixed(dig)}`;
          el.calibChips.appendChild(sp);
        }
      });
      if (anchors.power && anchors.power.rms_p90_db !== undefined) {
        const sp = document.createElement('span');
        sp.className = 'wb-b-chip wb-b-chip-power';
        sp.textContent = `②Power [RMS: ${Number(anchors.power.rms_p90_db).toFixed(1)}dB / F0: ${Number(anchors.power.f0_median_hz || 0).toFixed(0)}Hz]`;
        el.calibChips.appendChild(sp);
      }
      if (anchors.whisper && anchors.whisper.rms_p90_db !== undefined) {
        const sp = document.createElement('span');
        sp.className = 'wb-b-chip wb-b-chip-whisper';
        sp.textContent = `③Whisper [RMS: ${Number(anchors.whisper.rms_p90_db).toFixed(1)}dB / HNR: ${Number(anchors.whisper.hnr_db || 0).toFixed(1)}dB / Breath: ${Number(anchors.whisper.breath_ratio || 0).toFixed(3)}]`;
        el.calibChips.appendChild(sp);
      }
    }
  }

  function updateWbCalibButtonsUI(activeMode, elapsedSec = 0) {
    document.querySelectorAll('.wb-btn-calib-rec').forEach(btn => {
      const m = btn.getAttribute('data-calib-mode') || 'normal';
      const meta = WB_CALIB_META[m] || WB_CALIB_META.normal;
      const lbl = btn.querySelector('.wb-calib-btn-label') || btn;
      if (activeMode === m) {
        btn.disabled = false;
        btn.classList.add('recording');
        lbl.textContent = `⏹ 停止して登録 (${elapsedSec.toFixed(1)}s)`;
      } else if (activeMode) {
        btn.disabled = true;
        btn.classList.remove('recording');
        lbl.textContent = meta.btnDefault;
      } else {
        btn.disabled = false;
        btn.classList.remove('recording');
        lbl.textContent = meta.btnDefault;
      }
    });
  }

  function setWbCalibProgress(visible, text) {
    if (!el.calibProgress) return;
    if (visible) {
      el.calibProgress.classList.remove('hidden');
      el.calibProgress.textContent = text;
    } else {
      el.calibProgress.classList.add('hidden');
      el.calibProgress.textContent = '';
    }
  }

  async function toggleWbCalibRecording(mode) {
    const modeKey = (mode || 'normal').toLowerCase();
    if (wbState.isRecordingCalib) {
      if (wbState.calibRecordingMode === modeKey) {
        await stopAndSubmitWbCalib();
      }
      return;
    }
    await startWbCalibRecording(modeKey);
  }

  async function startWbCalibRecording(modeKey) {
    const meta = WB_CALIB_META[modeKey] || WB_CALIB_META.normal;
    wbState.isRecordingCalib = true;
    wbState.calibRecordingMode = modeKey;

    try {
      const micId = el.selectMic ? el.selectMic.value : '';
      const constraints = {
        audio: {
          deviceId: micId ? { exact: micId } : undefined,
          autoGainControl: false,
          noiseSuppression: false,
          echoCancellation: false,
          channelCount: 1
        },
        video: false
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = audioCtx.createMediaStreamSource(stream);
      const recorderNode = audioCtx.createScriptProcessor(4096, 1, 1);

      const chunks = [];
      recorderNode.onaudioprocess = (e) => {
        if (!wbState.isRecordingCalib) return;
        chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      };

      source.connect(recorderNode);
      recorderNode.connect(audioCtx.destination);

      const startTime = Date.now();
      updateWbCalibButtonsUI(modeKey, 0.0);
      setWbCalibProgress(true, `${meta.num}${meta.name} を録音中... 0.0s（もう一度押すと停止・最大6.0s）`);

      const timer = setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000;
        updateWbCalibButtonsUI(modeKey, elapsed);
        setWbCalibProgress(true, `${meta.num}${meta.name} を録音中... ${elapsed.toFixed(1)}s（もう一度押すと停止・最大6.0s）`);
      }, 100);

      const autoStopTimeout = setTimeout(() => {
        if (wbState.isRecordingCalib && wbState.calibRecordingMode === modeKey) {
          stopAndSubmitWbCalib();
        }
      }, 6000);

      wbState.calibSession = {
        modeKey,
        stream,
        audioCtx,
        source,
        recorderNode,
        chunks,
        timer,
        autoStopTimeout
      };
    } catch (e) {
      console.error('wb calib mic error:', e);
      showError('ボイスチェック録音開始に失敗しました: ' + e.message);
      wbState.isRecordingCalib = false;
      wbState.calibRecordingMode = null;
      wbState.calibSession = null;
      updateWbCalibButtonsUI(null);
      setWbCalibProgress(false, '');
    }
  }

  async function stopAndSubmitWbCalib() {
    const sess = wbState.calibSession;
    if (!sess) return;
    wbState.calibSession = null;

    clearInterval(sess.timer);
    clearTimeout(sess.autoStopTimeout);

    const { modeKey, stream, audioCtx, source, recorderNode, chunks } = sess;
    try {
      recorderNode.disconnect();
      source.disconnect();
      stream.getTracks().forEach(t => t.stop());
      await audioCtx.close();
    } catch (e) {
      console.warn('wb calib close warning:', e);
    }

    const wavBlob = encodeFloat32ToWav(chunks, 16000);
    await submitWbCalibrationBlob(wavBlob, modeKey);

    wbState.isRecordingCalib = false;
    wbState.calibRecordingMode = null;
    updateWbCalibButtonsUI(null);
    setWbCalibProgress(false, '');
  }

  async function submitWbCalibrationBlob(wavBlob, modeKey) {
    const meta = WB_CALIB_META[modeKey] || WB_CALIB_META.normal;
    document.querySelectorAll('.wb-btn-calib-rec').forEach(b => { b.disabled = true; });
    setWbCalibProgress(true, `${meta.num}${meta.name} を登録中...`);

    try {
      const formData = new FormData();
      formData.append('audio_file', wavBlob, `wb_calib_${modeKey}.wav`);
      formData.append('mode', modeKey);

      const res = await fetch('/api/calibrate_voice_emo', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      wbState.baselineData = data.baseline || {};
      renderWbBaselineStatus();

      if (modeKey === 'normal') {
        showToast('✓ ①棒読み（基準50pt）を更新しました（②③アンカーをリセット）', 'success');
      } else {
        showToast(`✓ ${meta.num}${meta.name} アンカーを更新しました`, 'success');
      }

      // すでにセリフ音声がセットされている場合は自動で再分析して新しいスコアを即時反映
      if (wbState.audioBlob) {
        await handleAnalyzeAudio();
      }
    } catch (e) {
      console.error('wb calibration submit error:', e);
      showError(`ボイスチェック登録失敗 (${modeKey}): ` + e.message);
    } finally {
      updateWbCalibButtonsUI(null);
      setWbCalibProgress(false, '');
    }
  }

  function renderWbRawFeatures(rawFeatures, baselineData) {
    if (!el.rawFeaturesGrid) return;
    el.rawFeaturesGrid.innerHTML = '';
    if (!rawFeatures) return;
    const b = baselineData || wbState.baselineData || {};
    const rawDefs = [
      ['rms_p90_db', 'RMS p90 (dB)', 2],
      ['peak_db', 'Peak (dB)', 2],
      ['centroid_hz', 'Centroid (Hz)', 0],
      ['rolloff_hz', 'Rolloff (Hz)', 0],
      ['flatness', 'Flatness', 4],
      ['onset_rate', 'Onset (/s)', 2],
      ['low_band_ratio', 'LowBand', 3],
      ['f0_median_hz', 'F0 Med (Hz)', 1],
      ['f0_std_st', 'F0 Std (st)', 2],
      ['f0_iqr_st', 'F0 IQR (st)', 2],
      ['f0_delta_st', 'F0 Delta (st)', 3],
      ['f0_slope_st', 'F0 Slope (st/s)', 2],
      ['hnr_db', 'HNR (dB)', 2],
      ['breath_ratio', 'Breath Ratio', 4],
      ['jitter', 'Jitter', 4],
      ['shimmer', 'Shimmer', 3]
    ];
    rawDefs.forEach(([k, label, dig]) => {
      if (rawFeatures[k] === undefined) return;
      const cell = document.createElement('div');
      cell.className = 'wb-raw-item';
      const rawVal = Number(rawFeatures[k]).toFixed(dig);
      const baseVal = b[k] !== undefined ? Number(b[k]).toFixed(dig) : '--';
      cell.innerHTML = `
        <span class="wb-raw-k">${label}</span>
        <span class="wb-raw-v">${rawVal} <small>(基準: ${baseVal})</small></span>
      `;
      el.rawFeaturesGrid.appendChild(cell);
    });
  }

  async function populateMicDevices() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
      const devices = await navigator.mediaDevices.enumerateDevices();
      const mics = devices.filter(d => d.kind === 'audioinput');
      el.selectMic.innerHTML = '';
      mics.forEach((m, idx) => {
        const opt = document.createElement('option');
        opt.value = m.deviceId;
        opt.textContent = m.label || `マイク ${idx + 1}`;
        el.selectMic.appendChild(opt);
      });
    } catch (e) {
      console.warn('mic enumeration error:', e);
    }
  }

  function setAudioBlob(blob, name = 'audio.wav') {
    wbState.audioBlob = blob;
    const url = URL.createObjectURL(blob);
    el.audioPlayer.src = url;
    el.audioInfo.textContent = `セット完了: ${name} (${(blob.size / 1024).toFixed(1)} KB)`;
  }

  async function loadTestAudio(filename) {
    try {
      const res = await fetch(`/test_assets/audio/${filename}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      setAudioBlob(blob, filename);
      showToast(`テスト音声「${filename}」をセットしました`, 'info');
    } catch (e) {
      showError('テスト音声の読み込みに失敗しました: ' + e.message);
    }
  }

  async function toggleMicRecording() {
    if (wbState.isRecording) {
      await stopMicRecording();
    } else {
      await startMicRecording();
    }
  }

  async function startMicRecording() {
    try {
      const micId = el.selectMic.value;
      const constraints = {
        audio: {
          deviceId: micId ? { exact: micId } : undefined,
          autoGainControl: false,
          noiseSuppression: false,
          echoCancellation: false,
          channelCount: 1
        },
        video: false
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      wbState.audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = wbState.audioContext.createMediaStreamSource(stream);

      // Level Meter Setup
      wbState.analyserNode = wbState.audioContext.createAnalyser();
      wbState.analyserNode.fftSize = 256;
      source.connect(wbState.analyserNode);

      // Recorder Setup (ScriptProcessor for Float32)
      const bufferSize = 4096;
      wbState.audioRecorderNode = wbState.audioContext.createScriptProcessor(bufferSize, 1, 1);
      wbState.audioChunks = [];

      wbState.audioRecorderNode.onaudioprocess = (e) => {
        if (!wbState.isRecording) return;
        const inputData = e.inputBuffer.getChannelData(0);
        wbState.audioChunks.push(new Float32Array(inputData));
      };

      source.connect(wbState.audioRecorderNode);
      wbState.audioRecorderNode.connect(wbState.audioContext.destination);

      wbState.isRecording = true;
      setStatus('recording_audio', 'マイク録音中 (16kHz モノラル WAV)...');
      el.btnMicToggle.classList.add('recording');
      el.recLabel.textContent = '録音停止';

      wbState.recStartTime = Date.now();
      wbState.recTimerInterval = setInterval(() => {
        const sec = ((Date.now() - wbState.recStartTime) / 1000).toFixed(1);
        el.recTimer.textContent = `${sec}s`;
      }, 100);

      startLevelMeter();
    } catch (e) {
      console.error('mic start error:', e);
      showError('マイクの初期化に失敗しました: ' + e.message);
    }
  }

  function startLevelMeter() {
    const dataArray = new Uint8Array(wbState.analyserNode.frequencyBinCount);
    function updateMeter() {
      if (!wbState.isRecording) {
        el.levelFill.style.width = '0%';
        return;
      }
      wbState.analyserNode.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
      const avg = sum / dataArray.length;
      const pct = Math.min(100, (avg / 128) * 100);
      el.levelFill.style.width = `${pct}%`;
      wbState.meterAnimFrame = requestAnimationFrame(updateMeter);
    }
    updateMeter();
  }

  async function stopMicRecording() {
    if (!wbState.isRecording) return;
    wbState.isRecording = false;
    clearInterval(wbState.recTimerInterval);
    if (wbState.meterAnimFrame) cancelAnimationFrame(wbState.meterAnimFrame);

    el.btnMicToggle.classList.remove('recording');
    el.recLabel.textContent = 'マイク録音開始';
    setStatus('idle');

    const wavBlob = encodeFloat32ToWav(wbState.audioChunks, 16000);
    setAudioBlob(wavBlob, `rec_${Date.now()}.wav`);

    if (wbState.audioContext) {
      await wbState.audioContext.close();
      wbState.audioContext = null;
    }
    showToast('録音完了！音声分析を実行できます', 'success');
  }

  // 16kHz mono WAV encoder
  function encodeFloat32ToWav(chunks, sampleRate) {
    let totalLen = 0;
    for (const c of chunks) totalLen += c.length;
    const merged = new Float32Array(totalLen);
    let offset = 0;
    for (const c of chunks) {
      merged.set(c, offset);
      offset += c.length;
    }

    const buffer = new ArrayBuffer(44 + merged.length * 2);
    const view = new DataView(buffer);

    writeStr(view, 0, 'RIFF');
    view.setUint32(4, 36 + merged.length * 2, true);
    writeStr(view, 8, 'WAVE');
    writeStr(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(view, 36, 'data');
    view.setUint32(40, merged.length * 2, true);

    let idx = 44;
    for (let i = 0; i < merged.length; i++) {
      let s = Math.max(-1, Math.min(1, merged[i]));
      view.setInt16(idx, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      idx += 2;
    }
    return new Blob([view], { type: 'audio/wav' });
  }

  function writeStr(view, offset, str) {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  }

  async function handleAnalyzeAudio() {
    if (!wbState.audioBlob) {
      showError('分析対象の音声ファイルまたは録音をセットしてください');
      return;
    }

    showError('');
    const currentMode = el.selectEmotionMode ? el.selectEmotionMode.value : 'standard';
    if (currentMode === 'qwen2_audio_hybrid') {
      setStatus('analyzing_audio', 'Step 1: Qwen2-Audio 聴覚知覚 ＋ Step 2: Gemma 4 e2b 採点中... (GPU推論)');
    } else {
      setStatus('analyzing_audio', 'SenseVoice 推論 ＋ ピーク音量 rms_p90 算出中...');
    }
    el.btnAnalyzeAudio.disabled = true;

    try {
      const formData = new FormData();
      formData.append('audio_file', wbState.audioBlob, 'workbench_audio.wav');
      if (currentMode === 'qwen2_audio_hybrid') {
        const sysPrompt = el.qwenSystemPrompt ? el.qwenSystemPrompt.value.trim() : '';
        const customInst = el.qwenCustomInstruction ? el.qwenCustomInstruction.value.trim() : '';
        if (sysPrompt && sysPrompt !== DEFAULT_QWEN_SYSTEM_PROMPT) {
          formData.append('custom_system_prompt', sysPrompt);
        }
        if (customInst) formData.append('custom_instruction', customInst);
      }

      const res = await fetch('/api/analyze_audio', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(errJson.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      wbState.audioAnalysis = data;

      // 基本結果表示
      el.audioBadge.textContent = '分析完了';
      el.audioBadge.className = 'badge-mini ready';
      el.resSenseEmo.textContent = data.emotion || '--';
      el.resRmsDb.textContent = `${(data.rms_db || 0).toFixed(1)} dBFS`;
      el.resVerdict.textContent = data.expression_state || '--';
      el.resRecognizedText.textContent = data.recognized_text || '（テキストなし）';

      // 感情定義辞書
      const emoDefs = {
        joy: { name_ja: '歓喜・笑顔', icon: '🌟', tier: 'primary' },
        burning: { name_ja: '情熱・怒気・叫び', icon: '🔥', tier: 'primary' },
        sorrow: { name_ja: '哀愁・切なさ', icon: '💧', tier: 'primary' },
        surprise_fear: { name_ja: '驚愕・怯え', icon: '😨', tier: 'primary' },
        confident: { name_ja: '不敵・自信・クール', icon: '😏', tier: 'primary' },
        serene: { name_ja: '穏やか・優しさ', icon: '🕊️', tier: 'primary' },
        sultry_modifier: { name_ja: '色気・吐息ニュアンス', icon: '💋', tier: 'modifier' },
        bashful_modifier: { name_ja: '照れ・上ずりニュアンス', icon: '😳', tier: 'modifier' },
        none_modifier: { name_ja: 'ストレート表現（修飾なし）', icon: '➖', tier: 'modifier' }
      };

      if (data.emotion_mode === 'qwen2_audio_hybrid') {
        // Qwen2-Audio ハイブリッド結果カードの描画
        if (el.detailed12Card) el.detailed12Card.classList.add('hidden');
        if (el.qwenResultsCard) {
          el.qwenResultsCard.classList.remove('hidden');
          renderQwenResults(data, emoDefs);
        }
      } else if (data.emotion_mode === 'detailed_12' && data.primary_emotion) {
        if (el.qwenResultsCard) el.qwenResultsCard.classList.add('hidden');
        if (el.detailed12Card) {
          el.detailed12Card.classList.remove('hidden');
          const p1 = data.primary_emotion;
          const p2 = data.secondary_emotion || { id: 'none_modifier', name_ja: 'ストレート表現（修飾なし）', score: 0.0, icon: '➖' };
          const isNoneMod = (p2.id === 'none_modifier' || Number(p2.score || 0) <= 0);

          el.top1Score.textContent = Number(p1.score || 0).toFixed(1);
          el.top1Icon.textContent = p1.icon || emoDefs[p1.id]?.icon || '✨';
          el.top1Name.textContent = p1.name_ja || emoDefs[p1.id]?.name_ja || p1.id;

          if (el.top2Card) {
            el.top2Card.style.opacity = isNoneMod ? '0.68' : '1.0';
            el.top2Card.style.borderColor = isNoneMod ? 'rgba(255, 255, 255, 0.14)' : 'rgba(139, 92, 246, 0.5)';
          }
          if (el.top2Rank) {
            el.top2Rank.textContent = isNoneMod ? 'STRAIGHT' : 'NUANCE';
          }
          if (isNoneMod) {
            if (el.top2ScoreWrap) el.top2ScoreWrap.innerHTML = `<span style="font-size:11px;color:var(--text-dim);">修飾なし</span>`;
            el.top2Icon.textContent = p2.icon || '➖';
            el.top2Name.textContent = p2.name_ja || 'ストレート表現（修飾なし）';
          } else {
            if (el.top2ScoreWrap) {
              el.top2ScoreWrap.innerHTML = `<strong id="wb-top2-score">${Number(p2.score || 0).toFixed(1)}</strong> pt`;
              el.top2Score = document.getElementById('wb-top2-score');
            } else if (el.top2Score) {
              el.top2Score.textContent = Number(p2.score || 0).toFixed(1);
            }
            el.top2Icon.textContent = p2.icon || emoDefs[p2.id]?.icon || '✨';
            el.top2Name.textContent = p2.name_ja || emoDefs[p2.id]?.name_ja || p2.id;
          }

          // 7つの基礎指標
          if (data.features_7 && el.f7Grid) {
            el.f7Grid.innerHTML = '';
            const f7Labels = {
              valence: '快・ポジティブ',
              arousal: '覚醒・熱量',
              dominance: '支配・力強さ',
              breathiness: '吐息・息漏れ(HNR)',
              jitter: '高さの揺れ(Jitter)',
              shimmer: '大きさの揺れ(Shimmer)',
              pitch: '声の高さ・語尾'
            };
            for (const [k, v] of Object.entries(data.features_7)) {
              const item = document.createElement('div');
              item.className = 'f7-item';
              item.innerHTML = `<span class="f7-label">${f7Labels[k] || k}</span><span class="f7-val">${Number(v).toFixed(1)} pt</span>`;
              el.f7Grid.appendChild(item);
            }
          }

          // 全8項目（基本6＋修飾2）スコア一覧
          if (data.emotions_12 && el.e12List) {
            el.e12List.innerHTML = '';
            const entries = Array.isArray(data.emotions_12)
              ? data.emotions_12
              : Object.entries(data.emotions_12).map(([k, v]) => ({
                  id: k,
                  score: typeof v === 'number' ? v : (v.score || 0),
                  name_ja: emoDefs[k]?.name_ja || k,
                  icon: emoDefs[k]?.icon || '✨'
                }));

            entries.sort((a, b) => b.score - a.score);

            entries.forEach(e => {
              const row = document.createElement('div');
              row.className = 'e12-item';
              const isPrimaryTop = (e.id === p1.id);
              const isActiveMod = (!isNoneMod && e.id === p2.id);
              const isTop = isPrimaryTop || isActiveMod;
              row.innerHTML = `
                <span class="e12-name" style="${isTop ? 'font-weight: 700; color: var(--accent-cyan);' : ''}">${e.icon} ${e.name_ja}</span>
                <div class="e12-bar-track"><div class="e12-bar-fill" style="width: ${Math.min(100, Math.max(0, e.score))}%; ${isTop ? 'background: linear-gradient(90deg, var(--accent-cyan), var(--primary));' : ''}"></div></div>
                <span class="e12-score">${Number(e.score).toFixed(1)} pt</span>
              `;
              el.e12List.appendChild(row);
            });
          }

          // 生特徴量16項目 (raw_features vs baseline) の描画
          if (data.raw_features) {
            renderWbRawFeatures(data.raw_features, wbState.baselineData);
          }
        }
      } else {
        if (el.detailed12Card) el.detailed12Card.classList.add('hidden');
        if (el.qwenResultsCard) el.qwenResultsCard.classList.add('hidden');
      }

      // 表情プロンプトの反映（全モード共通で自動セット・微調整可）
      if (data.expression_prompt) {
        el.inputExpression.value = data.expression_prompt;
      }

      // 認識セリフが取れた場合
      if (data.recognized_text && data.recognized_text.trim()) {
        showToast(`音声認識: 「${data.recognized_text.trim()}」`, 'info');
      }

      showToast(`感情判定: ${data.emotion || data.expression_state} (音量: ${(data.rms_db || 0).toFixed(1)} dBFS)`, 'success');
      triggerAutoAssemble();
    } catch (e) {
      console.error('analyze_audio error:', e);
      showError('音声分析に失敗しました: ' + e.message);
    } finally {
      el.btnAnalyzeAudio.disabled = false;
      setStatus('idle');
    }
  }

  function renderQwenResults(data, emoDefs) {
    if (el.qwenNuanceBadge) {
      el.qwenNuanceBadge.textContent = data.overall_impression_en || data.detected_nuance_short || '--';
    }
    if (el.qwenTimeVal) {
      el.qwenTimeVal.textContent = `${Number(data.analysis_time_sec || 0).toFixed(2)} s`;
    }
    if (el.qwenVramVal) {
      el.qwenVramVal.textContent = `${Number(data.vram_used_mb || 0).toFixed(0)} MB`;
    }
    if (el.qwenPerceptionEn) {
      el.qwenPerceptionEn.textContent = data.qwen2_perception_en || '--';
    }
    if (el.qwenSemanticBridgeEn) {
      el.qwenSemanticBridgeEn.textContent = data.semantic_bridge_en || '--';
    }

    // 棒読み基準からの物理変化メーター
    renderQwenDeltas(data.baseline_deltas);

    // Primary / Nuance カード
    const p1 = data.primary_emotion || { id: 'serene', name_ja: '穏やか・優しさ', score: 50.0, icon: '🕊️' };
    const p2 = data.secondary_emotion || { id: 'none_modifier', name_ja: 'ストレート表現（修飾なし）', score: 0.0, icon: '➖' };
    const isNoneMod = (p2.id === 'none_modifier' || Number(p2.score || 0) <= 0);

    if (el.qwenTop1Score) el.qwenTop1Score.textContent = Number(p1.score || 0).toFixed(1);
    if (el.qwenTop1Icon) el.qwenTop1Icon.textContent = p1.icon || emoDefs[p1.id]?.icon || '✨';
    if (el.qwenTop1Name) el.qwenTop1Name.textContent = p1.name_ja || emoDefs[p1.id]?.name_ja || p1.id;

    if (el.qwenTop2Card) {
      el.qwenTop2Card.style.opacity = isNoneMod ? '0.68' : '1.0';
      el.qwenTop2Card.style.borderColor = isNoneMod ? 'rgba(255, 255, 255, 0.14)' : 'rgba(236, 72, 153, 0.6)';
    }
    if (el.qwenTop2Rank) {
      el.qwenTop2Rank.textContent = isNoneMod ? 'STRAIGHT' : 'NUANCE';
    }
    if (isNoneMod) {
      if (el.qwenTop2ScoreWrap) el.qwenTop2ScoreWrap.innerHTML = `<span style="font-size:11px;color:var(--text-dim);">修飾なし</span>`;
      if (el.qwenTop2Icon) el.qwenTop2Icon.textContent = p2.icon || '➖';
      if (el.qwenTop2Name) el.qwenTop2Name.textContent = p2.name_ja || 'ストレート表現（修飾なし）';
    } else {
      if (el.qwenTop2ScoreWrap) {
        el.qwenTop2ScoreWrap.innerHTML = `<strong id="wb-qwen-top2-score">${Number(p2.score || 0).toFixed(1)}</strong> pt`;
        el.qwenTop2Score = document.getElementById('wb-qwen-top2-score');
      } else if (el.qwenTop2Score) {
        el.qwenTop2Score.textContent = Number(p2.score || 0).toFixed(1);
      }
      if (el.qwenTop2Icon) el.qwenTop2Icon.textContent = p2.icon || emoDefs[p2.id]?.icon || '✨';
      if (el.qwenTop2Name) el.qwenTop2Name.textContent = p2.name_ja || emoDefs[p2.id]?.name_ja || p2.id;
    }

    // 8感情スコア一覧
    if (data.emotions_12 && el.qwenE8List) {
      el.qwenE8List.innerHTML = '';
      const entries = Array.isArray(data.emotions_12)
        ? data.emotions_12
        : Object.entries(data.emotions_12).map(([k, v]) => ({
            id: k,
            score: typeof v === 'number' ? v : (v.score || 0),
            name_ja: emoDefs[k]?.name_ja || k,
            icon: emoDefs[k]?.icon || '✨'
          }));

      entries.sort((a, b) => b.score - a.score);

      entries.forEach(e => {
        const row = document.createElement('div');
        row.className = 'e12-item';
        const isPrimaryTop = (e.id === p1.id);
        const isActiveMod = (!isNoneMod && e.id === p2.id);
        const isTop = isPrimaryTop || isActiveMod;
        row.innerHTML = `
          <span class="e12-name" style="${isTop ? 'font-weight: 700; color: var(--accent-cyan);' : ''}">${e.icon} ${e.name_ja}</span>
          <div class="e12-bar-track"><div class="e12-bar-fill" style="width: ${Math.min(100, Math.max(0, e.score))}%; ${isTop ? 'background: linear-gradient(90deg, var(--accent-cyan), var(--primary));' : ''}"></div></div>
          <span class="e12-score">${Number(e.score).toFixed(1)} pt</span>
        `;
        el.qwenE8List.appendChild(row);
      });
    }
  }

  function renderQwenDeltas(baselineDeltas) {
    if (!el.qwenDeltasGrid) return;
    el.qwenDeltasGrid.innerHTML = '';
    const b = baselineDeltas || {};
    const d = b.deltas || b;

    const items = [
      {
        name: '声量変化 (ΔRMS)',
        val: d.delta_rms_db !== undefined ? `${d.delta_rms_db > 0 ? '+' : ''}${Number(d.delta_rms_db).toFixed(1)} dB` : '--',
        ratio: d.delta_rms_db !== undefined ? Math.max(-1, Math.min(1, d.delta_rms_db / 15.0)) : 0,
        cls: d.delta_rms_db > 1.5 ? 'is-up' : (d.delta_rms_db < -1.5 ? 'is-down' : 'is-neutral')
      },
      {
        name: 'ピッチ変化 (ΔPitch)',
        val: d.delta_pitch_st !== undefined ? `${d.delta_pitch_st > 0 ? '+' : ''}${Number(d.delta_pitch_st).toFixed(1)} 半音` : '--',
        ratio: d.delta_pitch_st !== undefined ? Math.max(-1, Math.min(1, d.delta_pitch_st / 12.0)) : 0,
        cls: d.delta_pitch_st > 1.0 ? 'is-up' : (d.delta_pitch_st < -1.0 ? 'is-down' : 'is-neutral')
      },
      {
        name: '抑揚変化 (ΔF0 Std)',
        val: d.delta_f0_std_st !== undefined ? `${d.delta_f0_std_st > 0 ? '+' : ''}${Number(d.delta_f0_std_st).toFixed(1)} 半音` : '--',
        ratio: d.delta_f0_std_st !== undefined ? Math.max(-1, Math.min(1, d.delta_f0_std_st / 4.0)) : 0,
        cls: d.delta_f0_std_st > 0.5 ? 'is-up' : (d.delta_f0_std_st < -0.5 ? 'is-down' : 'is-neutral')
      },
      {
        name: '音色明度 (ΔCentroid)',
        val: d.delta_centroid_hz !== undefined ? `${d.delta_centroid_hz > 0 ? '+' : ''}${Number(d.delta_centroid_hz).toFixed(0)} Hz` : '--',
        ratio: d.delta_centroid_hz !== undefined ? Math.max(-1, Math.min(1, d.delta_centroid_hz / 1000.0)) : 0,
        cls: d.delta_centroid_hz > 100 ? 'is-up' : (d.delta_centroid_hz < -100 ? 'is-down' : 'is-neutral')
      },
      {
        name: '澄み具合変化 (ΔHNR)',
        val: d.delta_hnr_db !== undefined ? `${d.delta_hnr_db > 0 ? '+' : ''}${Number(d.delta_hnr_db).toFixed(1)} dB` : '--',
        ratio: d.delta_hnr_db !== undefined ? Math.max(-1, Math.min(1, d.delta_hnr_db / 12.0)) : 0,
        cls: d.delta_hnr_db > 1.5 ? 'is-up' : (d.delta_hnr_db < -1.5 ? 'is-down' : 'is-neutral')
      },
      {
        name: '息漏れ倍率 (Breath Fold)',
        val: d.breath_ratio_fold !== undefined ? `${Number(d.breath_ratio_fold).toFixed(2)} 倍` : '--',
        ratio: d.breath_ratio_fold !== undefined ? Math.max(-1, Math.min(1, (d.breath_ratio_fold - 1.0) / 2.0)) : 0,
        cls: d.breath_ratio_fold > 1.3 ? 'is-up' : (d.breath_ratio_fold < 0.8 ? 'is-down' : 'is-neutral')
      }
    ];

    items.forEach(it => {
      const div = document.createElement('div');
      div.className = 'delta-item';

      let fillStyle = '';
      if (it.isZeroCenter === false) {
        // 0から右へ伸びるバー
        const w = (it.ratio * 100).toFixed(1);
        fillStyle = `left: 0; width: ${w}%; background: linear-gradient(90deg, #38bdf8, #818cf8);`;
      } else {
        // 中央(50%)基準の左右バー
        if (it.ratio >= 0) {
          const w = (it.ratio * 50).toFixed(1);
          fillStyle = `left: 50%; width: ${w}%; background: #f43f5e;`;
        } else {
          const w = (Math.abs(it.ratio) * 50).toFixed(1);
          fillStyle = `right: 50%; width: ${w}%; background: #3b82f6;`;
        }
      }

      div.innerHTML = `
        <div class="delta-item-head">
          <span class="delta-name">${it.name}</span>
          <span class="delta-val ${it.cls}">${it.val}</span>
        </div>
        <div class="delta-meter-track">
          ${it.isZeroCenter !== false ? '<div class="delta-meter-center"></div>' : ''}
          <div class="delta-meter-fill" style="${fillStyle}"></div>
        </div>
      `;
      el.qwenDeltasGrid.appendChild(div);
    });
  }

  async function handleQwenUnload() {
    if (el.btnQwenUnload) el.btnQwenUnload.disabled = true;
    try {
      showToast('Qwen2-Audio の VRAM を解放しています...', 'info');
      const res = await fetch('/api/qwen2_audio/unload', { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const before = Number(data.vram_before_mb || 0).toFixed(0);
      const after = Number(data.vram_after_mb || 0).toFixed(0);
      if (data.was_loaded) {
        showToast(`Qwen2 VRAMを正常に解放しました (${before}MB → ${after}MB)`, 'success');
      } else {
        showToast(`Qwen2 は現在アンロード済みです (現在のVRAM: ${after}MB)`, 'info');
      }
    } catch (e) {
      console.error('qwen unload error:', e);
      showError('Qwen2 VRAM解放失敗: ' + e.message);
    } finally {
      if (el.btnQwenUnload) el.btnQwenUnload.disabled = false;
    }
  }

  async function handleSaveMode() {
    const mode = el.selectEmotionMode.value;
    const modeNames = {
      standard: '従来 (SenseVoice 5段階)',
      detailed_12: '詳細感情 (2階層 12-Emo / librosa)',
      qwen2_audio_hybrid: 'Qwen2-Audio ハイブリッド (4bit Audio-LLM ＋ 棒読み物理差分)'
    };
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ emotion_mode: mode })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast(`感情分析モードを「${modeNames[mode] || mode}」に更新・保存しました`, 'success');
      updateEmotionModeUI();
    } catch (e) {
      showError('モード保存失敗: ' + e.message);
    }
  }

  async function handleSaveThreshold() {
    const val = parseFloat(el.burningSlider.value);
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ BURNING_DB_THRESHOLD: val })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast(`BURNING 閾値を ${val.toFixed(1)} dBFS に更新・保存しました`, 'success');
    } catch (e) {
      showError('設定更新失敗: ' + e.message);
    }
  }

  // -------------------------------------------------------------------------
  // E. Prompt Assembling & Image Generation
  // -------------------------------------------------------------------------
  function triggerAutoAssemble() {
    if (!el.autoAssembleToggle.checked) return;
    assemblePrompts();
  }

  function stripGender(traits, gender) {
    if (!traits) return '';
    const items = traits.split(',').map(t => t.trim()).filter(t => t && t.toLowerCase() !== gender.toLowerCase());
    return items.join(', ');
  }

  function assemblePrompts() {
    const gender = (el.inputGender.value || '1boy').trim();
    const traitsRaw = (el.inputTraits.value || '').trim();
    const traits = stripGender(traitsRaw, gender);
    const negBias = (el.inputNegbias.value || '').trim();
    const expr = (el.inputExpression.value || '').trim();
    const scene = (el.scenePrompt.value || '').trim();
    const sceneNeg = (el.sceneNegPrompt ? el.sceneNegPrompt.value : '').trim();
    const quality = (el.qualityPrompt.value || '').trim();
    const baseNeg = (el.baseNegative.value || '').trim();

    // 1. Node_Pos_Base (Node 5)
    // {gender}, solo, {traits}, {expr}, {scene}, {quality}
    const baseParts = [gender, 'solo', traits, expr, scene, quality].filter(Boolean);
    el.promptPosBase.value = baseParts.join(', ');

    // 2. Node_Neg_Base (Node 6)
    // {neg_bias}, {scene_neg_prompt}, {base_neg}
    const negParts = [negBias, sceneNeg, baseNeg].filter(Boolean);
    el.promptNegBase.value = negParts.join(', ');

    // 3. Node_Pos_FD (Node 32)
    // 案B (正式採用): {gender}, solo, close-up, face focus, {expr}, detailed anime eyes, {quality}
    // 案A (外見包含): {gender}, solo, close-up, face focus, {traits}, {expr}, detailed anime eyes, {quality}
    if (wbState.fdOption === 'B') {
      const fdParts = [gender, 'solo', 'close-up', 'face focus', expr, 'detailed anime eyes', quality].filter(Boolean);
      el.promptPosFd.value = fdParts.join(', ');
    } else {
      const fdParts = [gender, 'solo', 'close-up', 'face focus', traits, expr, 'detailed anime eyes', quality].filter(Boolean);
      el.promptPosFd.value = fdParts.join(', ');
    }

    // カードプレビュー更新
    el.cardScriptText.textContent = el.scriptFinal.value || el.sceneScript.value || '';
  }

  async function handleStartGenerate() {
    showError('');

    // 入力検証
    const posBase = el.promptPosBase.value.trim();
    const negBase = el.promptNegBase.value.trim();
    const posFd = el.promptPosFd.value.trim();
    const hasFd = isCurrentWorkflowHasFd();
    const selectedWorkflow = el.workflowSelect ? el.workflowSelect.value : wbState.currentWorkflow;

    if (!posBase || !negBase || (hasFd && !posFd)) {
      showError(hasFd
        ? '3系統のプロンプト（Base Posi, Base Nega, FD Posi）をすべて入力してください'
        : 'Base Posi と Base Nega プロンプトを入力してください');
      return;
    }

    if (!wbState.faceBlob && !wbState.faceImageFilename && !wbState.sessionId) {
      showError('人物画像または有効なセッションが必要です。画像をセットしてください');
      return;
    }

    setStatus('generating_image', 'ComfyUI ワークフローを実行中 (最大数分)...');
    el.btnStartGenerate.disabled = true;
    el.genSpinner.classList.remove('hidden');
    el.imagePlaceholder.classList.add('hidden');

    try {
      const formData = new FormData();
      const autoCrop = el.autoCropCheck ? el.autoCropCheck.checked : true;

      if (wbState.isCroppedImage && wbState.faceImageFilename) {
        // すでにクロップ済みの画像ファイル (sw_crop_xxx.jpg 等) は再クロップせずそのまま使用
        formData.append('image_filename', wbState.faceImageFilename);
        formData.append('auto_crop', 'false');
      } else if (wbState.faceBlob) {
        formData.append('face_image', wbState.faceBlob, wbState.faceImageFilename || 'face.jpg');
        formData.append('auto_crop', wbState.isCroppedImage ? 'false' : String(autoCrop));
      } else if (wbState.faceImageFilename) {
        formData.append('image_filename', wbState.faceImageFilename);
        formData.append('auto_crop', String(autoCrop));
      } else if (wbState.sessionId) {
        formData.append('session_id', wbState.sessionId);
      }

      formData.append('pos_base', posBase);
      formData.append('neg_base', negBase);
      formData.append('pos_fd', posFd);
      if (selectedWorkflow) {
        formData.append('workflow_path', selectedWorkflow);
      }
      formData.append('scene_id', el.sceneId.value || 'custom');
      formData.append('script_text', el.scriptFinal.value || '');

      const res = await fetch('/api/generate_custom', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(errJson.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      wbState.lastResult = data;

      // 生成イラスト表示
      const imgBase64 = `data:image/png;base64,${data.imageBase64}`;
      el.generatedImage.src = imgBase64;
      el.generatedImage.classList.remove('hidden');
      el.btnDownloadResult.disabled = false;
      el.savedPathText.textContent = `保存先: ${data.saved_filename || data.saved_path || 'outputs/cards/'}`;

      // カードプレビュー更新
      el.cardScriptText.textContent = data.script_text || el.scriptFinal.value;

      // 履歴に追加
      const usedWf = data.workflow_path || selectedWorkflow;
      addToHistory({
        time: new Date().toLocaleTimeString(),
        filename: data.saved_filename,
        imgSrc: imgBase64,
        sceneName: el.sceneName.value || 'カスタム',
        posBase: posBase,
        negBase: negBase,
        posFd: posFd,
        workflowPath: usedWf
      });

      showToast('イラストの生成が完了しました！', 'success');
    } catch (e) {
      console.error('generate error:', e);
      showError('画像生成に失敗しました: ' + e.message);
    } finally {
      el.genSpinner.classList.add('hidden');
      el.btnStartGenerate.disabled = false;
      setStatus('idle');
    }
  }

  function addToHistory(item) {
    wbState.history.unshift(item);
    renderHistory();
  }

  function renderHistory() {
    if (wbState.history.length === 0) {
      el.historyList.innerHTML = '<div class="empty-history">生成履歴はまだありません</div>';
      return;
    }
    el.historyList.innerHTML = '';
    wbState.history.forEach((h, idx) => {
      const card = document.createElement('div');
      card.className = 'history-card-item';
      const wfBadge = h.workflowPath === 'storyweaver_anime_nofd_api.json' ? ' [FDなし]' : ' [標準FD]';
      card.innerHTML = `
        <img src="${h.imgSrc}" class="history-card-thumb" alt="サムネイル">
        <div class="history-card-meta">
          <span class="history-card-title">${h.time} - ${h.sceneName}${wfBadge}</span>
          <span class="history-card-sub">${h.filename || 'card.png'} (${h.workflowPath || ''})</span>
        </div>
      `;
      card.addEventListener('click', () => {
        // 条件復元
        el.promptPosBase.value = h.posBase;
        el.promptNegBase.value = h.negBase;
        el.promptPosFd.value = h.posFd;
        if (h.workflowPath && el.workflowSelect) {
          el.workflowSelect.value = h.workflowPath;
          wbState.currentWorkflow = h.workflowPath;
          updateWorkflowFdUiState();
        }
        el.generatedImage.src = h.imgSrc;
        el.generatedImage.classList.remove('hidden');
        el.imagePlaceholder.classList.add('hidden');
        el.btnDownloadResult.disabled = false;
        showToast(`履歴 (${h.time}) のプロンプト・ワークフロー条件を復元しました`, 'info');
      });
      el.historyList.appendChild(card);
    });
  }

  function handleDownloadResult() {
    if (!el.generatedImage.src) return;
    const a = document.createElement('a');
    a.href = el.generatedImage.src;
    a.download = `StoryWeaver_${Date.now()}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  // -------------------------------------------------------------------------
  // Event Listeners Setup
  // -------------------------------------------------------------------------
  function setupEventListeners() {
    // Error banner close
    el.btnCloseError.addEventListener('click', () => showError(''));

    // Scene CRUD
    el.sceneSelect.addEventListener('change', (e) => selectScene(e.target.value));
    el.btnLoadScene.addEventListener('click', () => selectScene(el.sceneSelect.value));
    el.btnSaveCurrentScene.addEventListener('click', handleSaveCurrentScene);
    el.btnAddScene.addEventListener('click', handleAddNewScene);
    el.btnDeleteScene.addEventListener('click', handleDeleteScene);

    // Scene Inputs -> Auto assemble
    [el.sceneScript, el.scenePrompt, el.sceneNegPrompt].filter(Boolean).forEach(i => {
      i.addEventListener('input', () => {
        el.cardScriptText.textContent = el.scriptFinal.value || el.sceneScript.value;
        triggerAutoAssemble();
      });
    });

    // Face Dropzone
    el.faceDropzone.addEventListener('click', () => el.faceFileInput.click());
    el.faceFileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        setFaceImageFile(e.target.files[0]);
      }
    });

    el.faceDropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      el.faceDropzone.classList.add('dragover');
    });
    el.faceDropzone.addEventListener('dragleave', () => el.faceDropzone.classList.remove('dragover'));
    el.faceDropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      el.faceDropzone.classList.remove('dragover');
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        setFaceImageFile(e.dataTransfer.files[0]);
      }
    });

    // Quick Face buttons
    document.querySelectorAll('.face-quick-set button').forEach(btn => {
      btn.addEventListener('click', () => loadTestFace(btn.getAttribute('data-face')));
    });

    // Camera capture & cropped face selection
    if (el.btnToggleCamera) el.btnToggleCamera.addEventListener('click', toggleWorkbenchCamera);
    if (el.selectCamera) {
      el.selectCamera.addEventListener('change', () => {
        if (wbState.cameraActive) startWorkbenchCamera();
      });
    }
    if (el.btnCaptureCrop) el.btnCaptureCrop.addEventListener('click', handleCaptureAndCrop);
    if (el.btnRetakeCamera) el.btnRetakeCamera.addEventListener('click', resetWorkbenchCameraReview);
    if (el.btnUseCropped) el.btnUseCropped.addEventListener('click', handleUsePendingCropped);
    if (el.btnRefreshCaptured) el.btnRefreshCaptured.addEventListener('click', loadCapturedFacesList);

    el.btnAnalyzeFace.addEventListener('click', handleAnalyzeFace);

    // Face trait inputs -> Auto assemble
    [el.inputGender, el.inputTraits, el.inputNegbias].forEach(i => {
      i.addEventListener('input', triggerAutoAssemble);
    });

    // Audio Input (File)
    el.audioFileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        setAudioBlob(e.target.files[0], e.target.files[0].name);
      }
    });

    // Quick Audio buttons
    document.querySelectorAll('.audio-quick-buttons button').forEach(btn => {
      btn.addEventListener('click', () => loadTestAudio(btn.getAttribute('data-audio')));
    });

    // Mic recording & Analysis
    el.btnMicToggle.addEventListener('click', toggleMicRecording);
    el.btnAnalyzeAudio.addEventListener('click', handleAnalyzeAudio);

    // 3-Point Calibration buttons & WAV file inputs
    document.querySelectorAll('.wb-btn-calib-rec').forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.getAttribute('data-calib-mode') || 'normal';
        toggleWbCalibRecording(mode);
      });
    });
    document.querySelectorAll('.wb-calib-file-input').forEach(inp => {
      inp.addEventListener('change', async (e) => {
        if (e.target.files && e.target.files[0]) {
          const mode = inp.getAttribute('data-calib-mode') || 'normal';
          await submitWbCalibrationBlob(e.target.files[0], mode);
          inp.value = '';
        }
      });
    });
    if (el.btnReanalyzeAfterCalib) {
      el.btnReanalyzeAfterCalib.addEventListener('click', async () => {
        if (!wbState.audioBlob) {
          showError('再分析するセリフ音声がセットされていません');
          return;
        }
        await handleAnalyzeAudio();
      });
    }

    // Threshold Slider & Emotion Mode
    el.burningSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      el.thresholdValText.innerHTML = `<strong>${val.toFixed(1)}</strong> dBFS`;
    });
    el.btnSaveThreshold.addEventListener('click', handleSaveThreshold);
    el.btnSaveMode.addEventListener('click', handleSaveMode);
    if (el.selectEmotionMode) {
      el.selectEmotionMode.addEventListener('change', updateEmotionModeUI);
    }
    if (el.btnResetQwenPrompt) {
      el.btnResetQwenPrompt.addEventListener('click', () => {
        if (el.qwenSystemPrompt) el.qwenSystemPrompt.value = DEFAULT_QWEN_SYSTEM_PROMPT;
        showToast('Qwen2 System Promptを初期値に戻しました', 'info');
      });
    }
    if (el.btnQwenUnload) {
      el.btnQwenUnload.addEventListener('click', handleQwenUnload);
    }

    // Script tools
    el.btnRestoreSceneScript.addEventListener('click', () => {
      el.scriptFinal.value = el.sceneScript.value;
      el.cardScriptText.textContent = el.scriptFinal.value;
      showToast('事前台本のセリフに戻しました', 'info');
    });
    el.btnApplyRecognizedScript.addEventListener('click', () => {
      if (wbState.audioAnalysis && wbState.audioAnalysis.recognized_text) {
        el.scriptFinal.value = wbState.audioAnalysis.recognized_text.trim();
        el.cardScriptText.textContent = el.scriptFinal.value;
        showToast('音声認識結果を反映しました', 'success');
      } else {
        showError('音声認識結果がまだありません');
      }
    });
    el.scriptFinal.addEventListener('input', () => {
      el.cardScriptText.textContent = el.scriptFinal.value;
    });

    // Expression Presets buttons
    document.querySelectorAll('.btn-preset-expr').forEach(btn => {
      btn.addEventListener('click', () => {
        const cat = btn.getAttribute('data-expr');
        if (wbState.expressionPresets[cat]) {
          el.inputExpression.value = wbState.expressionPresets[cat];
          triggerAutoAssemble();
          showToast(`表情プリセット「${cat}」をセットしました`, 'info');
        }
      });
    });

    el.inputExpression.addEventListener('input', triggerAutoAssemble);

    // Workflow Select Change
    if (el.workflowSelect) {
      el.workflowSelect.addEventListener('change', (e) => {
        wbState.currentWorkflow = e.target.value;
        updateWorkflowFdUiState();
        const wfObj = wbState.workflows.find(w => w.filename === wbState.currentWorkflow);
        showToast(`使用ワークフローを「${wfObj ? wfObj.label : wbState.currentWorkflow}」に切り替えました`, 'info');
      });
    }

    // FD Mode Toggles
    el.btnFdModeB.addEventListener('click', () => {
      wbState.fdOption = 'B';
      el.btnFdModeB.className = 'btn btn-xs btn-primary';
      el.btnFdModeA.className = 'btn btn-xs btn-glass';
      assemblePrompts();
      showToast('FaceDetailer: 案B (表情専念) を適用', 'info');
    });
    el.btnFdModeA.addEventListener('click', () => {
      wbState.fdOption = 'A';
      el.btnFdModeA.className = 'btn btn-xs btn-primary';
      el.btnFdModeB.className = 'btn btn-xs btn-glass';
      assemblePrompts();
      showToast('FaceDetailer: 案A (外見包含) を適用', 'info');
    });

    // Common parts -> Auto assemble
    [el.qualityPrompt, el.baseNegative].forEach(i => {
      i.addEventListener('input', triggerAutoAssemble);
    });

    // Manual assemble button
    el.btnManualAssemble.addEventListener('click', () => {
      assemblePrompts();
      showToast('プロンプト3系統を再構築しました', 'info');
    });

    // Generate button
    el.btnStartGenerate.addEventListener('click', handleStartGenerate);
    el.btnDownloadResult.addEventListener('click', handleDownloadResult);

    // Clear history
    el.btnClearHistory.addEventListener('click', () => {
      wbState.history = [];
      renderHistory();
    });
  }

  // Initialize on DOM ready
  document.addEventListener('DOMContentLoaded', init);
})();
