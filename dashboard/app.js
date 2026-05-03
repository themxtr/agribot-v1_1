/**
 * Agribot v1.1 Dashboard Logic
 * Powered by roslibjs
 */

const CONFIG = {
    ros_url: `ws://${window.location.hostname}:9090`,
    video_url_base: `http://${window.location.hostname}:8080/stream?topic=`,
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

        this.initDOM();
        this.initROS();
        this.bindEvents();
        this.startStatsTimer();
    }

    initDOM() {
        // UI Elements
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
            hwMotor: document.getElementById('hw-motor')
        };
    }

    initROS() {
        this.ros.on('connection', () => {
            console.log('Connected to websocket server.');
            this.els.rosStatus.classList.add('ros-connected');
            this.els.rosStatus.querySelector('.status-text').innerText = 'CONNECTED';
            this.log('System: Connected to ROS Bridge', 'success');
            this.setupSubscribers();
        });

        this.ros.on('error', (error) => {
            console.log('Error connecting to websocket server: ', error);
            this.els.rosStatus.classList.remove('ros-connected');
            this.els.rosStatus.querySelector('.status-text').innerText = 'CONNECTION ERROR';
            this.log('Error: Failed to connect to ROS Bridge', 'error');
        });

        this.ros.on('close', () => {
            console.log('Connection to websocket server closed.');
            this.els.rosStatus.classList.remove('ros-connected');
            this.els.rosStatus.querySelector('.status-text').innerText = 'DISCONNECTED';
            this.log('System: Connection lost. Retrying...', 'warning');
            setTimeout(() => this.connect(), 5000);
        });

        this.connect();
    }

    connect() {
        // Handle local dev vs production hostname
        const url = window.location.hostname === '' || window.location.hostname === 'localhost' 
            ? 'ws://agribot.local:9090' 
            : CONFIG.ros_url;
        
        this.ros.connect(url);
    }

    setupSubscribers() {
        // 1. System State
        this.topics.systemState = new ROSLIB.Topic({
            ros: this.ros,
            name: '/system_state',
            messageType: 'std_msgs/String'
        });
        this.topics.systemState.subscribe((msg) => this.handleStateChange(msg.data));

        // 2. Hardware Capabilities (JSON)
        this.topics.hwCaps = new ROSLIB.Topic({
            ros: this.ros,
            name: '/hw_capabilities',
            messageType: 'std_msgs/String'
        });
        this.topics.hwCaps.subscribe((msg) => this.handleHwCapabilities(msg.data));

        // 3. Detections (for FPS)
        this.topics.detections = new ROSLIB.Topic({
            ros: this.ros,
            name: '/detections',
            messageType: 'agribot_msgs/msg/DetectionArray' // Assumed custom msg
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
        if (state === this.currentState) return;

        console.log(`State transition: ${this.currentState} -> ${state}`);
        this.log(`State: Transitioned to ${state}`, 'system');
        
        this.currentState = state;
        this.updateUIForState(state);
    }

    updateUIForState(state) {
        const el = this.els.systemState;
        el.innerText = state;
        el.className = 'state-badge'; // Reset
        
        // Remove old classes and add new one
        el.classList.add(`state-${state.toLowerCase()}`);

        // Toggle buttons based on state machine logic
        const isSafe = state === 'SAFE' || state === 'CONFIGURING';
        const isReady = state === 'READY';
        const isActive = state === 'ACTIVE';

        this.els.btnActivate.disabled = !isReady;
        this.els.btnScan.disabled = !isActive;
        this.els.btnDetect.disabled = !isActive;
        this.els.btnSpray.disabled = !isActive;

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
        } catch (e) {
            console.error('Failed to parse HW capabilities', e);
        }
    }

    updateHwStatus(el, active) {
        if (active) el.classList.add('active');
        else el.classList.remove('active');
    }

    bindEvents() {
        // Activate Button
        this.els.btnActivate.addEventListener('click', () => {
            this.publishMsg(this.topics.operatorConfirm, 'ACTIVATE');
            this.log('Action: Sending activation confirmation...', 'system');
        });

        // Mode Buttons
        this.els.btnScan.addEventListener('click', () => this.setMode('SCAN'));
        this.els.btnDetect.addEventListener('click', () => this.setMode('DETECT'));
        
        // Spray Button (Safety Modal)
        this.els.btnSpray.addEventListener('click', () => {
            this.pendingMode = 'SPRAY';
            this.showModal();
        });

        // Emergency Stop
        this.els.btnEmergency.addEventListener('click', () => {
            this.publishMsg(this.topics.setMode, 'SAFE');
            this.log('EMERGENCY: SAFE mode commanded!', 'error');
            this.playAlertSound();
        });

        // Modal Actions
        this.els.modalCancel.addEventListener('click', () => this.hideModal());
        this.els.modalConfirm.addEventListener('click', () => {
            if (this.pendingMode) {
                this.setMode(this.pendingMode);
                this.hideModal();
            }
        });

        // Feed Selection
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
        
        // Highlight active mode button
        document.querySelectorAll('.btn-mode').forEach(btn => btn.classList.remove('active'));
        if (mode === 'SCAN') this.els.btnScan.classList.add('active');
        if (mode === 'DETECT') this.els.btnDetect.classList.add('active');
    }

    publishMsg(topic, data) {
        if (!topic) return;
        const msg = new ROSLIB.Message({ data: data });
        topic.publish(msg);
    }

    updateVideoFeed(topic) {
        const hostname = window.location.hostname || 'agribot.local';
        const url = `http://${hostname}:8080/stream?topic=${topic}&quality=30&width=640&height=480`;
        this.els.videoFeed.src = url;
        document.getElementById('stream-topic').innerText = topic;
    }

    log(msg, type = 'system') {
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;
        const time = new Date().toLocaleTimeString([], { hour12: false });
        entry.innerText = `[${time}] ${msg}`;
        this.els.logWindow.prepend(entry);
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

            // Simple latency simulation or fetch from diagnostic topic if available
            // this.els.statLatency.innerText = '12ms';
        }, 2000);
    }

    playAlertSound() {
        // Generate a simple beep using Web Audio API
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioCtx.createOscillator();
        oscillator.type = 'square';
        oscillator.frequency.setValueAtTime(440, audioCtx.currentTime);
        oscillator.connect(audioCtx.destination);
        oscillator.start();
        oscillator.stop(audioCtx.currentTime + 0.2);
    }
}

// Start Dashboard
window.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new AgribotDashboard();
});
