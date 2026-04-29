import os

app_tsx = """import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LineChart, Line, Legend } from 'recharts';
import { Activity, Camera, Cpu, Map as MapIcon, AlertTriangle, Menu, MapPin, Gauge, Settings, ShieldAlert, LogOut, Video, ActivitySquare } from 'lucide-react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

// --- Types ---
interface TrafficState {
  counts: { North: number; South: number; East: number; West: number };
  current_phase: number;
  last_vision_update: number;
  system_status: string;
  mode: string;
  manual_phase: number;
  last_green_ts: { [key: string]: number };
  active_override: { phase: number | null; expires_at: number };
}

const API_BASE = 'http://localhost:8000';
const WS_BASE = 'ws://localhost:8000/ws';

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

// --- Main App ---
export default function App() {
  const [state, setState] = useState<TrafficState | null>(null);
  const [connStatus, setConnStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connect = () => {
      ws = new WebSocket(WS_BASE);
      setConnStatus('connecting');

      ws.onopen = () => setConnStatus('connected');
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as TrafficState;
          setState(data);
          
          setHistory(prev => {
            const now = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
            const newHistory = [...prev, { time: now, ...data.counts }];
            if (newHistory.length > 60) newHistory.shift();
            return newHistory;
          });
        } catch (e) {}
      };

      ws.onclose = () => {
        setConnStatus('disconnected');
        reconnectTimeout = setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);

  const changeMode = async (mode: string) => {
    try { await fetch(`${API_BASE}/set_mode`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }) }); } catch (e) {}
  };

  const manualPhase = async (phase: number) => {
    try { await fetch(`${API_BASE}/set_phase`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phase }) }); } catch (e) {}
  };

  const triggerOverride = async (phase: number, duration: number) => {
    try { await fetch(`${API_BASE}/trigger_override`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phase, duration }) }); } catch (e) {}
  };

  const isStale = state ? ((Date.now() / 1000) - state.last_vision_update) > 5 : true;
  const isOverrideActive = state?.active_override?.phase !== null && (state?.active_override?.expires_at || 0) > (Date.now() / 1000);
  const nsWait = state ? Math.floor((Date.now() / 1000) - (state.last_green_ts["0"] || 0)) : 0;
  const ewWait = state ? Math.floor((Date.now() / 1000) - (state.last_green_ts["2"] || 0)) : 0;
  
  const chartData = state ? [
    { name: 'North', val: state.counts.North, fill: '#ef4444' },
    { name: 'South', val: state.counts.South, fill: '#3b82f6' },
    { name: 'East', val: state.counts.East, fill: '#eab308' },
    { name: 'West', val: state.counts.West, fill: '#22c55e' },
  ] : [];

  return (
    <div className="min-h-screen flex bg-[#f0f4f8] text-slate-800 font-sans">
      
      {/* Sidebar - Inspired by reference */}
      <aside className="w-20 bg-white border-r border-slate-200 flex flex-col pt-6 items-center flex-shrink-0 z-10 shadow-sm">
        <div className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center font-bold text-xl mb-8">
           ql
        </div>
        <nav className="flex-1 w-full flex flex-col gap-4 items-center">
          {[
            {icon: ActivitySquare, active: true}, 
            {icon: Gauge}, 
            {icon: Camera}, 
            {icon: Cpu}, 
            {icon: MapIcon}, 
            {icon: Settings}
          ].map((item, idx) => (
             <button key={idx} className={cn("p-3 rounded-xl transition-all", item.active ? "bg-blue-50 text-blue-600 shadow-sm" : "text-slate-400 hover:bg-slate-100 hover:text-slate-700")}>
               <item.icon className="w-6 h-6" strokeWidth={2}/>
             </button>
          ))}
        </nav>
        <div className="pb-6">
           <button className="w-10 h-10 rounded-full bg-slate-100 text-slate-500 hover:bg-rose-50 hover:text-rose-500 flex items-center justify-center transition-colors">
              <LogOut className="w-5 h-5 ml-1"/>
           </button>
        </div>
      </aside>

      {/* Main Area */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        
        {/* Top Bar */}
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0 relative z-0">
          <div className="flex items-center gap-3">
             <h1 className="font-bold text-lg text-slate-800 tracking-tight flex items-center gap-2">
                <MapPin className="text-emerald-500 w-5 h-5" /> 
                Intersection 01 (Central)
             </h1>
          </div>
          <div className="flex items-center gap-4">
             <div className="flex items-center bg-slate-100 rounded-full px-3 py-1.5 shadow-inner">
                <div className={cn("w-2.5 h-2.5 rounded-full mr-2 shadow-sm", connStatus === 'connected' ? 'bg-emerald-500' : 'bg-rose-500 animate-pulse')}/>
                <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">{connStatus}</span>
             </div>
          </div>
        </header>

        {/* Dashboard Content */}
        <div className="flex-1 overflow-auto p-4 lg:p-6">
          <div className="max-w-[1600px] mx-auto flex flex-col lg:flex-row gap-6">
            
            {/* Left Canvas (Cameras & Metrics) */}
            <div className="flex-1 space-y-6">
               
               {/* Quick Alert Banner */}
               {isOverrideActive && (
                 <div className="bg-red-500 text-white rounded-2xl p-4 flex items-center gap-4 shadow-lg animate-in slide-in-from-top-4">
                    <ShieldAlert className="w-8 h-8 animate-pulse shrink-0"/>
                    <div>
                      <h2 className="font-bold text-lg">Priority Override Active</h2>
                      <p className="text-red-100 font-medium">System is forcing Phase {state?.active_override.phase === 0 ? "NORTH-SOUTH" : "EAST-WEST"} Green.</p>
                    </div>
                 </div>
               )}

               {/* KPI Row */}
               <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <KpiCard title="North Appr." val={state?.counts.North || 0} isGreen={state?.current_phase === 0} wait={nsWait} color="red"/>
                  <KpiCard title="South Appr." val={state?.counts.South || 0} isGreen={state?.current_phase === 0} wait={nsWait} color="blue"/>
                  <KpiCard title="East Appr."  val={state?.counts.East || 0}  isGreen={state?.current_phase === 2} wait={ewWait} color="amber"/>
                  <KpiCard title="West Appr."  val={state?.counts.West || 0}  isGreen={state?.current_phase === 2} wait={ewWait} color="emerald"/>
               </div>

               {/* Map / Camera Grid Section (Visualizing the physical junction) */}
               <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                  <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                     <h2 className="font-bold flex items-center gap-2"><Video className="w-5 h-5 text-blue-500"/> Live Vision Feeds</h2>
                     <span className={cn("text-xs font-bold px-2 py-1 rounded bg-opacity-20", isStale ? "bg-rose-500 text-rose-600" : "bg-emerald-500 text-emerald-600")}>{isStale ? 'STALE DETECTIONS' : 'LIVE DETECTIONS'}</span>
                  </div>
                  <div className="grid grid-cols-2 p-4 gap-4 bg-slate-50">
                     <CameraMock dir="North" val={state?.counts.North || 0} state={state?.current_phase}/>
                     <CameraMock dir="South" val={state?.counts.South || 0} state={state?.current_phase}/>
                     <CameraMock dir="East" val={state?.counts.East || 0} state={state?.current_phase}/>
                     <CameraMock dir="West" val={state?.counts.West || 0} state={state?.current_phase}/>
                  </div>
               </div>

               {/* Charting */}
               <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5">
                  <div className="mb-4 pl-2">
                     <h2 className="font-bold text-lg">Traffic Volume Trend</h2>
                     <p className="text-sm text-slate-500">60-second rolling average</p>
                  </div>
                  <div className="h-64">
                     <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={history}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9"/>
                          <XAxis dataKey="time" hide/>
                          <YAxis tick={{fontSize: 12, fill: '#94a3b8'}} width={30} tickLine={false} axisLine={false}/>
                          <Tooltip contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'}} />
                          <Legend iconType="circle" wrapperStyle={{fontSize: '13px', paddingTop: '10px'}}/>
                          <Line type="monotone" dataKey="North" stroke="#ef4444" strokeWidth={3} dot={false} isAnimationActive={false}/>
                          <Line type="monotone" dataKey="South" stroke="#3b82f6" strokeWidth={3} dot={false} isAnimationActive={false}/>
                          <Line type="monotone" dataKey="East" stroke="#eab308" strokeWidth={3} dot={false} isAnimationActive={false}/>
                          <Line type="monotone" dataKey="West" stroke="#22c55e" strokeWidth={3} dot={false} isAnimationActive={false}/>
                        </LineChart>
                     </ResponsiveContainer>
                  </div>
               </div>

            </div>

            {/* Right Context Panel (Controls & Intelligence) */}
            <div className="w-full lg:w-80 flex flex-col gap-6 shrink-0">
               
               {/* Current Mode */}
               <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5">
                  <div className="flex items-center justify-between mb-4">
                     <h2 className="font-bold text-slate-800">Traffic Mode</h2>
                     <Cpu className="w-5 h-5 text-indigo-500"/>
                  </div>
                  <div className="flex flex-col gap-2">
                     {["AI Controlled", "Fixed Timing", "Manual Override"].map(m => (
                       <button 
                         key={m} onClick={() => changeMode(m)}
                         className={cn("w-full text-left px-4 py-3 rounded-xl border-2 font-bold text-sm transition-all flex justify-between items-center group", state?.mode === m ? "bg-indigo-50 border-indigo-500 text-indigo-700 hover:bg-indigo-100" : "bg-white border-transparent text-slate-500 shadow-sm hover:border-slate-200")}
                       >
                         {m}
                         <div className={cn("w-2 h-2 rounded-full", state?.mode === m ? "bg-indigo-500" : "bg-transparent group-hover:bg-slate-200")}/>
                       </button>
                     ))}
                  </div>
               </div>

               {/* Manual Phase Config */}
               <div className={cn("bg-white rounded-2xl shadow-sm border border-slate-200 p-5 transition-all", state?.mode !== 'Manual Override' && "opacity-40 grayscale pointer-events-none")}>
                  <h2 className="font-bold text-slate-800 mb-4">Manual Control</h2>
                  <div className="flex flex-col gap-3">
                     <button onClick={() => manualPhase(0)} className={cn("py-3 px-4 rounded-xl font-bold text-sm transition-all focus:outline-none flex justify-between shadow-sm border-b-4 placeholder", state?.current_phase === 0 ? "bg-emerald-500 text-white border-emerald-600 active:border-b-0 active:translate-y-1" : "bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200 active:border-b-0 active:translate-y-1")}>
                        Set NORTH-SOUTH
                        {state?.current_phase === 0 && <span className="bg-white text-emerald-600 text-xs px-2 py-0.5 rounded-md">ACTIVE</span>}
                     </button>
                     <button onClick={() => manualPhase(2)} className={cn("py-3 px-4 rounded-xl font-bold text-sm transition-all focus:outline-none flex justify-between shadow-sm border-b-4 placeholder", state?.current_phase === 2 ? "bg-emerald-500 text-white border-emerald-600 active:border-b-0 active:translate-y-1" : "bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200 active:border-b-0 active:translate-y-1")}>
                        Set EAST-WEST
                        {state?.current_phase === 2 && <span className="bg-white text-emerald-600 text-xs px-2 py-0.5 rounded-md">ACTIVE</span>}
                     </button>
                  </div>
               </div>

               {/* Priority Intervention */}
               <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-rose-500"/>
                  <h2 className="font-bold text-slate-800 mb-1">Priority Override</h2>
                  <p className="text-xs text-slate-500 mb-4">Pre-empt AI for emergency/pedestrian phases.</p>
                  
                  <div className="grid grid-cols-2 gap-3">
                     <button disabled={isOverrideActive} onClick={() => triggerOverride(0, 15)} className="col-span-1 bg-white border-2 border-rose-200 hover:bg-rose-50 hover:border-rose-300 text-rose-600 font-bold rounded-xl py-4 flex flex-col items-center justify-center gap-2 transition-all disabled:opacity-50">
                        <AlertTriangle className="w-6 h-6"/>
                        <span className="text-xs uppercase tracking-wider">NS Block</span>
                     </button>
                     <button disabled={isOverrideActive} onClick={() => triggerOverride(2, 15)} className="col-span-1 bg-white border-2 border-rose-200 hover:bg-rose-50 hover:border-rose-300 text-rose-600 font-bold rounded-xl py-4 flex flex-col items-center justify-center gap-2 transition-all disabled:opacity-50">
                        <AlertTriangle className="w-6 h-6"/>
                        <span className="text-xs uppercase tracking-wider">EW Block</span>
                     </button>
                  </div>
               </div>

            </div>

          </div>
        </div>
      </main>
    </div>
  );
}

// --- Helpers ---
function KpiCard({ title, val, isGreen, wait, color }: any) {
  const cMap: any = {
     red: 'text-rose-500 bg-rose-50',
     blue: 'text-blue-500 bg-blue-50',
     amber: 'text-amber-500 bg-amber-50',
     emerald: 'text-emerald-500 bg-emerald-50'
  };
  const isStarving = wait > 40 && !isGreen;

  return (
    <div className={cn("bg-white p-5 rounded-2xl border border-slate-200 shadow-sm relative overflow-hidden transition-all", isGreen ? "ring-2 ring-emerald-400" : "")}>
       <div className="flex justify-between items-start mb-2">
          <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">{title}</p>
          <div className={cn("w-3 h-3 rounded-full shadow-inner", isGreen ? "bg-emerald-500" : "bg-rose-500")}/>
       </div>
       <div className="flex items-baseline gap-2 mb-3">
         <span className="text-4xl font-extrabold text-slate-800 leading-none">{val}</span>
         <span className="text-sm font-semibold text-slate-400">vehs</span>
       </div>
       <div className={cn("px-3 py-2 rounded-lg text-xs font-bold flex justify-between items-center transition-colors", isGreen ? "bg-emerald-50 text-emerald-700" : (isStarving ? "bg-rose-500 text-white animate-pulse" : "bg-slate-50 text-slate-500"))}>
         <span>WAIT TIME</span>
         <span>{isGreen ? '0s' : `${wait}s`} {isStarving && '⚠️'}</span>
       </div>
    </div>
  );
}

function CameraMock({ dir, val, state }: any) {
   const isGreen = (dir === 'North' || dir === 'South') ? state === 0 : state === 2;
   return (
      <div className="relative aspect-video rounded-xl bg-slate-800 overflow-hidden group shadow-inner">
         <div className="absolute inset-0 opacity-20 pointer-events-none" style={{backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)', backgroundSize: '10px 10px'}}/>
         <div className="absolute top-2 left-2 right-2 flex justify-between items-center z-10">
            <div className="bg-black/60 backdrop-blur-md text-white text-[10px] font-bold px-2 py-1 rounded flex items-center gap-2 border border-white/10">
               <div className={cn("w-2 h-2 rounded-full", isGreen ? "bg-emerald-500" : "bg-rose-500")} />
               Cam: {dir}
            </div>
            <div className="bg-blue-500/80 backdrop-blur-md text-white text-xs font-black px-2 py-0.5 rounded shadow-sm border border-blue-400/50">
               {val}
            </div>
         </div>
         {/* Simulate camera perspective */}
         <div className="w-full h-full flex flex-col justify-end p-2 opacity-50 font-mono text-[8px] text-emerald-400">
            <p>REC • 1080P/60FPS</p>
         </div>
      </div>
   );
}
"""

index_css = """@import "tailwindcss";

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background-color: #f0f4f8;
  color: #333333;
}
"""

with open("dashboard_ui/src/App.tsx", "w", encoding="utf-8") as f:
    f.write(app_tsx)

with open("dashboard_ui/src/index.css", "w", encoding="utf-8") as f:
    f.write(index_css)

print("Dashboard UI files updated successfully.")
