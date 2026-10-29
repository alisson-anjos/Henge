'use client';
import {useEffect,useState} from 'react';
import type {Language} from '../lib/design-copy';
import Markdown from '../lib/markdown';

type Updates={worker_current?:string|null;current:string|null;latest:string|null;check_ok:boolean;update_available:boolean;changelog:string;changelog_url:string;update_url:string};
export default function VersionStatus({lang}:{lang:Language}){
  const tr=(en:string,pt:string,es:string)=>({en,pt,es})[lang];
  const [data,setData]=useState<Updates|null>(null);
  useEffect(()=>{let disposed=false;
    const load=()=>fetch('/api/backend/updates',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(value=>{if(!disposed&&value)setData(value);}).catch(()=>{});
    void load();const timer=setInterval(load,300000);return()=>{disposed=true;clearInterval(timer);};
  },[]);
  return <div className="version-status">
    <span className="mono">{tr('Version','Versão','Versión')} {data?.current?data.current.slice(0,7):tr('unknown','desconhecida','desconocida')}</span>
    {data?.update_available&&<a className="version-update" href={data.update_url} target="_blank" rel="noreferrer">{tr('New version available','Nova versão disponível','Nueva versión disponible')} · {data.latest?.slice(0,7)}</a>}
    {data&&<details className="version-changelog"><summary>{tr('What’s new','Novidades','Novedades')}</summary><div className="version-changelog-body">
      <p>{tr('Current version','Versão atual','Versión actual')}: <code>{data.current?.slice(0,7)||'?'}</code> · {tr('Latest code','Código mais recente','Código más reciente')}: <code>{data.latest?.slice(0,7)||'?'}</code></p>
      {data.worker_current&&<p>Worker: <code>{data.worker_current.slice(0,7)}</code></p>}
      {!data.check_ok&&<p>{tr('Update check unavailable. Showing bundled release notes.','Consulta de atualizações indisponível. Exibindo notas incluídas nesta versão.','Consulta de actualizaciones no disponible. Se muestran las notas incluidas en esta versión.')}</p>}
      <p>{tr('Code, published images and deployment are separate. Update when no job is running.','Código, imagens publicadas e implantação são etapas separadas. Atualize quando não houver jobs ativos.','Código, imágenes publicadas y despliegue son etapas separadas. Actualiza cuando no haya trabajos activos.')}</p>
      <Markdown text={data.changelog}/><a href={data.changelog_url} target="_blank" rel="noreferrer">{tr('Full changelog on GitHub','Changelog completo no GitHub','Changelog completo en GitHub')}</a>
    </div></details>}
  </div>;
}
