'use client';
import {useEffect,useRef,useState} from 'react';
import {videoFrames} from '../lib/media';
export type ClipRange={start:number;end:number};
const clock=(seconds:number)=>`${Math.floor(seconds/60)}:${(seconds%60).toFixed(1).padStart(4,'0')}`;
// A new video starts with its first 15 seconds selected (the whole video when shorter).
const DEFAULT_SECONDS=15;
export default function VideoTrimModal({file,url,initial,onConfirm,onCancel}:{file:File;url:string;initial?:ClipRange;onConfirm:(range:ClipRange,duration:number)=>void;onCancel:()=>void}){
  const dialog=useRef<HTMLDialogElement>(null),player=useRef<HTMLVideoElement>(null),track=useRef<HTMLDivElement>(null);
  const [duration,setDuration]=useState(0),[start,setStart]=useState(initial?.start||0),[end,setEnd]=useState(initial?.end||0);
  const [position,setPosition]=useState(initial?.start||0),[playing,setPlaying]=useState(false),[error,setError]=useState('');
  const [thumbnails,setThumbnails]=useState<{time:number;data:string}[]>([]);
  useEffect(()=>{const previous=document.activeElement;dialog.current?.showModal();let active=true;
    videoFrames(file,undefined,10).then(frames=>{if(active)setThumbnails(frames);}).catch(()=>{});
    return()=>{active=false;if(previous instanceof HTMLElement)previous.focus();};
  },[file]);
  const gap=Math.min(.1,duration);
  const valid=duration>0&&end>start&&start>=0&&end<=duration;
  function seek(time:number){if(player.current){player.current.currentTime=time;setPosition(time);}}
  function changeStart(value:number){const next=Math.max(0,Math.min(value,end-gap));setStart(next);seek(next);}
  function changeEnd(value:number){const next=Math.min(duration,Math.max(value,start+gap));setEnd(next);if(position>next)seek(start);}
  function drag(event:React.PointerEvent<HTMLButtonElement>,kind:'start'|'end'){
    event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);
    const rect=track.current?.getBoundingClientRect();if(!rect)return;
    const value=Math.max(0,Math.min(duration,(event.clientX-rect.left)/rect.width*duration));
    if(kind==='start')changeStart(value);else changeEnd(value);
  }
  return <dialog ref={dialog} className="trim-modal" aria-labelledby="trim-heading" onCancel={e=>{e.preventDefault();onCancel();}}>
    <header className="trim-header"><div><span className="eyebrow">GUIDE VIDEO</span><h2 id="trim-heading">Choose your performance</h2><p>Select the part of the video you want to use.</p></div><button type="button" className="trim-close" aria-label="Cancel video selection" onClick={onCancel}>×</button></header>
    <div className="trim-player"><video ref={player} src={url} playsInline preload="auto" onLoadedMetadata={e=>{const d=e.currentTarget.duration;if(!Number.isFinite(d)||d<=0){setError('Unable to read this video. Choose another file.');return;}setDuration(d);setEnd(Math.min(initial?.end??Math.min(d,DEFAULT_SECONDS),d));setStart(Math.min(initial?.start??0,Math.max(0,d-.1)));if(initial?.start)e.currentTarget.currentTime=initial.start;}} onError={()=>setError('Your browser cannot play this video. Try an MP4 with H.264 video.')} onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} onTimeUpdate={e=>{const t=e.currentTarget.currentTime;if(t>=end&&end>start){e.currentTarget.pause();e.currentTarget.currentTime=start;setPosition(start);}else setPosition(t);}}/><span>{clock(position)} / {clock(duration)}</span></div>
    <div className="trim-timeline"><button type="button" className="trim-play" aria-label={playing?'Pause preview':'Play selected interval'} disabled={!valid} onClick={()=>{if(!player.current)return;if(playing)player.current.pause();else{if(position<start||position>=end)seek(start);void player.current.play().catch(()=>setError('Unable to play this preview.'));}}}>{playing?'Ⅱ':'▶'}</button>
    <div className="trim-track" ref={track}><div className="trim-thumbnails">{thumbnails.map((frame,i)=><img key={i} src={frame.data} alt="" draggable={false}/>)}</div>{duration>0&&<><div className="trim-dim left" style={{width:`${start/duration*100}%`}}/><div className="trim-dim right" style={{width:`${(duration-end)/duration*100}%`}}/><div className="trim-selection" style={{left:`${start/duration*100}%`,width:`${(end-start)/duration*100}%`}}/>{(['start','end'] as const).map(kind=><button key={kind} type="button" className={'trim-handle '+kind} style={{left:`${(kind==='start'?start:end)/duration*100}%`}} role="slider" aria-label={kind==='start'?'Selection start':'Selection end'} aria-valuemin={kind==='start'?0:start+gap} aria-valuemax={kind==='start'?end-gap:duration} aria-valuenow={kind==='start'?start:end} aria-valuetext={clock(kind==='start'?start:end)} onPointerDown={e=>drag(e,kind)} onPointerMove={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))drag(e,kind);}} onKeyDown={e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const current=kind==='start'?start:end;const value=e.key==='Home'?0:e.key==='End'?duration:current+(e.key==='ArrowRight'?1:-1)*(e.shiftKey?1:.1);if(kind==='start')changeStart(value);else changeEnd(value);}}}>Ⅱ</button>)}</>}</div></div>
    <label className="trim-scrub">Preview position<input type="range" min={0} max={duration||1} step="0.01" value={position} disabled={!duration} onChange={e=>seek(Number(e.target.value))}/></label>
    <div className="trim-fields"><label>Start (seconds)<input type="number" min="0" max={Math.max(0,end-gap)} step="0.1" value={Number(start.toFixed(2))} disabled={!duration} onChange={e=>changeStart(Number(e.target.value)||0)}/></label><label>End (seconds)<input type="number" min={start+gap} max={duration} step="0.1" value={Number(end.toFixed(2))} disabled={!duration} onChange={e=>changeEnd(Number(e.target.value)||0)}/></label><div className="trim-duration"><span>Selected duration</span><strong>{Math.max(0,end-start).toFixed(1)}s</strong></div></div>
    {valid&&end-start>15&&<p className="trim-context">Context Window will be used for this interval. Set the maximum segment duration in the studio.</p>}{error&&<p role="alert" className="validation">{error}</p>}
    <footer className="trim-actions"><button type="button" className="quiet-button" disabled={!duration||!!error} onClick={()=>onConfirm({start:0,end:duration},duration)}>Use full video</button><button type="button" className="primary" disabled={!valid||!!error} onClick={()=>onConfirm({start,end},duration)}>Confirm interval →</button></footer>
  </dialog>;
}
