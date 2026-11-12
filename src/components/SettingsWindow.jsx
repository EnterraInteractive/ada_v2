import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';

const TOOLS = [
    { id: 'browser_navigate', label: 'Browser Navigation' },
    { id: 'browser_click', label: 'Browser Click' },
    { id: 'browser_type', label: 'Browser Input' },
    { id: 'browser_press', label: 'Browser Keyboard' },
    { id: 'browser_read_page', label: 'Read Web Page' },
    { id: 'browser_screenshot', label: 'Browser Screenshot' },
    { id: 'browser_wait', label: 'Browser Wait' },
    { id: 'browser_close', label: 'Close Browser' },
    { id: 'write_file', label: 'Write File' },
    { id: 'read_directory', label: 'Read Directory' },
    { id: 'search_project', label: 'Search Project' },
    { id: 'run_terminal_command', label: 'Run Terminal Commands' },
    { id: 'analyze_image', label: 'Analyze Camera / Screenshot' },
    { id: 'read_file', label: 'Read File' },
    { id: 'create_project', label: 'Create Project' },
    { id: 'switch_project', label: 'Switch Project' },
    { id: 'list_projects', label: 'List Projects' },
    { id: 'unreal_mcp_readonly', label: 'Unreal Editor Read-Only Queries' },
    { id: 'unreal_mcp', label: 'Unreal Editor Changes and Actions' },
];

