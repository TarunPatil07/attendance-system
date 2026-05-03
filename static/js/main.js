// ==================== Tab navigation ====================
const tabButtons = document.querySelectorAll('.tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');

function setActiveTab(tab) {
    tabButtons.forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    tabPanels.forEach((panel) => {
        panel.classList.toggle('active', panel.dataset.tabPanel === tab);
    });
}

if (tabButtons.length) {
    tabButtons.forEach((btn) => {
        btn.addEventListener('click', () => setActiveTab(btn.dataset.tab));
    });

    if (window.location.hash === '#tab-registration') {
        setActiveTab('registration');
    }
}

function setStatus(el, message, isError = false) {
    if (!el) return;
    el.textContent = message || '';
    el.classList.remove('success', 'error');
    if (message) {
        el.classList.add(isError ? 'error' : 'success');
    }
}

// ==================== Webcam helpers ====================
async function startWebcam(videoEl) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('Webcam not supported in this browser.');
        return;
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        videoEl.srcObject = stream;
    } catch (err) {
        console.error('Webcam error', err);
        alert('Unable to access webcam: ' + err.message);
    }
}

function stopWebcam(videoEl) {
    if (videoEl.srcObject) {
        const tracks = videoEl.srcObject.getTracks();
        tracks.forEach((track) => track.stop());
        videoEl.srcObject = null;
    }
}

function captureFrame(videoEl, canvasEl) {
    const width = videoEl.videoWidth;
    const height = videoEl.videoHeight;
    if (!width || !height) return null;
    canvasEl.width = width;
    canvasEl.height = height;
    const ctx = canvasEl.getContext('2d');
    ctx.drawImage(videoEl, 0, 0, width, height);
    return canvasEl.toDataURL('image/png');
}

// ==================== Student Registration: Upload ====================
const formRegisterUpload = document.getElementById('form-register-upload');
if (formRegisterUpload) {
    const statusEl = document.getElementById('status-register-upload');
    formRegisterUpload.addEventListener('submit', async (e) => {
        e.preventDefault();
        setStatus(statusEl, 'Registering student from uploaded images...');

        const formData = new FormData(formRegisterUpload);
        try {
            const res = await fetch('/api/students/register/upload', {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.message || 'Registration failed');
            }
            setStatus(
                statusEl,
                data.message + (data.embeddings_saved ? ` (Faces saved: ${data.embeddings_saved})` : ''),
                false
            );
            formRegisterUpload.reset();
        } catch (err) {
            console.error(err);
            setStatus(statusEl, err.message, true);
        }
    });
}

// ==================== Student Registration: Webcam ====================
const formRegisterWebcam = document.getElementById('form-register-webcam');
if (formRegisterWebcam) {
    const video = document.getElementById('webcam-register');
    const canvas = document.getElementById('canvas-register');
    const btnStart = document.getElementById('btn-start-webcam-register');
    const btnCapture = document.getElementById('btn-capture-register');
    const statusEl = document.getElementById('status-register-webcam');

    btnStart.addEventListener('click', () => {
        startWebcam(video);
    });

    btnCapture.addEventListener('click', async () => {
        setStatus(statusEl, 'Capturing and registering student...');
        const imgData = captureFrame(video, canvas);
        if (!imgData) {
            setStatus(statusEl, 'Camera not ready. Please try again.', true);
            return;
        }

        stopWebcam(video);

        const formData = new FormData(formRegisterWebcam);
        const student_id = formData.get('student_id');
        const name = formData.get('name');
        const email = formData.get('email');

        if (!student_id || !name) {
            setStatus(statusEl, 'Student ID and Name are required.', true);
            return;
        }

        try {
            const res = await fetch('/api/students/register/webcam', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ student_id, name, email, imageData: imgData }),
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.message || 'Registration via webcam failed');
            }
            setStatus(statusEl, data.message, false);
            formRegisterWebcam.reset();
        } catch (err) {
            console.error(err);
            setStatus(statusEl, err.message, true);
        }
    });
}

// ==================== Group Attendance ====================
const btnStartWebcamAttendance = document.getElementById('btn-start-webcam-attendance');
const btnCaptureAttendance = document.getElementById('btn-capture-attendance');
const btnTakeAttendance = document.getElementById('btn-take-attendance');

