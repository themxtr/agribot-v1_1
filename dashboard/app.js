/**
 * Agribot v1.1 Dashboard Logic
 * Powered by roslibjs
 */

const CONFIG = {
    ros_url: `ws://${window.location.hostname}:9090`,
    video_url_base: `http://${window.location.hostname}:8081/stream?topic=`, // Standardized to 8081
    default_video_topic: '/detections_annotated'
};

class AgribotDashboard {
    constructor() {
        this.ros = new ROSLIB.Ros();
        this.topics = {};
        this.currentState = 'SAFE';
        this.isModalOpen = false;
        this.pendingMode = null;
        this.fpsCount = 0;
        this.lastFpsTime = Date.now();
        
        // Reconnection Logic
        this.reconnectInterval = 3000;
        this.maxReconnectInterval = 30000;
        this.reconnectTimer = null;
        this.isConnecting = false;

        this.initDOM();
        this.initROS();
        this.bindEvents();
        this.startStatsTimer();
    }

    initDOM() {
        this.els = {
            rosStatus: document.getElementById('ros-status'),
            systemState: document.getElementById('system-state'),
            videoFeed: document.getElementById('video-feed'),
            btnActivate: document.getElementById('btn-activate'),
            btnScan: document.getElementById('btn-scan'),
            btnDetect: document.getElementById('btn-detect'),
            btnSpray: document.getElementById('btn-spray'),
            btnEmergency: document.getElementById('btn-emergency'),
            logWindow: document.getElementById('log-window'),
            modal: document.getElementById('modal-confirm'),
            modalCancel: document.getElementById('modal-cancel'),
            modalConfirm: document.getElementById('modal-confirm-btn'),
            statFps: document.getElementById('stat-fps'),
            statLatency: document.getElementById('stat-latency'),
            hwCamera: document.getElementById('hw-camera'),
            hwLidar: document.getElementById('hw-lidar'),
            hwMotor: document.getElementById('hw-motor'),
            disconnectOverlay: document.getElementById('disconnect-overlay')
        };
    }

    initROS() {
        this.ros.on('connection', () => {
            console.log('Connected to websocket server.');
            this.isConnecting = false;
            this.reconnectInterval = 3000; // Reset interval
            
            this.els.rosStatus.classList.add('ros-connected');
            this.els.rosStatus.querySelector('.status-text').innerText = 'CONNECTED';
            this.log('System: Connected to ROS Bridge', 'success');
            
            this.hideDisconnectOverlay();
            this.setupSubscribers();
        });

        this.ros.on('error', (error) => {
            console.log('Error connecting to websocket server: ', error);
            this.handleDisconnect();
        });

        this.ros.on('close', () => {
            console.log('Connection to websocket server closed.');
            this.handleDisconnect();
        });

        this.connect();
    }

    connect() {
        if (this.isConnecting) return;
        this.isConnecting = true;

        const hostname = window.location.hostname || 'localhost';
        const url = (hostname === 'localhost' || hostname === '127.0.0.1')
            ? 'ws://localhost:9090' 
            : `ws://${hostname}:9090`;
        
        console.log(`Attempting to connect to ${url}...`);
        this.ros.connect(url);
    }

    handleDisconnect() {
        this.isConnecting = false;
        this.els.rosStatus.classList.remove('ros-connected');
        this.els.rosStatus.querySelector('.status-text').innerText = 'DISCONNECTED';
        
        this.showDisconnectOverlay();
        
        // Exponential backoff reconnection
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = setTimeout(() => {
            this.log(`System: Retrying connection in ${this.reconnectInterval/1000}s...`, 'warning');
            this.connect();
            // Increase interval for next time
            this.reconnectInterval = Math.min(this.reconnectInterval * 1.5, this.maxReconnectInterval);
        }, this.reconnectInterval);
    }

    showDisconnectOverlay() {
        if (this.els.disconnectOverlay) {
            this.els.disconnectOverlay.classList.add('visible');
        }
        // Disable all command buttons at DOM level
        this.setAllButtonsDisabled(true);
    }

