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
    baselineData: null,
    isRecordingBaseline: false
  };

  // DOM Elements
  const el = {
    scenesGrid: document.getElementById('scenes-grid'),
    video: document.getElementById('camera-video'),
    canvas: document.getElementById('camera-canvas'),
    snapshotPreview: document.getElementById('camera-snapshot-preview'),
    guideOverlay: document.getElementById('guide-overlay'),
    btnSwitchCamera: document.getElementById('btn-switch-camera'),
    btnTakePhoto: document.getElementById('btn-take-photo'),
    btnRetakePhoto: document.getElementById('btn-retake-photo'),
    btnConfirmPhoto: document.getElementById('btn-confirm-photo'),
    cameraReviewActions: document.getElementById('camera-review-actions'),
    cameraCountdown: document.getElementById('camera-countdown'),
    vlmBanner: document.getElementById('vlm-status-banner'),
    vlmBannerText: document.getElementById('vlm-banner-text'),
    currentSceneChip: document.getElementById('current-scene-chip'),
    btnRecordToggle: document.getElementById('btn-record-toggle'),
    recordStatusLabel: document.getElementById('record-status-label'),
    recordTimer: document.getElementById('record-timer'),
    audioVisCanvas: document.getElementById('audio-visualizer-canvas'),
    audioAnalysisResult: document.getElementById('audio-analysis-result'),
    resultStandardContainer: document.getElementById('result-standard-container'),
    resultDetailedContainer: document.getElementById('result-detailed-container'),
    emotionBadge: document.getElementById('emotion-badge'),
    emotionBadgeIcon: document.getElementById('emotion-badge-icon'),
    emotionBadgeLabel: document.getElementById('emotion-badge-label'),
    analysisRmsText: document.getElementById('analysis-rms-text'),
    analysisThresholdTag: document.getElementById('analysis-threshold-tag'),
    // 12感情UI要素
    detailedAnalysisTime: document.getElementById('detailed-analysis-time'),
    top1Score: document.getElementById('top1-score'),
    top1Icon: document.getElementById('top1-icon'),
    top1Name: document.getElementById('top1-name'),
    top1Bar: document.getElementById('top1-bar'),
    top2Score: document.getElementById('top2-score'),
    top2Icon: document.getElementById('top2-icon'),
    top2Name: document.getElementById('top2-name'),
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
    // Staff modal
    staffModal: document.getElementById('staff-modal'),
    btnOpenStaffSettings: document.getElementById('btn-open-staff-settings'),
    btnCloseStaffModal: document.getElementById('btn-close-staff-modal'),
    selectCamera: document.getElementById('select-camera'),
    selectMic: document.getElementById('select-mic'),
    selectEmotionMode: document.getElementById('select-emotion-mode'),
    meterFill: document.getElementById('meter-fill'),
    meterThresholdMarker: document.getElementById('meter-threshold-marker'),
    meterThresholdLabel: document.getElementById('meter-threshold-label'),
    meterCurrentDb: document.getElementById('meter-current-db'),
    meterLiveVerdict: document.getElementById('meter-live-verdict'),
    sliderBurningThreshold: document.getElementById('slider-burning-threshold'),
    sliderThresholdVal: document.getElementById('slider-threshold-val'),
    btnSaveThreshold: document.getElementById('btn-save-threshold'),
    // 棒読みベースライン要素
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
    if (stepNum === 2) {
      startCamera();
    } else {
      stopCamera();
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
      updateSystemInfo(healthRes);
      loadBaselineStatus();
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
    el.video.classList.remove('hidden');
    el.snapshotPreview.classList.add('hidden');
    el.guideOverlay.classList.remove('hidden');
    el.btnTakePhoto.classList.remove('hidden');
    el.btnSwitchCamera.classList.remove('hidden');
    el.cameraReviewActions.classList.add('hidden');
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

    canvas.toBlob(blob => {
      state.capturedBlob = blob;
      el.snapshotPreview.src = URL.createObjectURL(blob);
      el.video.classList.add('hidden');
      el.guideOverlay.classList.add('hidden');
      el.snapshotPreview.classList.remove('hidden');
      el.btnTakePhoto.classList.add('hidden');
      el.btnSwitchCamera.classList.add('hidden');
      el.cameraReviewActions.classList.remove('hidden');
    }, 'image/jpeg', 0.95);
  }

  el.btnRetakePhoto.addEventListener('click', () => {
    resetCameraPreview();
  });

  el.btnConfirmPhoto.addEventListener('click', () => {
    if (!state.capturedBlob) return;

    // 新規セッションIDを発行
    state.currentSessionId = 'sw_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    state.vlmAnalysisDone = false;
    state.vlmError = null;

    // バックグラウンドで POST /api/analyze_face 送信
    startVlmAnalysis(state.currentSessionId, state.capturedBlob);

    // ステップ3へ即座に進行
    goToStep(3);
  });

  async function startVlmAnalysis(sessionId, imageBlob) {
    el.vlmBanner.classList.remove('hidden');
    el.vlmBanner.style.borderColor = 'rgba(139, 92, 246, 0.4)';
    el.vlmBannerText.textContent = '裏側であなたの外見特徴（髪型・生え際・眼鏡）をAI解析中...';

    const formData = new FormData();
    formData.append('face_image', imageBlob, 'capture.jpg');
    formData.append('session_id', sessionId);

    state.vlmPromise = (async () => {
      try {
        const resp = await fetch('/api/analyze_face', {
          method: 'POST',
          body: formData
        });

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
        state.vlmAnalysisDone = true;
        state.vlmError = null;
        el.vlmBannerText.textContent = `✓ 外見抽出完了: ${res.gender_tag}, ${res.physical_traits || '標準'}`;
        setTimeout(() => {
          if (state.vlmAnalysisDone) {
            el.vlmBanner.classList.add('hidden');
          }
        }, 4000);
        return true;
      } catch (err) {
        console.error('VLM 解析エラー:', err);
        state.vlmError = err.message;
        state.vlmAnalysisDone = false;
        el.vlmBanner.style.borderColor = '#ef4444';
        el.vlmBannerText.innerHTML = `⚠️ 外見解析エラー: ${escapeHtml(err.message)} <button id="btn-retry-vlm" class="btn btn-small btn-glass" style="margin-left:8px;padding:2px 8px;">再試行</button>`;
        const btnRetry = document.getElementById('btn-retry-vlm');
        if (btnRetry) {
          btnRetry.addEventListener('click', (e) => {
            e.stopPropagation();
            startVlmAnalysis(state.currentSessionId, state.capturedBlob);
          });
        }
        return false;
      }
    })();

    return state.vlmPromise;
  }

  function handleFaceNotDetected() {
    el.faceAlertModal.classList.remove('hidden');
  }

  el.btnAlertRetry.addEventListener('click', () => {
    el.faceAlertModal.classList.add('hidden');
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
    goToStep(2);
  });

  el.btnRecordToggle.addEventListener('click', () => {
    if (state.isRecording) {
      stopRecording();
    } else {
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
      if (data.emotion_mode === 'detailed_12') {
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
    } catch (err) {
      console.error('analyze_audio 失敗:', err);
      el.recordStatusLabel.textContent = '音声解析に失敗しました。再録音または手動入力してください';
    }
  }

  // 従来モード用バッジ描画
  function renderEmotionStandard(category, rmsDb) {
    el.audioAnalysisResult.classList.remove('hidden');
    el.resultDetailedContainer.classList.add('hidden');
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

  // 詳細12感情・色気モード用描画
  function renderEmotionDetailed(data) {
    el.audioAnalysisResult.classList.remove('hidden');
    el.resultStandardContainer.classList.add('hidden');
    el.resultDetailedContainer.classList.remove('hidden');

    const top1 = data.primary_emotion;
    const top2 = data.secondary_emotion;

    // Top-1
    el.top1Score.textContent = top1.score.toFixed(1);
    el.top1Icon.textContent = top1.icon;
    el.top1Name.textContent = top1.name_ja;
    el.top1Bar.style.width = `${Math.min(100, Math.max(0, top1.score))}%`;

    // Top-2
    el.top2Score.textContent = top2.score.toFixed(1);
    el.top2Icon.textContent = top2.icon;
    el.top2Name.textContent = top2.name_ja;
    el.top2Bar.style.width = `${Math.min(100, Math.max(0, top2.score))}%`;

    // 解析時間
    if (el.detailedAnalysisTime && data.analysis_time_sec) {
      el.detailedAnalysisTime.textContent = `${data.analysis_time_sec}s`;
    }

    // 7基礎指標グリッド
    if (el.f7MetricsGrid && data.features_7) {
      el.f7MetricsGrid.innerHTML = '';
      const f7Labels = {
        valence: '快・ポジティブ',
        arousal: '覚醒・熱量',
        dominance: '支配・力強さ',
        breathiness: '吐息・息漏れ',
        softness: '声の柔らかさ',
        slowness: '余韻・ゆったり',
        tremor: '微細な揺らぎ'
      };
      for (const [k, v] of Object.entries(data.features_7)) {
        const item = document.createElement('div');
        item.className = 'f7-item';
        item.innerHTML = `
          <span class="f7-label">${f7Labels[k] || k}</span>
          <span class="f7-val">${v.toFixed(1)} pt</span>
        `;
        el.f7MetricsGrid.appendChild(item);
      }
    }

    // 12感情一覧リスト
    if (el.e12MetricsList && data.emotions_12) {
      el.e12MetricsList.innerHTML = '';
      const sorted = Object.entries(data.emotions_12).sort((a, b) => b[1] - a[1]);
      sorted.forEach(([emoId, score]) => {
        const row = document.createElement('div');
        row.className = 'e12-row';
        const isTop = (emoId === top1.id || emoId === top2.id);
        const nameDisp = (emoId === top1.id) ? `${top1.icon} ${top1.name_ja}` :
                         (emoId === top2.id) ? `${top2.icon} ${top2.name_ja}` : emoId;
        row.innerHTML = `
          <span class="e12-name" style="${isTop ? 'color: #f472b6; font-weight: 700;' : ''}">${nameDisp}</span>
          <div class="e12-track">
            <div class="e12-fill" style="width: ${Math.min(100, Math.max(0, score))}%; ${isTop ? 'background: linear-gradient(90deg, #ec4899, #f43f5e);' : ''}"></div>
          </div>
          <span class="e12-val">${score.toFixed(1)} pt</span>
        `;
        el.e12MetricsList.appendChild(row);
      });
    }

    // 生成中タグおよびアートカード準備
    el.generatingEmotionTag.textContent = `${top1.icon} ${top1.name_ja} (${top1.score}pt) × ${top2.icon} ${top2.name_ja} (${top2.score}pt)`;
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
    el.generatedCardImg.src = `data:image/png;base64,${result.imageBase64}`;
    el.cardEmotionBadge.textContent = result.emotion || 'BURNING';
    el.cardSceneTitle.textContent = state.selectedScene ? state.selectedScene.name : '覚醒の瞬間';
    el.cardScriptText.textContent = finalScript;
    el.cardMetaDate.textContent = `${new Date().toLocaleDateString('ja-JP')} AI Creators Market`;
  }

  el.btnDownloadCard.addEventListener('click', () => {
    const link = document.createElement('a');
    link.download = `StoryWeaver_${state.selectedScene.id}_${Date.now()}.png`;
    link.href = el.generatedCardImg.src;
    link.click();
  });

  el.btnPrintCard.addEventListener('click', () => {
    window.print();
  });

  el.btnRestartExperience.addEventListener('click', () => {
    state.capturedBlob = null;
    state.audioBlob = null;
    state.audioAnalysis = null;
    el.audioAnalysisResult.classList.add('hidden');
    goToStep(1);
  });

  // =========================================================================
  // STAFF MODAL: Devices & Presets CRUD
  // =========================================================================
  el.btnOpenStaffSettings.addEventListener('click', () => {
    el.staffModal.classList.remove('hidden');
    refreshDeviceLists();
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
          showToast(`感情分析モードを「${newMode === 'detailed_12' ? '詳細12感情モード' : '従来モード'}」に変更しました`, 'success');
        }
      } catch (err) {
        showToast('モード変更の保存に失敗しました', 'error');
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
  }

  // 棒読みベースライン情報の取得と描画
  async function loadBaselineStatus() {
    try {
      const resp = await fetch('/api/voice_emo_baseline');
      if (!resp.ok) return;
      const data = await resp.json();
      state.baselineData = data.baseline || {};

      if (el.baselineStatusText) {
        const count = state.baselineData.samples_count || 0;
        if (count > 0) {
          el.baselineStatusText.textContent = `登録済み (${count} サンプル)`;
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
          ['valence', 'Valence'],
          ['arousal', 'Arousal'],
          ['logRelF0-H1-H2', 'H1-H2'],
          ['alphaRatioV', 'AlphaRatio'],
          ['jitterLocal', 'Jitter']
        ];
        keys.forEach(([k, label]) => {
          if (state.baselineData[k] !== undefined) {
            const chip = document.createElement('span');
            chip.className = 'b-chip';
            chip.textContent = `${label}: ${Number(state.baselineData[k]).toFixed(2)}`;
            el.baselinePreviewChips.appendChild(chip);
          }
        });
      }
    } catch (e) {
      console.warn('ベースライン情報取得失敗:', e);
    }
  }

  // 棒読みベースライン録音 (3.5秒)
  if (el.btnRecordBaseline) {
    el.btnRecordBaseline.addEventListener('click', async () => {
      if (state.isRecordingBaseline) return;
      state.isRecordingBaseline = true;

      el.btnRecordBaseline.disabled = true;
      el.baselineRecordProgress.classList.remove('hidden');

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

        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const source = audioCtx.createMediaStreamSource(stream);
        const recorderNode = audioCtx.createScriptProcessor(4096, 1, 1);

        const chunks = [];
        recorderNode.onaudioprocess = (e) => {
          chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
        };

        source.connect(recorderNode);
        recorderNode.connect(audioCtx.destination);

        // カウントダウン
        let remain = 3.5;
        const timer = setInterval(() => {
          remain -= 0.5;
          if (remain > 0) {
            el.baselineProgressText.textContent = `録音中... 残り ${remain.toFixed(1)} 秒 (棒読みで発声)`;
          } else {
            clearInterval(timer);
          }
        }, 500);

        await new Promise(r => setTimeout(r, 3500));

        // 停止
        recorderNode.disconnect();
        source.disconnect();
        stream.getTracks().forEach(t => t.stop());
        await audioCtx.close();

        el.baselineProgressText.textContent = '特徴量を解析・登録中...';

        const wavBlob = encodeFloat32ToWav(chunks, 16000);
        const formData = new FormData();
        formData.append('audio_file', wavBlob, 'baseline.wav');

        const resp = await fetch('/api/calibrate_voice_emo', {
          method: 'POST',
          body: formData
        });

        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }

        const resData = await resp.json();
        showToast('棒読み基準値（ベースライン）を正常に更新しました！', 'success');
        await loadBaselineStatus();
      } catch (err) {
        console.error('ベースライン録音失敗:', err);
        showToast(`ベースライン登録に失敗しました: ${err.message}`, 'error');
      } finally {
        state.isRecordingBaseline = false;
        el.btnRecordBaseline.disabled = false;
        el.baselineRecordProgress.classList.add('hidden');
      }
    });
  }

  // Scene Presets CRUD
  function renderAdminScenes() {
    el.adminScenesList.innerHTML = '';
    state.presets.forEach((scene, idx) => {
      const item = document.createElement('div');
      item.className = 'admin-scene-item';
      item.innerHTML = `
        <div class="admin-scene-row">
          <input type="text" class="form-input scene-id-input" value="${escapeHtml(scene.id)}" placeholder="ID" style="width: 120px;" readonly>
          <input type="text" class="form-input scene-name-input" value="${escapeHtml(scene.name)}" placeholder="シーン名" style="flex: 1;">
          <button class="btn btn-glass btn-small btn-del-scene" data-idx="${idx}" style="color: #f87171;">削除</button>
        </div>
        <input type="text" class="form-input scene-script-input" value="${escapeHtml(scene.script_text)}" placeholder="事前セリフ">
        <textarea class="form-input scene-prompt-input" rows="2" placeholder="事前プロンプト">${escapeHtml(scene.scene_prompt)}</textarea>
      `;

      item.querySelector('.btn-del-scene').addEventListener('click', () => {
        state.presets.splice(idx, 1);
        renderAdminScenes();
      });

      // 入力変更の反映
      item.querySelector('.scene-name-input').addEventListener('input', (e) => scene.name = e.target.value);
      item.querySelector('.scene-script-input').addEventListener('input', (e) => scene.script_text = e.target.value);
      item.querySelector('.scene-prompt-input').addEventListener('input', (e) => scene.scene_prompt = e.target.value);

      el.adminScenesList.appendChild(item);
    });
  }

  el.btnAddNewScene.addEventListener('click', () => {
    const newId = `scene_${(state.presets.length + 1).toString().padStart(2, '0')}`;
    state.presets.push({
      id: newId,
      name: '新しいシーン',
      script_text: 'セリフを入力してください',
      scene_prompt: 'masterpiece anime scenery'
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
