import { useMemo, useRef, useState } from "react";

type ServerEvent = {
  type: "agent_text_delta" | "agent_action_plan" | "state_update" | "error";
  payload: Record<string, unknown>;
};

type TimelineItem = { role: "user" | "agent" | "system"; text: string };

const API_BASE = import.meta.env.VITE_AGENT_BASE_URL ?? "http://localhost:8000";

export default function App() {
  const [sessionId, setSessionId] = useState<string>("");
  const [wsState, setWsState] = useState<"idle" | "connecting" | "open">("idle");
  const [input, setInput] = useState("");
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [actionPlan, setActionPlan] = useState<Record<string, unknown> | null>(null);
  const [screenOn, setScreenOn] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const frameTimerRef = useRef<number | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);

  const wsUrl = useMemo(() => {
    if (!sessionId) return "";
    const base = API_BASE.replace("http://", "ws://").replace("https://", "wss://");
    return `${base}/ws/${sessionId}`;
  }, [sessionId]);

  const append = (role: TimelineItem["role"], text: string) => {
    setTimeline((prev) => [...prev, { role, text }]);
  };

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
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
        }
      } else if (event.type === "agent_action_plan") {
        setActionPlan(event.payload);
      } else if (event.type === "state_update") {
        append("system", `State: ${String(event.payload.status ?? "updated")}`);
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
    mediaStreamRef.current = stream;
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
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    setScreenOn(false);
  };

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
        <pre>{actionPlan ? JSON.stringify(actionPlan, null, 2) : "No plan yet."}</pre>
      </section>

      <video ref={videoRef} style={{ display: "none" }} playsInline muted />
    </div>
  );
}

