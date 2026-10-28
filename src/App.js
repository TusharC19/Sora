import React, { useState, useRef } from 'react';
import './App.css';

const API_BASE = 'http://localhost:8000';

function App() {
  const [videoFile, setVideoFile] = useState(null);
  const [videoId, setVideoId] = useState(null);
  const [videoSrc, setVideoSrc] = useState(null);
  const [analysisData, setAnalysisData] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [isAsking, setIsAsking] = useState(false);
  const [geminiKey, setGeminiKey] = useState('');

  const videoRef = useRef(null);

  // Jump video player to exact timestamp
  const seekTo = (seconds) => {
    if (videoRef.current) {
      videoRef.current.currentTime = seconds;
      videoRef.current.play();
    }
  };

  // Handle local video selection & upload
  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setVideoFile(file);
    setVideoSrc(URL.createObjectURL(file));
    setAnalysisData(null);
    setAnswer(null);

    // Auto-upload to backend
    const formData = new FormData();
    formData.append('file', file);

    setIsUploading(true);
    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error('Failed to upload video');
      const data = await res.json();
      setVideoId(data.video_id);
    } catch (err) {
      alert(`Upload error: ${err.message}. Make sure the FastAPI backend is running!`);
    } finally {
      setIsUploading(false);
    }
  };

  // Run YOLO + ByteTrack event extraction
  const handleProcessVideo = async () => {
    if (!videoId) return;

    setIsProcessing(true);
    try {
      const res = await fetch(`${API_BASE}/api/process/${videoId}?sample_rate=1.0`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Video processing failed');
      const data = await res.json();
      setAnalysisData(data);
    } catch (err) {
      alert(`Analysis error: ${err.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  // Ask natural language question
  const handleAsk = async (e) => {
    e.preventDefault();
    if (!question.trim() || !videoId) return;

    setIsAsking(true);
    try {
      const res = await fetch(`${API_BASE}/api/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_id: videoId,
          question: question,
          gemini_api_key: geminiKey || undefined,
        }),
      });
      if (!res.ok) throw new Error('Query failed');
      const data = await res.json();
      setAnswer(data);
    } catch (err) {
      alert(`Query error: ${err.message}`);
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <div className="sora-app">
      {/* Header */}
      <header className="sora-header">
        <div className="brand-section">
          <div className="brand-logo">SORA</div>
          <div className="brand-tagline">Searchable Observation & Reasoning Assistant</div>
        </div>
        <div className="status-badge">
          <div className="status-dot"></div>
          AI Forensics Engine Ready
        </div>
      </header>

      {/* Main Content Grid */}
      <main className="sora-main">
        {/* Left Column: Video & Controls */}
        <div className="video-column">
          <div className="card">
            <div className="video-container">
              {videoSrc ? (
                <video
                  ref={videoRef}
                  src={videoSrc}
                  controls
                  className="video-player"
                />
              ) : (
                <div className="video-placeholder">
                  <svg width="48" height="48" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  <span>Select an MP4 video to begin analysis</span>
                </div>
              )}
            </div>

            <div className="toolbar">
              <div className="file-input-wrapper">
                <button className="btn btn-primary" disabled={isUploading || isProcessing}>
                  {isUploading ? 'Uploading Video...' : '📁 Select Video'}
                </button>
                <input
                  type="file"
                  accept="video/mp4,video/mov,video/webm"
                  onChange={handleFileChange}
                  disabled={isUploading || isProcessing}
                />
              </div>

              {videoId && (
                <button
                  className="btn btn-accent"
                  onClick={handleProcessVideo}
                  disabled={isProcessing}
                >
                  {isProcessing ? '⚡ Analyzing Video (YOLO + Tracking)...' : '⚡ Extract Events'}
                </button>
              )}

              {videoFile && (
                <div className="video-meta-pill">
                  {videoFile.name} {analysisData && `(${analysisData.duration_formatted})`}
                </div>
              )}
            </div>
          </div>

          {/* Ask SORA Section */}
          <div className="card ask-sora-card">
            <h3>💬 Ask SORA (Evidence-Backed Q&A)</h3>
            <form onSubmit={handleAsk}>
              <div className="ask-input-row">
                <input
                  type="text"
                  className="input-box"
                  placeholder="e.g. When did someone approach the bag? Did anyone enter at night?"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  disabled={!analysisData || isAsking}
                />
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!analysisData || !question.trim() || isAsking}
                >
                  {isAsking ? 'Searching...' : 'Ask'}
                </button>
              </div>

              {/* Optional Gemini API Key input for advanced reasoning */}
              <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '11px', color: '#94a3b8' }}>Gemini Free API Key (optional):</span>
                <input
                  type="password"
                  placeholder="Paste free Gemini API key (optional)"
                  value={geminiKey}
                  onChange={(e) => setGeminiKey(e.target.value)}
                  style={{
                    fontSize: '11px',
                    padding: '4px 8px',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '4px',
                    color: '#fff',
                    flex: 1
                  }}
                />
              </div>
            </form>

            {answer && (
              <div className="answer-box">
                <div style={{ whiteSpace: 'pre-wrap' }}>{answer.answer}</div>
                {answer.evidence && answer.evidence.length > 0 && (
                  <div className="evidence-chips">
                    <span style={{ fontSize: '12px', color: '#94a3b8' }}>Jump to evidence:</span>
                    {answer.evidence.map((ts, idx) => {
                      const [m, s] = ts.split(':').map(Number);
                      const sec = m * 60 + s;
                      return (
                        <span
                          key={idx}
                          className="timestamp-pill"
                          onClick={() => seekTo(sec)}
                          title="Click to jump in video"
                        >
                          ▶ {ts}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Interactive Event Timeline */}
        <div className="timeline-column">
          <div className="card timeline-card">
            <div className="timeline-header">
              <h3>Structured Event Timeline</h3>
              <span className="event-count">
                {analysisData ? `${analysisData.total_events} events` : '0 events'}
              </span>
            </div>

            <div className="events-list">
              {analysisData && analysisData.events.length > 0 ? (
                analysisData.events.map((ev, index) => (
                  <div
                    key={index}
                    className="event-item"
                    onClick={() => seekTo(ev.time_seconds)}
                    title="Click to jump to this moment"
                  >
                    <div className="event-time">{ev.timestamp}</div>
                    <div className="event-details">
                      <span className={`event-type ${ev.severity || 'info'}`}>
                        {ev.type}
                      </span>
                      <span className="event-desc">{ev.description}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="empty-state">
                  {isProcessing
                    ? 'Processing video frames with YOLOv8 & ByteTrack...'
                    : 'Upload a video and click "Extract Events" to generate the interactive timeline.'}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
