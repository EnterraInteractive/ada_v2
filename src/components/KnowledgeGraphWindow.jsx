import React, { useCallback, useEffect, useRef, useState } from 'react';
import { X, RefreshCw, Search, Network, FileText } from 'lucide-react';

const API_ROOT = 'http://127.0.0.1:8001';
const MAX_VISIBLE_NODES = 360;

function projectNode(node, width, height, camera) {
    const cy = Math.cos(camera.yaw);
    const sy = Math.sin(camera.yaw);
    const cp = Math.cos(camera.pitch);
    const sp = Math.sin(camera.pitch);
    const x = node.x * cy - node.z * sy;
    const z1 = node.x * sy + node.z * cy;
    const y = node.y * cp - z1 * sp;
    const z = node.y * sp + z1 * cp;
    const perspective = camera.zoom / Math.max(0.35, 1 + z / 700);
    return {
        x: width / 2 + x * perspective + camera.panX,
        y: height / 2 + y * perspective + camera.panY,
        radius: Math.max(2.2, 5.2 * perspective),
        depth: z,
    };
}

function KnowledgeCanvas({ graph, selectedId, highlightedIds, onSelect }) {
    const canvasRef = useRef(null);
    const selectedRef = useRef(selectedId);
    const highlightedRef = useRef(highlightedIds);
    const cameraRef = useRef({ yaw: 0.15, pitch: -0.12, zoom: 1, panX: 0, panY: 0 });
    const dragRef = useRef(null);

    useEffect(() => { selectedRef.current = selectedId; }, [selectedId]);
    useEffect(() => { highlightedRef.current = highlightedIds; }, [highlightedIds]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const context = canvas.getContext('2d');
        const sourceNodes = (graph.nodes || []).slice(0, MAX_VISIBLE_NODES);
        const visibleIds = new Set(sourceNodes.map(node => node.id));
        const edges = (graph.links || []).filter(edge => visibleIds.has(edge.source) && visibleIds.has(edge.target));
        const count = Math.max(1, sourceNodes.length);
        const nodes = sourceNodes.map((node, index) => {
            const goldenAngle = Math.PI * (3 - Math.sqrt(5));
            const y = 1 - (index / Math.max(1, count - 1)) * 2;
            const radius = Math.sqrt(Math.max(0, 1 - y * y));
            const angle = goldenAngle * index;
            const spread = 150 + (index % 7) * 7;
            return {
                ...node,
                x: Math.cos(angle) * radius * spread,
                y: y * spread,
                z: Math.sin(angle) * radius * spread,
                vx: 0, vy: 0, vz: 0,
            };
        });
        const nodeById = new Map(nodes.map(node => [node.id, node]));
        let animationId = 0;
        let lastTime = 0;

        const draw = (time) => {
            const width = canvas.clientWidth || 800;
            const height = canvas.clientHeight || 560;
            const ratio = Math.min(window.devicePixelRatio || 1, 2);
            const targetWidth = Math.floor(width * ratio);
            const targetHeight = Math.floor(height * ratio);
            if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
                canvas.width = targetWidth;
                canvas.height = targetHeight;
            }
            context.setTransform(ratio, 0, 0, ratio, 0, 0);
            context.clearRect(0, 0, width, height);

            if (time - lastTime > 20 && nodes.length < 500) {
                lastTime = time;
                for (let i = 0; i < nodes.length; i++) {
                    const a = nodes[i];
                    for (let j = i + 1; j < nodes.length; j++) {
                        const b = nodes[j];
                        const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
                        const distanceSq = Math.max(80, dx * dx + dy * dy + dz * dz);
                        const force = 420 / (distanceSq * Math.sqrt(distanceSq));
                        a.vx += dx * force; a.vy += dy * force; a.vz += dz * force;
                        b.vx -= dx * force; b.vy -= dy * force; b.vz -= dz * force;
                    }
                }
                for (const edge of edges) {
                    const a = nodeById.get(edge.source), b = nodeById.get(edge.target);
                    if (!a || !b) continue;
                    const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
                    const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy + dz * dz));
                    const force = (distance - 105) * 0.00045;
                    a.vx += dx / distance * force; a.vy += dy / distance * force; a.vz += dz / distance * force;
                    b.vx -= dx / distance * force; b.vy -= dy / distance * force; b.vz -= dz / distance * force;
                }
                for (const node of nodes) {
                    node.vx += -node.x * 0.00045;
                    node.vy += -node.y * 0.00045;
                    node.vz += -node.z * 0.00045;
                    node.vx *= 0.91; node.vy *= 0.91; node.vz *= 0.91;
                    node.x += node.vx; node.y += node.vy; node.z += node.vz;
                }
            }

            const camera = cameraRef.current;
            const projected = new Map(nodes.map(node => [node.id, projectNode(node, width, height, camera)]));
            context.fillStyle = 'rgba(5, 18, 28, 0.42)';
            context.fillRect(0, 0, width, height);

            for (let i = 0; i < 85; i++) {
                const x = (i * 97.13) % width;
                const y = (i * 53.71) % height;
                context.fillStyle = 'rgba(103, 232, 249, 0.16)';
                context.fillRect(x, y, 1, 1);
            }

            for (const edge of edges) {
                const a = projected.get(edge.source), b = projected.get(edge.target);
                if (!a || !b) continue;
                context.beginPath();
                context.moveTo(a.x, a.y);
                context.lineTo(b.x, b.y);
                context.strokeStyle = 'rgba(34, 211, 238, 0.19)';
                context.lineWidth = 0.8;
                context.stroke();
            }

            const selected = selectedRef.current;
            const highlighted = highlightedRef.current;
            const ordered = [...nodes].sort((a, b) => projected.get(a.id).depth - projected.get(b.id).depth);
            for (const node of ordered) {
                const point = projected.get(node.id);
                const isSelected = node.id === selected;
                const isHighlighted = highlighted.has(node.source_id);
                const groupHue = [...(node.group || 'docs')].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 70;
                const color = isHighlighted ? '#facc15' : isSelected ? '#ffffff' : 'hsl(' + (180 + groupHue) + ', 78%, 62%)';
                context.beginPath();
                context.arc(point.x, point.y, point.radius + (isSelected ? 4 : 0), 0, Math.PI * 2);
                context.fillStyle = isSelected ? 'rgba(255,255,255,0.2)' : isHighlighted ? 'rgba(250,204,21,0.17)' : 'rgba(34,211,238,0.10)';
                context.fill();
                context.beginPath();
                context.arc(point.x, point.y, point.radius, 0, Math.PI * 2);
                context.fillStyle = color;
                context.shadowColor = color;
                context.shadowBlur = isSelected || isHighlighted ? 18 : 8;
                context.fill();
                context.shadowBlur = 0;

                if (isSelected || isHighlighted || point.radius > 4.4) {
                    context.font = isSelected ? '12px Segoe UI' : '10px Segoe UI';
                    context.fillStyle = isSelected ? '#ffffff' : 'rgba(207,250,254,0.88)';
                    context.textAlign = 'center';
                    context.fillText(String(node.label || '').slice(0, 34), point.x, point.y - point.radius - 8);
                }
            }
            animationId = requestAnimationFrame(draw);
        };

        const handlePointerDown = (event) => {
            dragRef.current = { x: event.clientX, y: event.clientY, moved: false };
            canvas.setPointerCapture?.(event.pointerId);
        };
        const handlePointerMove = (event) => {
            if (!dragRef.current) return;
            const dx = event.clientX - dragRef.current.x;
            const dy = event.clientY - dragRef.current.y;
            if (Math.abs(dx) + Math.abs(dy) > 3) dragRef.current.moved = true;
            cameraRef.current.yaw += dx * 0.006;
            cameraRef.current.pitch = Math.max(-1.3, Math.min(1.3, cameraRef.current.pitch + dy * 0.005));
            dragRef.current.x = event.clientX;
            dragRef.current.y = event.clientY;
        };
        const handlePointerUp = (event) => {
            const drag = dragRef.current;
            dragRef.current = null;
            if (!drag || drag.moved) return;
            const rect = canvas.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;
            let nearest = null, nearestDistance = 22;
            for (const node of nodes) {
                const point = projectNode(node, canvas.clientWidth, canvas.clientHeight, cameraRef.current);
                const distance = Math.hypot(point.x - x, point.y - y);
                if (distance < nearestDistance) { nearest = node; nearestDistance = distance; }
            }
            if (nearest) onSelect(nearest);
        };
        const handleWheel = (event) => {
            event.preventDefault();
            cameraRef.current.zoom = Math.max(0.45, Math.min(2.8, cameraRef.current.zoom * (event.deltaY < 0 ? 1.08 : 0.92)));
        };

        canvas.addEventListener('pointerdown', handlePointerDown);
        canvas.addEventListener('pointermove', handlePointerMove);
        canvas.addEventListener('pointerup', handlePointerUp);
        canvas.addEventListener('pointercancel', handlePointerUp);
        canvas.addEventListener('wheel', handleWheel, { passive: false });
        animationId = requestAnimationFrame(draw);

        return () => {
            cancelAnimationFrame(animationId);
            canvas.removeEventListener('pointerdown', handlePointerDown);
            canvas.removeEventListener('pointermove', handlePointerMove);
            canvas.removeEventListener('pointerup', handlePointerUp);
            canvas.removeEventListener('pointercancel', handlePointerUp);
            canvas.removeEventListener('wheel', handleWheel);
        };
    }, [graph, onSelect]);

    return <canvas ref={canvasRef} className="w-full h-full cursor-grab active:cursor-grabbing" aria-label="Interactive 3D knowledge graph" />;
}