const SettingsWindow = ({
    socket,
    micDevices,
    speakerDevices,
    webcamDevices,
    selectedMicId,
    setSelectedMicId,
    selectedSpeakerId,
    setSelectedSpeakerId,
    selectedWebcamId,
    setSelectedWebcamId,
    cursorSensitivity,
    setCursorSensitivity,
    isCameraFlipped,
    setIsCameraFlipped,
    handleFileUpload,
    onClose
}) => {
    const [permissions, setPermissions] = useState({});
    const [faceAuthEnabled, setFaceAuthEnabled] = useState(false);
    const [workspacePath, setWorkspacePath] = useState('');
    const [modelRuntime, setModelRuntime] = useState({ primary_model_id: '', vision_model_id: '', models: [] });
    const [modelRuntimeStatus, setModelRuntimeStatus] = useState({ runtime_available: false, runtime_error: '' });
    const [voiceSettings, setVoiceSettings] = useState({ provider: 'gemini_api', enabled: false, api_key_env: 'GEMINI_API_KEY' });
    const [unrealMcp, setUnrealMcp] = useState({ enabled: true, url: 'http://127.0.0.1:8000/mcp' });
    const [unrealMcpStatus, setUnrealMcpStatus] = useState({ connected: false, tool_count: 0 });

    useEffect(() => {
        // Request initial permissions
        socket.emit('get_settings');
        socket.emit('get_unreal_mcp_status');
        socket.emit('get_model_status');

        // Listen for updates
        const handleSettings = (settings) => {
            console.log("Received settings:", settings);
            if (settings) {
                if (settings.tool_permissions) setPermissions(settings.tool_permissions);
                if (typeof settings.workspace_path === 'string') setWorkspacePath(settings.workspace_path);
                if (settings.model_runtime) setModelRuntime(settings.model_runtime);
                if (settings.voice) setVoiceSettings(settings.voice);
                if (settings.unreal_mcp) setUnrealMcp(settings.unreal_mcp);
                if (typeof settings.face_auth_enabled !== 'undefined') {
                    setFaceAuthEnabled(settings.face_auth_enabled);
                    localStorage.setItem('face_auth_enabled', settings.face_auth_enabled);
                }
            }
        };

        const handleUnrealMcpStatus = status => setUnrealMcpStatus(status || { connected: false });
        const handleModelStatus = status => setModelRuntimeStatus(status || { runtime_available: false, runtime_error: '' });
        socket.on('settings', handleSettings);
        socket.on('unreal_mcp_status', handleUnrealMcpStatus);
        socket.on('model_status', handleModelStatus);
        // Also listen for legacy tool_permissions if needed, but 'settings' covers it
        // socket.on('tool_permissions', handlePermissions); 

        return () => {
            socket.off('settings', handleSettings);
            socket.off('unreal_mcp_status', handleUnrealMcpStatus);
            socket.off('model_status', handleModelStatus);
        };
    }, [socket]);

    const updateModel = (modelId, patch) => {
        setModelRuntime(prev => ({
            ...prev,
            models: (prev.models || []).map(model => model.id === modelId ? { ...model, ...patch } : model)
        }));
    };

    const pickPath = async (options) => {
        try {
            const { ipcRenderer } = window.require('electron');
            return await ipcRenderer.invoke('select-path', options);
        } catch (error) {
            console.error('Native file picker unavailable:', error);
            return null;
        }
    };

    const saveDevelopmentSettings = () => {
        socket.emit('update_settings', {
            workspace_path: workspacePath,
            model_runtime: modelRuntime,
            voice: voiceSettings,
            unreal_mcp: unrealMcp
        });
    };

    const addModel = () => {
        const id = `custom-model-${Date.now()}`;
        setModelRuntime(prev => ({
            ...prev,
            models: [...(prev.models || []), {
                id,
                name: 'New Local Model',
                model_path: '',
                capabilities: ['chat', 'coding', 'reasoning', 'tools'],
                context_size: 16384,
                gpu_layers: 99,
                max_tokens: 4096,
                temperature: 0.2
            }]
        }));
    };

    const removeModel = (modelId) => {
        setModelRuntime(prev => ({
            ...prev,
            models: (prev.models || []).filter(model => model.id !== modelId),
            primary_model_id: prev.primary_model_id === modelId ? '' : prev.primary_model_id,
            vision_model_id: prev.vision_model_id === modelId ? '' : prev.vision_model_id
        }));
    };

    const togglePermission = (toolId) => {
        const currentVal = permissions[toolId] !== false; // Default True
        const nextVal = !currentVal;

        // Update local mostly for responsiveness, but socket roundtrip handles truth
        // setPermissions(prev => ({ ...prev, [toolId]: nextVal }));

        // Send update
        socket.emit('update_settings', { tool_permissions: { [toolId]: nextVal } });
    };

    const toggleFaceAuth = () => {
        const newVal = !faceAuthEnabled;
        setFaceAuthEnabled(newVal); // Optimistic Update
        localStorage.setItem('face_auth_enabled', newVal);
        socket.emit('update_settings', { face_auth_enabled: newVal });
    };

    const toggleCameraFlip = () => {
        const newVal = !isCameraFlipped;
        setIsCameraFlipped(newVal);
        socket.emit('update_settings', { camera_flipped: newVal });
    };

    return (
        <div className="absolute top-16 right-6 bg-black/95 border border-cyan-500/50 p-4 rounded-lg z-50 w-[min(92vw,460px)] max-h-[88vh] overflow-y-auto backdrop-blur-xl shadow-[0_0_30px_rgba(6,182,212,0.2)]">
            <div className="flex justify-between items-center mb-4 border-b border-cyan-900/50 pb-2">
                <h2 className="text-cyan-400 font-bold text-sm uppercase tracking-wider">Settings</h2>
                <button onClick={onClose} className="text-cyan-600 hover:text-cyan-400">
                    <X size={16} />
                </button>
            </div>

            {/* Authentication Section */}
            <div className="mb-6">
                <h3 className="text-cyan-400 font-bold mb-3 text-xs uppercase tracking-wider opacity-80">Security</h3>
                <div className="flex items-center justify-between text-xs bg-gray-900/50 p-2 rounded border border-cyan-900/30">
                    <span className="text-cyan-100/80">Face Authentication</span>
                    <button
                        onClick={toggleFaceAuth}
                        className={`relative w-8 h-4 rounded-full transition-colors duration-200 ${faceAuthEnabled ? 'bg-cyan-500/80' : 'bg-gray-700'}`}
                    >
                        <div
                            className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform duration-200 ${faceAuthEnabled ? 'translate-x-4' : 'translate-x-0'}`}
                        />
                    </button>
                </div>
            </div>

            {/* Microphone Section */}
            <div className="mb-4">
                <h3 className="text-cyan-400 font-bold mb-2 text-xs uppercase tracking-wider opacity-80">Microphone</h3>
                <select
                    value={selectedMicId}
                    onChange={(e) => setSelectedMicId(e.target.value)}
                    className="w-full bg-gray-900 border border-cyan-800 rounded p-2 text-xs text-cyan-100 focus:border-cyan-400 outline-none"
                >
                    {micDevices.map((device, i) => (
                        <option key={device.deviceId} value={device.deviceId}>
                            {device.label || `Microphone ${i + 1}`}
                        </option>
                    ))}
                </select>
            </div>

            <div className="mb-4 rounded border border-gray-800 bg-gray-950/50 p-3">
                <h3 className="text-cyan-400 font-bold mb-1 text-xs uppercase tracking-wider opacity-80">Speech Output</h3>
                <p className="text-[10px] text-gray-500">Gemini API voice is the selected provider. Voice runs remotely; no local speech model is loaded. The API adapter must be configured before voice can be enabled.</p>
            </div>

            {/* Webcam Section */}
            <div className="mb-6">
                <h3 className="text-cyan-400 font-bold mb-2 text-xs uppercase tracking-wider opacity-80">Webcam</h3>
                <select
                    value={selectedWebcamId}
                    onChange={(e) => setSelectedWebcamId(e.target.value)}
                    className="w-full bg-gray-900 border border-cyan-800 rounded p-2 text-xs text-cyan-100 focus:border-cyan-400 outline-none"
                >
                    {webcamDevices.map((device, i) => (
                        <option key={device.deviceId} value={device.deviceId}>
                            {device.label || `Camera ${i + 1}`}
                        </option>
                    ))}
                </select>
            </div>

            {/* Cursor Section */}
            <div className="mb-6">
                <div className="flex justify-between mb-2">
                    <h3 className="text-cyan-400 font-bold text-xs uppercase tracking-wider opacity-80">Cursor Sensitivity</h3>
                    <span className="text-xs text-cyan-500">{cursorSensitivity}x</span>
                </div>
                <input
                    type="range"
                    min="1.0"
                    max="5.0"
                    step="0.1"
                    value={cursorSensitivity}
                    onChange={(e) => setCursorSensitivity(parseFloat(e.target.value))}
                    className="w-full accent-cyan-400 cursor-pointer h-1 bg-gray-800 rounded-lg appearance-none"
                />
            </div>

            {/* Gesture Control Section */}
            <div className="mb-6">
                <h3 className="text-cyan-400 font-bold mb-3 text-xs uppercase tracking-wider opacity-80">Gesture Control</h3>
                <div className="flex items-center justify-between text-xs bg-gray-900/50 p-2 rounded border border-cyan-900/30">
                    <span className="text-cyan-100/80">Flip Camera Horizontal</span>
                    <button
                        onClick={toggleCameraFlip}
                        className={`relative w-8 h-4 rounded-full transition-colors duration-200 ${isCameraFlipped ? 'bg-cyan-500/80' : 'bg-gray-700'}`}
                    >
                        <div
                            className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform duration-200 ${isCameraFlipped ? 'translate-x-4' : 'translate-x-0'}`}
                        />
                    </button>
                </div>
            </div>

            {/* Development Workspace */}
            <div className="mb-6 border-b border-cyan-900/50 pb-5">
                <h3 className="text-cyan-400 font-bold mb-3 text-xs uppercase tracking-wider">Development Workspace</h3>
                <div className="flex gap-2">
                    <input value={workspacePath} onChange={e => setWorkspacePath(e.target.value)} placeholder="Select your project or repository folder"
                        className="min-w-0 flex-1 bg-gray-900 border border-cyan-800 rounded p-2 text-[11px] text-cyan-100" />
                    <button onClick={async () => {
                        const path = await pickPath({ directory: true, title: 'Open development workspace' });
                        if (path) setWorkspacePath(path);
                    }} className="px-3 rounded border border-cyan-700 text-cyan-300 text-xs hover:bg-cyan-900/40">Browse</button>
                </div>
                <p className="text-[10px] text-gray-500 mt-2">A.D.A reads and edits files only inside this selected workspace.</p>
            </div>

            {/* Unreal Editor MCP */}
            <div className="mb-6 border-b border-cyan-900/50 pb-5">
                <h3 className="text-cyan-400 font-bold mb-3 text-xs uppercase tracking-wider">Unreal Editor Connection</h3>
                <div className="flex items-center justify-between text-xs bg-gray-900/50 p-2 rounded border border-cyan-900/30 mb-3">
                    <span className="text-cyan-100/80">Connect to the running Unreal Editor</span>
                    <button onClick={() => setUnrealMcp(prev => ({ ...prev, enabled: !prev.enabled }))}
                        className={`relative w-8 h-4 rounded-full transition-colors duration-200 ${unrealMcp.enabled ? 'bg-cyan-500/80' : 'bg-gray-700'}`}>
                        <div className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform duration-200 ${unrealMcp.enabled ? 'translate-x-4' : 'translate-x-0'}`} />
                    </button>
                </div>
                <label className="block text-[10px] text-cyan-500/70 mb-1">Unreal MCP endpoint</label>
                <input value={unrealMcp.url || ''} onChange={e => setUnrealMcp(prev => ({ ...prev, url: e.target.value }))}
                    placeholder="http://127.0.0.1:8000/mcp"
                    className="w-full bg-gray-900 border border-cyan-800 rounded p-2 text-[11px] text-cyan-100 mb-2" />
                <div className="flex items-center justify-between gap-2 text-[10px] mb-3">
                    <span className={unrealMcpStatus.connected ? "text-green-400" : "text-amber-400"}>
                        {unrealMcpStatus.connected ? `Connected · ${unrealMcpStatus.tool_count || 0} editor tools` : (unrealMcpStatus.error || "Not connected — open Unreal Editor and enable its MCP server")}
                    </span>
                    <button onClick={() => socket.emit('reconnect_unreal_mcp')}
                        disabled={!unrealMcp.enabled}
                        className="shrink-0 px-2 py-1 rounded border border-cyan-800 text-cyan-300 disabled:opacity-40">Reconnect</button>
                </div>
                <p className="text-[9px] text-gray-600">A.D.A connects directly to the existing Unreal MCP server. It does not launch a second editor or an MCP server of its own.</p>
            </div>

            {/* Local Model Registry */}
            <div className="mb-6 border-b border-cyan-900/50 pb-5">
                <h3 className="text-cyan-400 font-bold mb-3 text-xs uppercase tracking-wider">Local Model Runtime</h3>
                <p className="text-[10px] text-cyan-300/80 mb-2">Embedded llama-cpp-python runtime · inference runs inside A.D.A. No llama-server process or separate model app.</p>
                <p className={`text-[10px] mb-3 ${modelRuntimeStatus.runtime_available ? "text-green-400" : "text-amber-400"}`}>
                    {modelRuntimeStatus.runtime_available ? (modelRuntimeStatus.gpu_offload_supported ? "Native runtime and GPU offload are available." : (modelRuntimeStatus.runtime_error || "GPU offload is unavailable.")) : (modelRuntimeStatus.runtime_error || "Install the CUDA-enabled runtime from requirements.txt.")}
                </p>

                <label className="block text-[10px] text-cyan-500/70 mb-1">Primary chat / coding model</label>
                <select value={modelRuntime.primary_model_id || ''} onChange={e => setModelRuntime(prev => ({ ...prev, primary_model_id: e.target.value }))}
                    className="w-full bg-gray-900 border border-cyan-800 rounded p-2 text-xs text-cyan-100 mb-3">
                    <option value="">Select primary model</option>
                    {(modelRuntime.models || []).map(model => <option key={model.id} value={model.id}>{model.name || model.id}</option>)}
                </select>

                <label className="block text-[10px] text-cyan-500/70 mb-1">Vision delegate</label>
                <select value={modelRuntime.vision_model_id || ''} onChange={e => setModelRuntime(prev => ({ ...prev, vision_model_id: e.target.value }))}
                    className="w-full bg-gray-900 border border-cyan-800 rounded p-2 text-xs text-cyan-100 mb-4">
                    <option value="">Select vision model</option>
                    {(modelRuntime.models || []).map(model => <option key={model.id} value={model.id}>{model.name || model.id}</option>)}
                </select>

                <div className="space-y-3">
                    {(modelRuntime.models || []).map(model => (
                        <div key={model.id} className="rounded border border-cyan-900/60 bg-gray-950/70 p-3">
                            <div className="flex items-center gap-2 mb-2">
                                <input value={model.name || ''} onChange={e => updateModel(model.id, { name: e.target.value })}
                                    className="min-w-0 flex-1 bg-gray-900 border border-gray-700 rounded p-2 text-xs text-cyan-100" />
                                <button onClick={() => removeModel(model.id)} className="text-[10px] text-red-400">Remove</button>
                            </div>
                            <div className="flex gap-2 mb-2">
                                <input value={model.model_path || ''} onChange={e => updateModel(model.id, { model_path: e.target.value })} placeholder="Model .gguf file"
                                    className="min-w-0 flex-1 bg-gray-900 border border-gray-700 rounded p-2 text-[10px] text-gray-300" />
                                <button onClick={async () => {
                                    const path = await pickPath({ title: 'Select GGUF model', filters: [{ name: 'GGUF model', extensions: ['gguf'] }] });
                                    if (path) updateModel(model.id, { model_path: path });
                                }} className="px-2 rounded border border-cyan-800 text-cyan-300 text-[10px]">GGUF</button>
                            </div>
                            <div className="flex gap-2 mb-2">
                                <input value={model.mmproj_path || ''} onChange={e => updateModel(model.id, { mmproj_path: e.target.value })} placeholder="Optional vision projector .gguf"
                                    className="min-w-0 flex-1 bg-gray-900 border border-gray-700 rounded p-2 text-[10px] text-gray-300" />
                                <button onClick={async () => {
                                    const path = await pickPath({ title: 'Select multimodal projector', filters: [{ name: 'GGUF projector', extensions: ['gguf'] }] });
                                    if (path) updateModel(model.id, { mmproj_path: path });
                                }} className="px-2 rounded border border-cyan-800 text-cyan-300 text-[10px]">MMProj</button>
                            </div>
                            <label className="block text-[9px] text-gray-500 mb-2">Vision handler
                                <select value={model.chat_handler || (model.id === 'gemma-4-12b' ? 'gemma4' : 'mtmd')} onChange={e => updateModel(model.id, { chat_handler: e.target.value })}
                                    className="w-full bg-gray-900 border border-gray-700 rounded p-1 text-[10px] text-cyan-100">
                                    <option value="gemma4">Gemma 4</option>
                                    <option value="mtmd">Generic MTMD</option>
                                    <option value="qwen25vl">Qwen 2.5 VL</option>
                                    <option value="minicpmv26">MiniCPM-V 2.6</option>
                                    <option value="llava15">LLaVA 1.5</option>
                                    <option value="llava16">LLaVA 1.6</option>
                                    <option value="moondream">Moondream</option>
                                </select>
                            </label>
                            <div className="grid grid-cols-3 gap-2">
                                <label className="text-[9px] text-gray-500">Context
                                    <input type="number" value={model.context_size || 16384} onChange={e => updateModel(model.id, { context_size: Number(e.target.value) })}
                                        className="w-full bg-gray-900 border border-gray-700 rounded p-1 text-[10px] text-cyan-100" />
                                </label>
                                <label className="text-[9px] text-gray-500">GPU layers
                                    <input type="number" value={model.gpu_layers ?? 99} onChange={e => updateModel(model.id, { gpu_layers: Number(e.target.value) })}
                                        className="w-full bg-gray-900 border border-gray-700 rounded p-1 text-[10px] text-cyan-100" />
                                </label>
                                <label className="text-[9px] text-gray-500">Max tokens
                                    <input type="number" value={model.max_tokens || 2048} onChange={e => updateModel(model.id, { max_tokens: Number(e.target.value) })}
                                        className="w-full bg-gray-900 border border-gray-700 rounded p-1 text-[10px] text-cyan-100" />
                                </label>
                            </div>
                            <div className="grid grid-cols-2 gap-2 mt-2">
                                <label className="text-[9px] text-gray-500">KV cache K
                                    <select value={model.cache_type_k || 'f16'} onChange={e => updateModel(model.id, { cache_type_k: e.target.value })}
                                        className="w-full bg-gray-900 border border-gray-700 rounded p-1 text-[10px] text-cyan-100">
                                        <option value="f16">F16</option><option value="q8_0">Q8_0</option><option value="q4_0">Q4_0</option>
                                    </select>
                                </label>
                                <label className="text-[9px] text-gray-500">KV cache V
                                    <select value={model.cache_type_v || 'f16'} onChange={e => updateModel(model.id, { cache_type_v: e.target.value })}
                                        className="w-full bg-gray-900 border border-gray-700 rounded p-1 text-[10px] text-cyan-100">
                                        <option value="f16">F16</option><option value="q8_0">Q8_0</option><option value="q4_0">Q4_0</option>
                                    </select>
                                </label>
                            </div>
                            <label className="flex items-center gap-2 text-[9px] text-gray-500 mt-2">
                                <input type="checkbox" checked={!!model.no_kv_offload} onChange={e => updateModel(model.id, { no_kv_offload: e.target.checked })} />
                                Keep KV cache in system RAM (less VRAM, potentially slower)
                            </label>
                            <p className="text-[9px] text-gray-600 mt-2">ID: {model.id} · {Array.isArray(model.capabilities) ? model.capabilities.join(', ') : 'custom'}</p>
                        </div>
                    ))}
                </div>
                <div className="mt-4 rounded border border-cyan-900/60 bg-gray-950/70 p-3">
                    <h4 className="text-[10px] text-cyan-400 uppercase tracking-wider mb-2">Gemini API Voice</h4>
                    <p className="text-[10px] text-gray-400">Provider: Gemini API</p>
                    <p className="text-[10px] text-gray-400">Credential: GEMINI_API_KEY environment variable</p>
                    <p className="text-[9px] text-amber-400 mt-2">Remote voice transport is not connected yet. Local Whisper and operating-system speech fallback are disabled.</p>
                </div>

                <div className="flex gap-2 mt-3">
                    <button onClick={addModel} className="flex-1 px-3 py-2 rounded border border-cyan-800 text-cyan-300 text-xs">Add Model</button>
                    <button onClick={saveDevelopmentSettings} className="flex-1 px-3 py-2 rounded bg-cyan-800/60 border border-cyan-500 text-cyan-100 text-xs">Save Local Setup</button>
                </div>
            </div>

            {/* Tool Permissions Section */}
            <div className="mb-6">
                <h3 className="text-cyan-400 font-bold mb-3 text-xs uppercase tracking-wider opacity-80">Tool Confirmations</h3>
                <div className="space-y-2 max-h-40 overflow-y-auto pr-2 custom-scrollbar">
                    {TOOLS.map(tool => {
                        const isRequired = permissions[tool.id] !== false; // Default True
                        return (
                            <div key={tool.id} className="flex items-center justify-between text-xs bg-gray-900/50 p-2 rounded border border-cyan-900/30">
                                <span className="text-cyan-100/80">{tool.label}</span>
                                <button
                                    onClick={() => togglePermission(tool.id)}
                                    className={`relative w-8 h-4 rounded-full transition-colors duration-200 ${isRequired ? 'bg-cyan-500/80' : 'bg-gray-700'}`}
                                >
                                    <div
                                        className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform duration-200 ${isRequired ? 'translate-x-4' : 'translate-x-0'}`}
                                    />
                                </button>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Memory Section */}
            <div>
                <h3 className="text-cyan-400 font-bold mb-2 text-xs uppercase tracking-wider opacity-80">Memory Data</h3>
                <div className="flex flex-col gap-2">
                    <label className="text-[10px] text-cyan-500/60 uppercase">Upload Memory Text</label>
                    <input
                        type="file"
                        accept=".txt"
                        onChange={handleFileUpload}
                        className="text-xs text-cyan-100 bg-gray-900 border border-cyan-800 rounded p-2 file:mr-2 file:py-1 file:px-2 file:rounded-full file:border-0 file:text-[10px] file:font-semibold file:bg-cyan-900 file:text-cyan-400 hover:file:bg-cyan-800 cursor-pointer"
                    />
                </div>
            </div>
        </div>
    );
};

export default SettingsWindow;
