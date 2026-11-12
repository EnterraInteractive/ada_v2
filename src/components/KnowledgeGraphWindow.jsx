import React, { useCallback, useEffect, useRef, useState } from 'react';
import { X, RefreshCw, Mic, MicOff, Send, Network, FileText, Volume2, VolumeX } from 'lucide-react';

const API = 'http://127.0.0.1:8001/knowledge';
const GRAPH_CDN = 'https://unpkg.com/3d-force-graph@1.73.3/dist/3d-force-graph.min.js';

function loadGraphLibrary() {
    if (window.ForceGraph3D) return Promise.resolve(window.ForceGraph3D);
    if (window.__adaGraphLibraryPromise) return window.__adaGraphLibraryPromise;
    window.__adaGraphLibraryPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = GRAPH_CDN;
        script.async = true;
        script.onload = () => window.ForceGraph3D ? resolve(window.ForceGraph3D) : reject(new Error('3D graph library did not initialise.'));
        script.onerror = () => reject(new Error('Could not load the 3D graph library. Connect to the internet once, then reopen the galaxy.'));
        document.head.appendChild(script);
    });
    return window.__adaGraphLibraryPromise;
}

function makeSessionId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return 'galaxy-' + Date.now() + '-' + Math.random().toString(36).slice(2);
}

function groupColor(group) {
    let hash = 0;
    for (const char of String(group || 'notes')) hash = (hash * 31 + char.charCodeAt(0)) | 0;
    const hue = Math.abs(hash) % 360;
    return 'hsl(' + hue + ', 85%, 68%)';
}