if (btnTakeAttendance) {
    const videoAtt = document.getElementById('webcam-attendance');
    const canvasAtt = document.getElementById('canvas-attendance');
    const hiddenInput = document.getElementById('attendance-webcam-data');
    const statusUpload = document.getElementById('status-attendance-upload');
    const statusWebcam = document.getElementById('status-attendance-webcam');
    const fileInput = document.getElementById('attendance-group-image');
    const summaryContainer = document.getElementById('attendance-summary');
    const tablePresentBody = document.getElementById('table-present-body');
    const tableAbsentBody = document.getElementById('table-absent-body');

    if (btnStartWebcamAttendance) {
        btnStartWebcamAttendance.addEventListener('click', () => {
            startWebcam(videoAtt);
        });
    }

    if (btnCaptureAttendance) {
        btnCaptureAttendance.addEventListener('click', () => {
            const imgData = captureFrame(videoAtt, canvasAtt);
            if (!imgData) {
                setStatus(statusWebcam, 'Camera not ready. Please try again.', true);
                return;
            }
            stopWebcam(videoAtt);
            hiddenInput.value = imgData;
            setStatus(statusWebcam, 'Frame captured. Click TAKE ATTENDANCE to process.');
        });
    }

    btnTakeAttendance.addEventListener('click', async () => {
        setStatus(statusUpload, '');
        setStatus(statusWebcam, '');
        setStatus(statusUpload, 'Processing attendance...');

        let endpoint = '';
        let options = {};

        if (fileInput && fileInput.files && fileInput.files.length > 0) {
            endpoint = '/api/attendance/upload';
            const formData = new FormData();
            formData.append('group_image', fileInput.files[0]);
            options = { method: 'POST', body: formData };
        } else if (hiddenInput && hiddenInput.value) {
            endpoint = '/api/attendance/webcam';
            options = {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ imageData: hiddenInput.value }),
            };
        } else {
            setStatus(statusUpload, 'Please upload a group image or capture via webcam first.', true);
            return;
        }

        try {
            const res = await fetch(endpoint, options);
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.message || 'Attendance processing failed');
            }

            const summary = data.summary || { present: [], absent: [] };

            // Populate present table
            tablePresentBody.innerHTML = '';
            (summary.present || []).forEach((row) => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${row.name}</td>
                    <td>${row.student_id}</td>
                    <td>${row.timestamp || ''}</td>
                    <td>${row.image_path ? `<img src="/${row.image_path}" alt="thumb" />` : ''}</td>
                `;
                tablePresentBody.appendChild(tr);
            });

            // Populate absent table
            tableAbsentBody.innerHTML = '';
            (summary.absent || []).forEach((row) => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${row.name}</td>
                    <td>${row.student_id}</td>
                `;
                tableAbsentBody.appendChild(tr);
            });

            summaryContainer.classList.remove('hidden');
            setStatus(statusUpload, 'Attendance processed successfully. Summary updated.', false);
        } catch (err) {
            console.error(err);
            setStatus(statusUpload, err.message, true);
        }
    });
}

// ==================== Download Attendance ====================
const btnDownloadExcel = document.getElementById('btn-download-excel');
if (btnDownloadExcel) {
    btnDownloadExcel.addEventListener('click', () => {
        const presentRows = Array.from(document.querySelectorAll('#table-present-body tr'));
        const absentRows = Array.from(document.querySelectorAll('#table-absent-body tr'));

        const rows = [['Status', 'Name', 'Student ID', 'Timestamp']];

        presentRows.forEach((tr) => {
            const tds = tr.querySelectorAll('td');
            rows.push(['Present', tds[0].textContent, tds[1].textContent, tds[2]?.textContent || '']);
        });

        absentRows.forEach((tr) => {
            const tds = tr.querySelectorAll('td');
            rows.push(['Absent', tds[0].textContent, tds[1].textContent, '']);
        });

        const csvContent = rows.map((r) => r.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(',')).join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);

        const link = document.createElement('a');
        link.setAttribute('href', url);
        link.setAttribute('download', `attendance_${new Date().toISOString().slice(0, 10)}.csv`);
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    });
}

// ==================== Notification Settings ====================
const formNotifyConfig = document.getElementById('form-notify-config');
if (formNotifyConfig) {
    const statusEl = document.getElementById('status-notify-config');

    (async () => {
        try {
            const res = await fetch('/api/notifications/config');
            if (!res.ok) return;
            const cfg = await res.json();
            if (!cfg) return;

            formNotifyConfig.smtp_server.value = cfg.smtp_server || '';
            formNotifyConfig.smtp_port.value = cfg.smtp_port || '';
            formNotifyConfig.smtp_username.value = cfg.smtp_username || '';
            formNotifyConfig.smtp_password.value = cfg.smtp_password || '';
            formNotifyConfig.from_email.value = cfg.from_email || '';
            formNotifyConfig.use_tls.checked = cfg.use_tls !== false;
            formNotifyConfig.auto_email_enabled.checked = !!cfg.auto_email_enabled;
        } catch (err) {
            console.error('Failed to load notification config', err);
        }
    })();

    formNotifyConfig.addEventListener('submit', async (e) => {
        e.preventDefault();
        setStatus(statusEl, 'Saving notification settings...');

        const body = {
            smtp_server: formNotifyConfig.smtp_server.value,
            smtp_port: formNotifyConfig.smtp_port.value ? parseInt(formNotifyConfig.smtp_port.value, 10) : null,
            smtp_username: formNotifyConfig.smtp_username.value,
            smtp_password: formNotifyConfig.smtp_password.value,
            from_email: formNotifyConfig.from_email.value,
            use_tls: formNotifyConfig.use_tls.checked,
            auto_email_enabled: formNotifyConfig.auto_email_enabled.checked,
        };

        try {
            const res = await fetch('/api/notifications/save', {
                method: 'POST',
                body: new URLSearchParams(body),
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.message || 'Failed to save settings');
            }
            setStatus(statusEl, data.message, false);
        } catch (err) {
            console.error(err);
            setStatus(statusEl, err.message, true);
        }
    });
}

// ==================== Send Absentee Emails ====================
const formNotifySend = document.getElementById('form-notify-send');
if (formNotifySend) {
    const statusEl = document.getElementById('status-notify-send');
    formNotifySend.addEventListener('submit', async (e) => {
        e.preventDefault();
        setStatus(statusEl, 'Sending absentee emails...');

        const date = formNotifySend.date.value || null;
        const body = date ? { date } : {};

        try {
            const res = await fetch('/api/notifications/send_absent', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.message || 'Failed to send absentee emails');
            }
            setStatus(statusEl, data.message, false);
        } catch (err) {
            console.error(err);
            setStatus(statusEl, err.message, true);
        }
    });
}