export default function KnowledgeGraphWindow({ onClose }) {
    const [graph, setGraph] = useState({ nodes: [], links: [], count: 0 });
    const [selectedNode, setSelectedNode] = useState(null);
    const [searchText, setSearchText] = useState('');
    const [highlightedIds, setHighlightedIds] = useState(new Set());
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [reindexing, setReindexing] = useState(false);

    const loadGraph = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const response = await fetch(API_ROOT + '/knowledge/graph');
            if (!response.ok) throw new Error('Knowledge index request failed (' + response.status + ').');
            const data = await response.json();
            setGraph(data);
            setSelectedNode(current => current || data.nodes?.[0] || null);
        } catch (err) {
            setError(err.message || 'Could not load the knowledge graph.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadGraph(); }, [loadGraph]);

    const selectNode = useCallback((node) => setSelectedNode(node), []);

    const runSearch = async (event) => {
        event?.preventDefault();
        if (!searchText.trim()) {
            setHighlightedIds(new Set());
            return;
        }
        try {
            const response = await fetch(API_ROOT + '/knowledge/search?q=' + encodeURIComponent(searchText) + '&limit=12');
            const data = await response.json();
            const sources = data.sources || [];
            setHighlightedIds(new Set(sources.map(source => source.id)));
            if (sources.length) {
                const first = sources[0];
                const node = graph.nodes.find(item => item.source_id === first.id);
                if (node) setSelectedNode(node);
            }
        } catch (err) {
            setError(err.message || 'Knowledge search failed.');
        }
    };

    const reindex = async () => {
        setReindexing(true);
        setError('');
        try {
            const response = await fetch(API_ROOT + '/knowledge/reindex', { method: 'POST' });
            if (!response.ok) throw new Error('Reindex failed (' + response.status + ').');
            await loadGraph();
        } catch (err) {
            setError(err.message || 'Could not reindex knowledge sources.');
        } finally {
            setReindexing(false);
        }
    };

    const visibleCount = Math.min(graph.nodes.length, MAX_VISIBLE_NODES);

    return (
        <div className="fixed inset-6 z-[90] flex flex-col overflow-hidden rounded-2xl border border-cyan-500/30 bg-[#030b13]/95 shadow-[0_0_60px_rgba(6,182,212,0.15)] backdrop-blur-xl">
            <div className="flex items-center justify-between border-b border-cyan-500/20 px-5 py-3">
                <div className="flex items-center gap-3">
                    <Network size={20} className="text-cyan-400" />
                    <div>
                        <div className="text-sm font-bold tracking-[0.22em] text-cyan-100">KNOWLEDGE GALAXY</div>
                        <div className="text-[10px] text-cyan-700">{graph.count} indexed sources · drag to rotate · scroll to zoom</div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button onClick={reindex} disabled={reindexing || loading} className="flex items-center gap-2 rounded-lg border border-cyan-800 px-3 py-2 text-xs text-cyan-300 hover:border-cyan-400 disabled:opacity-40">
                        <RefreshCw size={14} className={reindexing ? 'animate-spin' : ''} /> Reindex
                    </button>
                    <button onClick={onClose} className="rounded-lg p-2 text-cyan-600 hover:bg-cyan-950 hover:text-white"><X size={18} /></button>
                </div>
            </div>

            <div className="flex min-h-0 flex-1">
                <div className="relative min-w-0 flex-1">
                    <KnowledgeCanvas graph={graph} selectedId={selectedNode?.id} highlightedIds={highlightedIds} onSelect={selectNode} />
                    {loading && <div className="absolute inset-0 flex items-center justify-center bg-black/50 text-sm text-cyan-300">Indexing documents and reference PDFs…</div>}
                    {error && <div className="absolute bottom-4 left-4 right-4 rounded-lg border border-red-500/30 bg-red-950/80 px-3 py-2 text-xs text-red-200">{error}</div>}
                    <form onSubmit={runSearch} className="absolute left-4 top-4 flex w-[min(440px,80%)] items-center gap-2 rounded-xl border border-cyan-500/25 bg-black/75 p-2">
                        <Search size={16} className="text-cyan-500" />
                        <input value={searchText} onChange={event => setSearchText(event.target.value)} placeholder="Search your indexed notes and PDFs…" className="min-w-0 flex-1 bg-transparent text-xs text-cyan-100 outline-none placeholder:text-cyan-800" />
                        <button type="submit" className="rounded-md bg-cyan-900/60 px-3 py-1.5 text-[10px] font-bold tracking-wider text-cyan-200 hover:bg-cyan-800">SEARCH</button>
                    </form>
                    <div className="absolute bottom-4 left-4 rounded-lg border border-cyan-900/50 bg-black/60 px-3 py-2 text-[10px] text-cyan-700">
                        Showing {visibleCount} of {graph.count} sources · linked by references and shared wikilinks
                    </div>
                </div>

                <aside className="flex w-[320px] shrink-0 flex-col border-l border-cyan-500/20 bg-black/45 p-5">
                    <div className="mb-4 flex items-center gap-2 text-[10px] font-bold tracking-[0.2em] text-cyan-600">
                        <FileText size={14} /> SOURCE DETAILS
                    </div>
                    {selectedNode ? (
                        <>
                            <div className="mb-2 text-[10px] font-mono text-cyan-700">[K{selectedNode.source_id}] · {selectedNode.group}</div>
                            <h2 className="mb-4 text-base font-semibold text-cyan-100">{selectedNode.label}</h2>
                            <p className="mb-5 flex-1 overflow-y-auto whitespace-pre-wrap text-xs leading-6 text-cyan-200/80">{selectedNode.excerpt}</p>
                            <div className="border-t border-cyan-900/60 pt-3 text-[10px] leading-5 text-cyan-800 break-all">{selectedNode.path}</div>
                        </>
                    ) : (
                        <div className="text-xs leading-6 text-cyan-800">Select a node to inspect its source excerpt and location.</div>
                    )}
                </aside>
            </div>
        </div>
    );
}