export default function KnowledgeGraphWindow({ onClose }) {
    const mountRef = useRef(null);
    const graphRef = useRef(null);
    const sessionRef = useRef(makeSessionId());
    const recognitionRef = useRef(null);
    const driftTimerRef = useRef(null);
    const bootGreetingDoneRef = useRef(false);
    const pendingSpeechRef = useRef('');
    const interactedRef = useRef(false);
    const [graph, setGraph] = useState({ nodes: [], links: [], count: 0 });
    const [selectedNode, setSelectedNode] = useState(null);
    const [highlighted, setHighlighted] = useState([]);
    const [question, setQuestion] = useState('');
    const [answer, setAnswer] = useState('');
    const [status, setStatus] = useState('initialising');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);
    const [listening, setListening] = useState(false);
    const [speaking, setSpeaking] = useState(true);
    const [busy, setBusy] = useState(false);

    const speak = useCallback((text) => {
        if (!speaking || !text || !('speechSynthesis' in window)) return;
        const speakNow = () => {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            const voices = window.speechSynthesis.getVoices();
            const british = voices.find(voice => /^en-GB/i.test(voice.lang)) ||
                voices.find(voice => /British|United Kingdom/i.test(voice.name));
            if (british) utterance.voice = british;
            utterance.rate = 0.94;
            utterance.pitch = 0.92;
            window.speechSynthesis.speak(utterance);
        };
        if (!interactedRef.current) {
            pendingSpeechRef.current = text;
            return;
        }
        speakNow();
    }, [speaking]);

    const markInteraction = useCallback(() => {
        interactedRef.current = true;
        if (pendingSpeechRef.current) {
            const pending = pendingSpeechRef.current;
            pendingSpeechRef.current = '';
            speak(pending);
        }
    }, [speak]);

    const selectNode = useCallback((node, fly = true) => {
        if (!node) return;
        setSelectedNode(node);
        setHighlighted([Number(node.id)]);
        const graphApi = graphRef.current;
        if (fly && graphApi) {
            const distance = 180;
            const length = Math.hypot(node.x || 1, node.y || 1, node.z || 1) || 1;
            const ratio = 1 + distance / length;
            graphApi.cameraPosition(
                { x: (node.x || 0) * ratio, y: (node.y || 0) * ratio, z: (node.z || 0) * ratio },
                { x: node.x || 0, y: node.y || 0, z: node.z || 0 },
                1300
            );
        }
    }, []);

    const loadGraph = useCallback(async (newNodeId = null, anchorId = null) => {
        setLoading(true);
        try {
            const response = await fetch(API + '/graph');
            if (!response.ok) throw new Error('Knowledge index returned HTTP ' + response.status);
            const data = await response.json();
            const previous = graphRef.current?.graphData?.().nodes || [];
            const previousBySource = new Map(previous.map(node => [node.source_id, node]));
            const nodes = (data.nodes || []).map(node => {
                const old = previousBySource.get(node.source_id);
                if (old) return { ...node, x: old.x, y: old.y, z: old.z };
                const anchor = anchorId == null ? null : previousBySource.get(anchorId);
                if (anchor) return { ...node, x: anchor.x, y: anchor.y, z: anchor.z };
                return node;
            });
            const nextGraph = { ...data, nodes, links: (data.links || []).map(link => ({ ...link })) };
            setGraph(nextGraph);
            if (graphRef.current) graphRef.current.graphData(nextGraph);
            if (newNodeId != null) {
                const created = nodes.find(node => node.source_id === newNodeId);
                if (created) {
                    selectNode(created, true);
                    setHighlighted([Number(created.id)]);
                    const pulseUntil = Date.now() + 2200;
                    created.__pulseUntil = pulseUntil;
                    const timer = setInterval(() => {
                        if (Date.now() > pulseUntil) clearInterval(timer);
                        graphRef.current?.refresh?.();
                    }, 80);
                }
            }
            return nextGraph;
        } catch (err) {
            setError(err.message || 'Could not load the knowledge galaxy.');
            return null;
        } finally {
            setLoading(false);
        }
    }, [selectNode]);

    useEffect(() => {
        let disposed = false;
        loadGraph().then(async data => {
            if (!data || disposed) return;
            try {
                const ForceGraph3D = await loadGraphLibrary();
                if (disposed || !mountRef.current) return;
                const graphApi = ForceGraph3D()(mountRef.current)
                    .backgroundColor('#02040b')
                    .showNavInfo(false)
                    .nodeId('id')
                    .nodeLabel(node => node.label || '')
                    .nodeColor(node => node.__pulseUntil > Date.now() ? '#ffffff' : highlighted.includes(Number(node.id)) ? '#fff0a8' : groupColor(node.group))
                    .nodeVal(node => node.__pulseUntil > Date.now() ? 13 : highlighted.includes(Number(node.id)) ? 7 : 3.5)
                    .linkColor(() => 'rgba(90, 180, 220, 0.20)')
                    .linkOpacity(0.36)
                    .linkWidth(link => highlighted.includes(Number(link.source?.id ?? link.source)) && highlighted.includes(Number(link.target?.id ?? link.target)) ? 1.8 : 0.45)
                    .onNodeClick(node => { markInteraction(); selectNode(node, true); })
                    .onBackgroundClick(() => { setSelectedNode(null); setHighlighted([]); });
                graphApi.d3Force('charge').strength(-115);
                graphApi.d3Force('link').distance(75);
                graphApi.d3VelocityDecay(0.28);
                graphApi.warmupTicks(80);
                graphApi.cooldownTime(18000);
                driftTimerRef.current = setInterval(() => graphApi.d3ReheatSimulation(), 12000);
                graphRef.current = graphApi;
                graphApi.graphData(data);
                graphApi.cameraPosition({ x: 0, y: 0, z: 650 }, { x: 0, y: 0, z: 0 }, 0);
            } catch (err) {
                setError(err.message || 'The galaxy renderer could not start.');
            }
        });
        return () => {
            disposed = true;
            recognitionRef.current?.stop?.();
            window.speechSynthesis?.cancel?.();
            if (driftTimerRef.current) clearInterval(driftTimerRef.current);
            graphRef.current?._destructor?.();
            graphRef.current = null;
        };
    }, []); // initial boot only

    useEffect(() => {
        if (graphRef.current && graph.nodes.length) {
            graphRef.current.nodeColor(node => node.__pulseUntil > Date.now() ? '#ffffff' : highlighted.includes(Number(node.id)) ? '#fff0a8' : groupColor(node.group));
            graphRef.current.nodeVal(node => node.__pulseUntil > Date.now() ? 13 : highlighted.includes(Number(node.id)) ? 8 : 3.5);
            graphRef.current.refresh();
        }
    }, [highlighted, graph.nodes.length]);

    useEffect(() => {
        if (loading || bootGreetingDoneRef.current) return;
        bootGreetingDoneRef.current = true;
        speak('Good evening, sir. ' + graph.count + ' notes indexed, all present and accounted for.');
    }, [graph.count, loading, speak]);

    const submit = async (rawText) => {
        const text = String(rawText || question).trim();
        if (!text || busy) return;
        markInteraction();
        setQuestion('');
        setError('');
        setBusy(true);
        setStatus('thinking');
        setAnswer('');
        try {
            if (/^remember that\b/i.test(text)) {
                const response = await fetch(API + '/remember', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                const data = await response.json();
                if (!response.ok || data.error) throw new Error(data.error || 'Memory capture failed.');
                await loadGraph(data.id, data.anchor_source_id ?? null);
                const confirmation = 'Consider it filed, sir. My memory has grown another neuron; try not to make a habit of being interesting.';
                setAnswer(confirmation);
                speak(confirmation);
            } else {
                const response = await fetch(API + '/chat', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: text, session_id: sessionRef.current })
                });
                const data = await response.json();
                if (!response.ok || data.error) throw new Error(data.error || 'The notes could not be queried.');
                setAnswer(data.answer || '');
                speak(data.answer || '');
                const indexes = (data.nodes || []).map(Number).filter(Number.isInteger);
                if (indexes.length >= 4) {
                    setHighlighted(indexes);
                    const first = graph.nodes.find(node => Number(node.id) === indexes[0]);
                    if (first) setSelectedNode(first);
                } else if (indexes.length) {
                    const source = graph.nodes.find(node => Number(node.id) === indexes[0]);
                    if (source) {
                        const neighborIds = graph.links.filter(link => Number(link.source?.id ?? link.source) === indexes[0] || Number(link.target?.id ?? link.target) === indexes[0])
                            .map(link => Number(link.source?.id ?? link.source) === indexes[0] ? Number(link.target?.id ?? link.target) : Number(link.source?.id ?? link.source));
                        setHighlighted([indexes[0], ...neighborIds]);
                        selectNode(source, true);
                    }
                } else {
                    setHighlighted([]);
                }
            }
        } catch (err) {
            setError(err.message || 'The request failed.');
            setStatus('error');
        } finally {
            setBusy(false);
            setStatus('ready');
        }
    };

    const startListening = () => {
        markInteraction();
        const Recognition = window.webkitSpeechRecognition || window.SpeechRecognition;
        if (!Recognition) {
            setError('Speech recognition is unavailable. Please use Chrome on desktop.');
            return;
        }
        const recognition = new Recognition();
        recognition.lang = 'en-GB';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognitionRef.current = recognition;
        recognition.onstart = () => { setListening(true); setStatus('listening'); };
        recognition.onresult = event => {
            const transcript = event.results?.[0]?.[0]?.transcript || '';
            setQuestion(transcript);
            submit(transcript);
        };
        recognition.onerror = event => setError('Microphone: ' + event.error);
        recognition.onend = () => { setListening(false); if (!busy) setStatus('ready'); };
        recognition.start();
    };

    const reindex = async () => {
        markInteraction();
        setError('');
        setStatus('thinking');
        try {
            const response = await fetch(API + '/reindex', { method: 'POST' });
            const data = await response.json();
            if (!response.ok) throw new Error('Reindex failed.');
            await loadGraph();
            setAnswer(data.total + ' notes indexed, sir. The filing cabinet remains disgracefully organised.');
        } catch (err) { setError(err.message); }
        finally { setStatus('ready'); }
    };

    return (
        <div onPointerDown={markInteraction} className="fixed inset-3 z-[90] flex flex-col overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#02040b] text-cyan-50 shadow-[0_0_90px_rgba(14,165,233,0.16)]">
            <div className="pointer-events-none absolute inset-0 opacity-60" style={{ backgroundImage: 'radial-gradient(1px 1px at 7% 12%,#d8f5ff 98%,transparent),radial-gradient(1px 1px at 28% 72%,#b4e5ff 98%,transparent),radial-gradient(2px 2px at 76% 23%,#fff 98%,transparent),radial-gradient(1px 1px at 92% 81%,#d8f5ff 98%,transparent),radial-gradient(1px 1px at 54% 42%,#fff 98%,transparent),radial-gradient(1px 1px at 42% 18%,#b4e5ff 98%,transparent)', backgroundSize: '420px 310px' }} />
            <header className="relative z-10 flex items-center justify-between border-b border-cyan-300/15 bg-black/45 px-5 py-3 backdrop-blur">
                <div className="flex items-center gap-3"><Network className="text-cyan-300" size={19} /><div><div className="text-xs font-semibold tracking-[0.32em] text-cyan-100">KNOWLEDGE GALAXY</div><div className="mt-1 text-[10px] tracking-wider text-cyan-700">{graph.count} NOTES · {status === 'listening' ? '● LISTENING…' : status === 'thinking' ? '● THINKING…' : status.toUpperCase()}</div></div></div>
                <div className="flex items-center gap-2">
                    <button onClick={() => setSpeaking(v => !v)} title="Toggle spoken answers" className="rounded-lg border border-cyan-900/70 p-2 text-cyan-300 hover:border-cyan-400">{speaking ? <Volume2 size={15} /> : <VolumeX size={15} />}</button>
                    <button onClick={reindex} disabled={loading || busy} className="rounded-lg border border-cyan-900/70 p-2 text-cyan-300 hover:border-cyan-400 disabled:opacity-40"><RefreshCw size={15} /></button>
                    <button onClick={onClose} className="rounded-lg p-2 text-cyan-700 hover:bg-cyan-950 hover:text-white"><X size={18} /></button>
                </div>
            </header>
            <div className="relative z-0 flex min-h-0 flex-1">
                <div ref={mountRef} className="min-w-0 flex-1" />
                <aside className="flex w-[310px] shrink-0 flex-col border-l border-cyan-300/15 bg-[#030711]/85 p-5 backdrop-blur">
                    <div className="mb-4 flex items-center gap-2 text-[10px] font-semibold tracking-[0.25em] text-cyan-600"><FileText size={14} /> SOURCE NOTE</div>
                    {selectedNode ? <><div className="mb-2 text-[10px] text-cyan-700">{selectedNode.group} · node {selectedNode.id}</div><h2 className="mb-4 text-base font-medium text-cyan-100">{selectedNode.label}</h2><p className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap text-xs leading-6 text-cyan-100/65">{selectedNode.excerpt}</p><div className="mt-4 break-all border-t border-cyan-900/60 pt-3 text-[9px] text-cyan-800">{selectedNode.path}</div></> : <p className="text-xs leading-6 text-cyan-800">Ask about your notes or select a glowing node to inspect its source.</p>}
                </aside>
            </div>
            <div className="relative z-10 border-t border-cyan-300/15 bg-black/75 px-4 py-3 backdrop-blur-xl">
                {answer && <div className="mx-auto mb-3 max-w-5xl rounded-xl border border-cyan-400/15 bg-cyan-950/25 px-4 py-3 text-sm leading-6 text-cyan-50">{answer}</div>}
                {error && <div className="mx-auto mb-2 max-w-5xl text-xs text-rose-300">{error}</div>}
                <form onSubmit={event => { event.preventDefault(); submit(); }} className="mx-auto flex max-w-5xl items-center gap-3 rounded-2xl border border-cyan-300/25 bg-[#07121d] px-3 py-2 shadow-[0_0_30px_rgba(8,145,178,0.08)]">
                    <button type="button" onClick={listening ? () => recognitionRef.current?.stop?.() : startListening} className={'rounded-xl p-2 ' + (listening ? 'bg-rose-500/20 text-rose-300' : 'text-cyan-300 hover:bg-cyan-900/40')} title="Speak to Jarvis">{listening ? <MicOff size={18} /> : <Mic size={18} />}</button>
                    <input value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask your notes… or say “remember that…”" className="min-w-0 flex-1 bg-transparent py-2 text-sm text-cyan-50 outline-none placeholder:text-cyan-800" />
                    <button type="submit" disabled={busy || !question.trim()} className="rounded-xl bg-cyan-500/15 p-2.5 text-cyan-200 hover:bg-cyan-500/30 disabled:opacity-30"><Send size={17} /></button>
                </form>
                <div className="mx-auto mt-2 max-w-5xl text-[9px] tracking-wider text-cyan-900">BROWSER VOICE · BRITISH ENGLISH PREFERRED · {loading ? 'INDEXING' : 'ALL SYSTEMS NOMINAL'}</div>
            </div>
        </div>
    );
}