    hideDisconnectOverlay() {
        if (this.els.disconnectOverlay) {
            this.els.disconnectOverlay.classList.remove('visible');
        }
        // Buttons will be re-enabled by updateUIForState once first message arrives
    }

    setAllButtonsDisabled(disabled) {
        const buttons = [
            this.els.btnActivate, this.els.btnScan, 
            this.els.btnDetect, this.els.btnSpray, 
            this.els.btnEmergency
        ];
        buttons.forEach(btn => {
            if (btn) btn.disabled = disabled;
        });
    }

    setupSubscribers() {
        // 1. System State
        this.topics.systemState = new ROSLIB.Topic({
            ros: this.ros,
            name: '/system_state',
            messageType: 'std_msgs/String'
        });
        this.topics.systemState.subscribe((msg) => this.handleStateChange(msg.data));

        // 2. Hardware Capabilities
        this.topics.hwCaps = new ROSLIB.Topic({
            ros: this.ros,
            name: '/hw_capabilities',
            messageType: 'std_msgs/String'
        });
        this.topics.hwCaps.subscribe((msg) => this.handleHwCapabilities(msg.data));

        // 3. Detections
        this.topics.detections = new ROSLIB.Topic({
            ros: this.ros,
            name: '/detections',
            messageType: 'agribot_msgs/DetectionArray'
        });
        this.topics.detections.subscribe(() => {
            this.fpsCount++;
        });

        // Setup Publishers
        this.topics.setMode = new ROSLIB.Topic({
            ros: this.ros,
            name: '/set_mode',
            messageType: 'std_msgs/String'
        });

        this.topics.operatorConfirm = new ROSLIB.Topic({
            ros: this.ros,
            name: '/operator_confirm',
            messageType: 'std_msgs/String'
        });

        // Initialize Video
        this.updateVideoFeed(CONFIG.default_video_topic);
    }

    handleStateChange(state) {
        if (state === this.currentState && !this.els.disconnectOverlay.classList.contains('visible')) return;

        console.log(`State transition: ${this.currentState} -> ${state}`);
        this.currentState = state;
        this.updateUIForState(state);
    }

    updateUIForState(state) {
        const el = this.els.systemState;
        el.innerText = state;
        el.className = 'state-badge';
        el.classList.add(`state-${state.toLowerCase()}`);

        const isActive = state === 'ACTIVE';
        const isReady = state === 'READY';

        this.els.btnActivate.disabled = !isReady;
        this.els.btnScan.disabled = !isActive;
        this.els.btnDetect.disabled = !isActive;
        this.els.btnSpray.disabled = !isActive;
        this.els.btnEmergency.disabled = false; // Always enabled when connected

        if (isActive) {
            this.els.btnActivate.innerText = 'SYSTEM ARMED';
            this.els.btnActivate.classList.add('armed');
        } else {
            this.els.btnActivate.innerText = 'ACTIVATE SYSTEM';
            this.els.btnActivate.classList.remove('armed');
        }
    }

    handleHwCapabilities(jsonStr) {
        try {
            const caps = JSON.parse(jsonStr);
            this.updateHwStatus(this.els.hwCamera, caps.has_camera);
            this.updateHwStatus(this.els.hwLidar, caps.has_lidar);
            this.updateHwStatus(this.els.hwMotor, caps.has_motor);
        } catch (e) {}
    }

    updateHwStatus(el, active) {
        if (el) {
            if (active) el.classList.add('active');
            else el.classList.remove('active');
        }
    }

