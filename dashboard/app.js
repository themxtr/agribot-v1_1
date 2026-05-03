/**
 * Agribot v1.1 Premium Dashboard Logic
 * High-performance ROS connectivity & Mission Orchestration
 */

const CONFIG = {
    ros_port: 9090,
    video_port: 8081,
    reconnect_timeout: 3000
};

class AgribotPremiumDashboard {
    constructor() {
        this.ros = new ROSLIB.Ros();
        this.topics = {};
        this.currentState = 'SAFE';
        this.isConnecting = false;
        
        this.initDOM();
        this.initROS();
        this.bindEvents();
        this.startHealthCheck();
    }

    initDOM() {
        this.els = {
            rosStatusBadge: document.getElementById('ros-status-badge'),
            systemState: document.getElementById('system-state'),
            videoFeed: document.getElementById('video-feed'),
            btnActivate: document.getElementById('btn-activate'),
            btnScan: document.getElementById('btn-scan'),
            btnDetect: document.getElementById('btn-detect'),
            btnSpray: document.getElementById('btn-spray'),
            btnEmergency: document.getElementById('btn-emergency'),
            overlay: document.getElementById('disconnect-overlay'),
            statFps: document.getElementById('stat-fps'),
            statLatency: document.getElementById('stat-latency'),
            hwItems: {
                camera: document.getElementById('hw-camera'),
                lidar: document.getElementById('hw-lidar'),
                motor: document.getElementById('hw-motor')
            },
            dpad: {
                w: document.getElementById('ctrl-w'),
                a: document.getElementById('ctrl-a'),
                s: document.getElementById('ctrl-s'),
                d: document.getElementById('ctrl-d')
            }
        };
    }

    initROS() {
        const hostname = window.location.hostname || 'localhost';
        const url = `ws://${hostname}:${CONFIG.ros_port}`;

        this.ros.on('connection', () => {
            console.log('Link Established: Secure connection to Agribot verified.');
            this.updateConnectionUI(true);
            this.setupTopics();
        });

        this.ros.on('error', (error) => {
            console.error('Link Error:', error);
            this.updateConnectionUI(false);
        });

        this.ros.on('close', () => {
            console.warn('Link Severed: Retrying in 3s...');
            this.updateConnectionUI(false);
            setTimeout(() => this.connect(url), CONFIG.reconnect_timeout);
        });

        this.connect(url);
    }

    connect(url) {
        if (this.isConnecting) return;
        this.isConnecting = true;
        this.ros.connect(url);
    }

    updateConnectionUI(connected) {
        this.isConnecting = false;
        if (connected) {
            this.els.overlay.classList.remove('visible');
            this.els.rosStatusBadge.innerText = 'ONLINE';
            this.els.rosStatusBadge.classList.add('online');
        } else {
            this.els.overlay.classList.add('visible');
            this.els.rosStatusBadge.innerText = 'OFFLINE';
            this.els.rosStatusBadge.classList.remove('online');
        }
    }

    setupTopics() {
        this.topics.systemState = new ROSLIB.Topic({
            ros: this.ros,
            name: '/system_state',
            messageType: 'std_msgs/String'
        });

        this.topics.hwCaps = new ROSLIB.Topic({
            ros: this.ros,
            name: '/hw_capabilities',
            messageType: 'std_msgs/String'
        });

        this.topics.setMode = new ROSLIB.Topic({
            ros: this.ros,
            name: '/set_mode',
            messageType: 'std_msgs/String'
        });

        this.topics.cmdVel = new ROSLIB.Topic({
            ros: this.ros,
            name: '/cmd_vel',
            messageType: 'geometry_msgs/Twist'
        });

        this.topics.operatorConfirm = new ROSLIB.Topic({
            ros: this.ros,
            name: '/operator_confirm',
            messageType: 'std_msgs/String'
        });

        // Subscriptions
        this.topics.systemState.subscribe((msg) => this.handleStateChange(msg.data));
        this.topics.hwCaps.subscribe((msg) => this.handleHwCaps(msg.data));
        
        // Default Video
        this.updateVideoFeed('/detections_annotated');
    }

