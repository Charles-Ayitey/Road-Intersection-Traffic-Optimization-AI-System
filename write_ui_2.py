import os

app_tsx = """import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LineChart, Line, Legend, AreaChart, Area } from 'recharts';
import { Activity, Camera, Cpu, Map as MapIcon, AlertTriangle, Menu, MapPin, Gauge, Settings, ShieldAlert, LogOut, Video, ActivitySquare, BrainCircuit } from 'lucide-react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

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
  ai_metrics: { reward: number; step: number; mp_override: boolean };
}

const API_BASE = 'http://localhost:8000';
const WS_BASE = 'ws://localhost:8000/ws';

export default function App() {
  const [state, setState] = useState<TrafficState | null>(null);
  const [connStatus, setConnStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [history, setHistory] = useState<any[]>([]);
  const [metricsHistory, setMetricsHistory] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'overview' | 'ai_metrics'>('overview');

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
          
          const now = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
          setHistory(prev => {
            const newHistory = [...prev, { time: now, ...data.counts }];
            if (newHistory.length > 60) newHistory.shift();
            return newHistory;
          });
          
          if (data.ai_metrics) {
            setMetricsHistory(prev => {
               // only push if step changed
               const last = prev[prev.length - 1];
               if (last && last.step === data.ai_metrics.step) return prev;
               const newM = [...prev, { time: now, ...data.ai_metrics }];
               if (newM.length > 100) newM.shift();
               return newM;
            });
          }
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
  
  return (
    <div className="min-h-screen flex bg-[#f0f4f8] text-slate-800 font-sans">
      
      {/* Sidebar Navigation */}
      <aside className="w-20 bg-white border-r border-slate-200 flex flex-col pt-6 items-center flex-shrink-0 z-10 shadow-sm">
        <div className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center font-bold text-xl mb-8 shadow-inner">
           ql
        </div>
        <nav className="flex-1 w-full flex flex-col gap-4 items-center">
           <button 
             onClick={() => setActiveTab('overview')}
             title="Live Overview"
             className={cn("p-3 rounded-xl transition-all", activeTab === 'overview' ? "bg-blue-50 text-blue-600 shadow-sm" : "text-slate-400 hover:bg-slate-100 hover:text-slate-700")}
           >
             <ActivitySquare className="w-6 h-6" strokeWidth={2}/>
           </button>
           <button 
             onClick={() => setActiveTab('ai_metrics')}
             title="AI Metrics & Telemetry"
             className={cn("p-3 rounded-xl transition-all", activeTab === 'ai_metrics' ? "bg-indigo-50 text-indigo-600 shadow-sm" : "text-slate-400 hover:bg-slate-100 hover:text-slate-700")}
           >
             <BrainCircuit className="w-6 h-6" strokeWidth={2}/>
           </button>
           <div className="w-10 border-t border-slate-200 my-2" />
           {[
             {icon: Camera, title: "Vision Feeds"}, 
             {icon: MapIcon, title: "Map View"}, 
             {icon: Settings, title: "Settings"}
           ].map((item, idx) => (
             <button key={idx} title={item.title} className="p-3 rounded-xl transition-all text-slate-400 hover:bg-slate-100 hover:text-slate-700">
               <item.icon className="w-6 h-6" strokeWidth={2}/>
             </button>
           ))}
        </nav>
        <div className="pb-6">
           <button className="w-10 h-10 rounded-full bg-slate-100 text-slate-500 hover:bg-rose-50 hover:text-rose-500 flex items-center justify-center transition-colors" title="Logout">
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
                {activeTab === 'overview' ? 'Intersection 01 (Central)' : 'AI Telemetry Hub'}
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
            
            {activeTab === 'overview' ? (
              <>
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
                       <KpiCard title="North Appr." val={state?.counts. नॉर्थ || state?.counts.North || 0} isGreen={state?.current_phase === 0} wait={nsWait} />
                       <KpiCard title="South Appr." val={state?.counts.South || 0} isGreen={state?.current_phase === 0} wait={nsWait} />
                       <KpiCard title="East Appr."  val={state?.counts.East || 0}  isGreen={state?.current_phase === 2} wait={ewWait} />
                       <KpiCard title="West Appr."  val={state?.counts.West || 0}  isGreen={state?.current_phase === 2} wait={ewWait} />
                    </div>

                    {/* Map / Camera Grid Section */}
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                       <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                          <h2 className="font-bold flex items-center gap-2"><Video className="w-5 h-5 text-blue-500"/> Sensors & Camera Data</h2>
                          <span className={cn("text-xs font-bold px-2 py-1 rounded bg-opacity-20", isStale ? "bg-rose-50 text-rose-600 border border-rose-200" : "bg-emerald-50 text-emerald-600 border border-emerald-200")}>{isStale ? 'VISION STALE (Sim Only Active)' : 'LIVE DETECTIONS'}</span>
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
                          <p className="text-sm text-slate-500">Live queue counts from environment</p>
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
              </>
            ) : (
              // AI Metrics Dashboard content
              <div className="flex-1 space-y-6 animate-in fade-in duration-300">
                 
                 {/* Top row - Summary metrics */}
                 <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="bg-indigo-500 text-white rounded-2xl p-5 shadow-md flex items-center justify-between">
                       <div>
                         <p className="text-indigo-100 text-xs font-bold uppercase tracking-wider mb-1">Current Step</p>
                         <h3 className="text-4xl font-extrabold">{state?.ai_metrics?.step || 0}</h3>
                       </div>
                       <Activity className="w-12 h-12 opacity-50"/>
                    </div>
                    <div className="bg-white border text-center border-slate-200 rounded-2xl p-5 shadow-sm">
                       <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">PPO Reward Feedback</p>
                       <h3 className={cn("text-3xl font-extrabold", (state?.ai_metrics?.reward || 0) < 0 ? "text-rose-500" : "text-emerald-500")}>
                          {(state?.ai_metrics?.reward || 0).toFixed(2)}
                       </h3>
                    </div>
                    <div className="bg-white border text-center border-slate-200 rounded-2xl p-5 shadow-sm flex flex-col justify-center">
                       <p className="text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">Max Pressure Guard</p>
                       <div className="mt-2 flex gap-2 items-center justify-center">
                         <span className={cn("w-3 h-3 rounded-full shadow-inner", state?.ai_metrics?.mp_override ? "bg-amber-500 animate-pulse" : "bg-slate-300")}/>
                         <h3 className="text-xl font-bold text-slate-800">{state?.ai_metrics?.mp_override ? "OVERRIDING" : "STANDBY"}</h3>
                       </div>
                    </div>
                 </div>

                 {/* Realtime Reward Graph */}
                 <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5">
                    <div className="mb-4 pl-2">
                       <h2 className="font-bold text-lg flex items-center gap-2 text-indigo-700">
                          <Cpu className="w-5 h-5"/> Live Reward Optimization Curve
                       </h2>
                       <p className="text-sm text-slate-500">Monitoring real-time throughput vs penalty optimization (PPO Agent)</p>
                    </div>
                    <div className="h-80">
                       <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={metricsHistory}>
                            <defs>
                              <linearGradient id="colorReward" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                                <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9"/>
                            <XAxis dataKey="step" tick={{fontSize: 12, fill: '#94a3b8'}} axisLine={false} tickLine={false}/>
                            <YAxis tick={{fontSize: 12, fill: '#94a3b8'}} width={50} tickLine={false} axisLine={false}/>
                            <Tooltip contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'}} />
                            <Area type="monotone" dataKey="reward" stroke="#6366f1" strokeWidth={3} fillOpacity={1} fill="url(#colorReward)" isAnimationActive={false}/>
                          </AreaChart>
                       </ResponsiveContainer>
                    </div>
                 </div>
                 
              </div>
            )}

            {/* Right Context Panel (Controls) */}
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
               <div className={cn("bg-white rounded-2xl shadow-sm border border-slate-200 p-5 transition-all", state?.mode !== 'Manual Override' && "opacity-50 grayscale pointer-events-none")}>
                  <h2 className="font-bold text-slate-800 mb-4">Manual Control</h2>
                  <div className="flex flex-col gap-3">
                     <button onClick={() => manualPhase(0)} className={cn("py-3 px-4 rounded-xl font-bold text-sm transition-all focus:outline-none flex justify-between shadow-sm border-b-4 placeholder", (state?.mode === 'Manual Override' && state?.manual_phase === 0) ? "bg-emerald-500 text-white border-emerald-600 border-b-0 translate-y-1" : "bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200 active:border-b-0 active:translate-y-1")}>
                        Set NORTH-SOUTH
                        {state?.manual_phase === 0 && <span className="bg-white text-emerald-600 text-xs px-2 py-0.5 rounded-md">ACTIVE</span>}
                     </button>
                     <button onClick={() => manualPhase(2)} className={cn("py-3 px-4 rounded-xl font-bold text-sm transition-all focus:outline-none flex justify-between shadow-sm border-b-4 placeholder", (state?.mode === 'Manual Override' && state?.manual_phase === 2) ? "bg-emerald-500 text-white border-emerald-600 border-b-0 translate-y-1" : "bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200 active:border-b-0 active:translate-y-1")}>
                        Set EAST-WEST
                        {state?.manual_phase === 2 && <span className="bg-white text-emerald-600 text-xs px-2 py-0.5 rounded-md">ACTIVE</span>}
                     </button>
                  </div>
               </div>

               {/* Priority Intervention */}
               <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-rose-500"/>
                  <h2 className="font-bold text-slate-800 mb-1">Priority Override</h2>
                  <p className="text-xs text-slate-500 mb-4">Pre-empt AI for emergency/pedestrian phases.</p>
                  
                  <div className="grid grid-cols-2 gap-3">
                     <button disabled={isOverrideActive} onClick={() => triggerOverride(0, 15)} className="col-span-1 bg-white border-2 border-rose-200 hover:bg-rose-50 hover:border-rose-300 text-rose-600 font-bold rounded-xl py-4 flex flex-col items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:grayscale">
                        <AlertTriangle className="w-6 h-6"/>
                        <span className="text-xs uppercase tracking-wider">NS Block</span>
                     </button>
                     <button disabled={isOverrideActive} onClick={() => triggerOverride(2, 15)} className="col-span-1 bg-white border-2 border-rose-200 hover:bg-rose-50 hover:border-rose-300 text-rose-600 font-bold rounded-xl py-4 flex flex-col items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:grayscale">
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
function KpiCard({ title, val, isGreen, wait }: any) {
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
         <div className="w-full h-full flex flex-col justify-end p-2 opacity-50 font-mono text-[8px] text-emerald-400">
            <p>REC • 1080P/60FPS</p>
         </div>
      </div>
   );
}
"""

with open("dashboard_ui/src/App.tsx", "w", encoding="utf-8") as f:
    f.write(app_tsx)

print("Updated App.tsx.")