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

    // Face / Person Image
    faceBlob: null,
    faceImageFilename: '',
    sessionId: '',
    vlmData: null,
    vlmExtraction: null,

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
    btnSaveCurrentScene: document.getElementById('wb-btn-save-current-scene'),
    btnAddScene: document.getElementById('wb-btn-add-scene'),
    btnDeleteScene: document.getElementById('wb-btn-delete-scene'),

    // Face
    faceDropzone: document.getElementById('face-dropzone'),
    faceFileInput: document.getElementById('face-file-input'),
    facePreviewImg: document.getElementById('face-preview-img'),
    facePlaceholder: document.getElementById('face-placeholder'),
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

    // Audio
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
    detailed12Card: document.getElementById('wb-detailed-12-card'),
    top1Score: document.getElementById('wb-top1-score'),
    top1Icon: document.getElementById('wb-top1-icon'),
    top1Name: document.getElementById('wb-top1-name'),
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
    await loadPresets();
    await populateMicDevices();
    triggerAutoAssemble();
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
      scene_prompt: el.scenePrompt.value.trim()
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
      scene_prompt: 'fantasy anime, dynamic pose, vibrant colors'
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
  // C. Face Image & VLM Analysis
  // -------------------------------------------------------------------------
  function setFaceImageFile(file) {
    if (!file) return;
    wbState.faceBlob = file;
    wbState.faceImageFilename = file.name;
    const url = URL.createObjectURL(file);
    el.facePreviewImg.src = url;
    el.facePreviewImg.classList.remove('hidden');
    el.facePlaceholder.classList.add('hidden');
    showError('');
  }

  async function loadTestFace(filename) {
    try {
      const res = await fetch(`/test_assets/faces/${filename}`);
      if (!res.ok) {
        // static からの配信または直取得フォールバック
        throw new Error(`test_asset fetch HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const file = new File([blob], filename, { type: blob.type || 'image/jpeg' });
      setFaceImageFile(file);
      showToast(`テスト画像「${filename}」をセットしました`, 'info');
    } catch (e) {
      // サーバー経由で直接画像取得できない場合、ファイル名のみ保持
      wbState.faceImageFilename = filename;
      el.facePlaceholder.innerHTML = `<span class="dropzone-icon">🖼</span><p>テスト画像指定: <strong>${filename}</strong></p>`;
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
  // D. Audio Input, Recording, & Emotion Analysis
  // -------------------------------------------------------------------------
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
    setStatus('analyzing_audio', 'SenseVoice 推論 ＋ ピーク音量 rms_p90 算出中...');
    el.btnAnalyzeAudio.disabled = true;

    try {
      const formData = new FormData();
      formData.append('audio_file', wbState.audioBlob, 'workbench_audio.wav');

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

      // 結果表示
      el.audioBadge.textContent = '分析完了';
      el.audioBadge.className = 'badge-mini ready';
      el.resSenseEmo.textContent = data.emotion || '--';
      el.resRmsDb.textContent = `${(data.rms_db || 0).toFixed(1)} dBFS`;
      el.resVerdict.textContent = data.expression_state || '--';
      el.resRecognizedText.textContent = data.recognized_text || '（テキストなし）';

      // 詳細12感情モードの描画
      if (data.emotion_mode === 'detailed_12' && data.primary_emotion) {
        el.detailed12Card.classList.remove('hidden');
        el.top1Score.textContent = data.primary_emotion.score.toFixed(1);
        el.top1Icon.textContent = data.primary_emotion.icon || '✨';
        el.top1Name.textContent = data.primary_emotion.name_ja;

        if (data.secondary_emotion) {
          el.top2Score.textContent = data.secondary_emotion.score.toFixed(1);
          el.top2Icon.textContent = data.secondary_emotion.icon || '✨';
          el.top2Name.textContent = data.secondary_emotion.name_ja;
        }

        // 7つの基礎指標
        if (data.features_7 && el.f7Grid) {
          el.f7Grid.innerHTML = '';
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
            item.innerHTML = `<span class="f7-label">${f7Labels[k] || k}</span><span class="f7-val">${v.toFixed(1)} pt</span>`;
            el.f7Grid.appendChild(item);
          }
        }

        // 12感情全スコア (オブジェクト形式: { sensuality: 88.5, ... })
        if (data.emotions_12 && el.e12List) {
          el.e12List.innerHTML = '';
          const emoDefs = {
            sensuality: { name_ja: '色気・官能', icon: '💋' },
            affection: { name_ja: '愛情・親愛', icon: '💖' },
            benevolence: { name_ja: '慈愛・優しさ', icon: '🕊️' },
            self_love: { name_ja: '自愛・陶酔', icon: '✨' },
            euphoria: { name_ja: '歓喜・高揚', icon: '🎉' },
            sorrow: { name_ja: '哀愁・悲壮', icon: '🌧️' },
            fury: { name_ja: '激情・怒り', icon: '🔥' },
            despair: { name_ja: '絶望・苦悶', icon: '💔' },
            yearning: { name_ja: '切望・渇望', icon: '🥀' },
            hatred: { name_ja: '憎悪・怨嗟', icon: '⚡' },
            contempt: { name_ja: '軽蔑・冷酷', icon: '❄️' },
            fear: { name_ja: '恐怖・怯え', icon: '😨' }
          };

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
            const isTop = (e.id === data.primary_emotion?.id || e.id === data.secondary_emotion?.id);
            row.innerHTML = `
              <span class="e12-name" style="${isTop ? 'font-weight: 700; color: var(--accent-cyan);' : ''}">${e.icon} ${e.name_ja}</span>
              <div class="e12-bar-track"><div class="e12-bar-fill" style="width: ${Math.min(100, Math.max(0, e.score))}%; ${isTop ? 'background: linear-gradient(90deg, var(--accent-cyan), var(--primary));' : ''}"></div></div>
              <span class="e12-score">${e.score.toFixed(1)} pt</span>
            `;
            el.e12List.appendChild(row);
          });
        }
      } else {
        el.detailed12Card.classList.add('hidden');
      }

      // 表情プロンプトの反映
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

  async function handleSaveMode() {
    const mode = el.selectEmotionMode.value;
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ emotion_mode: mode })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast(`感情分析モードを「${mode === 'detailed_12' ? '詳細12感情' : '従来'}」に更新しました`, 'success');
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
    const quality = (el.qualityPrompt.value || '').trim();
    const baseNeg = (el.baseNegative.value || '').trim();

    // 1. Node_Pos_Base (Node 5)
    // {gender}, solo, {traits}, {expr}, {scene}, {quality}
    const baseParts = [gender, 'solo', traits, expr, scene, quality].filter(Boolean);
    el.promptPosBase.value = baseParts.join(', ');

    // 2. Node_Neg_Base (Node 6)
    // {neg_bias}, {base_neg}
    el.promptNegBase.value = negBias ? `${negBias}, ${baseNeg}` : baseNeg;

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
    if (!posBase || !negBase || !posFd) {
      showError('3系統のプロンプト（Base Posi, Base Nega, FD Posi）をすべて入力してください');
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
      if (wbState.faceBlob) {
        formData.append('face_image', wbState.faceBlob, wbState.faceImageFilename || 'face.jpg');
      } else if (wbState.faceImageFilename) {
        formData.append('image_filename', wbState.faceImageFilename);
      } else if (wbState.sessionId) {
        formData.append('session_id', wbState.sessionId);
      }

      formData.append('pos_base', posBase);
      formData.append('neg_base', negBase);
      formData.append('pos_fd', posFd);
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
      addToHistory({
        time: new Date().toLocaleTimeString(),
        filename: data.saved_filename,
        imgSrc: imgBase64,
        sceneName: el.sceneName.value || 'カスタム',
        posBase: posBase,
        negBase: negBase,
        posFd: posFd
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
      card.innerHTML = `
        <img src="${h.imgSrc}" class="history-card-thumb" alt="サムネイル">
        <div class="history-card-meta">
          <span class="history-card-title">${h.time} - ${h.sceneName}</span>
          <span class="history-card-sub">${h.filename || 'card.png'}</span>
        </div>
      `;
      card.addEventListener('click', () => {
        // 条件復元
        el.promptPosBase.value = h.posBase;
        el.promptNegBase.value = h.negBase;
        el.promptPosFd.value = h.posFd;
        el.generatedImage.src = h.imgSrc;
        el.generatedImage.classList.remove('hidden');
        el.imagePlaceholder.classList.add('hidden');
        el.btnDownloadResult.disabled = false;
        showToast(`履歴 (${h.time}) のプロンプト条件を復元しました`, 'info');
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
    [el.sceneScript, el.scenePrompt].forEach(i => {
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

    // Mic recording
    el.btnMicToggle.addEventListener('click', toggleMicRecording);
    el.btnAnalyzeAudio.addEventListener('click', handleAnalyzeAudio);

    // Threshold Slider
    el.burningSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      el.thresholdValText.innerHTML = `<strong>${val.toFixed(1)}</strong> dBFS`;
    });
    el.btnSaveThreshold.addEventListener('click', handleSaveThreshold);
    el.btnSaveMode.addEventListener('click', handleSaveMode);

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
