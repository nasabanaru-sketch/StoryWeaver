/**
 * StoryWeaver Live — Frontend Application Logic (Phase 4)
 */

(function () {
  'use strict';

  // Application State
  const state = {
    currentStep: 1,
    presets: [],
    config: {},
    selectedScene: null,
    selectedCameraId: localStorage.getItem('storyweaver_camera_id') || '',
    selectedMicId: localStorage.getItem('storyweaver_mic_id') || '',
    currentSessionId: '',
    capturedBlob: null,
    croppedImageDataUrl: '',
    vlmPromise: null,
    vlmAnalysisDone: false,
    vlmError: null,
    audioBlob: null,
    audioAnalysis: null,
    isRecording: false,
    mediaStream: null,
    audioContext: null,
    audioRecorderNode: null,
    audioChunks: [],
    recStartTime: 0,
    recTimerInterval: null,
    visAnimFrame: null,
    calibAudioContext: null,
    calibStream: null,
    calibAnimFrame: null,
    burningThreshold: -12.0,
    emotionMode: 'standard',
    workflows: [],
    currentWorkflow: 'storyweaver_anime_api.json',
    baselineData: null,
    isRecordingBaseline: false,
    calibRecordingMode: null,
    calibRecSession: null,
    // 2ステップ導線（棒読み測定 → 本番セリフ）
    flowBaselineDone: false,
    flowBaselineSkipped: false,
    isAnalyzingAudio: false,
    qwenAnalyzingTimer: null,
    // アートカード履歴＆再生成
    cardHistory: [],
    activeCardIndex: 0,
    isRegenerating: false,
    // Step 1 手動スタンバイ状態
    isStandbyLoading: false,
    standbyTimer: null
  };

  // DOM Elements
  const el = {
    badgeSystemText: document.getElementById('badge-system-text'),
    step1StandbyBar: document.getElementById('step1-standby-bar'),
    step1StandbyDot: document.getElementById('step1-standby-dot'),
    step1StandbyTitle: document.getElementById('step1-standby-title'),
    step1StandbySub: document.getElementById('step1-standby-sub'),
    btnStep1Standby: document.getElementById('btn-step1-standby'),
    step1StandbyIcon: document.getElementById('step1-standby-icon'),
    step1StandbyLabel: document.getElementById('step1-standby-label'),
    scenesGrid: document.getElementById('scenes-grid'),
    cameraStepTitle: document.getElementById('camera-step-title'),
    cameraStepDesc: document.getElementById('camera-step-desc'),
    cameraViewfinder: document.getElementById('camera-viewfinder'),
    video: document.getElementById('camera-video'),
    canvas: document.getElementById('camera-canvas'),
    snapshotPreview: document.getElementById('camera-snapshot-preview'),
    guideOverlay: document.getElementById('guide-overlay'),
    cropPreviewBadge: document.getElementById('crop-preview-badge'),
    cropConfirmNotice: document.getElementById('crop-confirm-notice'),
    step2VlmSpinner: document.getElementById('step2-vlm-spinner'),
    step2VlmText: document.getElementById('step2-vlm-text'),
    btnSwitchCamera: document.getElementById('btn-switch-camera'),
    btnTakePhoto: document.getElementById('btn-take-photo'),
    btnRetakePhoto: document.getElementById('btn-retake-photo'),
    btnConfirmPhoto: document.getElementById('btn-confirm-photo'),
    cameraReviewActions: document.getElementById('camera-review-actions'),
    cameraCountdown: document.getElementById('camera-countdown'),
    vlmBanner: document.getElementById('vlm-status-banner'),
    vlmBannerText: document.getElementById('vlm-banner-text'),
    currentSceneChip: document.getElementById('current-scene-chip'),
    step3CroppedThumbBox: document.getElementById('step3-cropped-thumb-box'),
    step3CroppedThumb: document.getElementById('step3-cropped-thumb'),
    btnRecordToggle: document.getElementById('btn-record-toggle'),
    recordStatusLabel: document.getElementById('record-status-label'),
    recordTimer: document.getElementById('record-timer'),
    audioVisCanvas: document.getElementById('audio-visualizer-canvas'),
    audioAnalysisResult: document.getElementById('audio-analysis-result'),
    resultStandardContainer: document.getElementById('result-standard-container'),
    resultDetailedContainer: document.getElementById('result-detailed-container'),
    // Qwen2-Audio ハイブリッド結果パネル
    resultQwenContainer: document.getElementById('result-qwen-container'),
    qwenAnalysisTime: document.getElementById('qwen-analysis-time'),
    qwenNuanceBadge: document.getElementById('qwen-nuance-badge'),
    qwenPrimaryIcon: document.getElementById('qwen-primary-icon'),
    qwenPrimaryName: document.getElementById('qwen-primary-name'),
    qwenPrimaryScore: document.getElementById('qwen-primary-score'),
    qwenSecondaryCard: document.getElementById('qwen-secondary-card'),
    qwenSecondaryLabel: document.getElementById('qwen-secondary-label'),
    qwenSecondaryIcon: document.getElementById('qwen-secondary-icon'),
    qwenSecondaryName: document.getElementById('qwen-secondary-name'),
    qwenSecondaryScore: document.getElementById('qwen-secondary-score'),
    qwenCommentText: document.getElementById('qwen-comment-text'),
    qwenCalibTag: document.getElementById('qwen-calib-tag'),
    qwenDeltaGrid: document.getElementById('qwen-delta-grid'),
    qwenE8List: document.getElementById('qwen-e8-list'),
    qwenAnalyzingOverlay: document.getElementById('qwen-analyzing-overlay'),
    qwenAnalyzingSub: document.getElementById('qwen-analyzing-sub'),
    // 2ステップ導線
    step3FlowGuide: document.getElementById('step3-flow-guide'),
    flowStepBaseline: document.getElementById('flow-step-baseline'),
    flowStepMain: document.getElementById('flow-step-main'),
    flowBaselineState: document.getElementById('flow-baseline-state'),
    flowMainState: document.getElementById('flow-main-state'),
    flowBaselineResult: document.getElementById('flow-baseline-result'),
    btnFlowSkipBaseline: document.getElementById('btn-flow-skip-baseline'),
    // スタッフ設定: Qwen2-Audio VRAM 管理
    qwen2VramStatus: document.getElementById('qwen2-vram-status'),
    btnQwen2RefreshStatus: document.getElementById('btn-qwen2-refresh-status'),
    btnQwen2Unload: document.getElementById('btn-qwen2-unload'),
    emotionBadge: document.getElementById('emotion-badge'),
    emotionBadgeIcon: document.getElementById('emotion-badge-icon'),
    emotionBadgeLabel: document.getElementById('emotion-badge-label'),
    analysisRmsText: document.getElementById('analysis-rms-text'),
    analysisThresholdTag: document.getElementById('analysis-threshold-tag'),
    // 2階層感情UI要素
    detailedAnalysisTime: document.getElementById('detailed-analysis-time'),
    top1EmoCard: document.getElementById('top1-emo-card'),
    top1ScoreWrap: document.getElementById('top1-score-wrap'),
    top1Score: document.getElementById('top1-score'),
    top1Icon: document.getElementById('top1-icon'),
    top1Name: document.getElementById('top1-name'),
    top1Bar: document.getElementById('top1-bar'),
    top2EmoCard: document.getElementById('top2-emo-card'),
    top2RankLabel: document.getElementById('top2-rank-label'),
    top2ScoreWrap: document.getElementById('top2-score-wrap'),
    top2Score: document.getElementById('top2-score'),
    top2Icon: document.getElementById('top2-icon'),
    top2Name: document.getElementById('top2-name'),
    top2BarTrack: document.getElementById('top2-bar-track'),
    top2Bar: document.getElementById('top2-bar'),
    btnToggleDetailedMetrics: document.getElementById('btn-toggle-detailed-metrics'),
    detailedMetricsPanel: document.getElementById('detailed-metrics-panel'),
    f7MetricsGrid: document.getElementById('f7-metrics-grid'),
    e12MetricsList: document.getElementById('e12-metrics-list'),
    scriptInput: document.getElementById('script-input-textarea'),
    scriptCharCount: document.getElementById('script-char-count'),
    btnResetScript: document.getElementById('btn-reset-script'),
    btnBackToCamera: document.getElementById('btn-back-to-camera'),
    btnStartGeneration: document.getElementById('btn-start-generation'),
    generatingEmotionTag: document.getElementById('generating-emotion-tag'),
    generatingProgressFill: document.getElementById('generating-progress-fill'),
    generatedCardImg: document.getElementById('generated-card-image'),
    cardEmotionBadge: document.getElementById('card-emotion-badge'),
    cardSceneTitle: document.getElementById('card-scene-title'),
    cardScriptText: document.getElementById('card-script-text'),
    cardMetaDate: document.getElementById('card-meta-date'),
    btnDownloadCard: document.getElementById('btn-download-card'),
    btnPrintCard: document.getElementById('btnPrintCard') || document.getElementById('btn-print-card'),
    btnRestartExperience: document.getElementById('btn-restart-experience'),
    btnRegenerateCard: document.getElementById('btn-regenerate-card'),
    cardHistoryContainer: document.getElementById('card-history-container'),
    cardHistoryStrip: document.getElementById('card-history-strip'),
    btnHistoryPrev: document.getElementById('btn-history-prev'),
    btnHistoryNext: document.getElementById('btn-history-next'),
    historyPageIndicator: document.getElementById('history-page-indicator'),
    // Staff modal
    staffModal: document.getElementById('staff-modal'),
    btnOpenStaffSettings: document.getElementById('btn-open-staff-settings'),
    btnCloseStaffModal: document.getElementById('btn-close-staff-modal'),
    selectCamera: document.getElementById('select-camera'),
    selectMic: document.getElementById('select-mic'),
    selectEmotionMode: document.getElementById('select-emotion-mode'),
    selectWorkflow: document.getElementById('select-workflow'),
    meterFill: document.getElementById('meter-fill'),
    meterThresholdMarker: document.getElementById('meter-threshold-marker'),
    meterThresholdLabel: document.getElementById('meter-threshold-label'),
    meterCurrentDb: document.getElementById('meter-current-db'),
    meterLiveVerdict: document.getElementById('meter-live-verdict'),
    sliderBurningThreshold: document.getElementById('slider-burning-threshold'),
    sliderThresholdVal: document.getElementById('slider-threshold-val'),
    btnSaveThreshold: document.getElementById('btn-save-threshold'),
    // 3点ボイスチェック・棒読みベースライン要素
    step3VoiceCheckBox: document.getElementById('step3-voice-check-box'),
    step3VcReadyMsg: document.getElementById('step3-vc-ready-msg'),
    step3BadgeNormal: document.getElementById('step3-badge-normal'),
    step3BadgePower: document.getElementById('step3-badge-power'),
    step3BadgeWhisper: document.getElementById('step3-badge-whisper'),
    step3CalibProgress: document.getElementById('step3-calib-progress'),
    step3CalibProgressText: document.getElementById('step3-calib-progress-text'),
    staffBadgeNormal: document.getElementById('staff-badge-normal'),
    staffBadgePower: document.getElementById('staff-badge-power'),
    staffBadgeWhisper: document.getElementById('staff-badge-whisper'),
    baselineStatusText: document.getElementById('baseline-status-text'),
    baselineUpdatedAt: document.getElementById('baseline-updated-at'),
    baselinePreviewChips: document.getElementById('baseline-preview-chips'),
    btnRecordBaseline: document.getElementById('btn-record-baseline'),
    btnRecordBaselineText: document.getElementById('btn-record-baseline-text'),
    baselineRecordProgress: document.getElementById('baseline-record-progress'),
    baselineProgressText: document.getElementById('baseline-progress-text'),
    adminScenesList: document.getElementById('admin-scenes-list'),
    btnAddNewScene: document.getElementById('btn-add-new-scene'),
    btnSaveAllPresets: document.getElementById('btn-save-all-presets'),
    infoSensevoice: document.getElementById('info-sensevoice'),
    infoComfyUrl: document.getElementById('info-comfy-url'),
    infoOllamaModel: document.getElementById('info-ollama-model'),
    infoSessionsCount: document.getElementById('info-sessions-count'),
    // Face alert modal
    faceAlertModal: document.getElementById('face-alert-modal'),
    btnAlertRetry: document.getElementById('btn-alert-retry')
  };

  // Toast Notification
  function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  // Step Navigation
  function goToStep(stepNum) {
    const prevStep = state.currentStep;
    state.currentStep = stepNum;
    document.querySelectorAll('.wizard-step').forEach(elStep => elStep.classList.remove('active'));
    const target = document.getElementById(`step-${stepNum}-${getStepName(stepNum)}`);
    if (target) target.classList.add('active');

    // Update Nav bar
    document.querySelectorAll('.step-item').forEach(item => {
      const s = parseInt(item.getAttribute('data-step'), 10);
      item.classList.remove('active', 'completed');
      if (s === stepNum) item.classList.add('active');
      else if (s < stepNum) item.classList.add('completed');
    });

    // Step-specific initializations
    if (stepNum === 1) {
      refreshQwen2Status();
    }
    if (stepNum === 2) {
      startCamera();
    } else {
      stopCamera();
    }

    // 撮影画面から Step 3 へ進んだ（＝新しい来場者）場合は 2ステップ導線を初期化
    if (stepNum === 3 && prevStep === 2) {
      resetVoiceFlow();
    }
  }

  function getStepName(step) {
    switch (step) {
      case 1: return 'scene';
      case 2: return 'camera';
      case 3: return 'audio';
      case 4: return 'generating';
      case 5: return 'card';
      default: return 'scene';
    }
  }

  // Load Presets & Config
  async function loadInitialData() {
    try {
      const [presetsRes, configRes, healthRes] = await Promise.all([
        fetch('/api/presets').then(r => r.json()),
        fetch('/api/config').then(r => r.json()),
        fetch('/api/health').then(r => r.json()).catch(() => ({ status: 'unknown' }))
      ]);

      state.presets = presetsRes.scenes || [];
      state.config = configRes || {};
      state.burningThreshold = parseFloat(state.config.BURNING_DB_THRESHOLD || -12.0);
      state.emotionMode = state.config.emotion_mode || 'standard';

      renderScenesGrid();
      updateStaffModalValues();
      updateVoiceCheckVisibility();
      updateSystemInfo(healthRes);
      loadBaselineStatus();
      loadWorkflows();
      refreshQwen2Status();
    } catch (err) {
      console.error('初期データ読み込み失敗:', err);
      showToast('初期設定の読み込みに失敗しました', 'error');
    }
  }

  // Render Step 1 Scenes
  function renderScenesGrid() {
    el.scenesGrid.innerHTML = '';
    state.presets.forEach(scene => {
      const card = document.createElement('div');
      card.className = 'scene-card';
      card.innerHTML = `
        <div class="scene-card-top">
          <span class="scene-card-id">${scene.id}</span>
          <h3 class="scene-card-name">${escapeHtml(scene.name)}</h3>
          <p class="scene-card-prompt-preview">${escapeHtml(scene.scene_prompt)}</p>
          <div class="scene-card-script-box">
            「${escapeHtml(scene.script_text)}」
          </div>
        </div>
        <div class="scene-card-bottom">
          <button class="btn btn-primary scene-select-btn">この世界に入る ➔</button>
        </div>
      `;
      card.addEventListener('click', () => selectScene(scene));
      el.scenesGrid.appendChild(card);
    });
  }

  function selectScene(scene) {
    state.selectedScene = scene;
    el.currentSceneChip.textContent = `シーン: ${scene.name}`;
    el.scriptInput.value = scene.script_text;
    updateCharCount();
    goToStep(2);
  }

  // =========================================================================
  // STEP 2: Camera Functions
  // =========================================================================
  let cameraFacingMode = 'user';

  async function startCamera() {
    resetCameraPreview();
    if (state.mediaStream) {
      state.mediaStream.getTracks().forEach(t => t.stop());
    }

    const constraints = {
      video: state.selectedCameraId
        ? { deviceId: { exact: state.selectedCameraId }, width: { ideal: 1280 }, height: { ideal: 960 } }
        : { facingMode: cameraFacingMode, width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false
    };

    try {
      state.mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
      el.video.srcObject = state.mediaStream;
      await el.video.play();
    } catch (err) {
      console.warn('getUserMedia error, retrying with basic constraint:', err);
      try {
        state.mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        el.video.srcObject = state.mediaStream;
        await el.video.play();
      } catch (e2) {
        showToast('カメラへのアクセスに失敗しました', 'error');
      }
    }
  }

  function stopCamera() {
    if (state.mediaStream) {
      state.mediaStream.getTracks().forEach(t => t.stop());
      state.mediaStream = null;
    }
  }

  function resetCameraPreview() {
    if (el.cameraViewfinder) el.cameraViewfinder.classList.remove('cropped-mode');
    if (el.cameraStepTitle) el.cameraStepTitle.textContent = 'カメラに顔を合わせて撮影してください';
    if (el.cameraStepDesc) el.cameraStepDesc.textContent = '頭部と輪郭をガイド枠に合わせることで、アニメへの転生精度が格段に向上します。';
    el.video.classList.remove('hidden');
    el.snapshotPreview.classList.add('hidden');
    el.guideOverlay.classList.remove('hidden');
    if (el.cropPreviewBadge) el.cropPreviewBadge.classList.add('hidden');
    if (el.cropConfirmNotice) el.cropConfirmNotice.classList.add('hidden');
    el.btnTakePhoto.classList.remove('hidden');
    el.btnSwitchCamera.classList.remove('hidden');
    el.cameraReviewActions.classList.add('hidden');
  }

  function applyCroppedImagePreview(dataUrl) {
    state.croppedImageDataUrl = dataUrl;
    el.snapshotPreview.src = dataUrl;
    if (el.step3CroppedThumb && el.step3CroppedThumbBox) {
      el.step3CroppedThumb.src = dataUrl;
      el.step3CroppedThumbBox.classList.remove('hidden');
    }
  }

  el.btnSwitchCamera.addEventListener('click', async () => {
    cameraFacingMode = (cameraFacingMode === 'user') ? 'environment' : 'user';
    state.selectedCameraId = '';
    await startCamera();
  });

  el.btnTakePhoto.addEventListener('click', () => {
    // 簡易カウントダウン
    let count = 3;
    el.cameraCountdown.textContent = count;
    el.cameraCountdown.classList.remove('hidden');

    const timer = setInterval(() => {
      count--;
      if (count > 0) {
        el.cameraCountdown.textContent = count;
      } else {
        clearInterval(timer);
        el.cameraCountdown.classList.add('hidden');
        captureSnapshot();
      }
    }, 600);
  });

  function captureSnapshot() {
    const video = el.video;
    const canvas = el.canvas;
    canvas.width = video.videoWidth || 768;
    canvas.height = video.videoHeight || 1024;
    const ctx = canvas.getContext('2d');

    // ミラー表示に合わせて描画
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(async blob => {
      if (!blob) return;
      state.capturedBlob = blob;

      // 新規セッションIDを発行し、撮影と同時に裏でVLM解析＆クロップ画像取得を並行開始
      const sid = 'sw_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
      state.currentSessionId = sid;
      state.vlmAnalysisDone = false;
      state.vlmError = null;

      // 確認状態へUI切り替え
      if (el.cameraViewfinder) el.cameraViewfinder.classList.add('cropped-mode');
      if (el.cameraStepTitle) el.cameraStepTitle.textContent = '切り抜き結果を確認してください';
      if (el.cameraStepDesc) el.cameraStepDesc.textContent = '頭髪から肩までが正方形枠内にバランスよく収まっているかご確認ください。';

      el.video.classList.add('hidden');
      el.guideOverlay.classList.add('hidden');
      el.snapshotPreview.src = URL.createObjectURL(blob);
      el.snapshotPreview.classList.remove('hidden');
      if (el.cropPreviewBadge) el.cropPreviewBadge.classList.remove('hidden');
      if (el.cropConfirmNotice) el.cropConfirmNotice.classList.remove('hidden');
      el.btnTakePhoto.classList.add('hidden');
      el.btnSwitchCamera.classList.add('hidden');
      el.cameraReviewActions.classList.remove('hidden');

      // 1) バックグラウンドで POST /api/analyze_face を非同期開始（待ち時間最小化）
      startVlmAnalysis(sid, blob);

      // 2) 即座に POST /api/capture_cropped_face で頭髪〜肩クロップ画像を取得してプレビュー表示
      try {
        const cropForm = new FormData();
        cropForm.append('face_image', blob, 'capture.jpg');
        const cropResp = await fetch('/api/capture_cropped_face', {
          method: 'POST',
          body: cropForm
        });
        if (cropResp.ok && state.currentSessionId === sid) {
          const cropData = await cropResp.json();
          if (cropData.cropped_image_base64) {
            applyCroppedImagePreview(`data:image/jpeg;base64,${cropData.cropped_image_base64}`);
          }
        }
      } catch (e) {
        console.warn('即時クロッププレビュー取得失敗（analyze_face側で補完します）:', e);
      }
    }, 'image/jpeg', 0.95);
  }

  el.btnRetakePhoto.addEventListener('click', () => {
    // 進行中のセッションを無効化し、カメラライブプレビューに戻す
    state.currentSessionId = '';
    state.capturedBlob = null;
    state.croppedImageDataUrl = '';
    state.vlmPromise = null;
    state.vlmAnalysisDone = false;
    state.vlmError = null;
    if (el.step3CroppedThumbBox) el.step3CroppedThumbBox.classList.add('hidden');
    resetCameraPreview();
  });

  el.btnConfirmPhoto.addEventListener('click', () => {
    if (!state.capturedBlob) return;

    // もしセッションが未開始の場合は開始する
    if (!state.currentSessionId || !state.vlmPromise) {
      state.currentSessionId = 'sw_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
      state.vlmAnalysisDone = false;
      state.vlmError = null;
      startVlmAnalysis(state.currentSessionId, state.capturedBlob);
    }

    // ステップ3へ即座に進行
    goToStep(3);
  });

  async function startVlmAnalysis(sessionId, imageBlob) {
    el.vlmBanner.classList.remove('hidden');
    el.vlmBanner.style.borderColor = 'rgba(139, 92, 246, 0.4)';
    el.vlmBannerText.textContent = '裏側であなたの外見特徴（髪型・生え際・眼鏡）をAI解析中...';
    if (el.step2VlmSpinner) el.step2VlmSpinner.classList.remove('hidden');
    if (el.step2VlmText) el.step2VlmText.textContent = '裏側で外見特徴（髪型・眼鏡）をAI解析中... このまま次へ進めます';

    const formData = new FormData();
    formData.append('face_image', imageBlob, 'capture.jpg');
    formData.append('session_id', sessionId);

    state.vlmPromise = (async () => {
      try {
        const resp = await fetch('/api/analyze_face', {
          method: 'POST',
          body: formData
        });

        // 撮り直し等で別セッションに切り替わっていた場合は無視
        if (state.currentSessionId !== sessionId) {
          return false;
        }

        if (resp.status === 422) {
          // 顔未検出
          const errJson = await resp.json().catch(() => ({}));
          state.vlmError = errJson.detail || 'FACE_NOT_DETECTED';
          state.vlmAnalysisDone = false;
          handleFaceNotDetected();
          return false;
        }

        if (!resp.ok) {
          const errJson = await resp.json().catch(() => ({}));
          const errMsg = errJson.detail || `HTTP ${resp.status}`;
          throw new Error(errMsg);
        }

        const res = await resp.json();
        if (state.currentSessionId !== sessionId) {
          return false;
        }

        if (res.cropped_image_base64 && !state.croppedImageDataUrl) {
          applyCroppedImagePreview(`data:image/jpeg;base64,${res.cropped_image_base64}`);
        }

        state.vlmAnalysisDone = true;
        state.vlmError = null;
        const summaryText = `✓ 外見抽出完了: ${res.gender_tag}, ${res.physical_traits || '標準'}`;
        el.vlmBannerText.textContent = summaryText;
        if (el.step2VlmSpinner) el.step2VlmSpinner.classList.add('hidden');
        if (el.step2VlmText) el.step2VlmText.textContent = summaryText;

        setTimeout(() => {
          if (state.vlmAnalysisDone && state.currentSessionId === sessionId) {
            el.vlmBanner.classList.add('hidden');
          }
        }, 4000);
        return true;
      } catch (err) {
        if (state.currentSessionId !== sessionId) {
          return false;
        }
        console.error('VLM 解析エラー:', err);
        state.vlmError = err.message;
        state.vlmAnalysisDone = false;
        el.vlmBanner.style.borderColor = '#ef4444';
        el.vlmBannerText.innerHTML = `⚠️ 外見解析エラー: ${escapeHtml(err.message)} <button id="btn-retry-vlm" class="btn btn-small btn-glass" style="margin-left:8px;padding:2px 8px;">再試行</button>`;
        if (el.step2VlmSpinner) el.step2VlmSpinner.classList.add('hidden');
        if (el.step2VlmText) el.step2VlmText.textContent = `⚠️ 外見解析エラー: ${err.message}`;

        const btnRetry = document.getElementById('btn-retry-vlm');
        if (btnRetry) {
          btnRetry.addEventListener('click', (e) => {
            e.stopPropagation();
            const retrySid = 'sw_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
            state.currentSessionId = retrySid;
            startVlmAnalysis(retrySid, state.capturedBlob);
          });
        }
        return false;
      }
    })();

    return state.vlmPromise;
  }

  function handleFaceNotDetected() {
    state.currentSessionId = '';
    state.vlmPromise = null;
    el.faceAlertModal.classList.remove('hidden');
  }

  el.btnAlertRetry.addEventListener('click', () => {
    el.faceAlertModal.classList.add('hidden');
    state.capturedBlob = null;
    state.croppedImageDataUrl = '';
    if (el.step3CroppedThumbBox) el.step3CroppedThumbBox.classList.add('hidden');
    goToStep(2);
  });

  // =========================================================================
  // STEP 3: Audio Recording & Script Editing
  // =========================================================================
  el.scriptInput.addEventListener('input', updateCharCount);

  function updateCharCount() {
    el.scriptCharCount.textContent = `${el.scriptInput.value.length} 文字`;
  }

  el.btnResetScript.addEventListener('click', () => {
    if (state.selectedScene) {
      el.scriptInput.value = state.selectedScene.script_text;
      updateCharCount();
    }
  });

  el.btnBackToCamera.addEventListener('click', () => {
    state.currentSessionId = '';
    state.capturedBlob = null;
    state.croppedImageDataUrl = '';
    state.vlmPromise = null;
    state.vlmAnalysisDone = false;
    state.vlmError = null;
    if (el.step3CroppedThumbBox) el.step3CroppedThumbBox.classList.add('hidden');
    goToStep(2);
  });

  el.btnRecordToggle.addEventListener('click', () => {
    if (state.isRecording) {
      stopRecording();
    } else {
      if (state.isAnalyzingAudio) {
        showToast('AIが分析中です。完了までお待ちください', 'info');
        return;
      }
      if (state.isRecordingBaseline) {
        showToast('棒読み測定の録音中です。先に測定を停止してください', 'info');
        return;
      }
      startRecording();
    }
  });

  async function startRecording() {
    try {
      const constraints = {
        audio: {
          deviceId: state.selectedMicId ? { exact: state.selectedMicId } : undefined,
          autoGainControl: false,
          noiseSuppression: false,
          echoCancellation: false,
          channelCount: 1
        },
        video: false
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      state.audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = state.audioContext.createMediaStreamSource(stream);

      // ScriptProcessor を用いて 16kHz モノラル Float32 データを蓄積
      const bufferSize = 4096;
      state.audioRecorderNode = state.audioContext.createScriptProcessor(bufferSize, 1, 1);
      state.audioChunks = [];

      state.audioRecorderNode.onaudioprocess = (e) => {
        if (!state.isRecording) return;
        const inputData = e.inputBuffer.getChannelData(0);
        state.audioChunks.push(new Float32Array(inputData));
      };

      source.connect(state.audioRecorderNode);
      state.audioRecorderNode.connect(state.audioContext.destination);

      // ビジュアライザー起動
      setupVisualizer(source, state.audioContext);

      state.isRecording = true;
      el.btnRecordToggle.classList.add('recording');
      el.btnRecordToggle.querySelector('.icon-mic').classList.add('hidden');
      el.btnRecordToggle.querySelector('.icon-stop').classList.remove('hidden');
      el.recordStatusLabel.textContent = '録音中... 魂を込めて発声してください！';

      state.recStartTime = Date.now();
      state.recTimerInterval = setInterval(updateRecTimer, 200);
    } catch (err) {
      console.error('マイク録音開始失敗:', err);
      showToast('マイクの初期化に失敗しました。設定を確認してください', 'error');
    }
  }

  function updateRecTimer() {
    const elapsedMs = Date.now() - state.recStartTime;
    const sec = Math.floor(elapsedMs / 1000);
    const ms = Math.floor((elapsedMs % 1000) / 100);
    const sStr = (sec < 10 ? '0' : '') + sec;
    el.recordTimer.textContent = `${sStr}.${ms}s`;
  }

  async function stopRecording() {
    if (!state.isRecording) return;
    state.isRecording = false;
    clearInterval(state.recTimerInterval);

    el.btnRecordToggle.classList.remove('recording');
    el.btnRecordToggle.querySelector('.icon-mic').classList.remove('hidden');
    el.btnRecordToggle.querySelector('.icon-stop').classList.add('hidden');
    el.recordStatusLabel.textContent = '音声解析中... (SenseVoice)';

    if (state.visAnimFrame) cancelAnimationFrame(state.visAnimFrame);

    // エンコード: 16kHz mono 16bit PCM WAV
    const wavBlob = encodeFloat32ToWav(state.audioChunks, 16000);
    state.audioBlob = wavBlob;

    if (state.audioContext) {
      await state.audioContext.close();
      state.audioContext = null;
    }

    // POST /api/analyze_audio 送信
    await postAnalyzeAudio(wavBlob);
  }

  async function postAnalyzeAudio(wavBlob) {
    const formData = new FormData();
    formData.append('audio_file', wavBlob, 'recording.wav');

    const isQwenMode = state.emotionMode === 'qwen2_audio_hybrid';
    state.isAnalyzingAudio = true;
    el.btnRecordToggle.disabled = true;
    setFlowMainState('analyzing');
    if (isQwenMode) {
      el.recordStatusLabel.textContent = 'AIが声の演技ニュアンスと物理変化を精密分析中...';
      showQwenAnalyzing(true);
    }

    try {
      const resp = await fetch('/api/analyze_audio', {
        method: 'POST',
        body: formData
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const data = await resp.json();
      state.audioAnalysis = data;

      // 感情バッジ表示 (モードに応じて分岐)
      if (data.emotion_mode === 'qwen2_audio_hybrid') {
        renderEmotionQwen(data);
      } else if (data.emotion_mode === 'detailed_12') {
        renderEmotionDetailed(data);
      } else {
        renderEmotionStandard(data.expression_state, data.rms_db);
      }

      // セリフ自動反映（認識テキストが存在する場合）
      if (data.recognized_text && data.recognized_text.trim()) {
        el.scriptInput.value = data.recognized_text.trim();
        updateCharCount();
        showToast('音声認識セリフを自動入力しました（編集可能です）', 'success');
      }

      el.recordStatusLabel.textContent = '録音完了！必要に応じてセリフを修正してください';
      setFlowMainState('done');
    } catch (err) {
      console.error('analyze_audio 失敗:', err);
      el.recordStatusLabel.textContent = '音声解析に失敗しました。再録音または手動入力してください';
      setFlowMainState('error');
    } finally {
      state.isAnalyzingAudio = false;
      el.btnRecordToggle.disabled = false;
      showQwenAnalyzing(false);
      refreshQwen2Status();
    }
  }

  // Qwen2-Audio 精密分析中ローディング演出
  function showQwenAnalyzing(visible) {
    if (!el.qwenAnalyzingOverlay) return;
    if (state.qwenAnalyzingTimer) {
      clearInterval(state.qwenAnalyzingTimer);
      state.qwenAnalyzingTimer = null;
    }
    if (visible) {
      el.qwenAnalyzingOverlay.classList.remove('hidden');
      el.audioAnalysisResult.classList.add('hidden');
      const t0 = Date.now();
      const tick = () => {
        const sec = (Date.now() - t0) / 1000;
        if (el.qwenAnalyzingSub) {
          el.qwenAnalyzingSub.textContent = `経過 ${sec.toFixed(1)} 秒（通常 10〜20 秒・初回はモデル読込で約1分）`;
        }
      };
      tick();
      state.qwenAnalyzingTimer = setInterval(tick, 200);
    } else {
      el.qwenAnalyzingOverlay.classList.add('hidden');
    }
  }

  // 従来モード用バッジ描画
  function renderEmotionStandard(category, rmsDb) {
    el.audioAnalysisResult.classList.remove('hidden');
    el.resultDetailedContainer.classList.add('hidden');
    if (el.resultQwenContainer) el.resultQwenContainer.classList.add('hidden');
    el.resultStandardContainer.classList.remove('hidden');

    el.emotionBadge.className = `analysis-badge badge-${category.toLowerCase()}`;
    el.emotionBadgeLabel.textContent = category;

    let icon = '🔥';
    if (category === 'JOYFUL') icon = '✨';
    else if (category === 'EMOTIONAL') icon = '💧';
    else if (category === 'COOL') icon = '❄️';
    el.emotionBadgeIcon.textContent = icon;

    el.analysisRmsText.textContent = `${rmsDb.toFixed(1)} dBFS`;

    if (rmsDb >= state.burningThreshold) {
      el.analysisThresholdTag.textContent = '閾値突破 (BURNING昇格)';
      el.analysisThresholdTag.style.display = 'inline-block';
    } else {
      el.analysisThresholdTag.style.display = 'none';
    }
  }

  // 2階層感情・ニュアンス修飾定義辞書（全8項目）
  const EMOTION_DEFS_8 = {
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

  // 詳細感情モード（2階層方式：基本6表情＋ニュアンス修飾2種）用描画
  function renderEmotionDetailed(data) {
    el.audioAnalysisResult.classList.remove('hidden');
    el.resultStandardContainer.classList.add('hidden');
    if (el.resultQwenContainer) el.resultQwenContainer.classList.add('hidden');
    el.resultDetailedContainer.classList.remove('hidden');

    const top1 = data.primary_emotion || { id: 'serene', name_ja: '穏やか・優しさ', score: 52.0, icon: '🕊️', weight: 0.85 };
    const top2 = data.secondary_emotion || { id: 'none_modifier', name_ja: 'ストレート表現（修飾なし）', score: 0.0, icon: '➖', weight: 0.0 };
    const isNoneMod = (top2.id === 'none_modifier' || top2.score <= 0);

    // 第1階層: 主感情 (Primary)
    el.top1Score.textContent = Number(top1.score || 0).toFixed(1);
    el.top1Icon.textContent = top1.icon || EMOTION_DEFS_8[top1.id]?.icon || '✨';
    el.top1Name.textContent = top1.name_ja || EMOTION_DEFS_8[top1.id]?.name_ja || top1.id;
    el.top1Bar.style.width = `${Math.min(100, Math.max(0, top1.score || 0))}%`;

    // 第2階層: 声質ニュアンス修飾 (Secondary / Nuance)
    if (el.top2EmoCard) {
      el.top2EmoCard.style.opacity = isNoneMod ? '0.68' : '1.0';
      el.top2EmoCard.style.borderColor = isNoneMod ? 'rgba(255, 255, 255, 0.14)' : 'rgba(168, 85, 247, 0.45)';
    }
    if (el.top2RankLabel) {
      el.top2RankLabel.textContent = isNoneMod ? 'STRAIGHT' : 'NUANCE';
    }
    if (isNoneMod) {
      if (el.top2ScoreWrap) el.top2ScoreWrap.innerHTML = `<span style="font-size:12px;color:#94a3b8;">修飾なし</span>`;
      el.top2Icon.textContent = top2.icon || '➖';
      el.top2Name.textContent = top2.name_ja || 'ストレート表現（修飾なし）';
      el.top2Bar.style.width = '0%';
    } else {
      if (el.top2ScoreWrap) {
        el.top2ScoreWrap.innerHTML = `<strong id="top2-score">${Number(top2.score || 0).toFixed(1)}</strong> pt`;
        el.top2Score = document.getElementById('top2-score');
      } else if (el.top2Score) {
        el.top2Score.textContent = Number(top2.score || 0).toFixed(1);
      }
      el.top2Icon.textContent = top2.icon || EMOTION_DEFS_8[top2.id]?.icon || '✨';
      el.top2Name.textContent = top2.name_ja || EMOTION_DEFS_8[top2.id]?.name_ja || top2.id;
      el.top2Bar.style.width = `${Math.min(100, Math.max(0, top2.score || 0))}%`;
    }

    // 解析時間
    if (el.detailedAnalysisTime && data.analysis_time_sec !== undefined) {
      el.detailedAnalysisTime.textContent = `${data.analysis_time_sec}s`;
    }

    // 7基礎指標グリッド
    if (el.f7MetricsGrid && data.features_7) {
      el.f7MetricsGrid.innerHTML = '';
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
        item.innerHTML = `
          <span class="f7-label">${f7Labels[k] || k}</span>
          <span class="f7-val">${Number(v).toFixed(1)} pt</span>
        `;
        el.f7MetricsGrid.appendChild(item);
      }
    }

    // 全8項目（基本6＋修飾2）スコア一覧リスト
    if (el.e12MetricsList && data.emotions_12) {
      el.e12MetricsList.innerHTML = '';
      const sorted = Object.entries(data.emotions_12).sort((a, b) => b[1] - a[1]);
      sorted.forEach(([emoId, score]) => {
        const row = document.createElement('div');
        row.className = 'e12-row';
        const isPrimaryTop = (emoId === top1.id);
        const isActiveMod = (!isNoneMod && emoId === top2.id);
        const isTop = isPrimaryTop || isActiveMod;
        const def = EMOTION_DEFS_8[emoId];
        const nameDisp = def ? `${def.icon} ${def.name_ja}` : emoId;
        row.innerHTML = `
          <span class="e12-name" style="width: 145px; ${isTop ? 'color: #f472b6; font-weight: 700;' : ''}">${nameDisp}</span>
          <div class="e12-track">
            <div class="e12-fill" style="width: ${Math.min(100, Math.max(0, score))}%; ${isTop ? 'background: linear-gradient(90deg, #ec4899, #f43f5e);' : ''}"></div>
          </div>
          <span class="e12-val">${Number(score).toFixed(1)} pt</span>
        `;
        el.e12MetricsList.appendChild(row);
      });
    }

    // 生成中タグおよびアートカード準備
    if (isNoneMod) {
      el.generatingEmotionTag.textContent = `${top1.icon} ${top1.name_ja} (${Number(top1.score).toFixed(1)}pt / w=${top1.weight ?? 1.0})`;
    } else {
      el.generatingEmotionTag.textContent = `${top1.icon} ${top1.name_ja} (${Number(top1.score).toFixed(1)}pt) ＋ ${top2.icon} ${top2.name_ja} (${Number(top2.score).toFixed(1)}pt)`;
    }
  }

  // =========================================================================
  // Qwen2-Audio ハイブリッドモード専用描画
  // =========================================================================
  const MODIFIER_THRESHOLD = 60.0;

  function fmtSigned(v, digits) {
    const n = Number(v) || 0;
    return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}`;
  }

  function clamp(v, lo, hi) {
    return Math.min(hi, Math.max(lo, v));
  }

  // 棒読み基準（中央=±0 / 1.0倍）からの増減を中央起点バーで表示するための定義
  function buildDeltaMetrics(d) {
    const fold = Number(d.breath_ratio_fold ?? d.breath_ratio_Multiple ?? 1.0) || 0;
    const hasStdDelta = d.delta_f0_std_st !== undefined && d.delta_f0_std_st !== null;
    const hasHnrDelta = d.delta_hnr_db !== undefined && d.delta_hnr_db !== null;
    const rms = Number(d.delta_rms_db || 0);
    const pitch = Number(d.delta_pitch_st || 0);
    const std = Number(d.f0_std_st || 0);
    const stdDelta = hasStdDelta ? Number(d.delta_f0_std_st) : std - 2.5;
    const cent = Number(d.delta_centroid_hz || 0);
    const hnr = Number(d.hnr_db || 0);
    const hnrDelta = hasHnrDelta ? Number(d.delta_hnr_db) : 0;

    return [
      {
        icon: '🔊', label: '声量変化', value: `${fmtSigned(rms, 1)} dB`,
        norm: clamp(rms / 10, -1, 1),
        hint: rms >= 6 ? '大幅に大きい・叫び/張り声' : rms >= 2.5 ? 'やや大きい' : rms <= -4 ? '小さい・ささやき/抑えめ' : rms <= -1.5 ? 'やや控えめ' : '平常並み'
      },
      {
        icon: '🎵', label: 'ピッチ変化', value: `${fmtSigned(pitch, 1)} 半音`,
        norm: clamp(pitch / 5, -1, 1),
        hint: pitch >= 3 ? '大幅に高い・高揚/驚き' : pitch >= 1.2 ? 'やや高い' : pitch <= -2.5 ? '低い・沈み/威厳' : pitch <= -1 ? 'やや低い' : '平常並み'
      },
      {
        icon: '〰️', label: '抑揚の広さ', value: `${std.toFixed(2)} 半音${hasStdDelta ? `（${fmtSigned(stdDelta, 2)}）` : ''}`,
        norm: clamp(stdDelta / 2, -1, 1),
        hint: (stdDelta >= 1.0 || std >= 3.8) ? '抑揚が大きい・劇的' : (stdDelta <= -0.8 || std <= 1.5) ? '平坦・棒読み傾向' : '標準的な抑揚'
      },
      {
        icon: '💡', label: '明るさ変化', value: `${fmtSigned(cent, 0)} Hz`,
        norm: clamp(cent / 800, -1, 1),
        hint: cent >= 350 ? '明るい・鋭い声質' : cent <= -300 ? '暗い・柔らかい声質' : '平常並み'
      },
      {
        icon: '💎', label: '澄み具合 (HNR)', value: `${hnr.toFixed(1)} dB${hasHnrDelta ? `（${fmtSigned(hnrDelta, 1)}）` : ''}`,
        norm: clamp(hnrDelta / 6, -1, 1),
        hint: hnrDelta >= 3 ? '澄んだ芯のある声' : hnrDelta <= -3 ? '息混じり・かすれ' : '標準的'
      },
      {
        icon: '🌬️', label: '息漏れ倍率', value: `×${fold.toFixed(2)}`,
        norm: clamp(Math.log2(Math.max(fold, 0.01)) / 2, -1, 1),
        hint: fold >= 2.0 ? '吐息が多い・艶/恥じらい' : fold <= 0.6 ? '息漏れ少なめ・明瞭' : '平常並み'
      }
    ];
  }

  function renderEmotionQwen(data) {
    el.audioAnalysisResult.classList.remove('hidden');
    el.resultStandardContainer.classList.add('hidden');
    el.resultDetailedContainer.classList.add('hidden');
    if (!el.resultQwenContainer) return;
    el.resultQwenContainer.classList.remove('hidden');

    const top1 = data.primary_emotion || { id: 'serene', name_ja: '穏やか・優しさ', score: 52.0, icon: '🕊️', weight: 0.85 };
    const top2 = data.secondary_emotion || { id: 'none_modifier', name_ja: 'ストレート表現（修飾なし）', score: 0.0, icon: '➖', weight: 0.0 };
    const isNoneMod = (top2.id === 'none_modifier' || Number(top2.score || 0) < MODIFIER_THRESHOLD);

    // 解析時間
    if (el.qwenAnalysisTime) {
      el.qwenAnalysisTime.textContent = `${Number(data.analysis_time_sec || 0).toFixed(1)}s`;
    }

    // ① 一言ニュアンス ＋ 2階層感情
    const nuanceFallback = isNoneMod
      ? `${top1.name_ja}`
      : `${top1.name_ja} ＋ ${top2.name_ja}`;
    el.qwenNuanceBadge.textContent = data.overall_impression_en || data.detected_nuance_short || nuanceFallback;
    el.qwenPrimaryIcon.textContent = top1.icon || EMOTION_DEFS_8[top1.id]?.icon || '✨';
    el.qwenPrimaryName.textContent = top1.name_ja || EMOTION_DEFS_8[top1.id]?.name_ja || top1.id;
    el.qwenPrimaryScore.textContent = `${Number(top1.score || 0).toFixed(1)} pt`;

    el.qwenSecondaryCard.classList.toggle('is-active', !isNoneMod);
    if (isNoneMod) {
      el.qwenSecondaryLabel.textContent = '第2階層 STRAIGHT';
      el.qwenSecondaryIcon.textContent = '➖';
      el.qwenSecondaryName.textContent = 'ストレート表現（修飾なし）';
      el.qwenSecondaryScore.textContent = '未発動（60pt 未満）';
    } else {
      el.qwenSecondaryLabel.textContent = '第2階層 NUANCE 発動！';
      el.qwenSecondaryIcon.textContent = top2.icon || EMOTION_DEFS_8[top2.id]?.icon || '✨';
      el.qwenSecondaryName.textContent = top2.name_ja || EMOTION_DEFS_8[top2.id]?.name_ja || top2.id;
      el.qwenSecondaryScore.textContent = `${Number(top2.score || 0).toFixed(1)} pt`;
    }

    // ② 日本語講評コメントは出力しない仕様のため、空の場合は吹き出し自体を非表示にする
    const commentBubble = el.qwenCommentText ? el.qwenCommentText.closest('.qwen-comment-bubble') : null;
    if (data.acting_comment_ja && data.acting_comment_ja.trim()) {
      if (commentBubble) commentBubble.classList.remove('hidden');
      el.qwenCommentText.textContent = data.acting_comment_ja;
    } else if (commentBubble) {
      commentBubble.classList.add('hidden');
    }

    // ③ 棒読み基準からの物理変化メーター
    const bdRaw = data.baseline_deltas || {};
    const d = (bdRaw.deltas && typeof bdRaw.deltas === 'object') ? bdRaw.deltas : bdRaw;
    if (el.qwenCalibTag) {
      if (d.is_silent) {
        el.qwenCalibTag.textContent = '無音判定';
        el.qwenCalibTag.className = 'qwen-calib-tag is-warn';
      } else if (d.is_calibrated) {
        el.qwenCalibTag.textContent = '基準: あなたの棒読み';
        el.qwenCalibTag.className = 'qwen-calib-tag is-ok';
      } else {
        el.qwenCalibTag.textContent = '基準: 標準初期値（未測定）';
        el.qwenCalibTag.className = 'qwen-calib-tag is-warn';
      }
    }
    if (el.qwenDeltaGrid) {
      el.qwenDeltaGrid.innerHTML = '';
      buildDeltaMetrics(d).forEach(m => {
        const pct = Math.abs(m.norm) * 50;
        const dirClass = m.norm > 0.02 ? 'is-up' : m.norm < -0.02 ? 'is-down' : 'is-flat';
        const fillStyle = m.norm >= 0
          ? `left: 50%; width: ${pct}%;`
          : `left: ${50 - pct}%; width: ${pct}%;`;
        const item = document.createElement('div');
        item.className = `qwen-delta-item ${dirClass}`;
        item.innerHTML = `
          <div class="qwen-delta-head">
            <span class="qwen-delta-label">${m.icon} ${m.label}</span>
            <span class="qwen-delta-value">${escapeHtml(m.value)}</span>
          </div>
          <div class="qwen-delta-track">
            <div class="qwen-delta-center"></div>
            <div class="qwen-delta-fill" style="${fillStyle}"></div>
          </div>
          <span class="qwen-delta-hint">${escapeHtml(m.hint)}</span>
        `;
        el.qwenDeltaGrid.appendChild(item);
      });
    }

    // ④ 8感情スコア一覧（基本6 → 修飾2 の順、修飾は60ptラインを表示）
    if (el.qwenE8List && data.emotions_12) {
      el.qwenE8List.innerHTML = '';
      const order = ['joy', 'burning', 'sorrow', 'surprise_fear', 'confident', 'serene', 'sultry_modifier', 'bashful_modifier'];
      const keys = order.filter(k => k in data.emotions_12)
        .concat(Object.keys(data.emotions_12).filter(k => !order.includes(k)));
      keys.forEach((emoId, idx) => {
        const score = Number(data.emotions_12[emoId] || 0);
        const def = EMOTION_DEFS_8[emoId];
        const isModifier = def ? def.tier === 'modifier' : emoId.endsWith('_modifier');
        const isTop = emoId === top1.id || (!isNoneMod && emoId === top2.id);
        if (isModifier && idx > 0 && !EMOTION_DEFS_8[keys[idx - 1]]?.tier?.startsWith('modifier')) {
          const sep = document.createElement('div');
          sep.className = 'qwen-e8-sep';
          sep.textContent = '声質ニュアンス修飾（60pt 以上で発動）';
          el.qwenE8List.appendChild(sep);
        }
        const row = document.createElement('div');
        row.className = `qwen-e8-row${isTop ? ' is-top' : ''}${isModifier ? ' is-modifier' : ''}${isModifier && score >= MODIFIER_THRESHOLD ? ' is-fired' : ''}`;
        row.innerHTML = `
          <span class="qwen-e8-name">${def ? `${def.icon} ${def.name_ja}` : escapeHtml(emoId)}</span>
          <div class="qwen-e8-track">
            <div class="qwen-e8-fill" style="width: ${clamp(score, 0, 100)}%;"></div>
            ${isModifier ? `<div class="qwen-e8-threshold" style="left: ${MODIFIER_THRESHOLD}%;" title="発動閾値 60pt"></div>` : ''}
          </div>
          <span class="qwen-e8-val">${score.toFixed(1)}</span>
        `;
        el.qwenE8List.appendChild(row);
      });
    }

    // 生成中タグ
    if (isNoneMod) {
      el.generatingEmotionTag.textContent = `${top1.icon} ${top1.name_ja} (${Number(top1.score).toFixed(1)}pt) — ${data.detected_nuance_short || ''}`;
    } else {
      el.generatingEmotionTag.textContent = `${top1.icon} ${top1.name_ja} ＋ ${top2.icon} ${top2.name_ja} — ${data.detected_nuance_short || ''}`;
    }
  }

  // =========================================================================
  // 2ステップ導線（STEP 3-1 棒読み測定 → STEP 3-2 本番セリフ）
  // =========================================================================
  function isFlowMode() {
    return state.emotionMode === 'detailed_12' || state.emotionMode === 'qwen2_audio_hybrid';
  }

  function setFlowBaselineState(kind, html) {
    if (!el.flowStepBaseline) return;
    const labels = { pending: '未測定', recording: '測定中...', done: '✅ 登録済み', skipped: 'スキップ' };
    el.flowBaselineState.textContent = labels[kind] || '';
    el.flowBaselineState.className = `flow-step-state state-${kind}`;
    el.flowStepBaseline.classList.toggle('is-current', kind === 'pending' || kind === 'recording');
    el.flowStepBaseline.classList.toggle('is-done', kind === 'done' || kind === 'skipped');
    el.flowStepMain.classList.toggle('is-current', kind === 'done' || kind === 'skipped');
    if (el.flowBaselineResult) {
      if (html) {
        el.flowBaselineResult.innerHTML = html;
        el.flowBaselineResult.classList.remove('hidden');
      } else {
        el.flowBaselineResult.innerHTML = '';
        el.flowBaselineResult.classList.add('hidden');
      }
    }
    if (el.btnFlowSkipBaseline) {
      el.btnFlowSkipBaseline.classList.toggle('hidden', kind === 'done' || kind === 'skipped');
    }
  }

  function setFlowMainState(kind) {
    if (!el.flowMainState) return;
    const labels = { waiting: '待機中', analyzing: '分析中...', done: '✅ 分析完了', error: '⚠ 再録音してください' };
    el.flowMainState.textContent = labels[kind] || '';
    el.flowMainState.className = `flow-step-state state-${kind}`;
    if (kind === 'done') el.flowStepMain.classList.add('is-done');
    else el.flowStepMain.classList.remove('is-done');
  }

  function resetVoiceFlow() {
    state.flowBaselineDone = false;
    state.flowBaselineSkipped = false;
    state.audioBlob = null;
    state.audioAnalysis = null;
    if (el.audioAnalysisResult) el.audioAnalysisResult.classList.add('hidden');
    setFlowBaselineState('pending', '');
    setFlowMainState('waiting');
    if (el.step3FlowGuide) el.step3FlowGuide.classList.toggle('hidden', !isFlowMode());
  }

  if (el.btnFlowSkipBaseline) {
    el.btnFlowSkipBaseline.addEventListener('click', () => {
      state.flowBaselineSkipped = true;
      setFlowBaselineState('skipped', '<span class="flow-skip-note">基準測定をスキップしました（前回の基準値または標準初期値で分析します）</span>');
      showToast('本番セリフの録音へ進みます', 'info');
    });
  }

  // 詳細指標折りたたみトグル
  if (el.btnToggleDetailedMetrics) {
    el.btnToggleDetailedMetrics.addEventListener('click', () => {
      const isHidden = el.detailedMetricsPanel.classList.toggle('hidden');
      el.btnToggleDetailedMetrics.classList.toggle('expanded', !isHidden);
    });
  }

  // 16bit PCM WAV Encoder
  function encodeFloat32ToWav(chunks, sampleRate) {
    let totalLength = 0;
    for (let c of chunks) totalLength += c.length;
    const merged = new Float32Array(totalLength);
    let offset = 0;
    for (let c of chunks) {
      merged.set(c, offset);
      offset += c.length;
    }

    const buffer = new ArrayBuffer(44 + merged.length * 2);
    const view = new DataView(buffer);

    // RIFF header
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + merged.length * 2, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM format
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, 'data');
    view.setUint32(40, merged.length * 2, true);

    // Write samples
    let index = 44;
    for (let i = 0; i < merged.length; i++) {
      let s = Math.max(-1, Math.min(1, merged[i]));
      view.setInt16(index, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      index += 2;
    }

    return new Blob([view], { type: 'audio/wav' });
  }

  function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  // Visualizer
  function setupVisualizer(sourceNode, audioCtx) {
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64;
    sourceNode.connect(analyser);

    const canvas = el.audioVisCanvas;
    const ctx = canvas.getContext('2d');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function draw() {
      state.visAnimFrame = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);

      ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const barWidth = (canvas.width / bufferLength) * 1.5;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * canvas.height;
        ctx.fillStyle = `hsl(${260 + i * 3}, 80%, ${50 + (barHeight / canvas.height) * 40}%)`;
        ctx.fillRect(x, canvas.height - barHeight, barWidth - 2, barHeight);
        x += barWidth;
      }
    }
    draw();
  }

  // =========================================================================
  // STEP 4 & 5: Generation & Art Card Display
  // =========================================================================
  el.btnStartGeneration.addEventListener('click', async () => {
    const scriptText = el.scriptInput.value.trim();
    if (!scriptText) {
      showToast('セリフを入力してください', 'error');
      return;
    }

    // 外見解析の完了待機またはエラーハンドリング
    if (!state.vlmAnalysisDone) {
      if (state.vlmPromise) {
        showToast('外見特徴のAI解析完了を待っています...', 'info');
        el.btnStartGeneration.disabled = true;
        const ok = await state.vlmPromise;
        el.btnStartGeneration.disabled = false;
        if (!ok) {
          showToast(`外見解析が完了していないため生成できません (${state.vlmError || 'エラー'})。再試行ボタンまたは再撮影を行ってください`, 'error');
          return;
        }
      } else {
        showToast('顔写真の送信が行われていません。撮影画面に戻って再撮影してください', 'error');
        return;
      }
    }

    goToStep(4);
    simulateProgressSteps();

    // POST /api/generate_scene
    const formData = new FormData();
    formData.append('session_id', state.currentSessionId);
    formData.append('scene_id', state.selectedScene.id);
    formData.append('final_script_text', scriptText);

    if (state.audioAnalysis) {
      formData.append('expression_prompt', state.audioAnalysis.expression_prompt || '');
      // FaceDetailer案B: 表情専念プロンプト
      if (state.audioAnalysis.expression_prompt_fd) {
        formData.append('expression_prompt_fd', state.audioAnalysis.expression_prompt_fd);
      }
      formData.append('expression_state', state.audioAnalysis.expression_state || 'BURNING');
      formData.append('emotion', state.audioAnalysis.emotion || 'NEUTRAL');
      formData.append('rms_db', String(state.audioAnalysis.rms_db || -12.0));
    }

    if (state.audioBlob) {
      formData.append('audio_file', state.audioBlob, 'voice.wav');
    }

    try {
      const resp = await fetch('/api/generate_scene', {
        method: 'POST',
        body: formData
      });

      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({}));
        throw new Error(errJson.detail || `HTTP ${resp.status}`);
      }

      const result = await resp.json();
      displayCompletedCard(result, scriptText);
      goToStep(5);
    } catch (err) {
      console.error('画像生成失敗:', err);
      showToast(`イラスト生成に失敗しました: ${err.message}`, 'error');
      goToStep(3);
    }
  });

  function simulateProgressSteps() {
    let pct = 10;
    el.generatingProgressFill.style.width = '10%';
    const interval = setInterval(() => {
      pct += Math.random() * 8;
      if (pct > 92) pct = 92;
      el.generatingProgressFill.style.width = `${pct}%`;
      if (state.currentStep !== 4) clearInterval(interval);
    }, 1500);
  }

  function displayCompletedCard(result, finalScript) {
    const cardData = {
      imageBase64: result.imageBase64,
      emotion: result.emotion || 'BURNING',
      scriptText: finalScript,
      title: state.selectedScene ? state.selectedScene.name : '覚醒の瞬間',
      metaDate: `${new Date().toLocaleDateString('ja-JP')} AI Creators Market`
    };
    state.cardHistory = [cardData];
    state.activeCardIndex = 0;
    renderCardHistory();
    updateCardDisplay(0);
  }

  function updateCardDisplay(index) {
    if (index < 0 || index >= state.cardHistory.length) return;
    state.activeCardIndex = index;
    const item = state.cardHistory[index];
    el.generatedCardImg.src = `data:image/png;base64,${item.imageBase64}`;
    el.cardEmotionBadge.textContent = item.emotion || 'BURNING';
    el.cardSceneTitle.textContent = item.title || (state.selectedScene ? state.selectedScene.name : '覚醒の瞬間');
    el.cardScriptText.textContent = item.scriptText;
    el.cardMetaDate.textContent = item.metaDate || `${new Date().toLocaleDateString('ja-JP')} AI Creators Market`;

    if (el.historyPageIndicator) {
      el.historyPageIndicator.textContent = `Ver. ${index + 1} / ${state.cardHistory.length}`;
    }
    if (el.btnHistoryPrev) {
      el.btnHistoryPrev.disabled = (index === 0);
    }
    if (el.btnHistoryNext) {
      el.btnHistoryNext.disabled = (index === state.cardHistory.length - 1);
    }

    // カルーセル中央揃えスライド ＆ アクティブ表示更新
    updateCarouselPosition(index);
  }

  function updateCarouselPosition(index) {
    if (!el.cardHistoryStrip) return;
    const thumbWidth = 210;
    const gap = 16;
    const viewportWidth = 440;

    // 選択されたサムネイルの中心がビューポート中心（220px）に一致するオフセット
    const targetX = (viewportWidth / 2) - (index * (thumbWidth + gap) + (thumbWidth / 2));
    el.cardHistoryStrip.style.transform = `translateX(${targetX}px)`;

    const thumbs = el.cardHistoryStrip.querySelectorAll('.history-thumb-item');
    thumbs.forEach((thumb, i) => {
      if (i === index) {
        thumb.classList.add('active');
      } else {
        thumb.classList.remove('active');
      }
    });
  }

  function renderCardHistory() {
    if (!el.cardHistoryStrip) return;
    el.cardHistoryStrip.innerHTML = '';
    state.cardHistory.forEach((item, idx) => {
      const thumb = document.createElement('div');
      thumb.className = `history-thumb-item ${idx === state.activeCardIndex ? 'active' : ''}`;
      thumb.title = `Ver. ${idx + 1}`;

      const badge = document.createElement('span');
      badge.className = 'history-thumb-badge';
      badge.textContent = `Ver. ${idx + 1}`;

      const img = document.createElement('img');
      img.src = `data:image/png;base64,${item.imageBase64}`;
      img.alt = `Ver. ${idx + 1}`;

      thumb.appendChild(badge);
      thumb.appendChild(img);

      thumb.addEventListener('click', () => {
        updateCardDisplay(idx);
      });

      el.cardHistoryStrip.appendChild(thumb);
    });

    if (el.historyPageIndicator) {
      el.historyPageIndicator.textContent = `Ver. ${state.activeCardIndex + 1} / ${state.cardHistory.length}`;
    }
    if (el.btnHistoryPrev) {
      el.btnHistoryPrev.disabled = (state.activeCardIndex === 0);
    }
    if (el.btnHistoryNext) {
      el.btnHistoryNext.disabled = (state.activeCardIndex === state.cardHistory.length - 1);
    }

    updateCarouselPosition(state.activeCardIndex);
  }

  if (el.btnHistoryPrev) {
    el.btnHistoryPrev.addEventListener('click', () => {
      if (state.activeCardIndex > 0) {
        updateCardDisplay(state.activeCardIndex - 1);
      }
    });
  }

  if (el.btnHistoryNext) {
    el.btnHistoryNext.addEventListener('click', () => {
      if (state.activeCardIndex < state.cardHistory.length - 1) {
        updateCardDisplay(state.activeCardIndex + 1);
      }
    });
  }

  if (el.btnRegenerateCard) {
    el.btnRegenerateCard.addEventListener('click', async () => {
      if (state.isRegenerating) return;
      if (!state.currentSessionId) {
        showToast('セッションが見つかりません。撮影からやり直してください。', 'error');
        return;
      }

      state.isRegenerating = true;
      const originalText = el.btnRegenerateCard.querySelector('span') ? el.btnRegenerateCard.querySelector('span').textContent : 'イラストを再生成';
      if (el.btnRegenerateCard.querySelector('span')) {
        el.btnRegenerateCard.querySelector('span').textContent = '再生成中...';
      }
      el.btnRegenerateCard.classList.add('loading');
      el.btnRegenerateCard.disabled = true;

      try {
        const fd = new FormData();
        fd.append('session_id', state.currentSessionId);
        const resp = await fetch('/api/regenerate_card', {
          method: 'POST',
          body: fd
        });

        if (!resp.ok) {
          const errJson = await resp.json().catch(() => ({}));
          throw new Error(errJson.detail || `HTTP ${resp.status}`);
        }

        const result = await resp.json();
        const baseItem = state.cardHistory[0] || {};
        const newCardData = {
          imageBase64: result.imageBase64,
          emotion: result.emotion || baseItem.emotion || 'BURNING',
          scriptText: result.script_text || baseItem.scriptText || '',
          title: baseItem.title || (state.selectedScene ? state.selectedScene.name : '覚醒の瞬間'),
          metaDate: `${new Date().toLocaleDateString('ja-JP')} AI Creators Market`
        };

        state.cardHistory.push(newCardData);
        renderCardHistory();
        updateCardDisplay(state.cardHistory.length - 1);
        showToast(`イラストを再生成しました (Ver. ${state.cardHistory.length})`, 'success');
      } catch (err) {
        console.error('イラスト再生成失敗:', err);
        showToast(`イラスト再生成に失敗しました: ${err.message}`, 'error');
      } finally {
        state.isRegenerating = false;
        el.btnRegenerateCard.classList.remove('loading');
        el.btnRegenerateCard.disabled = false;
        if (el.btnRegenerateCard.querySelector('span')) {
          el.btnRegenerateCard.querySelector('span').textContent = originalText;
        }
      }
    });
  }

  /**
   * Canon SELPHY L判（1050 × 1406 px, 300dpi換算）仕様のアートカード合成
   * 外側5%余白（左右53px, 上下70px）を濃紺 #10141e で塗り足し、
   * セーフエリア（944 × 1266 px）内にすべての要素（カード枠、正方形イラスト、文字等）を収容
   */
  async function generateArtCardCanvas() {
    // 1. 出力キャンバス仕様（Canon SELPHY L判 1050×1406px）
    const canvasWidth = 1050;
    const canvasHeight = 1406;

    // 2. セーフエリア（外側5%余白マージン）
    const marginX = 53; // 左右 53px (~5.0%)
    const marginY = 70; // 上下 70px (~5.0%)
    const safeWidth = 944;  // 1050 - 53 * 2
    const safeHeight = 1266; // 1406 - 70 * 2
    const safeX = marginX;
    const safeY = marginY;

    // 3. テキスト等の取得
    const sceneTitle = (el.cardSceneTitle && el.cardSceneTitle.textContent) || '覚醒の瞬間';
    const brandTitle = 'STORYWEAVER LIVE';
    const emotionBadge = (el.cardEmotionBadge && el.cardEmotionBadge.textContent) || '';
    const scriptText = (el.cardScriptText && el.cardScriptText.textContent) || '';
    const metaDate = (el.cardMetaDate && el.cardMetaDate.textContent) || `${new Date().toLocaleDateString('ja-JP')} AI Creators Market`;

    // 4. セーフエリア内部のレイアウト寸法計算
    const cardPaddingX = 24;
    const cardPaddingTop = 24;

    // 正方形イラスト（アスペクト比 1:1 を厳密保持）
    const imgSize = safeWidth - (cardPaddingX * 2); // 944 - 48 = 896px
    const imgX = safeX + cardPaddingX; // 53 + 24 = 77px
    const imgY = safeY + cardPaddingTop; // 70 + 24 = 94px

    // セリフ文字の折り返し計算
    const quoteFontSize = 24;
    const quoteLineHeight = 40;
    const quotePaddingX = 22;
    const quotePaddingY = 16;
    const accentLineWidth = 5;
    const quoteBoxX = imgX;
    const quoteBoxW = imgSize; // 896px
    const quoteContentWidth = quoteBoxW - (quotePaddingX * 2) - accentLineWidth;

    const measureCanvas = document.createElement('canvas');
    const mCtx = measureCanvas.getContext('2d');
    mCtx.font = `600 ${quoteFontSize}px "Noto Serif JP", "Yu Mincho", "Hiragino Mincho ProN", serif`;

    const lines = [];
    const rawParagraphs = scriptText.split('\n');
    for (const paragraph of rawParagraphs) {
      let currentLine = '';
      for (const char of paragraph) {
        const testLine = currentLine + char;
        if (mCtx.measureText(testLine).width > quoteContentWidth && currentLine.length > 0) {
          lines.push(currentLine);
          currentLine = char;
        } else {
          currentLine = testLine;
        }
      }
      if (currentLine.length > 0) {
        lines.push(currentLine);
      }
    }
    if (lines.length === 0) lines.push('');

    const quoteBoxHeight = (quotePaddingY * 2) + (lines.length * quoteLineHeight);

    // キャンバスの生成
    const canvas = document.createElement('canvas');
    canvas.width = canvasWidth;
    canvas.height = canvasHeight;
    const ctx = canvas.getContext('2d');

    // ① 全面（外側余白・塗り足し領域含む）を濃紺 #10141e で塗りつぶし
    ctx.fillStyle = '#10141e';
    ctx.fillRect(0, 0, canvasWidth, canvasHeight);

    // ② セーフエリア内のカード背景（直角四角形 ＆ ダークグラデーション）
    const grad = ctx.createLinearGradient(safeX, safeY, safeX + safeWidth, safeY + safeHeight);
    grad.addColorStop(0, '#181926');
    grad.addColorStop(1, '#0e0f17');
    ctx.fillStyle = grad;
    ctx.fillRect(safeX, safeY, safeWidth, safeHeight);

    // セーフエリア外枠境界線（直角 2px）
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.16)';
    ctx.lineWidth = 2;
    ctx.strokeRect(safeX, safeY, safeWidth, safeHeight);

    // ③ 生成画像をアスペクト比 1:1（896 × 896 px）で描画
    let currentY = imgY;
    if (el.generatedCardImg && el.generatedCardImg.src) {
      if (!el.generatedCardImg.complete || el.generatedCardImg.naturalWidth === 0) {
        await new Promise((resolve) => {
          el.generatedCardImg.onload = resolve;
          el.generatedCardImg.onerror = resolve;
        });
      }
      ctx.drawImage(el.generatedCardImg, imgX, currentY, imgSize, imgSize);

      // 感情バッジ（右上にオーバーレイ表示）
      if (emotionBadge) {
        ctx.save();
        const badgeFontSize = 18;
        ctx.font = `800 ${badgeFontSize}px "Inter", "Hiragino Sans", sans-serif`;
        const textMetrics = ctx.measureText(emotionBadge);
        const badgePadX = 18;
        const badgePadY = 8;
        const badgeW = textMetrics.width + badgePadX * 2;
        const badgeH = badgeFontSize + badgePadY * 2 + 4;
        const badgeX = imgX + imgSize - badgeW - 20;
        const badgeY = currentY + 20;

        ctx.fillStyle = 'rgba(0, 0, 0, 0.78)';
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.28)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        const r = badgeH / 2;
        if (ctx.roundRect) {
          ctx.roundRect(badgeX, badgeY, badgeW, badgeH, r);
        } else {
          ctx.rect(badgeX, badgeY, badgeW, badgeH);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(emotionBadge, badgeX + badgeW / 2, badgeY + badgeH / 2 + 1);
        ctx.restore();
      }
    }

    currentY += imgSize + 16; // 間隔 16px

    // ④ ヘッダー行（シーンタイトル ＋ ブランドロゴ）
    const headerHeight = 32;
    ctx.save();
    ctx.font = `700 26px "Hiragino Sans", "Meiryo", sans-serif`;
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(sceneTitle, imgX + 6, currentY + headerHeight / 2);

    ctx.font = `800 18px "Inter", sans-serif`;
    ctx.fillStyle = '#38bdf8'; // cyan
    ctx.textAlign = 'right';
    ctx.fillText(brandTitle, imgX + imgSize - 6, currentY + headerHeight / 2);
    ctx.restore();

    currentY += headerHeight + 14; // 間隔 14px

    // ⑤ セリフ引用ブロック
    ctx.save();
    ctx.fillStyle = 'rgba(255, 255, 255, 0.04)';
    ctx.fillRect(quoteBoxX, currentY, quoteBoxW, quoteBoxHeight);

    ctx.fillStyle = '#38bdf8';
    ctx.fillRect(quoteBoxX, currentY, accentLineWidth, quoteBoxHeight);

    ctx.font = `600 ${quoteFontSize}px "Noto Serif JP", "Yu Mincho", "Hiragino Mincho ProN", serif`;
    ctx.fillStyle = '#f1f5f9';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';

    let textY = currentY + quotePaddingY;
    for (let i = 0; i < lines.length; i++) {
      const lineStr = (i === 0 ? '“ ' : '  ') + lines[i] + (i === lines.length - 1 ? ' ”' : '');
      ctx.fillText(lineStr, quoteBoxX + quotePaddingX + accentLineWidth, textY);
      textY += quoteLineHeight;
    }
    ctx.restore();

    currentY += quoteBoxHeight + 14; // 間隔 14px

    // ⑥ フッター行（日付・イベント名、※Insta-IDは含めない）
    const footerHeight = 22;
    ctx.save();
    ctx.font = `500 18px "Hiragino Sans", "Meiryo", sans-serif`;
    ctx.fillStyle = '#94a3b8';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(metaDate, imgX + 6, currentY + footerHeight / 2);
    ctx.restore();

    return canvas;
  }

  el.btnDownloadCard.addEventListener('click', async () => {
    try {
      const canvas = await generateArtCardCanvas();
      canvas.toBlob((blob) => {
        if (!blob) {
          throw new Error('Canvas blob generation failed');
        }
        const link = document.createElement('a');
        const sceneId = (state.selectedScene && state.selectedScene.id) ? state.selectedScene.id : 'card';
        link.download = `StoryWeaver_${sceneId}_${Date.now()}.png`;
        link.href = URL.createObjectURL(blob);
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 1000);
        showToast('アートカードを保存しました', 'success');
      }, 'image/png');
    } catch (err) {
      console.error('Canvas card generation failed:', err);
      showToast('アートカード保存に失敗しました: ' + err.message, 'error');
    }
  });

  el.btnPrintCard.addEventListener('click', async () => {
    try {
      showToast('印刷データを準備中...', 'info');
      const canvas = await generateArtCardCanvas();
      const cardDataUrl = canvas.toDataURL('image/png');

      // 印刷用の一時非表示iframeを作成（メイン画面のCSSやDOM崩れを完全に排除）
      let printFrame = document.getElementById('storyweaver-print-frame');
      if (printFrame) {
        printFrame.remove();
      }

      printFrame = document.createElement('iframe');
      printFrame.id = 'storyweaver-print-frame';
      printFrame.style.position = 'fixed';
      printFrame.style.top = '-9999px';
      printFrame.style.left = '-9999px';
      printFrame.style.width = '1px';
      printFrame.style.height = '1px';
      printFrame.style.border = 'none';
      document.body.appendChild(printFrame);

      const frameDoc = printFrame.contentWindow.document;
      frameDoc.open();
      frameDoc.write(`<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>StoryWeaver Art Card</title>
  <style>
    @page {
      size: auto;
      margin: 10mm;
    }
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    html, body {
      width: 100%;
      height: 100%;
      background: #fff;
      display: flex;
      justify-content: center;
      align-items: center;
    }
    .print-container {
      width: 100%;
      height: 100%;
      display: flex;
      justify-content: center;
      align-items: center;
    }
    img.card-print-image {
      max-width: 100%;
      max-height: 100%;
      width: auto;
      height: auto;
      object-fit: contain;
      display: block;
      margin: auto;
    }
  </style>
</head>
<body>
  <div class="print-container">
    <img class="card-print-image" src="${cardDataUrl}" alt="StoryWeaver Art Card">
  </div>
</body>
</html>`);
      frameDoc.close();

      const printImg = frameDoc.querySelector('img.card-print-image');
      const triggerPrint = () => {
        setTimeout(() => {
          printFrame.contentWindow.focus();
          printFrame.contentWindow.print();
        }, 300);
      };

      if (printImg.complete) {
        triggerPrint();
      } else {
        printImg.onload = triggerPrint;
      }
    } catch (err) {
      console.error('Print card generation failed:', err);
      window.print();
    }
  });

  el.btnRestartExperience.addEventListener('click', () => {
    if (state.currentSessionId) {
      const fd = new FormData();
      fd.append('session_id', state.currentSessionId);
      fetch('/api/discard_session', { method: 'POST', body: fd }).catch(() => {});
    }
    state.currentSessionId = '';
    state.capturedBlob = null;
    state.croppedImageDataUrl = '';
    state.vlmPromise = null;
    state.vlmAnalysisDone = false;
    state.vlmError = null;
    state.audioBlob = null;
    state.audioAnalysis = null;
    state.cardHistory = [];
    state.activeCardIndex = 0;
    if (el.cardHistoryStrip) {
      el.cardHistoryStrip.innerHTML = '';
      el.cardHistoryStrip.style.transform = '';
    }
    if (el.historyPageIndicator) el.historyPageIndicator.textContent = 'Ver. 1 / 1';
    el.audioAnalysisResult.classList.add('hidden');
    if (el.step3CroppedThumbBox) el.step3CroppedThumbBox.classList.add('hidden');
    goToStep(1);
  });

  // =========================================================================
  // STAFF MODAL: Devices & Presets CRUD
  // =========================================================================
  el.btnOpenStaffSettings.addEventListener('click', () => {
    el.staffModal.classList.remove('hidden');
    refreshDeviceLists();
    loadWorkflows();
    refreshQwen2Status();
    startMicCalibration();
    renderAdminScenes();
  });

  el.btnCloseStaffModal.addEventListener('click', () => {
    el.staffModal.classList.add('hidden');
    stopMicCalibration();
  });

  // Tab switching
  document.querySelectorAll('.modal-tab').forEach(tabBtn => {
    tabBtn.addEventListener('click', () => {
      document.querySelectorAll('.modal-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      tabBtn.classList.add('active');
      const targetId = tabBtn.getAttribute('data-tab');
      document.getElementById(targetId).classList.add('active');
    });
  });

  async function refreshDeviceLists() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      el.selectCamera.innerHTML = '';
      el.selectMic.innerHTML = '';

      devices.forEach(dev => {
        if (dev.kind === 'videoinput') {
          const opt = document.createElement('option');
          opt.value = dev.deviceId;
          opt.textContent = dev.label || `カメラ (${el.selectCamera.options.length + 1})`;
          if (dev.deviceId === state.selectedCameraId) opt.selected = true;
          el.selectCamera.appendChild(opt);
        } else if (dev.kind === 'audioinput') {
          const opt = document.createElement('option');
          opt.value = dev.deviceId;
          opt.textContent = dev.label || `マイク (${el.selectMic.options.length + 1})`;
          if (dev.deviceId === state.selectedMicId) opt.selected = true;
          el.selectMic.appendChild(opt);
        }
      });
    } catch (e) {
      console.warn('デバイス一覧取得エラー:', e);
    }
  }

  el.selectCamera.addEventListener('change', (e) => {
    state.selectedCameraId = e.target.value;
    localStorage.setItem('storyweaver_camera_id', state.selectedCameraId);
    showToast('カメラデバイスを変更しました', 'success');
  });

  el.selectMic.addEventListener('change', (e) => {
    state.selectedMicId = e.target.value;
    localStorage.setItem('storyweaver_mic_id', state.selectedMicId);
    showToast('マイクデバイスを変更しました', 'success');
    startMicCalibration();
  });

  // Microphone Live Calibration
  async function startMicCalibration() {
    stopMicCalibration();
    try {
      const constraints = {
        audio: {
          deviceId: state.selectedMicId ? { exact: state.selectedMicId } : undefined,
          autoGainControl: false,
          noiseSuppression: false,
          echoCancellation: false
        },
        video: false
      };

      state.calibStream = await navigator.mediaDevices.getUserMedia(constraints);
      state.calibAudioContext = new (window.AudioContext || window.webkitAudioContext)();
      const source = state.calibAudioContext.createMediaStreamSource(state.calibStream);
      const analyser = state.calibAudioContext.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);

      const dataArray = new Float32Array(analyser.fftSize);

      function monitor() {
        state.calibAnimFrame = requestAnimationFrame(monitor);
        analyser.getFloatTimeDomainData(dataArray);

        // RMS 計算
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i] * dataArray[i];
        }
        const rms = Math.sqrt(sum / dataArray.length);
        const db = Math.max(-60, Math.min(0, 20 * Math.log10(rms + 1e-9)));

        // -60 dBFS = 0%, 0 dBFS = 100%
        const pct = Math.max(0, Math.min(100, ((db + 60) / 60) * 100));
        el.meterFill.style.width = `${pct}%`;
        el.meterCurrentDb.textContent = db.toFixed(1);

        if (db >= state.burningThreshold) {
          el.meterLiveVerdict.textContent = '🔥 BURNING 昇格!';
          el.meterLiveVerdict.className = 'verdict-tag verdict-burning';
        } else {
          el.meterLiveVerdict.textContent = 'COOL 判定';
          el.meterLiveVerdict.className = 'verdict-tag verdict-cool';
        }
      }
      monitor();
    } catch (e) {
      console.warn('キャリブレーションマイク開始エラー:', e);
    }
  }

  function stopMicCalibration() {
    if (state.calibAnimFrame) cancelAnimationFrame(state.calibAnimFrame);
    if (state.calibStream) {
      state.calibStream.getTracks().forEach(t => t.stop());
      state.calibStream = null;
    }
    if (state.calibAudioContext) {
      state.calibAudioContext.close();
      state.calibAudioContext = null;
    }
  }

  // Threshold Slider
  el.sliderBurningThreshold.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    el.sliderThresholdVal.textContent = val.toFixed(1);
    updateThresholdMarker(val);
  });

  function updateThresholdMarker(val) {
    // -60 to 0 scale
    const markerPct = Math.max(0, Math.min(100, ((val + 60) / 60) * 100));
    el.meterThresholdMarker.style.left = `${markerPct}%`;
    el.meterThresholdLabel.textContent = `${val.toFixed(1)} dBFS (閾値)`;
  }

  el.btnSaveThreshold.addEventListener('click', async () => {
    const newThresh = parseFloat(el.sliderBurningThreshold.value);
    try {
      const resp = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ BURNING_DB_THRESHOLD: newThresh })
      });
      if (resp.ok) {
        state.burningThreshold = newThresh;
        showToast(`閾値を ${newThresh} dBFS に保存しました`, 'success');
      }
    } catch (err) {
      showToast('設定の保存に失敗しました', 'error');
    }
  });

  // 感情分析モード変更イベント
  const EMOTION_MODE_LABELS = {
    standard: '標準高速モード (SenseVoice)',
    detailed_12: '物理音響プロトタイプモード (librosa 2階層8感情)',
    qwen2_audio_hybrid: 'Qwen2-Audio ハイブリッドモード (4bit Audio-LLM)'
  };

  if (el.selectEmotionMode) {
    el.selectEmotionMode.addEventListener('change', async (e) => {
      const newMode = e.target.value;
      try {
        const resp = await fetch('/api/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ emotion_mode: newMode })
        });
        if (resp.ok) {
          state.emotionMode = newMode;
          updateVoiceCheckVisibility();
          refreshQwen2Status();
          showToast(`感情分析モードを「${EMOTION_MODE_LABELS[newMode] || newMode}」に変更しました`, 'success');
        } else {
          const errData = await resp.json().catch(() => ({}));
          showToast(`モード変更失敗: ${errData.detail || resp.status}`, 'error');
        }
      } catch (err) {
        showToast('モード変更の保存に失敗しました', 'error');
      }
    });
  }

  // Step 1 スタンバイバー & スタッフ設定 VRAM ステータス更新
  function updateStandbyBarUI(data) {
    if (state.isStandbyLoading) return;
    const qwenLoaded = Boolean(data && data.is_loaded);
    const gemmaLoaded = Boolean(data && data.ollama_loaded);
    const totalVram = Number(data?.gpu_vram_total_used_mb || 0).toFixed(0);

    if (el.step1StandbyBar && el.step1StandbyDot && el.step1StandbyTitle && el.step1StandbySub && el.btnStep1Standby) {
      el.btnStep1Standby.disabled = false;
      if (qwenLoaded && gemmaLoaded) {
        el.step1StandbyBar.className = 'step1-standby-bar is-ready';
        el.step1StandbyDot.className = 'standby-status-dot is-ready';
        el.step1StandbyTitle.textContent = '✅ AIモデル スタンバイ完了（Gemma 4 e2b ＋ Qwen2-Audio VRAM常駐中）';
        el.step1StandbySub.textContent = `写真認識・音声分析をロード待ちなしで即座に開始できます（GPU VRAM: ${totalVram} MB）`;
        el.btnStep1Standby.className = 'btn btn-secondary btn-standby is-ready';
        if (el.step1StandbyIcon) el.step1StandbyIcon.textContent = '✓';
        if (el.step1StandbyLabel) el.step1StandbyLabel.textContent = 'スタンバイ完了 (再ロード/確認)';
        if (el.badgeSystemText) el.badgeSystemText.textContent = 'LLM Standby Ready';
      } else if (qwenLoaded || gemmaLoaded) {
        el.step1StandbyBar.className = 'step1-standby-bar';
        el.step1StandbyDot.className = 'standby-status-dot is-partial';
        const gLabel = gemmaLoaded ? 'ロード済' : '未ロード';
        const qLabel = qwenLoaded ? 'ロード済' : '未ロード';
        el.step1StandbyTitle.textContent = `⚡ AIモデル 一部ロード済（Gemma: ${gLabel} ／ Qwen2: ${qLabel}）`;
        el.step1StandbySub.textContent = `ボタンを押すと両モデルを VRAM に揃えてスタンバイします（GPU VRAM: ${totalVram} MB）`;
        el.btnStep1Standby.className = 'btn btn-secondary btn-standby';
        if (el.step1StandbyIcon) el.step1StandbyIcon.textContent = '⚡';
        if (el.step1StandbyLabel) el.step1StandbyLabel.textContent = 'AIモデルをスタンバイ (Gemma + Qwen2 事前ロード)';
        if (el.badgeSystemText) el.badgeSystemText.textContent = 'System Ready';
      } else {
        el.step1StandbyBar.className = 'step1-standby-bar';
        el.step1StandbyDot.className = 'standby-status-dot is-idle';
        el.step1StandbyTitle.textContent = 'AIモデル 未ロード（オンデマンド待機中）';
        el.step1StandbySub.textContent = '世界観を選んでいる間にボタンを押すと、Gemma 4 e2b と Qwen2-Audio を事前に VRAM へロードします';
        el.btnStep1Standby.className = 'btn btn-secondary btn-standby';
        if (el.step1StandbyIcon) el.step1StandbyIcon.textContent = '⚡';
        if (el.step1StandbyLabel) el.step1StandbyLabel.textContent = 'AIモデルをスタンバイ (Gemma + Qwen2 事前ロード)';
        if (el.badgeSystemText) el.badgeSystemText.textContent = 'System Ready';
      }
    }
  }

  // Qwen2-Audio & Gemma 4 e2b VRAM ステータス取得・手動アンロード
  async function refreshQwen2Status() {
    try {
      const resp = await fetch('/api/qwen2_audio/status');
      if (!resp.ok) return;
      const data = await resp.json();
      updateStandbyBarUI(data);
      if (el.qwen2VramStatus) {
        const gState = data.ollama_loaded ? `Gemma: ${Number(data.ollama_vram_used_mb || 0).toFixed(0)}MB` : 'Gemma: 0MB';
        if (data.is_loaded) {
          el.qwen2VramStatus.textContent = `状態: ロード済 (Qwen2: ${Number(data.vram_used_mb || 0).toFixed(0)} MB / ${gState} / GPU全体: ${Number(data.gpu_vram_total_used_mb || 0).toFixed(0)} MB)`;
          el.qwen2VramStatus.className = 'qwen2-vram-status is-loaded';
        } else {
          el.qwen2VramStatus.textContent = `状態: アンロード済 (Qwen2: 0 MB / ${gState} / GPU全体: ${Number(data.gpu_vram_total_used_mb || 0).toFixed(0)} MB)`;
          el.qwen2VramStatus.className = 'qwen2-vram-status is-unloaded';
        }
      }
    } catch (e) {
      console.warn('Qwen2-Audio ステータス取得失敗:', e);
    }
  }

  // Step 1 手動スタンバイボタン押下イベント (非ブロッキング実行)
  if (el.btnStep1Standby) {
    el.btnStep1Standby.addEventListener('click', async () => {
      if (state.isStandbyLoading) return;
      state.isStandbyLoading = true;
      el.btnStep1Standby.disabled = true;

      if (el.step1StandbyBar) el.step1StandbyBar.className = 'step1-standby-bar is-loading';
      if (el.step1StandbyDot) el.step1StandbyDot.className = 'standby-status-dot is-loading';
      if (el.step1StandbyIcon) el.step1StandbyIcon.textContent = '⏳';

      const t0 = Date.now();
      const updateTick = () => {
        const sec = ((Date.now() - t0) / 1000).toFixed(1);
        if (el.step1StandbyTitle) {
          el.step1StandbyTitle.textContent = `⏳ AIモデルを VRAM へロード中... (${sec}秒)`;
        }
        if (el.step1StandbySub) {
          el.step1StandbySub.textContent = 'Gemma 4 e2b と Qwen2-Audio を展開中です。このまま世界観を選んで次へ進めます！';
        }
        if (el.step1StandbyLabel) {
          el.step1StandbyLabel.textContent = `VRAM ロード中... (${sec}s)`;
        }
        if (el.badgeSystemText) {
          el.badgeSystemText.textContent = `⏳ LLM Loading (${sec}s)...`;
        }
      };
      updateTick();
      state.standbyTimer = setInterval(updateTick, 200);

      try {
        const resp = await fetch('/api/models/standby', { method: 'POST' });
        if (!resp.ok) {
          const errJson = await resp.json().catch(() => ({}));
          throw new Error(errJson.detail || `HTTP ${resp.status}`);
        }
        const data = await resp.json();
        state.isStandbyLoading = false;
        if (state.standbyTimer) {
          clearInterval(state.standbyTimer);
          state.standbyTimer = null;
        }
        updateStandbyBarUI(data);
        showToast(
          `✅ AIモデル スタンバイ完了 (Gemma + Qwen2 ロード済 / 所要 ${Number(data.elapsed_sec || 0).toFixed(1)}s)`,
          'success'
        );
      } catch (e) {
        console.error('モデルスタンバイ失敗:', e);
        state.isStandbyLoading = false;
        if (state.standbyTimer) {
          clearInterval(state.standbyTimer);
          state.standbyTimer = null;
        }
        await refreshQwen2Status();
        showToast(`AIモデルのスタンバイに失敗しました: ${e.message}`, 'error');
      }
    });
  }

  if (el.btnQwen2RefreshStatus) {
    el.btnQwen2RefreshStatus.addEventListener('click', () => {
      refreshQwen2Status();
    });
  }

  if (el.btnQwen2Unload) {
    el.btnQwen2Unload.addEventListener('click', async () => {
      el.btnQwen2Unload.disabled = true;
      try {
        const resp = await fetch('/api/qwen2_audio/unload', { method: 'POST' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        await refreshQwen2Status();
        if (data.was_loaded) {
          showToast(
            `🧹 Qwen2-Audio VRAM を解放しました (${Number(data.vram_before_mb || 0).toFixed(0)}MB ➔ ${Number(data.vram_after_mb || 0).toFixed(0)}MB)`,
            'success'
          );
        } else {
          showToast('Qwen2-Audio は既にアンロード済みです（VRAM 空き状態）', 'info');
        }
      } catch (e) {
        showToast(`VRAM 解放リクエストに失敗しました: ${e.message}`, 'error');
      } finally {
        el.btnQwen2Unload.disabled = false;
      }
    });
  }

  // ComfyUI ワークフロー一覧取得・選択変更イベント
  async function loadWorkflows() {
    if (!el.selectWorkflow) return;
    try {
      const resp = await fetch('/api/workflows');
      if (!resp.ok) return;
      const data = await resp.json();
      state.workflows = data.workflows || [];
      state.currentWorkflow = data.current_workflow || state.config.WORKFLOW_PATH || 'storyweaver_anime_api.json';

      el.selectWorkflow.innerHTML = '';
      state.workflows.forEach(wf => {
        const opt = document.createElement('option');
        opt.value = wf.filename;
        opt.textContent = wf.exists === false ? `${wf.label} (${wf.filename} - 未配置)` : `${wf.label} (${wf.filename})`;
        if (wf.exists === false) opt.disabled = true;
        if (wf.filename === state.currentWorkflow) opt.selected = true;
        el.selectWorkflow.appendChild(opt);
      });
    } catch (e) {
      console.warn('ワークフロー一覧取得失敗:', e);
    }
  }

  if (el.selectWorkflow) {
    el.selectWorkflow.addEventListener('change', async (e) => {
      const newWf = e.target.value;
      try {
        const resp = await fetch('/api/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ WORKFLOW_PATH: newWf })
        });
        if (resp.ok) {
          state.currentWorkflow = newWf;
          state.config.WORKFLOW_PATH = newWf;
          const wfObj = state.workflows.find(w => w.filename === newWf);
          const label = wfObj ? wfObj.label : newWf;
          showToast(`ComfyUI ワークフローを「${label}」に変更しました`, 'success');
        } else {
          const errData = await resp.json().catch(() => ({}));
          showToast(`ワークフロー変更失敗: ${errData.detail || resp.status}`, 'error');
        }
      } catch (err) {
        showToast('ワークフロー設定の保存に失敗しました', 'error');
      }
    });
  }

  function updateStaffModalValues() {
    el.sliderBurningThreshold.value = state.burningThreshold;
    el.sliderThresholdVal.textContent = state.burningThreshold.toFixed(1);
    updateThresholdMarker(state.burningThreshold);
    if (el.selectEmotionMode) {
      el.selectEmotionMode.value = state.emotionMode || 'standard';
    }
    if (el.selectWorkflow && state.config.WORKFLOW_PATH) {
      el.selectWorkflow.value = state.config.WORKFLOW_PATH;
    }
  }

  function updateVoiceCheckVisibility() {
    const show = isFlowMode();
    if (el.step3VoiceCheckBox) {
      el.step3VoiceCheckBox.classList.toggle('hidden', !show);
    }
    if (el.step3FlowGuide) {
      el.step3FlowGuide.classList.toggle('hidden', !show);
    }
  }

  function updateAnchorBadgesUI(anchorsStatus) {
    const st = anchorsStatus || { normal: false, power: false, whisper: false };
    const applyBadge = (badgeEl, label, isRegistered, isRequired) => {
      if (!badgeEl) return;
      if (isRegistered) {
        badgeEl.textContent = `${label}: 登録済 ✓`;
        badgeEl.className = 'vc-status-badge vc-badge-registered';
      } else if (isRequired) {
        badgeEl.textContent = `${label}: 未登録`;
        badgeEl.className = 'vc-status-badge vc-badge-unregistered';
      } else {
        badgeEl.textContent = `${label}: オプション`;
        badgeEl.className = 'vc-status-badge vc-badge-optional';
      }
    };

    applyBadge(el.step3BadgeNormal, '①棒読み', st.normal, true);
    applyBadge(el.step3BadgePower, '②張り声', st.power, false);
    applyBadge(el.step3BadgeWhisper, '③ささやき', st.whisper, false);

    applyBadge(el.staffBadgeNormal, '①棒読み', st.normal, true);
    applyBadge(el.staffBadgePower, '②張り声', st.power, false);
    applyBadge(el.staffBadgeWhisper, '③ささやき', st.whisper, false);

    if (el.step3VcReadyMsg) {
      if (st.normal) {
        el.step3VcReadyMsg.classList.remove('hidden');
      } else {
        el.step3VcReadyMsg.classList.add('hidden');
      }
    }
  }

  // 棒読みベースライン＆3点アンカー情報の取得と描画
  async function loadBaselineStatus() {
    try {
      const resp = await fetch('/api/voice_emo_baseline');
      if (!resp.ok) return;
      const data = await resp.json();
      state.baselineData = data.baseline || {};

      const count = state.baselineData.samples_count || 0;
      const anchors = state.baselineData.anchors || {};
      const anchorsStatus = state.baselineData.anchors_status || {
        normal: count > 0,
        power: Boolean(anchors.power),
        whisper: Boolean(anchors.whisper)
      };

      updateAnchorBadgesUI(anchorsStatus);

      if (el.baselineStatusText) {
        if (anchorsStatus.normal) {
          const extra = [
            anchorsStatus.power ? '②張り声' : null,
            anchorsStatus.whisper ? '③ささやき' : null
          ].filter(Boolean);
          el.baselineStatusText.textContent = extra.length > 0
            ? `登録済み (①基準 ＋ ${extra.join('・')})`
            : `登録済み (①棒読み基準のみ / ${count} サンプル)`;
          el.baselineStatusText.className = 'text-success';
        } else {
          el.baselineStatusText.textContent = '標準初期値を使用中 (未登録)';
          el.baselineStatusText.className = 'text-warning';
        }
      }

      if (el.baselineUpdatedAt) {
        if (state.baselineData.calibrated_at) {
          const d = new Date(state.baselineData.calibrated_at);
          el.baselineUpdatedAt.textContent = `最終更新: ${d.toLocaleString('ja-JP')}`;
        } else {
          el.baselineUpdatedAt.textContent = '最終更新: 初期値';
        }
      }

      if (el.baselinePreviewChips) {
        el.baselinePreviewChips.innerHTML = '';
        const keys = [
          ['rms_p90_db', 'RMS(dB)', 2],
          ['f0_median_hz', 'F0(Hz)', 1],
          ['hnr_db', 'HNR(dB)', 2],
          ['breath_ratio', 'Breath', 4],
          ['jitter', 'Jitter', 4],
          ['shimmer', 'Shimmer', 3]
        ];
        keys.forEach(([k, label, digits]) => {
          if (state.baselineData[k] !== undefined) {
            const chip = document.createElement('span');
            chip.className = 'b-chip';
            chip.textContent = `①${label}: ${Number(state.baselineData[k]).toFixed(digits)}`;
            el.baselinePreviewChips.appendChild(chip);
          }
        });
        if (anchors.power && anchors.power.rms_p90_db !== undefined) {
          const chip = document.createElement('span');
          chip.className = 'b-chip b-chip-power';
          chip.textContent = `②Power RMS: ${Number(anchors.power.rms_p90_db).toFixed(1)}dB / F0: ${Number(anchors.power.f0_median_hz || 0).toFixed(0)}Hz`;
          el.baselinePreviewChips.appendChild(chip);
        }
        if (anchors.whisper && anchors.whisper.rms_p90_db !== undefined) {
          const chip = document.createElement('span');
          chip.className = 'b-chip b-chip-whisper';
          chip.textContent = `③Whisper RMS: ${Number(anchors.whisper.rms_p90_db).toFixed(1)}dB / Breath: ${Number(anchors.whisper.breath_ratio || 0).toFixed(3)}`;
          el.baselinePreviewChips.appendChild(chip);
        }
      }
    } catch (e) {
      console.warn('ベースライン情報取得失敗:', e);
    }
  }

  // 3点ボイスチェック（normal / power / whisper）開始・停止トグル録音（最大6.0秒で自動停止）
  const CALIB_MODE_META = {
    normal: { num: '①', name: '棒読み（基準）', btnDefault: '🎙 ① 棒読みを録音開始' },
    power: { num: '②', name: '張った声（上限）', btnDefault: '🎙 ② 張った声を録音開始' },
    whisper: { num: '③', name: 'ささやき声（吐息）', btnDefault: '🎙 ③ ささやき声を録音開始' }
  };

  function setCalibProgressUI(visible, text) {
    [
      [el.step3CalibProgress, el.step3CalibProgressText],
      [el.baselineRecordProgress, el.baselineProgressText]
    ].forEach(([box, txt]) => {
      if (!box) return;
      if (visible) box.classList.remove('hidden');
      else box.classList.add('hidden');
      if (txt && text !== undefined) txt.textContent = text;
    });
  }

  function updateCalibButtonsUI(activeMode, elapsedSec = 0) {
    document.querySelectorAll('.btn-calib-toggle').forEach(btn => {
      const m = btn.getAttribute('data-calib-mode') || 'normal';
      const meta = CALIB_MODE_META[m] || CALIB_MODE_META.normal;
      const defaultLabel = btn.getAttribute('data-label-default') || meta.btnDefault;
      const labelEl = btn.querySelector('.btn-calib-label') || btn;
      if (activeMode === m) {
        btn.disabled = false;
        btn.classList.add('recording');
        labelEl.textContent = `⏹ 停止して登録 (録音中 ${elapsedSec.toFixed(1)}s)`;
      } else if (activeMode) {
        btn.disabled = true;
        btn.classList.remove('recording');
        labelEl.textContent = defaultLabel;
      } else {
        btn.disabled = false;
        btn.classList.remove('recording');
        labelEl.textContent = defaultLabel;
      }
    });
  }

  async function toggleCalibrationRecording(mode) {
    const modeKey = (mode || 'normal').toLowerCase();
    if (state.isRecordingBaseline) {
      if (state.calibRecordingMode === modeKey) {
        await stopAndSubmitCalibration();
      }
      return;
    }
    await startCalibrationRecording(modeKey);
  }

  async function startCalibrationRecording(modeKey) {
    const meta = CALIB_MODE_META[modeKey] || CALIB_MODE_META.normal;
    state.isRecordingBaseline = true;
    state.calibRecordingMode = modeKey;

    try {
      const constraints = {
        audio: {
          deviceId: state.selectedMicId ? { exact: state.selectedMicId } : undefined,
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
        if (!state.isRecordingBaseline) return;
        chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      };

      source.connect(recorderNode);
      recorderNode.connect(audioCtx.destination);

      const startTime = Date.now();
      updateCalibButtonsUI(modeKey, 0.0);
      setCalibProgressUI(true, `${meta.num}${meta.name} を録音中... 0.0秒（もう一度押すと停止・最大6.0秒）`);
      if (modeKey === 'normal') {
        setFlowBaselineState('recording', '');
      }

      const timer = setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000;
        updateCalibButtonsUI(modeKey, elapsed);
        setCalibProgressUI(true, `${meta.num}${meta.name} を録音中... ${elapsed.toFixed(1)}秒（もう一度押すと停止・最大6.0秒）`);
      }, 100);

      const autoStopTimeout = setTimeout(() => {
        if (state.isRecordingBaseline && state.calibRecordingMode === modeKey) {
          stopAndSubmitCalibration();
        }
      }, 6000);

      state.calibRecSession = {
        modeKey,
        stream,
        audioCtx,
        source,
        recorderNode,
        chunks,
        timer,
        autoStopTimeout
      };
    } catch (err) {
      console.error('ボイスチェック録音開始失敗:', err);
      showToast(`マイクの初期化に失敗しました: ${err.message}`, 'error');
      state.isRecordingBaseline = false;
      state.calibRecordingMode = null;
      state.calibRecSession = null;
      updateCalibButtonsUI(null);
      setCalibProgressUI(false, '');
    }
  }

  async function stopAndSubmitCalibration() {
    const sess = state.calibRecSession;
    if (!sess) return;
    state.calibRecSession = null;

    clearInterval(sess.timer);
    clearTimeout(sess.autoStopTimeout);

    const { modeKey, stream, audioCtx, source, recorderNode, chunks } = sess;
    const meta = CALIB_MODE_META[modeKey] || CALIB_MODE_META.normal;

    try {
      recorderNode.disconnect();
      source.disconnect();
      stream.getTracks().forEach(t => t.stop());
      await audioCtx.close();
    } catch (e) {
      console.warn('audioCtx close warning:', e);
    }

    document.querySelectorAll('.btn-calib-toggle').forEach(b => { b.disabled = true; });
    setCalibProgressUI(true, `${meta.num}${meta.name} の特徴量を解析・登録中...`);

    try {
      const wavBlob = encodeFloat32ToWav(chunks, 16000);
      const formData = new FormData();
      formData.append('audio_file', wavBlob, `calib_${modeKey}.wav`);
      formData.append('mode', modeKey);

      const resp = await fetch('/api/calibrate_voice_emo', {
        method: 'POST',
        body: formData
      });

      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({}));
        throw new Error(errJson.detail || `HTTP ${resp.status}`);
      }

      const calibRes = await resp.json();
      if (modeKey === 'normal') {
        const raw = calibRes.raw_features || {};
        const base = calibRes.baseline || {};
        const f0 = Number(raw.f0_median_hz ?? base.f0_median_hz ?? 0);
        const rms = Number(raw.rms_p90_db ?? base.rms_p90_db ?? 0);
        state.flowBaselineDone = true;
        setFlowBaselineState(
          'done',
          `<span class="flow-baseline-badge">✅ あなたの声の基準（ベースライン）を登録しました（F0: ${f0.toFixed(1)}Hz / 声量: ${rms.toFixed(1)}dB）</span>`
        );
        showToast('✓ ①棒読み（基準50pt）を登録しました！本番セリフへ進めます', 'success');
      } else {
        showToast(`✓ ${meta.num}${meta.name} アンカーを登録しました！`, 'success');
      }
      await loadBaselineStatus();

      // すでにStep 3で本番セリフが録音済みの場合は新しい基準で自動再解析
      if (state.audioBlob && isFlowMode()) {
        await postAnalyzeAudio(state.audioBlob);
      }
    } catch (err) {
      console.error('ボイスチェック登録失敗:', err);
      showToast(`ボイスチェック登録に失敗しました: ${err.message}`, 'error');
      if (modeKey === 'normal' && !state.flowBaselineDone) {
        setFlowBaselineState('pending', '');
      }
    } finally {
      state.isRecordingBaseline = false;
      state.calibRecordingMode = null;
      updateCalibButtonsUI(null);
      setCalibProgressUI(false, '');
    }
  }

  document.querySelectorAll('.btn-calib-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.getAttribute('data-calib-mode') || 'normal';
      toggleCalibrationRecording(mode);
    });
  });

  // Scene Presets CRUD
  function renderAdminScenes() {
    el.adminScenesList.innerHTML = '';
    state.presets.forEach((scene, idx) => {
      if (scene.scene_neg_prompt === undefined) {
        scene.scene_neg_prompt = '';
      }
      const item = document.createElement('div');
      item.className = 'admin-scene-item';
      item.innerHTML = `
        <div class="admin-scene-row">
          <input type="text" class="form-input scene-id-input" value="${escapeHtml(scene.id)}" placeholder="ID" style="width: 120px;" readonly>
          <input type="text" class="form-input scene-name-input" value="${escapeHtml(scene.name)}" placeholder="シーン名" style="flex: 1;">
          <button class="btn btn-glass btn-small btn-del-scene" data-idx="${idx}" style="color: #f87171;">削除</button>
        </div>
        <input type="text" class="form-input scene-script-input" value="${escapeHtml(scene.script_text)}" placeholder="事前セリフ">
        <textarea class="form-input scene-prompt-input" rows="2" placeholder="背景・世界観プロンプト (Pos)">${escapeHtml(scene.scene_prompt)}</textarea>
        <textarea class="form-input scene-neg-prompt-input" rows="2" placeholder="シーン別ネガティブプロンプト (Nega) 例: modern buildings, weapons（空欄時は共通ネガティブのみ適用）">${escapeHtml(scene.scene_neg_prompt || '')}</textarea>
      `;

      item.querySelector('.btn-del-scene').addEventListener('click', () => {
        state.presets.splice(idx, 1);
        renderAdminScenes();
      });

      // 入力変更の反映
      item.querySelector('.scene-name-input').addEventListener('input', (e) => scene.name = e.target.value);
      item.querySelector('.scene-script-input').addEventListener('input', (e) => scene.script_text = e.target.value);
      item.querySelector('.scene-prompt-input').addEventListener('input', (e) => scene.scene_prompt = e.target.value);
      item.querySelector('.scene-neg-prompt-input').addEventListener('input', (e) => scene.scene_neg_prompt = e.target.value);

      el.adminScenesList.appendChild(item);
    });
  }

  el.btnAddNewScene.addEventListener('click', () => {
    const newId = `scene_${(state.presets.length + 1).toString().padStart(2, '0')}`;
    state.presets.push({
      id: newId,
      name: '新しいシーン',
      script_text: 'セリフを入力してください',
      scene_prompt: 'masterpiece anime scenery',
      scene_neg_prompt: ''
    });
    renderAdminScenes();
  });

  el.btnSaveAllPresets.addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/presets', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenes: state.presets })
      });
      if (resp.ok) {
        showToast('シーン一覧を保存・反映しました', 'success');
        renderScenesGrid();
      }
    } catch (e) {
      showToast('シーン一覧の保存に失敗しました', 'error');
    }
  });

  function updateSystemInfo(health) {
    if (health.sensevoice_loaded) {
      el.infoSensevoice.textContent = 'CPU Ready (VRAM 0MB)';
    }
    el.infoSessionsCount.textContent = health.sessions || 0;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>"']/g, m => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
    })[m]);
  }

  // Initialize
  window.addEventListener('DOMContentLoaded', () => {
    loadInitialData();
  });

})();