    bindEvents() {
        this.els.btnActivate.addEventListener('click', () => {
            this.publishMsg(this.topics.operatorConfirm, 'ACTIVATE');
            this.log('Action: Sending activation confirmation...', 'system');
        });

        this.els.btnScan.addEventListener('click', () => this.setMode('SCAN'));
        this.els.btnDetect.addEventListener('click', () => this.setMode('DETECT'));
        this.els.btnSpray.addEventListener('click', () => {
            this.pendingMode = 'SPRAY';
            this.showModal();
        });

        this.els.btnEmergency.addEventListener('click', () => {
            this.publishMsg(this.topics.setMode, 'SAFE');
            this.log('EMERGENCY: SAFE mode commanded!', 'error');
            this.playAlertSound();
        });

        this.els.modalCancel.addEventListener('click', () => this.hideModal());
        this.els.modalConfirm.addEventListener('click', () => {
            if (this.pendingMode) {
                this.setMode(this.pendingMode);
                this.hideModal();
            }
        });

        document.querySelectorAll('.feed-selector button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.feed-selector button').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.updateVideoFeed(e.target.dataset.topic);
            });
        });
    }

    setMode(mode) {
        this.publishMsg(this.topics.setMode, mode);
        this.log(`Action: Commanded ${mode} mode`, 'system');
        document.querySelectorAll('.btn-mode').forEach(btn => btn.classList.remove('active'));
        if (mode === 'SCAN') this.els.btnScan.classList.add('active');
        if (mode === 'DETECT') this.els.btnDetect.classList.add('active');
    }

    publishMsg(topic, data) {
        if (!topic || !this.ros.isConnected) return;
        const msg = new ROSLIB.Message({ data: data });
        topic.publish(msg);
    }

    updateVideoFeed(topic) {
        const hostname = window.location.hostname || 'localhost';
        const url = `http://${hostname}:8081/stream?topic=${topic}&quality=30&width=640&height=480`;
        
        // Reset to img element if it was replaced by replay fallback
        const container = this.els.videoFeed.parentElement || document.querySelector('.video-container');
        const existingFallback = container.querySelector('.replay-fallback');
        if (existingFallback) {
            existingFallback.remove();
            this.els.videoFeed.style.display = '';
        }

        this.els.videoFeed.src = url;
        document.getElementById('stream-topic').innerText = topic;

        // Fallback for replay mode (images not recorded in bags)
        this.els.videoFeed.onerror = () => {
            this.els.videoFeed.style.display = 'none';
            if (!container.querySelector('.replay-fallback')) {
                const fallback = document.createElement('div');
                fallback.className = 'replay-fallback';
                fallback.innerHTML = `
                    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--text-secondary);text-align:center;padding:2rem;">
                        <span style="font-size:3rem;margin-bottom:1rem;">📼</span>
                        <h3 style="margin-bottom:0.5rem;color:var(--text-primary);">Video Not Available</h3>
                        <p style="font-size:0.9rem;">Images are not recorded in bag files to save storage.<br>Telemetry data is streaming normally.</p>
                    </div>
                `;
                container.appendChild(fallback);
            }
        };
    }

    log(msg, type = 'system') {
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;
        const time = new Date().toLocaleTimeString([], { hour12: false });
        entry.innerText = `[${time}] ${msg}`;
        this.els.logWindow.prepend(entry);
        if (this.els.logWindow.childNodes.length > 50) {
            this.els.logWindow.removeChild(this.els.logWindow.lastChild);
        }
    }

    showModal() {
        this.els.modal.style.display = 'flex';
        this.isModalOpen = true;
    }

    hideModal() {
        this.els.modal.style.display = 'none';
        this.isModalOpen = false;
        this.pendingMode = null;
    }

    startStatsTimer() {
        setInterval(() => {
            const now = Date.now();
            const elapsed = (now - this.lastFpsTime) / 1000;
            const fps = (this.fpsCount / elapsed).toFixed(1);
            this.els.statFps.innerText = fps;
            this.fpsCount = 0;
            this.lastFpsTime = now;
        }, 2000);
    }

    playAlertSound() {
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioCtx.createOscillator();
            oscillator.type = 'square';
            oscillator.frequency.setValueAtTime(440, audioCtx.currentTime);
            oscillator.connect(audioCtx.destination);
            oscillator.start();
            oscillator.stop(audioCtx.currentTime + 0.2);
        } catch (e) {}
    }
}

window.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new AgribotDashboard();
});
