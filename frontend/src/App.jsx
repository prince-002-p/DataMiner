import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { 
  Play, Pause, Square, Download, Trash2, RefreshCw, 
  Settings, Database, Award, Shield, FileText, Check, List, User
} from 'lucide-react';

const API_BASE = "http://localhost:8000";

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [username, setUsername] = useState(localStorage.getItem('username') || '');
  const [isRegistering, setIsRegistering] = useState(false);
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  
  // Dashboard Configurations
  const [boards] = useState(["cbse", "icse", "ib", "state-board", "pre-primary"]);
  const [selectedBoard, setSelectedBoard] = useState("cbse");
  const [states, setStates] = useState([]);
  const [selectedState, setSelectedState] = useState("");
  const [districts, setDistricts] = useState([]);
  const [selectedDistricts, setSelectedDistricts] = useState([]);
  const [districtSearch, setDistrictSearch] = useState("");
  
  // Column Fields Configuration
  const allFields = [
    "School Name", "UDISE", "Affiliation Number", "Address", "Village", "City", 
    "District", "State", "PIN Code", "Phone", "Mobile", "Email", "Website", 
    "Principal", "Category", "Management", "School Type", "Medium", "Latitude", 
    "Longitude", "Established Year"
  ];
  const [selectedFields, setSelectedFields] = useState([
    "School Name", "Address", "District", "State", "PIN Code", "Phone", "Mobile", "Email", "Website"
  ]);
  const [presets, setPresets] = useState([]);
  const [newPresetName, setNewPresetName] = useState("");
  
  // Output Configs
  const [outputFormat, setOutputFormat] = useState("xlsx"); // xlsx, csv, both
  const [outputFolder, setOutputFolder] = useState("Output");
  
  // System Statistics
  const [stats, setStats] = useState({
    total_records: 0,
    completed_jobs: 0,
    running_jobs: 0,
    failed_jobs: 0,
    average_speed: 0.0,
    today_reports: 0
  });

  // Jobs List & Active Job
  const [jobs, setJobs] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [logs, setLogs] = useState([]);
  
  // Notifications
  const [toastMessage, setToastMessage] = useState("");
  
  // Axios Auth configuration
  const authConfig = {
    headers: { Authorization: `Bearer ${token}` }
  };

  // Poll Ref for cleanup
  const pollIntervalRef = useRef(null);

  // Show status toasts
  const triggerToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(""), 3000);
  };

  // Logout Handler
  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    setToken('');
    setUsername('');
    triggerToast("Logged out successfully");
  };

  // Login Handler
  const handleLogin = async (e) => {
    e.preventDefault();
    if (!authUsername || !authPassword) return;
    try {
      const params = new URLSearchParams();
      params.append('username', authUsername);
      params.append('password', authPassword);
      
      const response = await axios.post(`${API_BASE}/api/auth/login`, params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });
      
      const { access_token, username: loggedInName } = response.data;
      localStorage.setItem('token', access_token);
      localStorage.setItem('username', loggedInName);
      setToken(access_token);
      setUsername(loggedInName);
      setAuthUsername('');
      setAuthPassword('');
      triggerToast("Logged in successfully!");
    } catch (err) {
      console.error(err);
      triggerToast(err.response?.data?.detail || "Authentication Failed");
    }
  };

  // Registration Handler
  const handleRegister = async (e) => {
    e.preventDefault();
    if (!authUsername || !authPassword) return;
    try {
      await axios.post(`${API_BASE}/api/auth/register`, {
        username: authUsername,
        password: authPassword
      });
      triggerToast("Account registered! Please login.");
      setIsRegistering(false);
      setAuthPassword('');
    } catch (err) {
      console.error(err);
      triggerToast(err.response?.data?.detail || "Registration failed");
    }
  };

  // Fetch static states on login
  useEffect(() => {
    if (!token) return;
    axios.get(`${API_BASE}/api/data/states`, authConfig)
      .then(res => {
        setStates(res.data);
        if (res.data.length > 0) setSelectedState(res.data[0].slug);
      })
      .catch(err => console.error("Error loading states", err));
      
    fetchStatsAndPresets();
    fetchJobs();
  }, [token]);

  // Fetch stats and field presets
  const fetchStatsAndPresets = () => {
    axios.get(`${API_BASE}/api/stats`, authConfig)
      .then(res => setStats(res.data))
      .catch(err => console.error("Error loading statistics", err));

    axios.get(`${API_BASE}/api/presets`, authConfig)
      .then(res => setPresets(res.data))
      .catch(err => console.error("Error loading presets", err));
  };

  // Fetch jobs
  const fetchJobs = () => {
    axios.get(`${API_BASE}/api/jobs`, authConfig)
      .then(res => {
        setJobs(res.data);
        // If there's a running/paused job, set it as active
        const active = res.data.find(j => j.status === 'RUNNING' || j.status === 'PAUSED');
        if (active && !activeJob) {
          setActiveJob(active);
        }
      })
      .catch(err => console.error("Error loading jobs", err));
  };

  // Fetch districts list dynamically when board or state changes
  useEffect(() => {
    if (!token || !selectedState) return;
    setDistricts([]);
    setSelectedDistricts([]);
    
    axios.get(`${API_BASE}/api/data/districts?board=${selectedBoard}&state=${selectedState}`, authConfig)
      .then(res => {
        setDistricts(res.data);
      })
      .catch(err => {
        console.error("Error loading districts", err);
        triggerToast("Failed to fetch districts for state/board");
      });
  }, [selectedBoard, selectedState, token]);

  // Handle active job polling
  useEffect(() => {
    if (!token || !activeJob) {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      return;
    }
    
    const isRunning = activeJob.status === "RUNNING" || activeJob.status === "PAUSED";
    
    // Quick logs and job status fetch
    const pollFunc = () => {
      axios.get(`${API_BASE}/api/jobs/${activeJob.id}`, authConfig)
        .then(res => {
          setActiveJob(res.data);
          if (res.data.status !== "RUNNING" && res.data.status !== "PAUSED") {
            // Stop polling since job ended
            clearInterval(pollIntervalRef.current);
            fetchStatsAndPresets();
            fetchJobs();
            triggerToast(`Job finished with status: ${res.data.status}`);
          }
        })
        .catch(err => console.error(err));

      axios.get(`${API_BASE}/api/logs?job_id=${activeJob.id}`, authConfig)
        .then(res => setLogs(res.data))
        .catch(err => console.error(err));
    };

    pollFunc();
    
    if (isRunning) {
      pollIntervalRef.current = setInterval(pollFunc, 1500);
    } else {
      // Just one-off log load for completed/stopped jobs
      axios.get(`${API_BASE}/api/logs?job_id=${activeJob.id}`, authConfig)
        .then(res => setLogs(res.data))
        .catch(err => console.error(err));
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [activeJob?.id, activeJob?.status, token]);

  // Dispatch Scraper Start
  const handleStartScraping = async () => {
    if (selectedDistricts.length === 0) {
      triggerToast("Please select at least one district");
      return;
    }
    if (selectedFields.length === 0) {
      triggerToast("Please select at least one data field");
      return;
    }
    try {
      const createRes = await axios.post(`${API_BASE}/api/jobs`, {
        board: selectedBoard,
        state: selectedState,
        districts: selectedDistricts,
        fields: selectedFields,
        output_format: outputFormat,
        output_folder: outputFolder
      }, authConfig);
      
      const newJob = createRes.data;
      
      await axios.post(`${API_BASE}/api/jobs/${newJob.id}/start`, {}, authConfig);
      triggerToast("Scraper background worker dispatched!");
      
      // Select new job
      setActiveJob(newJob);
      fetchJobs();
      fetchStatsAndPresets();
    } catch (err) {
      console.error(err);
      triggerToast("Failed to dispatch scraper");
    }
  };

  // Job Controls API Calls
  const handlePause = async () => {
    if (!activeJob) return;
    try {
      await axios.post(`${API_BASE}/api/jobs/${activeJob.id}/pause`, {}, authConfig);
      triggerToast("Scraper pause signal sent.");
      fetchJobs();
    } catch (err) {
      triggerToast("Pause signal failed");
    }
  };

  const handleResume = async () => {
    if (!activeJob) return;
    try {
      await axios.post(`${API_BASE}/api/jobs/${activeJob.id}/resume`, {}, authConfig);
      triggerToast("Scraper resume signal sent.");
      fetchJobs();
    } catch (err) {
      triggerToast("Resume signal failed");
    }
  };

  const handleStop = async () => {
    if (!activeJob) return;
    try {
      await axios.post(`${API_BASE}/api/jobs/${activeJob.id}/stop`, {}, authConfig);
      triggerToast("Scraper termination signal sent.");
      fetchJobs();
    } catch (err) {
      triggerToast("Termination signal failed");
    }
  };

  const handleDeleteJob = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this job? All records will be removed.")) return;
    try {
      await axios.delete(`${API_BASE}/api/jobs/${id}`, authConfig);
      triggerToast("Job deleted");
      if (activeJob?.id === id) setActiveJob(null);
      fetchJobs();
      fetchStatsAndPresets();
    } catch (err) {
      triggerToast(err.response?.data?.detail || "Delete failed");
    }
  };

  // Presets Handlers
  const handleLoadPreset = (presetFields) => {
    setSelectedFields(presetFields);
    triggerToast("Preset selection loaded.");
  };

  const handleSavePreset = async () => {
    if (!newPresetName) return;
    try {
      await axios.post(`${API_BASE}/api/presets`, {
        name: newPresetName,
        fields: selectedFields
      }, authConfig);
      triggerToast("Preset selection saved successfully!");
      setNewPresetName("");
      fetchStatsAndPresets();
    } catch (err) {
      triggerToast("Failed to save preset");
    }
  };

  // Filter districts display list
  const filteredDistricts = districts.filter(d => 
    d.toLowerCase().includes(districtSearch.toLowerCase())
  );

  // Download Trigger Handler
  const handleDownload = (jobId, format) => {
    const url = `${API_BASE}/api/exports/${jobId}/download?format=${format}`;
    // Fetch file using axios or window.open with auth header
    // Simple way is to fetch with axios, convert to blob, and save
    axios({
      url: url,
      method: 'GET',
      responseType: 'blob',
      headers: { Authorization: `Bearer ${token}` }
    }).then((response) => {
      const fileURL = window.URL.createObjectURL(new Blob([response.data]));
      const fileLink = document.createElement('a');
      fileLink.href = fileURL;
      fileLink.setAttribute('download', `schoolminer_job_${jobId}_report.${format}`);
      document.body.appendChild(fileLink);
      fileLink.click();
      document.body.removeChild(fileLink);
    }).catch(err => {
      console.error(err);
      triggerToast("Failed to download file");
    });
  };

  // Copy Logs to Clipboard
  const handleCopyLogs = () => {
    const rawLogs = logs.map(l => `[${l.timestamp.slice(11, 19)}] [${l.level}] ${l.message}`).join("\n");
    navigator.clipboard.writeText(rawLogs)
      .then(() => triggerToast("Logs copied to clipboard!"))
      .catch(() => triggerToast("Clipboard copy failed"));
  };

  // Calculation of ETA
  const calculateETA = () => {
    if (!activeJob || activeJob.status !== "RUNNING" || activeJob.speed_rpm === 0) return "Calculating...";
    // We don't know total schools since schoolsindia.net page numbers are dynamic,
    // but we can estimate based on number of selected districts.
    // Let's mock a simple message
    return "Dynamic Paginated Scraper";
  };

  // Render Login page if not authenticated
  if (!token) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-header">
            <h1>SchoolMiner Enterprise</h1>
            <p>v5.0 - Data Scraping Portal</p>
          </div>
          <form onSubmit={isRegistering ? handleRegister : handleLogin}>
            <div className="form-group">
              <label>Username</label>
              <input 
                type="text" 
                className="form-input" 
                placeholder="Enter username" 
                value={authUsername}
                onChange={e => setAuthUsername(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label>Password</label>
              <input 
                type="password" 
                className="form-input" 
                placeholder="Enter password" 
                value={authPassword}
                onChange={e => setAuthPassword(e.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn-primary">
              {isRegistering ? "Create Account" : "Access Console"}
            </button>
          </form>
          <div className="auth-switch">
            {isRegistering ? (
              <p>Already have an account? <span onClick={() => setIsRegistering(false)}>Sign In</span></p>
            ) : (
              <p>New setup? <span onClick={() => setIsRegistering(true)}>Create Account</span></p>
            )}
          </div>
        </div>
        {toastMessage && <div className="toast">{toastMessage}</div>}
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      {/* Header Navbar */}
      <div className="navbar">
        <div className="logo-container">
          <Database className="logo-icon" size={24} />
          <span className="logo-text">SchoolMiner Enterprise v5.0</span>
        </div>
        <div className="nav-user">
          <div className="user-badge">
            <User size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'text-bottom' }} />
            {username}
          </div>
          <button className="btn-logout" onClick={handleLogout}>Logout</button>
        </div>
      </div>

      {/* Header Statistics Dashboard */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon-wrapper" style={{ background: 'rgba(59, 130, 246, 0.1)', color: 'var(--accent-primary)' }}>
            <Database size={24} />
          </div>
          <div className="stat-info">
            <h3>Total Records</h3>
            <p>{stats.total_records.toLocaleString()}</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon-wrapper" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--accent-success)' }}>
            <Award size={24} />
          </div>
          <div className="stat-info">
            <h3>Completed Jobs</h3>
            <p>{stats.completed_jobs}</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon-wrapper" style={{ background: 'rgba(139, 92, 246, 0.1)', color: 'var(--accent-purple)' }}>
            <RefreshCw size={24} />
          </div>
          <div className="stat-info">
            <h3>Running Workers</h3>
            <p>{stats.running_jobs}</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon-wrapper" style={{ background: 'rgba(239, 68, 68, 0.1)', color: 'var(--accent-danger)' }}>
            <Shield size={24} />
          </div>
          <div className="stat-info">
            <h3>Failed Workers</h3>
            <p>{stats.failed_jobs}</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon-wrapper" style={{ background: 'rgba(245, 158, 11, 0.1)', color: 'var(--accent-warning)' }}>
            <Play size={24} />
          </div>
          <div className="stat-info">
            <h3>Average Speed</h3>
            <p>{stats.average_speed} RPM</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon-wrapper" style={{ background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-secondary)' }}>
            <FileText size={24} />
          </div>
          <div className="stat-info">
            <h3>Today's Reports</h3>
            <p>{stats.today_reports}</p>
          </div>
        </div>
      </div>

      {/* Main Panel Division */}
      <div className="main-content">
        {/* LEFT COLUMN: CONTROL & SETTINGS */}
        <div className="left-panel">
          <div className="card">
            <h2 className="card-title"><Settings size={18} /> Data Source Config</h2>
            <div className="datasource-grid">
              <div>
                <label style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Select Board</label>
                <select className="dropdown-select" value={selectedBoard} onChange={e => setSelectedBoard(e.target.value)}>
                  {boards.map(b => <option key={b} value={b}>{b.toUpperCase()}</option>)}
                </select>
              </div>
              <div>
                <label style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Select State</label>
                <select className="dropdown-select" value={selectedState} onChange={e => setSelectedState(e.target.value)}>
                  <option value="" disabled>Select State</option>
                  {states.map(s => <option key={s.slug} value={s.slug}>{s.name}</option>)}
                </select>
              </div>
            </div>
            
            {/* Districts Selector */}
            <div style={{ marginBottom: '20px' }}>
              <div className="selection-toolbar">
                <span style={{ fontSize: '13.5px', fontWeight: '600' }}>Districts Selector ({selectedDistricts.length})</span>
                <div className="selection-actions">
                  <button className="btn-text" onClick={() => setSelectedDistricts(districts)}>Select All</button>
                  <button className="btn-text" onClick={() => setSelectedDistricts([])}>Clear All</button>
                </div>
              </div>
              <input 
                type="text" 
                className="form-input" 
                placeholder="Search district name..." 
                value={districtSearch}
                onChange={e => setDistrictSearch(e.target.value)}
                style={{ marginBottom: '8px', padding: '8px 12px' }}
              />
              <div className="scroll-selector">
                {filteredDistricts.length === 0 ? (
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>No districts loaded. Select state first.</span>
                ) : (
                  filteredDistricts.map(d => {
                    const isChecked = selectedDistricts.includes(d);
                    return (
                      <label key={d} className="checkbox-label">
                        <input 
                          type="checkbox" 
                          checked={isChecked}
                          onChange={() => {
                            if (isChecked) {
                              setSelectedDistricts(selectedDistricts.filter(item => item !== d));
                            } else {
                              setSelectedDistricts([...selectedDistricts, d]);
                            }
                          }}
                        />
                        {d}
                      </label>
                    );
                  })
                )}
              </div>
            </div>

            {/* Field Selection Checklist */}
            <div style={{ marginBottom: '20px' }}>
              <div className="selection-toolbar">
                <span style={{ fontSize: '13.5px', fontWeight: '600' }}>Export Parameter Fields ({selectedFields.length})</span>
                <div className="selection-actions">
                  <button className="btn-text" onClick={() => setSelectedFields(allFields)}>Select All</button>
                  <button className="btn-text" onClick={() => setSelectedFields([])}>Clear All</button>
                </div>
              </div>
              <div className="scroll-selector" style={{ maxHeight: '160px' }}>
                {allFields.map(f => {
                  const isChecked = selectedFields.includes(f);
                  return (
                    <label key={f} className="checkbox-label">
                      <input 
                        type="checkbox" 
                        checked={isChecked}
                        onChange={() => {
                          if (isChecked) {
                            setSelectedFields(selectedFields.filter(item => item !== f));
                          } else {
                            setSelectedFields([...selectedFields, f]);
                          }
                        }}
                      />
                      {f}
                    </label>
                  );
                })}
              </div>
              
              {/* Presets Manager */}
              <div style={{ marginTop: '12px' }}>
                <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '4px' }}>
                  {presets.map(p => (
                    <button 
                      key={p.name} 
                      className="btn-small"
                      onClick={() => handleLoadPreset(p.fields)}
                    >
                      {p.name}
                    </button>
                  ))}
                </div>
                <div className="preset-box">
                  <input 
                    type="text" 
                    className="form-input" 
                    placeholder="New preset name..." 
                    value={newPresetName}
                    onChange={e => setNewPresetName(e.target.value)}
                    style={{ padding: '6px 12px', fontSize: '13px' }}
                  />
                  <button className="btn-small" onClick={handleSavePreset}>Save Custom Preset</button>
                </div>
              </div>
            </div>

            {/* Output settings */}
            <div>
              <label style={{ fontSize: '13.5px', fontWeight: '600', display: 'block', marginBottom: '10px' }}>Output Settings</label>
              <div className="output-grid">
                <select className="dropdown-select" value={outputFormat} onChange={e => setOutputFormat(e.target.value)}>
                  <option value="xlsx">Excel (xlsx)</option>
                  <option value="csv">CSV only</option>
                  <option value="both">Both (Excel + CSV)</option>
                </select>
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="Output folder path" 
                  value={outputFolder}
                  onChange={e => setOutputFolder(e.target.value)}
                />
              </div>
            </div>

            <button 
              className="btn-primary" 
              onClick={handleStartScraping}
              disabled={activeJob?.status === "RUNNING" || activeJob?.status === "PAUSED"}
              style={{ marginTop: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
            >
              <Play size={16} /> Dispatched Scraper Task
            </button>
          </div>
        </div>

        {/* RIGHT COLUMN: PROGRESS AND TASKS QUEUE */}
        <div className="right-panel">
          {/* Active Job status Card */}
          <div className="card">
            <h2 className="card-title">
              <RefreshCw size={18} className={activeJob?.status === "RUNNING" ? "spin" : ""} /> 
              Scraper Active Control Console
            </h2>
            {activeJob ? (
              <div className="active-job-details">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '14px', fontWeight: '600' }}>Job ID: #{activeJob.id} ({activeJob.board.toUpperCase()} - {activeJob.state.title()})</span>
                  <span className={`status-badge ${activeJob.status.toLowerCase()}`}>{activeJob.status}</span>
                </div>
                
                {/* Progress bar */}
                <div className="progress-container">
                  <div className="progress-header">
                    <span>Exporting records</span>
                    <span>{activeJob.progress_percent}%</span>
                  </div>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${activeJob.progress_percent}%` }}></div>
                  </div>
                </div>

                {/* Scraper Speed/ETA Grid */}
                <div className="job-params-grid">
                  <div className="job-param-item">
                    <span>Records Scraped</span>
                    <span>{activeJob.total_schools_found}</span>
                  </div>
                  <div className="job-param-item">
                    <span>Current Speed</span>
                    <span>{activeJob.speed_rpm} RPM</span>
                  </div>
                  <div className="job-param-item">
                    <span>Current Target</span>
                    <span>{activeJob.current_district || "Initializing"} (Page {activeJob.current_page})</span>
                  </div>
                  <div className="job-param-item">
                    <span>Errors Resolved</span>
                    <span>{activeJob.errors_count}</span>
                  </div>
                </div>

                {/* Control Actions */}
                <div className="control-actions">
                  {activeJob.status === "RUNNING" && (
                    <button className="btn-icon btn-pause" onClick={handlePause}><Pause size={15} /> Pause</button>
                  )}
                  {activeJob.status === "PAUSED" && (
                    <button className="btn-icon btn-resume" onClick={handleResume}><Play size={15} /> Resume</button>
                  )}
                  {(activeJob.status === "RUNNING" || activeJob.status === "PAUSED") && (
                    <button className="btn-icon btn-stop" onClick={handleStop}><Square size={15} /> Stop</button>
                  )}
                  
                  {activeJob.status === "COMPLETED" && (
                    <div style={{ display: 'flex', gap: '8px', width: '100%' }}>
                      {(activeJob.output_format === "xlsx" || activeJob.output_format === "both") && (
                        <button className="btn-icon btn-resume" onClick={() => handleDownload(activeJob.id, 'xlsx')}><Download size={14} /> Download Excel</button>
                      )}
                      {(activeJob.output_format === "csv" || activeJob.output_format === "both") && (
                        <button className="btn-icon btn-small" onClick={() => handleDownload(activeJob.id, 'csv')}><Download size={14} /> Download CSV</button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <span style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>No active scraping job selected. Configure details on the left to start.</span>
            )}
          </div>

          {/* Past Jobs List Queue */}
          <div className="card">
            <h2 className="card-title"><List size={18} /> History Scraper Queue</h2>
            <div className="jobs-list">
              {jobs.length === 0 ? (
                <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No completed scrapers in history database.</span>
              ) : (
                jobs.map(job => (
                  <div 
                    key={job.id} 
                    className={`job-item ${activeJob?.id === job.id ? 'active' : ''}`}
                    onClick={() => setActiveJob(job)}
                  >
                    <div className="job-item-info">
                      <span>Job #{job.id}: {job.board.toUpperCase()} - {job.state.title()}</span>
                      <span>Records: {job.total_schools_found} | Speed: {job.speed_rpm} RPM | Status: {job.status}</span>
                    </div>
                    <div className="job-item-actions">
                      <div className="btn-download-wrapper">
                        {job.total_schools_found > 0 && (
                          <>
                            <button className="btn-small" onClick={(e) => { e.stopPropagation(); handleDownload(job.id, 'xlsx'); }} style={{ padding: '4px 8px' }}><Download size={12} /></button>
                          </>
                        )}
                      </div>
                      <button className="btn-logout" onClick={(e) => handleDeleteJob(job.id, e)} style={{ padding: '6px', border: 'none' }}><Trash2 size={13} /></button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Audit Logs Terminal View */}
          <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div className="console-header">
              <span style={{ fontSize: '13.5px', fontWeight: '600' }}>Live Logs Console</span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button className="btn-small" onClick={handleCopyLogs}>Copy Console</button>
              </div>
            </div>
            <div className="console-box" style={{ flex: 1, minHeight: '160px' }}>
              {logs.length === 0 ? (
                <span style={{ color: 'var(--text-muted)' }}>[Console initialized. Waiting for log output...]</span>
              ) : (
                logs.map(log => (
                  <div key={log.id} className="log-row">
                    <span className="log-time">[{log.timestamp.slice(11, 19)}]</span>
                    <span className={`log-level ${log.level.toLowerCase()}`}>{log.level}</span>
                    <span className="log-msg">{log.message}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
      {toastMessage && <div className="toast">{toastMessage}</div>}
    </div>
  );
}
