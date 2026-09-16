/* =====================================================================
   VECTOR 155mm Shell Web Ground Station - Client Engine (app.js)
   Real-Time Canvas Trajectory Rendering & SSE Telemetry Engine
   ===================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const canvas = document.getElementById("trajectoryCanvas");
  const ctx = canvas.getContext("2d");
  const canvasWrapper = document.getElementById("canvas-wrapper");

  const connPill = document.getElementById("conn-pill");
  const connDot = document.getElementById("conn-dot");
  const connLabel = document.getElementById("conn-label");
  const sourceVal = document.getElementById("source-val");
  const missionClock = document.getElementById("mission-clock");
  const phaseBadge = document.getElementById("phase-badge");

  const hudX = document.getElementById("hud-x");
  const hudY = document.getElementById("hud-y");
  const hudApogee = document.getElementById("hud-apogee");

  const metricSpin = document.getElementById("metric-spin");
  const spinBar = document.getElementById("spin-bar");
  const metricRoll = document.getElementById("metric-roll");
  const metricPitch = document.getElementById("metric-pitch");

  const metricPress = document.getElementById("metric-press");
  const pressBar = document.getElementById("press-bar");
  const metricTemp = document.getElementById("metric-temp");

  const metricAx = document.getElementById("metric-ax");
  const metricAy = document.getElementById("metric-ay");
  const metricAz = document.getElementById("metric-az");

  const metricDist = document.getElementById("metric-dist");
  const distBar = document.getElementById("dist-bar");

  const rawCoords = document.getElementById("raw-coords");
  const rawAlt = document.getElementById("raw-alt");
  const cleanCoords = document.getElementById("clean-coords");
  const cleanAlt = document.getElementById("clean-alt");
  const outlierBadge = document.getElementById("outlier-alert-badge");
  const anomalyLog = document.getElementById("anomaly-log");

  const missionModal = document.getElementById("mission-modal");
  const btnCloseModal = document.getElementById("btn-modal-close");
  const btnReset = document.getElementById("btn-reset");
  const btnReplay = document.getElementById("btn-replay");
  const countdownVal = document.getElementById("countdown-val");

  // Canvas State & Ballistic Parameters
  const MAX_RANGE = 3000.0;   // 3 km downrange
  const MAX_APOGEE = 950.0;   // 950m apogee
  let trajectoryHistory = [];
  let currentPos = { x: 0, y: 0 };
  let targetPos = { x: 0, y: 0 };
  let flightPhase = "LAUNCH_STANDBY";
  let hasShownModal = false;
  let modalManuallyClosed = false;
  let modalTimer = null;
  let lastFlaggedTimestamp = null;

  // Responsive High-DPI Canvas Resizing
  function resizeCanvas() {
    const rect = canvasWrapper.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
  }
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  // Coordinate Conversion: World meters -> Canvas pixels
  function toCanvasCoords(x, y) {
    const rect = canvasWrapper.getBoundingClientRect();
    const paddingX = 60;
    const paddingY = 45;
    const drawWidth = rect.width - paddingX * 2;
    const drawHeight = rect.height - paddingY * 2;

    const px = paddingX + (x / MAX_RANGE) * drawWidth;
    const py = rect.height - paddingY - (y / (MAX_APOGEE * 1.15)) * drawHeight;
    return { x: px, y: py };
  }

  // =====================================================================
  // DETONATION FX ENGINE (TOP-ATTACK AIRBURST PROXIMITY EXPLOSION)
  // =====================================================================
  class DetonationFX {
    constructor() {
      this.active = false;
      this.burstTime = 0;
      this.originX = 0;
      this.originY = 0;
      this.particles = [];
      this.shockwaves = [];
      this.flashAlpha = 0;
    }

    trigger(canvasX, canvasY) {
      this.active = true;
      this.burstTime = performance.now();
      this.originX = canvasX;
      this.originY = canvasY;
      this.flashAlpha = 0.95;
      this.particles = [];
      this.shockwaves = [
        { r: 4, maxR: 90, speed: 2.5, color: "rgba(255, 120, 0, 0.9)", width: 3.5 },
        { r: 0, maxR: 140, speed: 3.6, color: "rgba(0, 240, 255, 0.7)", width: 2.2 },
        { r: 0, maxR: 190, speed: 4.8, color: "rgba(255, 230, 100, 0.5)", width: 1.5 },
      ];

      // Screen-shake trigger on viewport wrapper
      canvasWrapper.classList.remove("detonating");
      void canvasWrapper.offsetWidth; // force DOM reflow
      canvasWrapper.classList.add("detonating");
      setTimeout(() => canvasWrapper.classList.remove("detonating"), 550);

      // Play synthesized cinematic explosion sound
      this.playSyntheticBlast();

      // 1. Omnidirectional Shrapnel & Fiery Embers (60+ particles)
      const colors = ["#ffffff", "#ffea00", "#ff6600", "#ff2200", "#f59e0b", "#94a3b8"];
      for (let i = 0; i < 65; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = 1.8 + Math.random() * 8.5;
        this.particles.push({
          x: canvasX,
          y: canvasY,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed * 0.75 - Math.random() * 2.5, // slight upward ejection bias
          size: 2 + Math.random() * 4.5,
          alpha: 1.0,
          color: colors[Math.floor(Math.random() * colors.length)],
          decay: 0.012 + Math.random() * 0.02,
          gravity: 0.12,
          drag: 0.96,
          isJet: false,
        });
      }

      // 2. High-Velocity Top-Attack Shaped-Charge Penetrator Jet (Spraying downward onto target roof)
      for (let i = 0; i < 28; i++) {
        const spreadAngle = (Math.PI / 2) + (Math.random() - 0.5) * 0.45; // straight down into target
        const speed = 7.0 + Math.random() * 10.0;
        this.particles.push({
          x: canvasX + (Math.random() - 0.5) * 8,
          y: canvasY,
          vx: Math.cos(spreadAngle) * speed * 0.35,
          vy: Math.sin(spreadAngle) * speed,
          size: 2.5 + Math.random() * 3.5,
          alpha: 1.0,
          color: Math.random() > 0.3 ? "#fff59d" : "#00f0ff", // incandescent white-yellow / plasma cyan
          decay: 0.022 + Math.random() * 0.028,
          gravity: 0.18,
          drag: 0.98,
          isJet: true,
        });
      }
    }

    playSyntheticBlast() {
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const audioCtx = new AudioCtx();
        if (audioCtx.state === "suspended") audioCtx.resume();

        // Sub-bass thump
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(150, audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(25, audioCtx.currentTime + 0.6);

        gain.gain.setValueAtTime(0.4, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.65);

        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.7);

        // Filtered white noise explosion body
        const bufferSize = audioCtx.sampleRate * 0.5;
        const buffer = audioCtx.createBuffer(1, bufferSize, audioCtx.sampleRate);
        const output = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
          output[i] = Math.random() * 2 - 1;
        }
        const whiteNoise = audioCtx.createBufferSource();
        whiteNoise.buffer = buffer;

        const filter = audioCtx.createBiquadFilter();
        filter.type = "lowpass";
        filter.frequency.setValueAtTime(900, audioCtx.currentTime);
        filter.frequency.exponentialRampToValueAtTime(90, audioCtx.currentTime + 0.5);

        const noiseGain = audioCtx.createGain();
        noiseGain.gain.setValueAtTime(0.45, audioCtx.currentTime);
        noiseGain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.55);

        whiteNoise.connect(filter);
        filter.connect(noiseGain);
        noiseGain.connect(audioCtx.destination);
        whiteNoise.start();
        whiteNoise.stop(audioCtx.currentTime + 0.55);
      } catch (e) {
        // Autoplay policy fallback
      }
    }

    reset() {
      this.active = false;
      this.particles = [];
      this.shockwaves = [];
      this.flashAlpha = 0;
    }

    render(ctx) {
      if (!this.active) return;
      const elapsed = (performance.now() - this.burstTime) / 1000;

      ctx.save();

      // 1. Tactical Blast Flash Glow
      if (this.flashAlpha > 0.01) {
        const flashGrad = ctx.createRadialGradient(
          this.originX, this.originY, 5,
          this.originX, this.originY, 240
        );
        flashGrad.addColorStop(0, `rgba(255, 255, 255, ${this.flashAlpha * 0.95})`);
        flashGrad.addColorStop(0.25, `rgba(255, 170, 0, ${this.flashAlpha * 0.7})`);
        flashGrad.addColorStop(0.65, `rgba(255, 50, 0, ${this.flashAlpha * 0.3})`);
        flashGrad.addColorStop(1, "rgba(0, 0, 0, 0)");

        ctx.fillStyle = flashGrad;
        ctx.beginPath();
        ctx.arc(this.originX, this.originY, 240, 0, Math.PI * 2);
        ctx.fill();

        this.flashAlpha *= 0.88;
      }

      // 2. Expanding Fireball Core (Grows to ~48px, pulses, then dissipates)
      if (elapsed < 1.6) {
        const fireballProgress = Math.min(1, elapsed / 0.35);
        const fireballFade = elapsed > 0.35 ? Math.max(0, 1 - (elapsed - 0.35) / 1.25) : 1;
        const fbRadius = (14 + 42 * Math.sin((fireballProgress * Math.PI) / 2)) * (0.85 + 0.15 * Math.sin(elapsed * 25));

        const fbGrad = ctx.createRadialGradient(
          this.originX, this.originY, 0,
          this.originX, this.originY, fbRadius
        );
        fbGrad.addColorStop(0, `rgba(255, 255, 255, ${0.95 * fireballFade})`);
        fbGrad.addColorStop(0.25, `rgba(255, 240, 80, ${0.9 * fireballFade})`);
        fbGrad.addColorStop(0.55, `rgba(255, 85, 0, ${0.8 * fireballFade})`);
        fbGrad.addColorStop(0.85, `rgba(180, 20, 0, ${0.5 * fireballFade})`);
        fbGrad.addColorStop(1, "rgba(40, 10, 10, 0)");

        ctx.fillStyle = fbGrad;
        ctx.beginPath();
        ctx.arc(this.originX, this.originY, fbRadius, 0, Math.PI * 2);
        ctx.fill();
      }

      // 3. Shockwave Rings
      this.shockwaves.forEach((sw) => {
        sw.r += sw.speed;
        const progress = sw.r / sw.maxR;
        if (progress < 1) {
          const swAlpha = Math.max(0, (1 - progress) * 0.9);
          ctx.strokeStyle = sw.color.replace(/[\d\.]+\)$/, `${swAlpha})`);
          ctx.lineWidth = sw.width * (1 - progress * 0.35);
          ctx.beginPath();
          ctx.arc(this.originX, this.originY, sw.r, 0, Math.PI * 2);
          ctx.stroke();
        }
      });

      // 4. Shrapnel & Sparks Particles
      for (let i = this.particles.length - 1; i >= 0; i--) {
        const p = this.particles[i];
        p.x += p.vx;
        p.y += p.vy;
        p.vx *= p.drag;
        p.vy = p.vy * p.drag + p.gravity;
        p.alpha -= p.decay;
        p.size = Math.max(0.5, p.size * 0.985);

        if (p.alpha <= 0) {
          this.particles.splice(i, 1);
          continue;
        }

        ctx.save();
        ctx.globalAlpha = Math.max(0, p.alpha);
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = p.isJet ? 9 : 4;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }

      // 5. Tactical Detonation HUD Callout
      if (elapsed < 3.2) {
        const bannerFade = elapsed < 0.2 ? elapsed / 0.2 : (elapsed > 2.3 ? Math.max(0, 1 - (elapsed - 2.3) / 0.9) : 1);
        ctx.save();
        ctx.globalAlpha = bannerFade;
        ctx.textAlign = "center";

        // Glowing callout tag
        ctx.font = "bold 13px 'JetBrains Mono', monospace";
        ctx.fillStyle = "#ff4400";
        ctx.shadowColor = "#ff4400";
        ctx.shadowBlur = 12;
        ctx.fillText("💥 AIRBURST PROXIMITY DETONATION", this.originX, this.originY - 56);

        // Sub-label
        ctx.font = "10px 'Outfit', sans-serif";
        ctx.fillStyle = "#38bdf8";
        ctx.shadowColor = "#38bdf8";
        ctx.shadowBlur = 8;
        ctx.fillText("HOB: 2.1m // TOP-ATTACK SHAPED CHARGE DIRECT HIT", this.originX, this.originY - 42);
        ctx.restore();
      }

      ctx.restore();
    }
  }

  const detonationFX = new DetonationFX();

  // Draw Full Ballistic Parabola & Grid
  function renderCanvas() {
    const rect = canvasWrapper.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    ctx.clearRect(0, 0, width, height);

    // 1. Gridlines & Axis Ticks
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.lineWidth = 1;

    // Range ticks (every 500m)
    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#64748b";
    ctx.textAlign = "center";
    for (let r = 0; r <= MAX_RANGE; r += 500) {
      const pt = toCanvasCoords(r, 0);
      ctx.beginPath();
      ctx.moveTo(pt.x, 20);
      ctx.lineTo(pt.x, height - 35);
      ctx.stroke();
      ctx.fillText(`${r}m`, pt.x, height - 20);
    }

    // Altitude ticks (every 250m)
    ctx.textAlign = "right";
    for (let a = 0; a <= 1000; a += 250) {
      const pt = toCanvasCoords(0, a);
      ctx.beginPath();
      ctx.moveTo(50, pt.y);
      ctx.lineTo(width - 40, pt.y);
      ctx.stroke();
      ctx.fillText(`${a}m`, 45, pt.y + 3);
    }

    // 2. Ground Baseline
    const groundStart = toCanvasCoords(0, 0);
    const groundEnd = toCanvasCoords(MAX_RANGE, 0);
    ctx.strokeStyle = "rgba(0, 240, 255, 0.25)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(groundStart.x - 20, groundStart.y);
    ctx.lineTo(groundEnd.x + 30, groundEnd.y);
    ctx.stroke();

    // 3. Pre-rendered Planned Ballistic Parabolic Arc (Dashed Line)
    ctx.strokeStyle = "rgba(148, 163, 184, 0.4)";
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    for (let x = 0; x <= MAX_RANGE; x += 30) {
      const tau = x / MAX_RANGE;
      const plannedY = 4.0 * MAX_APOGEE * tau * (1.0 - tau);
      const c = toCanvasCoords(x, plannedY);
      if (x === 0) ctx.moveTo(c.x, c.y);
      else ctx.lineTo(c.x, c.y);
    }
    ctx.stroke();
    ctx.setLineDash([]); // Reset to solid

    // 4. Apogee Peak Marker (1500m, 950m)
    const apogeeCoords = toCanvasCoords(MAX_RANGE / 2, MAX_APOGEE);
    ctx.fillStyle = "#f59e0b";
    ctx.beginPath();
    ctx.moveTo(apogeeCoords.x, apogeeCoords.y - 8);
    ctx.lineTo(apogeeCoords.x - 7, apogeeCoords.y + 6);
    ctx.lineTo(apogeeCoords.x + 7, apogeeCoords.y + 6);
    ctx.closePath();
    ctx.fill();
    ctx.font = "11px 'Outfit', sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("APOGEE 950m", apogeeCoords.x, apogeeCoords.y - 14);

    // 5. Target Impact Marker Cross (3000m, 0m)
    const targetCoords = toCanvasCoords(MAX_RANGE, 0);
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(targetCoords.x - 8, targetCoords.y - 8);
    ctx.lineTo(targetCoords.x + 8, targetCoords.y + 8);
    ctx.moveTo(targetCoords.x + 8, targetCoords.y - 8);
    ctx.lineTo(targetCoords.x - 8, targetCoords.y + 8);
    ctx.stroke();
    ctx.fillStyle = "#ef4444";
    ctx.fillText("TARGET (3000m)", targetCoords.x, targetCoords.y - 14);

    // 6. Live Trajectory Path (Tactical Avionics Blue Solid Line)
    if (trajectoryHistory.length > 1) {
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      trajectoryHistory.forEach((p, idx) => {
        const c = toCanvasCoords(p.x, p.y);
        if (idx === 0) ctx.moveTo(c.x, c.y);
        else ctx.lineTo(c.x, c.y);
      });
      ctx.stroke();
    }

    // 7. Live Projectile Marker (Tactical Radar Reticle & Tracking Dot)
    // Snap instantly on flight reset (jump > 400m)
    if (Math.abs(targetPos.x - currentPos.x) > 400) {
      currentPos.x = targetPos.x;
      currentPos.y = targetPos.y;
    } else {
      currentPos.x += (targetPos.x - currentPos.x) * 0.25;
      currentPos.y += (targetPos.y - currentPos.y) * 0.25;
    }

    const shellC = toCanvasCoords(currentPos.x, currentPos.y);

    // Outer tactical reticle ring
    const isImpact = flightPhase === "TARGET_IMPACT";
    ctx.strokeStyle = isImpact ? "#ef4444" : "#f59e0b";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(shellC.x, shellC.y, isImpact ? 22 : 13, 0, Math.PI * 2);
    ctx.stroke();

    // Tactical crosshair ticks
    const tickLen = 5;
    ctx.beginPath();
    ctx.moveTo(shellC.x - 18, shellC.y);
    ctx.lineTo(shellC.x - 18 + tickLen, shellC.y);
    ctx.moveTo(shellC.x + 18, shellC.y);
    ctx.lineTo(shellC.x + 18 - tickLen, shellC.y);
    ctx.moveTo(shellC.x, shellC.y - 18);
    ctx.lineTo(shellC.x, shellC.y - 18 + tickLen);
    ctx.moveTo(shellC.x, shellC.y + 18);
    ctx.lineTo(shellC.x, shellC.y + 18 - tickLen);
    ctx.stroke();

    // Center tracking dot (Radar Green in flight, Red at target impact)
    const dotColor = isImpact ? "#ef4444" : "#22c55e";
    ctx.fillStyle = dotColor;
    ctx.beginPath();
    ctx.arc(shellC.x, shellC.y, isImpact ? 8 : 5, 0, Math.PI * 2);
    ctx.fill();

    // 8. Top-Attack Airburst Detonation FX
    if (isImpact) {
      if (!detonationFX.active) {
        // Airburst triggers ~2.5m above ground at 3000m target
        const burstC = toCanvasCoords(MAX_RANGE, 2.5);
        detonationFX.trigger(burstC.x, burstC.y);
      }
      detonationFX.render(ctx);
    } else {
      detonationFX.reset();
    }

    requestAnimationFrame(renderCanvas);
  }
  requestAnimationFrame(renderCanvas);

  // Append entry to ML Anomaly Log
  function appendAnomalyLog(timeStr, fields, isMultivariate) {
    if (anomalyLog.children.length > 35) {
      anomalyLog.removeChild(anomalyLog.firstChild);
    }
    const entry = document.createElement("div");
    entry.className = "log-entry log-alert";
    entry.innerHTML = `
      <span class="log-time">[${timeStr}]</span>
      <span class="log-msg">⚠️ OUTLIER INTERCEPTED: Fields=${JSON.stringify(fields)} | MultiVar=${isMultivariate} &bull; Velocity Extrapolated Cleaned</span>
    `;
    anomalyLog.appendChild(entry);
    anomalyLog.scrollTop = anomalyLog.scrollHeight;
  }

  // Connect to SSE Telemetry Stream
  function connectTelemetryStream() {
    connLabel.innerText = "CONNECTING...";
    const evtSource = new EventSource("/events");

    evtSource.onopen = () => {
      connLabel.innerText = "STREAM ONLINE";
      connDot.className = "status-dot connected pulse";
    };

    evtSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        updateDashboard(data);
      } catch (err) {
        console.error("Telemetry parse error:", err);
      }
    };

    evtSource.onerror = () => {
      connLabel.innerText = "RECONNECTING";
      connDot.className = "status-dot disconnected pulse";
    };
  }

  // Update UI Elements with Live Telemetry
  function updateDashboard(data) {
    sourceVal.innerText = data.source;
    missionClock.innerText = `T+${(parseInt(data.timestamp || 0) * 0.1).toFixed(1)}s`;

    // Coordinates & Trajectory
    targetPos.x = data.x;
    targetPos.y = data.y;
    trajectoryHistory = data.trajectory || [];

    hudX.innerText = `${data.x.toFixed(1)} m`;
    hudY.innerText = `${data.y.toFixed(1)} m`;

    // Flight phase badge & Modal management
    flightPhase = data.phase || "BALLISTIC_ASCENT";
    phaseBadge.innerText = flightPhase.replace("_", " ");

    if (flightPhase === "APOGEE_GLIDE") {
      phaseBadge.style.color = "#f59e0b";
      phaseBadge.style.borderColor = "rgba(245, 158, 11, 0.5)";
    } else if (flightPhase === "TARGET_IMPACT") {
      phaseBadge.style.color = "#10b981";
      phaseBadge.style.borderColor = "rgba(16, 185, 129, 0.5)";

      // Update auto-replay countdown display
      if (countdownVal && typeof data.hold_countdown === "number") {
        countdownVal.innerText = `${data.hold_countdown.toFixed(1)}`;
      }

      if (!modalManuallyClosed && !hasShownModal) {
        hasShownModal = true;
        if (modalTimer) clearTimeout(modalTimer);
        // Delay modal slightly (1.3s) so the user can enjoy the full airburst explosion
        modalTimer = setTimeout(() => {
          if (flightPhase === "TARGET_IMPACT" && !modalManuallyClosed) {
            missionModal.style.display = "flex";
          }
        }, 1300);
      }
    } else {
      phaseBadge.style.color = "var(--neon-cyan)";
      phaseBadge.style.borderColor = "var(--border-active)";
      if (modalTimer) {
        clearTimeout(modalTimer);
        modalTimer = null;
      }
      hasShownModal = false;
      modalManuallyClosed = false;
      missionModal.style.display = "none";
    }

    // 1. IMU Spin
    metricSpin.innerHTML = `${data.roll_rpm.toFixed(1)} <span class="unit">RPM</span>`;
    spinBar.style.width = `${Math.min(100, (data.roll_rpm / 350) * 100)}%`;
    metricRoll.innerText = `${data.gyro_z.toFixed(2)} rad/s`;
    metricPitch.innerText = `${data.gyro_x.toFixed(2)} rad/s`;

    // 2. Barometer BMP388
    metricPress.innerHTML = `${data.pressure.toFixed(1)} <span class="unit">hPa</span>`;
    pressBar.style.width = `${Math.max(10, (data.pressure / 1013.25) * 100)}%`;
    metricTemp.innerText = `${data.temperature.toFixed(1)} °C`;

    // 3. Accelerations
    metricAx.innerText = `${data.accel_x > 0 ? "+" : ""}${data.accel_x.toFixed(2)} m/s²`;
    metricAy.innerText = `${data.accel_y > 0 ? "+" : ""}${data.accel_y.toFixed(2)} m/s²`;
    metricAz.innerText = `${data.accel_z.toFixed(2)} m/s²`;

    // 4. Distance / Proximity Fuze
    metricDist.innerHTML = `${data.distance.toFixed(1)} <span class="unit">cm</span>`;
    distBar.style.width = `${Math.min(100, (data.distance / 500.0) * 100)}%`;

    // 5. GPS Comparison
    rawCoords.innerText = `${data.latitude.toFixed(6)}°, ${data.longitude.toFixed(6)}°`;
    rawAlt.innerText = `${data.altitude.toFixed(1)} m`;
    cleanCoords.innerText = `${data.cleaned_lat.toFixed(6)}°, ${data.cleaned_lon.toFixed(6)}°`;
    cleanAlt.innerText = `${data.cleaned_alt.toFixed(1)} m`;

    // 6. Outlier Alert Trigger
    if (data.is_outlier) {
      outlierBadge.innerText = "OUTLIER INTERCEPTED & CLEANED";
      outlierBadge.className = "badge badge-alert";
      if (lastFlaggedTimestamp !== data.timestamp) {
        lastFlaggedTimestamp = data.timestamp;
        appendAnomalyLog(missionClock.innerText, data.field_outliers, data.multivariate_outlier);
      }
    } else {
      outlierBadge.innerText = "GUARD ACTIVE • NOMINAL";
      outlierBadge.className = "badge badge-active";
    }
  }

  // Reset Flight Simulation
  function triggerReset() {
    fetch("/api/reset")
      .then((res) => res.json())
      .then(() => {
        if (modalTimer) {
          clearTimeout(modalTimer);
          modalTimer = null;
        }
        detonationFX.reset();
        trajectoryHistory = [];
        currentPos = { x: 0, y: 0 };
        targetPos = { x: 0, y: 0 };
        missionModal.style.display = "none";
        hasShownModal = false;
        modalManuallyClosed = false;
      })
      .catch((err) => console.error("Reset failed:", err));
  }

  if (btnCloseModal) {
    btnCloseModal.addEventListener("click", () => {
      modalManuallyClosed = true;
      missionModal.style.display = "none";
    });
  }

  btnReset.addEventListener("click", triggerReset);
  btnReplay.addEventListener("click", triggerReset);

  // Start SSE connection
  connectTelemetryStream();
});
