import { useEffect, useMemo, useRef, useState } from "react";

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

export default function App() {
  const [sessionId, setSessionId] = useState<string>("");
  const [wsState, setWsState] = useState<"idle" | "connecting" | "open">("idle");
  const [input, setInput] = useState("");
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [actionPlan, setActionPlan] = useState<Record<string, unknown> | null>(null);
  const [screenOn, setScreenOn] = useState(false);
  const [micOn, setMicOn] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const frameTimerRef = useRef<number | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);

  const wsUrl = useMemo(() => {
    if (!sessionId) return "";
    const base = API_BASE.replace("http://", "ws://").replace("https://", "wss://");
    return `${base}/ws/${sessionId}`;
  }, [sessionId]);

  const append = (role: TimelineItem["role"], text: string) => {
    setTimeline((prev) => [...prev, { role, text }]);
  };

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

  const startSession = async () => {
    setWsState("connecting");
    const res = await fetch(`${API_BASE}/session/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: "local-dev-user" }),
    });
    const data = await res.json();
    setSessionId(data.session_id);
  };

  const connectWs = () => {
    if (!wsUrl || wsRef.current) return;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => {
      setWsState("open");
      append("system", "WebSocket connected.");
    };
    ws.onclose = () => {
      wsRef.current = null;
      setWsState("idle");
      append("system", "WebSocket closed.");
    };
    ws.onmessage = (e) => {
      const event: ServerEvent = JSON.parse(e.data);
      if (event.type === "agent_text_delta") {
        const text = String(event.payload.text ?? "");
        append("agent", text);
        if ("speechSynthesis" in window && text) {
          window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
        }
      } else if (event.type === "agent_action_plan") {
        setActionPlan(event.payload);
      } else if (event.type === "state_update") {
        const status = String(event.payload.status ?? "updated");
        if (status === "interrupted") {
          append("system", "State: interrupted");
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
    append("user", input.trim());
    sendEvent("user_text", { text: input.trim() });
    setInput("");
  };

  const interrupt = () => {
    sendEvent("interrupt", {});
    window.speechSynthesis.cancel();
  };

  const startScreen = async () => {
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
  };

  const stopMic = () => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    setMicOn(false);
  };

  const endSession = async () => {
    if (!sessionId) return;
    if (screenOn) stopScreen();
    if (micOn) stopMic();
    wsRef.current?.close();
    wsRef.current = null;
    await fetch(`${API_BASE}/session/${sessionId}/end`, { method: "POST" }).catch(() => null);
    setSessionId("");
    setWsState("idle");
    setActionPlan(null);
    append("system", "Session ended.");
  };

  const actionSteps = (actionPlan?.steps as ActionStep[] | undefined) ?? [];

  return (
    <div className="page">
      <header>
        <h1>ScreenSense Support Copilot</h1>
        <p>Real-time multimodal troubleshooting scaffold.</p>
      </header>

      <section className="controls">
        <button onClick={startSession} disabled={!!sessionId}>
          {sessionId ? `Session: ${sessionId.slice(0, 8)}...` : "Start Session"}
        </button>
        <button onClick={connectWs} disabled={!sessionId || wsState === "open"}>
          {wsState === "open" ? "Connected" : "Connect WS"}
        </button>
        <button onClick={interrupt} disabled={wsState !== "open"}>
          Interrupt
        </button>
        <button onClick={screenOn ? stopScreen : startScreen} disabled={wsState !== "open"}>
          {screenOn ? "Stop Screen Share" : "Start Screen Share"}
        </button>
        <button onClick={micOn ? stopMic : startMic} disabled={wsState !== "open"}>
          {micOn ? "Stop Mic Stream" : "Start Mic Stream"}
        </button>
        <button onClick={endSession} disabled={!sessionId}>
          End Session
        </button>
      </section>

      <section className="chat">
        <div className="inputRow">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendText()}
            placeholder="Ask the agent..."
          />
          <button onClick={sendText} disabled={wsState !== "open"}>
            Send
          </button>
        </div>

        <div className="timeline">
          {timeline.map((item, idx) => (
            <div key={`${item.role}-${idx}`} className={`msg ${item.role}`}>
              <strong>{item.role}:</strong> {item.text}
            </div>
          ))}
        </div>
      </section>

      <section className="plan">
        <h2>Action Plan</h2>
        <div className="steps">
          {actionSteps.length === 0 && <p>No actionable steps yet.</p>}
          {actionSteps.map((step, idx) => (
            <div className="step" key={`step-${idx}`}>
              <strong>{idx + 1}. {step.type ?? "action"}</strong>
              <span>{step.target ? `Target: ${step.target}` : "Target: N/A"}</span>
              {step.text && <span>Input: {step.text}</span>}
              {step.bbox && <span>BBox: {JSON.stringify(step.bbox)}</span>}
            </div>
          ))}
        </div>
        <pre>{actionPlan ? JSON.stringify(actionPlan, null, 2) : "No plan yet."}</pre>
      </section>

      <video ref={videoRef} style={{ display: "none" }} playsInline muted />
    </div>
  );
}
