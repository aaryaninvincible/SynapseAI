import { useEffect, useMemo, useRef, useState } from "react";
import { Mic, MonitorUp, Code, StopCircle, FileText, Send, Paperclip, ChevronRight, Sparkles, Activity, Volume2, VolumeX } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

type ServerEvent = {
  type: "agent_text_delta" | "agent_action_plan" | "state_update" | "error";
  payload: Record<string, unknown>;
};

type TimelineItem = { role: "user" | "agent" | "system"; text: string };
type ActionStep = {
  type?: string;
  target?: string;
  text?: string;
  bbox?: [number, number, number, number];
};

const API_BASE = import.meta.env.VITE_AGENT_BASE_URL ?? "http://localhost:8000";
type GeminiStatus = {
  backendUp: boolean;
  mode: "gemini" | "mock" | "unknown";
  keyConfigured: boolean;
  clientReady: boolean;
};

export default function App() {
  const [sessionId, setSessionId] = useState<string>("");
  const [wsState, setWsState] = useState<"idle" | "connecting" | "open">("connecting");
  const [input, setInput] = useState("");
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [actionPlan, setActionPlan] = useState<Record<string, unknown> | null>(null);
  const [screenOn, setScreenOn] = useState(false);
  const [micOn, setMicOn] = useState(false);
  const [speechOn, setSpeechOn] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [geminiStatus, setGeminiStatus] = useState<GeminiStatus>({
    backendUp: false,
    mode: "unknown",
    keyConfigured: false,
    clientReady: false,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const frameTimerRef = useRef<number | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const sessionIdRef = useRef<string>("");
  const autoStartRef = useRef(false);
  const closingSessionRef = useRef(false);
  const particleCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const speechOnRef = useRef(false);

  const wsUrl = useMemo(() => {
    if (!sessionId) return "";
    const base = API_BASE.replace("http://", "ws://").replace("https://", "wss://");
    return `${base}/ws/${sessionId}`;
  }, [sessionId]);
  const toWsUrl = (targetSessionId: string) => {
    const base = API_BASE.replace("http://", "ws://").replace("https://", "wss://");
    return `${base}/ws/${targetSessionId}`;
  };

  const append = (role: TimelineItem["role"], text: string) => {
    setTimeline((prev) => [...prev, { role, text }]);
  };

  const requestSessionEnd = (targetSessionId: string, preferBeacon = false) => {
    const url = `${API_BASE}/session/${targetSessionId}/end`;
    if (preferBeacon && typeof navigator !== "undefined" && "sendBeacon" in navigator) {
      try {
        const sent = navigator.sendBeacon(url, new Blob([], { type: "application/json" }));
        if (sent) return;
      } catch {
        // fall back to keepalive fetch
      }
    }
    void fetch(url, { method: "POST", keepalive: preferBeacon }).catch(() => null);
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [timeline]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    speechOnRef.current = speechOn;
  }, [speechOn]);

  useEffect(() => {
    const loadHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        if (!res.ok) throw new Error(`health ${res.status}`);
        const data = await res.json();
        setGeminiStatus({
          backendUp: true,
          mode: data.mode === "gemini" ? "gemini" : "mock",
          keyConfigured: Boolean(data.gemini_api_key_configured),
          clientReady: Boolean(data.gemini_client_ready),
        });
      } catch {
        setGeminiStatus({
          backendUp: false,
          mode: "unknown",
          keyConfigured: false,
          clientReady: false,
        });
      }
    };
    void loadHealth();
  }, []);

  useEffect(() => {
    return () => {
      if (frameTimerRef.current !== null) {
        window.clearInterval(frameTimerRef.current);
      }
      screenStreamRef.current?.getTracks().forEach((t) => t.stop());
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      recorderRef.current?.stop();
      wsRef.current?.close();
      window.speechSynthesis.cancel();
    };
  }, []);

  useEffect(() => {
    const canvas = particleCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let width = 0;
    let height = 0;
    const pointer = { x: -9999, y: -9999 };
    const particleCount = 48;
    const particles = Array.from({ length: particleCount }, () => ({
      x: Math.random(),
      y: Math.random(),
      vx: (Math.random() - 0.5) * 0.0009,
      vy: (Math.random() - 0.5) * 0.0009,
      r: 1 + Math.random() * 2.2,
    }));

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      canvas.width = width;
      canvas.height = height;
    };

    const onMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = e.clientX - rect.left;
      pointer.y = e.clientY - rect.top;
    };
    const onLeave = () => {
      pointer.x = -9999;
      pointer.y = -9999;
    };

    const step = () => {
      ctx.clearRect(0, 0, width, height);
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x <= 0 || p.x >= 1) p.vx *= -1;
        if (p.y <= 0 || p.y >= 1) p.vy *= -1;

        const px = p.x * width;
        const py = p.y * height;
        const dx = px - pointer.x;
        const dy = py - pointer.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < 17000 && d2 > 0.01) {
          const force = 0.000015;
          p.vx += (dx / d2) * force * width;
          p.vy += (dy / d2) * force * height;
          p.vx = Math.max(-0.002, Math.min(0.002, p.vx));
          p.vy = Math.max(-0.002, Math.min(0.002, p.vy));
        }

        ctx.beginPath();
        ctx.fillStyle = "rgba(168,194,255,0.55)";
        ctx.arc(px, py, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = window.requestAnimationFrame(step);
    };

    resize();
    step();
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerleave", onLeave);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  useEffect(() => {
    if (autoStartRef.current) return;
    autoStartRef.current = true;
    void startSession();
  }, []);

  useEffect(() => {
    const handlePageClose = () => {
      const activeSessionId = sessionIdRef.current;
      if (!activeSessionId || closingSessionRef.current) return;
      closingSessionRef.current = true;
      if (frameTimerRef.current !== null) {
        window.clearInterval(frameTimerRef.current);
        frameTimerRef.current = null;
      }
      screenStreamRef.current?.getTracks().forEach((t) => t.stop());
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      recorderRef.current?.stop();
      wsRef.current?.close();
      wsRef.current = null;
      requestSessionEnd(activeSessionId, true);
    };

    window.addEventListener("pagehide", handlePageClose);
    window.addEventListener("beforeunload", handlePageClose);
    return () => {
      window.removeEventListener("pagehide", handlePageClose);
      window.removeEventListener("beforeunload", handlePageClose);
    };
  }, []);

  const startSession = async () => {
    if (sessionIdRef.current || wsRef.current) return;
    try {
      setWsState("connecting");
      const res = await fetch(`${API_BASE}/session/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: "local-dev-user" }),
      });
      if (!res.ok) {
        throw new Error(`Session start failed (${res.status})`);
      }
      const data = await res.json();
      const newSessionId = String(data.session_id ?? "");
      if (!newSessionId) throw new Error("Backend returned empty session_id");
      setSessionId(newSessionId);
      sessionIdRef.current = newSessionId;
      closingSessionRef.current = false;
      connectWs(newSessionId);
    } catch (error) {
      setWsState("idle");
      append("system", `Unable to start session: ${error instanceof Error ? error.message : "unknown error"}`);
    }
  };

  const connectWs = (targetSessionId?: string) => {
    const url = targetSessionId ? toWsUrl(targetSessionId) : wsUrl;
    if (!url || wsRef.current) return;
    setWsState("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => {
      setWsState("open");
    };
    ws.onerror = () => {
      append("system", "Connection issue. Trying again may help.");
    };
    ws.onclose = () => {
      wsRef.current = null;
      setWsState("idle");
    };
    ws.onmessage = (e) => {
      const event: ServerEvent = JSON.parse(e.data);
      if (event.type === "agent_text_delta") {
        const text = String(event.payload.text ?? "");
        append("agent", text);
        if (speechOnRef.current && "speechSynthesis" in window && text) {
          window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
        }
      } else if (event.type === "agent_action_plan") {
        setActionPlan(event.payload);
      } else if (event.type === "state_update") {
        const status = String(event.payload.status ?? "updated");
        if (status === "interrupted") {
          append("system", "Interrupted");
        }
      } else if (event.type === "error") {
        append("system", `Error: ${String(event.payload.message ?? "unknown")}`);
      }
    };
  };

  const sendEvent = (type: string, payload: Record<string, unknown> = {}) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type, payload }));
  };

  const sendText = () => {
    if (!input.trim()) return;
    const text = input.trim();
    append("user", text);
    const normalized = text.toLowerCase();
    if (
      normalized.includes("who build") ||
      normalized.includes("who built") ||
      normalized.includes("developer") ||
      normalized.includes("made you")
    ) {
      const creatorLine = "Mr aryan is my developer, you can find him on instagram aaryaninvincible.";
      append("agent", creatorLine);
      if (speechOnRef.current && "speechSynthesis" in window) {
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(creatorLine));
      }
      setInput("");
      return;
    }
    sendEvent("user_text", { text });
    setInput("");
  };

  const interrupt = () => {
    sendEvent("interrupt", {});
    window.speechSynthesis.cancel();
  };

  const startScreen = async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: 5 },
        audio: false,
      });
      screenStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setScreenOn(true);

      frameTimerRef.current = window.setInterval(() => {
        if (!videoRef.current) return;
        const canvas = document.createElement("canvas");
        canvas.width = videoRef.current.videoWidth || 1280;
        canvas.height = videoRef.current.videoHeight || 720;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
        const imageBase64 = canvas.toDataURL("image/jpeg", 0.65);
        sendEvent("video_frame", { image_base64: imageBase64 });
      }, 1200);

      stream.getVideoTracks()[0].onended = () => {
          stopScreen();
      };
    } catch (e) {
        console.error("Screen share cancelled or failed.");
    }
  };

  const stopScreen = () => {
    if (frameTimerRef.current !== null) {
      window.clearInterval(frameTimerRef.current);
      frameTimerRef.current = null;
    }
    screenStreamRef.current?.getTracks().forEach((t) => t.stop());
    screenStreamRef.current = null;
    setScreenOn(false);
  };

  const blobToBase64 = (blob: Blob): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const result = String(reader.result ?? "");
        const payload = result.includes(",") ? result.split(",")[1] : "";
        resolve(payload);
      };
      reader.onerror = () => reject(new Error("Failed to convert audio blob"));
      reader.readAsDataURL(blob);
    });

  const startMic = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      micStreamRef.current = stream;

      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = async (event) => {
        if (!event.data || event.data.size === 0) return;
        const audioBase64 = await blobToBase64(event.data);
        sendEvent("audio_chunk", {
          audio_base64: audioBase64,
          mime_type: event.data.type || "audio/webm",
          size_bytes: event.data.size,
        });
      };
      recorder.start(500);
      setMicOn(true);
    } catch (e) {
      console.error("Mic access denied or failed.");
    }
  };

  const stopMic = () => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    setMicOn(false);
  };

  const endSession = async () => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) return;
    closingSessionRef.current = true;
    if (screenOn) stopScreen();
    if (micOn) stopMic();
    wsRef.current?.close();
    wsRef.current = null;
    await fetch(`${API_BASE}/session/${activeSessionId}/end`, { method: "POST" }).catch(() => null);
    sessionIdRef.current = "";
    setSessionId("");
    setWsState("idle");
    setActionPlan(null);
    append("system", "Session ended.");
    setIsSidebarOpen(false);
  };

  const actionSteps = (actionPlan?.steps as ActionStep[] | undefined) ?? [];

  return (
    <div className="dark min-h-[100svh] w-full flex text-[#E3E3E3] overflow-x-hidden relative selection:bg-indigo-500/30" style={{ fontFamily: "'Space Grotesk', sans-serif", backgroundColor: "#0b0c10" }}>
        <style>
        {`
            ::-webkit-scrollbar {
              width: 8px;
              height: 8px;
            }
            ::-webkit-scrollbar-track {
              background: transparent;
            }
            ::-webkit-scrollbar-thumb {
              background: rgba(255, 255, 255, 0.15);
              border-radius: 10px;
            }
            ::-webkit-scrollbar-thumb:hover {
              background: rgba(255, 255, 255, 0.25);
            }
            .gemini-gradient {
               background: linear-gradient(90deg, #A8C2FF 0%, #B9A2FF 30%, #E6A2FF 60%, #FFB6C1 100%);
               -webkit-background-clip: text;
               -webkit-text-fill-color: transparent;
            }
            .glow-border {
                position: relative;
            }
            .glow-border::before {
                content: "";
                position: absolute;
                inset: -2px;
                border-radius: inherit;
                background: linear-gradient(45deg, #A8C2FF, #B9A2FF, #E6A2FF, #FFB6C1);
                z-index: -1;
                filter: blur(8px);
                opacity: 0;
                transition: opacity 0.3s;
            }
            .glow-border:hover::before {
                opacity: 0.6;
            }
            .bg-glass {
                background: rgba(30,30,32, 0.6);
                backdrop-filter: blur(24px);
                -webkit-backdrop-filter: blur(24px);
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        `}
        </style>

        {/* Ambient Background Effects */}
        <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
            <canvas ref={particleCanvasRef} className="absolute inset-0 w-full h-full opacity-70" />
            <motion.div 
              animate={{ 
                rotate: [0, 360],
                scale: [1, 1.2, 1],
                opacity: [0.1, 0.2, 0.1]
              }}
              transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
              className="absolute -top-[20%] -left-[10%] w-[60%] h-[60%] rounded-full bg-indigo-500/20 blur-[120px]" 
            />
            <motion.div 
              animate={{ 
                rotate: [360, 0],
                scale: [1, 1.3, 1],
                opacity: [0.1, 0.25, 0.1]
              }}
              transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
              className="absolute top-[40%] -right-[10%] w-[50%] h-[50%] rounded-full bg-fuchsia-500/20 blur-[120px]" 
            />
        </div>

        {/* Main Chat Area */}
        <main className="flex-1 flex flex-col relative z-10 min-h-[100svh] transition-all duration-500">
            {/* Header */}
            <header className="px-3 sm:px-6 lg:px-8 py-3 sm:py-5 flex items-center justify-between gap-2 border-b border-white/5 bg-[#0b0c10]/70 backdrop-blur-md">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-500 to-fuchsia-500 flex items-center justify-center p-[1px]">
                        <div className="w-full h-full bg-[#131314] rounded-full flex items-center justify-center">
                            <Sparkles size={16} className="text-indigo-400" />
                        </div>
                    </div>
                    <h1 className="text-xl font-medium tracking-wide">
                        <span className="gemini-gradient font-bold">Synapse AI</span>
                    </h1>
                </div>
                
                <div className="flex items-center gap-2 sm:gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        setSpeechOn((prev) => !prev);
                        if (speechOnRef.current) {
                          window.speechSynthesis.cancel();
                        }
                      }}
                      className={`px-3 py-2 rounded-full border text-xs sm:text-sm transition ${speechOn ? "border-emerald-400/40 text-emerald-300 bg-emerald-500/10" : "border-white/20 text-slate-300 hover:bg-white/10"}`}
                    >
                      <span className="inline-flex items-center gap-1.5">
                        {speechOn ? <Volume2 size={15} /> : <VolumeX size={15} />}
                        Voice {speechOn ? "On" : "Off"}
                      </span>
                    </button>
                    {wsState === "idle" && (
                      <button onClick={() => connectWs()} className="hidden sm:inline text-sm px-4 py-1.5 rounded-full border border-white/20 hover:bg-white/10 transition">
                        Reconnect
                      </button>
                    )}
                    <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 rounded-full border border-white/10 hover:bg-white/10 transition text-slate-300">
                        <Activity size={18} />
                    </button>
                </div>
            </header>
            <nav className="px-3 sm:px-6 lg:px-8 py-2 border-b border-white/5 bg-[#0f1016]/70 backdrop-blur-md">
              <div className="flex items-center gap-2 overflow-x-auto whitespace-nowrap text-xs sm:text-sm text-slate-300 scrollbar-thin">
                <button className="px-3 py-1.5 rounded-full border border-white/10 hover:bg-white/10 transition-colors">Home</button>
                <button className="px-3 py-1.5 rounded-full border border-white/10 hover:bg-white/10 transition-colors">Features</button>
                <button className="px-3 py-1.5 rounded-full border border-white/10 hover:bg-white/10 transition-colors">About</button>
              </div>
            </nav>

            {/* Chat History */}
            <div className="flex-1 overflow-y-auto w-full max-w-5xl mx-auto px-3 sm:px-6 md:px-8 pt-4 sm:pt-6 pb-6 flex flex-col gap-6 scroll-smooth">
                {timeline.length === 0 ? (
                    <motion.div 
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex flex-col items-center justify-center h-full text-center mt-10 sm:mt-16"
                    >
                        <div className="w-20 h-20 mb-6 rounded-full bg-gradient-to-br from-indigo-500/20 to-fuchsia-500/20 flex items-center justify-center">
                            <Sparkles size={40} className="text-fuchsia-400 opacity-60" />
                        </div>
                        <h2 className="text-2xl sm:text-3xl font-medium mb-3">Welcome to Synapse AI</h2>
                        <p className="text-slate-400 max-w-xl px-4">Hi there. Session is ready in the background. Ask anything, share your screen when needed, and I will help you step by step.</p>
                    </motion.div>
                ) : (
                    timeline.map((item, idx) => (
                        <motion.div 
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            key={idx} 
                            className={`flex gap-4 ${item.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            {item.role !== 'user' && (
                                <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center mt-1 bg-gradient-to-tr from-indigo-600 to-fuchsia-600">
                                    {item.role === 'system' ? <Code size={14} className="text-white" /> : <Sparkles size={16} className="text-white" />}
                                </div>
                            )}
                            
                            <div className={`max-w-[80%] ${item.role === 'user' ? 'bg-[#282A2C] rounded-3xl rounded-tr-sm px-5 py-3.5' : item.role === 'system' ? 'bg-indigo-900/30 border border-indigo-500/20 text-indigo-200 rounded-2xl px-4 py-2 text-sm' : 'text-slate-200 text-lg leading-relaxed pt-1'}`}>
                                {item.text}
                            </div>
                        </motion.div>
                    ))
                )}
                <div ref={chatEndRef} />
            </div>

            {/* Input Area */}
            <div className="sticky bottom-0 left-0 w-full px-3 sm:px-6 pb-[max(10px,env(safe-area-inset-bottom))] pt-4 bg-gradient-to-t from-[#0b0c10] via-[#0b0c10]/85 to-transparent z-10">
                <div className="max-w-4xl mx-auto relative">
                    {/* Glowing shadow base */}
                    <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500/10 via-fuchsia-500/10 to-indigo-500/10 rounded-[32px] blur-xl opacity-50 transition-all duration-500 group-focus-within:opacity-100 group-focus-within:blur-2xl"></div>
                    
                    <div className="bg-[#1A1A1C]/80 backdrop-blur-xl rounded-[32px] p-2 flex flex-col shadow-2xl border border-white/5 transition-all focus-within:border-white/20 focus-within:bg-[#1E1F22]/90 relative z-10 group">
                        <textarea
                            disabled={wsState !== 'open'}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.shiftKey) {
                                  e.preventDefault();
                                  sendText();
                                }
                            }}
                            rows={1}
                            placeholder={wsState === 'open' ? "Ask about what's on your screen..." : wsState === "connecting" ? "Starting session..." : "Retry session to continue..."}
                            className="w-full bg-transparent px-4 sm:px-6 py-3 sm:py-4 outline-none text-[14px] sm:text-[15px] placeholder:text-[#6E6E73] text-white disabled:opacity-50 resize-none overflow-hidden max-h-[150px]"
                            style={{ minHeight: '60px' }}
                        />
                        
                        <div className="flex items-center justify-between px-2 sm:px-3 pb-2 pt-1 border-t border-white/5 mt-1 gap-2">
                            <div className="flex items-center gap-1">
                                <button className="p-2 rounded-full text-[#6E6E73] hover:bg-white/10 hover:text-white transition-colors" title="Attach file (mock)">
                                    <Paperclip size={18} />
                                </button>
                                
                                {/* Mic Toggle */}
                                <button 
                                    onClick={micOn ? stopMic : startMic} 
                                    disabled={wsState !== "open"}
                                    className={`p-2 rounded-full transition-all relative ${micOn ? 'text-rose-400 bg-rose-400/15' : 'text-[#6E6E73] hover:bg-white/10 hover:text-white disabled:opacity-50'}`}
                                    title={micOn ? "Mute Microphone" : "Unmute Microphone"}
                                >
                                    <Mic size={18} />
                                    {micOn && (
                                        <span className="absolute top-0 right-0 w-2.5 h-2.5 bg-rose-500 rounded-full animate-pulse border-2 border-[#1E1F22]"></span>
                                    )}
                                </button>

                                {/* Screen Share Toggle */}
                                <button 
                                    onClick={screenOn ? stopScreen : startScreen} 
                                    disabled={wsState !== "open"}
                                    className={`p-2 rounded-full transition-all ${screenOn ? 'text-indigo-400 bg-indigo-400/15' : 'text-[#6E6E73] hover:bg-white/10 hover:text-white disabled:opacity-50'}`}
                                    title={screenOn ? "Stop Screen Share" : "Start Screen Share"}
                                >
                                    <MonitorUp size={18} />
                                </button>
                                
                                <div className="h-5 w-[1px] bg-white/10 mx-1"></div>

                                {/* Interrupt Base */}
                                <button 
                                    onClick={interrupt} 
                                    disabled={wsState !== "open"}
                                    className="p-2 rounded-full text-[#6E6E73] hover:text-amber-400 hover:bg-amber-400/10 transition-colors disabled:opacity-50"
                                    title="Interrupt Agent"
                                >
                                    <StopCircle size={18} />
                                </button>
                            </div>

                            <div className="flex items-center gap-2">
                                {sessionId && (
                                     <button 
                                        onClick={endSession} 
                                        className="px-3 sm:px-4 py-2 rounded-full text-[11px] sm:text-xs font-semibold text-rose-400 bg-transparent hover:bg-rose-500/10 transition-colors border border-rose-500/20"
                                    >
                                        End Session
                                    </button>
                                )}
                                
                                <button 
                                    onClick={sendText} 
                                    disabled={wsState !== "open" || !input.trim()}
                                    className={`w-10 h-10 flex items-center justify-center rounded-full transition-all ${input.trim() && wsState === 'open' ? 'bg-gradient-to-r from-indigo-500 to-fuchsia-500 text-white shadow-[0_0_15px_rgba(99,102,241,0.4)] hover:scale-105' : 'bg-white/5 text-[#6E6E73]'}`}
                                >
                                    <Send size={16} className="translate-x-[1px] translate-y-[-1px]" />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>

        {/* Right Sidebar - Action Plan & Activity */}
        <AnimatePresence>
            {isSidebarOpen && (
                <>
                <motion.button
                    type="button"
                    aria-label="Close analysis panel"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={() => setIsSidebarOpen(false)}
                    className="absolute inset-0 z-20 bg-black/40 md:hidden"
                />
                <motion.aside 
                    initial={{ x: 400, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ x: 400, opacity: 0 }}
                    transition={{ type: "spring", damping: 25, stiffness: 200 }}
                    className="w-full md:w-[380px] h-[100svh] bg-glass border-l border-white/5 flex flex-col z-30 shadow-2xl absolute right-0 top-0"
                >
                    <div className="p-5 flex items-center justify-between border-b border-white/5 sticky top-0 bg-[#121319]/95 backdrop-blur-md">
                        <div className="flex items-center gap-2">
                            <Activity size={18} className="text-indigo-400" />
                            <h2 className="font-semibold tracking-wide text-sm">Live Analysis</h2>
                        </div>
                        <button
                            type="button"
                            aria-label="Collapse analysis panel"
                            onClick={() => setIsSidebarOpen(false)}
                            className="p-2 rounded-full hover:bg-white/10 text-slate-300"
                        >
                            <ChevronRight size={20} />
                        </button>
                    </div>

                    <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-6">
                        {/* Status Widget */}
                        <div className="bg-[#1E1F20] rounded-2xl p-4 border border-white/5">
                            <h3 className="text-xs uppercase text-slate-500 tracking-wider mb-3 font-semibold">Connections</h3>
                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-slate-300">WebSocket</span>
                                    <div className="flex items-center gap-2">
                                        <div className={`w-2 h-2 rounded-full ${wsState === 'open' ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]' : 'bg-red-400'}`}></div>
                                        <span className="text-xs text-slate-400 capitalize">{wsState}</span>
                                    </div>
                                </div>
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-slate-300">Screen Vision</span>
                                    <div className="flex items-center gap-2">
                                         <div className={`w-2 h-2 rounded-full ${screenOn ? 'bg-indigo-400 shadow-[0_0_8px_#818cf8]' : 'bg-slate-600'}`}></div>
                                         <span className="text-xs text-slate-400">{screenOn ? 'Active' : 'Idle'}</span>
                                    </div>
                                </div>
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-slate-300">Audio Stream</span>
                                    <div className="flex items-center gap-2">
                                         <div className={`w-2 h-2 rounded-full ${micOn ? 'bg-fuchsia-400 shadow-[0_0_8px_#e879f9]' : 'bg-slate-600'}`}></div>
                                          <span className="text-xs text-slate-400">{micOn ? 'Active' : 'Idle'}</span>
                                    </div>
                                </div>
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-slate-300">Gemini</span>
                                    <div className="flex items-center gap-2">
                                         <div className={`w-2 h-2 rounded-full ${geminiStatus.backendUp && geminiStatus.mode === 'gemini' ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]' : geminiStatus.backendUp ? 'bg-amber-400 shadow-[0_0_8px_#f59e0b]' : 'bg-red-400'}`}></div>
                                          <span className="text-xs text-slate-400">
                                            {!geminiStatus.backendUp ? 'Backend Down' : geminiStatus.mode === 'gemini' ? 'Live' : 'Mock'}
                                          </span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Action Plan */}
                        <div>
                            <h3 className="text-xs uppercase text-slate-500 tracking-wider mb-3 font-semibold flex items-center gap-2">
                                <FileText size={14} /> Agent Action Plan
                            </h3>
                            {actionSteps.length === 0 ? (
                                <div className="text-center p-6 border border-white/5 border-dashed rounded-2xl text-slate-500 text-sm">
                                    Waiting for agent to propose actions based on screen context.
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    {actionSteps.map((step, idx) => (
                                        <motion.div 
                                            initial={{ opacity: 0, x: 20 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            key={idx} 
                                            className="bg-[#1E1F20] rounded-xl p-3.5 border border-white/5 border-l-2 border-l-indigo-500"
                                        >
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className="text-[10px] bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded font-mono">STEP {idx + 1}</span>
                                                <span className="text-sm font-semibold text-slate-200 capitalize">{step.type || 'Action'}</span>
                                            </div>
                                            {step.target && <p className="text-xs text-slate-400 break-all"><span className="text-slate-500">Target:</span> {step.target}</p>}
                                            {step.text && <p className="text-xs text-slate-400 mt-1"><span className="text-slate-500">Value:</span> {step.text}</p>}
                                        </motion.div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Raw JSON Toggle */}
                        {actionPlan && (
                            <div>
                                <h3 className="text-xs uppercase text-slate-500 tracking-wider mb-3 font-semibold flex items-center gap-2">
                                    <Code size={14} /> Raw Packet
                                </h3>
                                <div className="bg-black/30 rounded-xl p-3 overflow-x-auto text-[10px] font-mono text-emerald-400 border border-white/5">
                                    <pre className="whitespace-pre-wrap break-words">{JSON.stringify(actionPlan, null, 2)}</pre>
                                </div>
                            </div>
                         )}
                    </div>
                </motion.aside>
                </>
            )}
        </AnimatePresence>

        <footer className="hidden sm:block absolute bottom-2 left-6 z-30 text-[11px] text-slate-500">
          Synapse AI | Developer - aryaninvincible
        </footer>

        <video ref={videoRef} style={{ display: "none" }} playsInline muted />
    </div>
  );
}