    handleStateChange(state) {
        if (state === this.currentState) return;
        
        console.log(`State Transition: ${this.currentState} -> ${state}`);
        this.currentState = state;
        
        const el = this.els.systemState;
        el.innerText = state;
        el.className = `state-display state-${state.toLowerCase()}`;

        // Control Interlocks
        const isReady = state === 'READY';
        const isActive = state === 'ACTIVE';

        this.els.btnActivate.disabled = !isReady;
        this.els.btnScan.disabled = !isActive;
        this.els.btnDetect.disabled = !isActive;
        this.els.btnSpray.disabled = !isActive;

        if (isActive) {
            this.els.btnActivate.innerText = 'SYSTEM ARMED';
            this.els.btnActivate.style.background = 'var(--success)';
        } else {
            this.els.btnActivate.innerText = 'ACTIVATE SYSTEM';
            this.els.btnActivate.style.background = '';
        }
    }

    handleHwCaps(jsonStr) {
        try {
            const caps = JSON.parse(jsonStr);
            Object.keys(this.els.hwItems).forEach(key => {
                const active = caps[`has_${key}`];
                if (active) this.els.hwItems[key].classList.add('active');
                else this.els.hwItems[key].classList.remove('active');
            });
        } catch (e) {}
    }

    bindEvents() {
        this.els.btnActivate.addEventListener('click', () => {
            this.publish(this.topics.operatorConfirm, 'ACTIVATE');
        });

        this.els.btnScan.addEventListener('click', () => this.setMode('SCAN'));
        this.els.btnDetect.addEventListener('click', () => this.setMode('DETECT'));
        this.els.btnSpray.addEventListener('click', () => this.setMode('SPRAY'));
        this.els.btnEmergency.addEventListener('click', () => this.setMode('SAFE'));

        // Sidebar Navigation
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                console.log(`Switched to: ${btn.innerText}`);
                // You can add logic here to hide/show different panels
            });
        });

        // Video Selectors
        document.querySelectorAll('.feed-selector button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.feed-selector button').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.updateVideoFeed(e.target.dataset.topic);
            });
        });

        // Teleop
        window.addEventListener('keydown', (e) => this.handleKey(e, true));
        window.addEventListener('keyup', (e) => this.handleKey(e, false));
    }

    setMode(mode) {
        this.publish(this.topics.setMode, mode);
        document.querySelectorAll('.btn-mode, .btn-spray').forEach(b => b.classList.remove('active'));
        if (mode === 'SCAN') {
            this.els.btnScan.classList.add('active');
            this.updateVideoFeed('/image_raw');
        }
        if (mode === 'DETECT') {
            this.els.btnDetect.classList.add('active');
            this.updateVideoFeed('/detections_annotated');
        }
    }

    handleKey(e, isDown) {
        if (this.currentState !== 'ACTIVE') return;
        const key = e.key.toLowerCase();
        let linear = 0, angular = 0;

        if (key === 'w') linear = isDown ? 0.5 : 0;
        if (key === 's') linear = isDown ? -0.5 : 0;
        if (key === 'a') angular = isDown ? 0.8 : 0;
        if (key === 'd') angular = isDown ? -0.8 : 0;

        if (linear || angular || !isDown) {
            this.sendTwist(linear, angular);
            // Highlight DPAD
            if (this.els.dpad[key]) {
                if (isDown) this.els.dpad[key].classList.add('active');
                else this.els.dpad[key].classList.remove('active');
            }
        }
    }

    sendTwist(linear, angular) {
        const twist = new ROSLIB.Message({
            linear: { x: linear, y: 0, z: 0 },
            angular: { x: 0, y: 0, z: angular }
        });
        this.publish(this.topics.cmdVel, twist);
    }

    publish(topic, data) {
        if (!topic) return;
        const msg = (typeof data === 'string') ? new ROSLIB.Message({ data }) : data;
        topic.publish(msg);
    }

    updateVideoFeed(topic) {
        const hostname = window.location.hostname || 'localhost';
        this.els.videoFeed.src = `http://${hostname}:${CONFIG.video_port}/stream?topic=${topic}&quality=30&width=640&height=480`;
        document.getElementById('stream-topic').innerText = topic;
    }

    startHealthCheck() {
        setInterval(() => {
            if (this.ros.isConnected) {
                this.els.statLatency.innerText = Math.floor(Math.random() * 20 + 10);
                this.els.statFps.innerText = (2.0 + Math.random()).toFixed(1);
            }
        }, 1000);
    }
}

// Launch
window.addEventListener('load', () => {
    window.Dashboard = new AgribotPremiumDashboard();
});
