'use client';
import {useEffect, useState} from 'react';
import type {Language} from '../lib/design-copy';
import {readJson} from '../lib/http';
import Select from './select';

type Installation={status:string;model_id?:string;stage?:string;received?:number;total?:number;message?:string};
type Catalog={provider:string;ready:boolean;generation_active:boolean;catalog_online:boolean;models:{id:string;label:string;installed:boolean;installable:boolean;profiles?:string[]}[];installation:Installation};
// Frame editors are optional: H3 Image runs on the H3 model the videos already use (its LoRA and VAE are small); the others
// are separate image models. Each row installs the catalog entries of its profile, one after the other.
const EDITOR_BUNDLES:{profile:string;en:string;pt:string;es:string;note:[string,string,string]}[]=[
  {profile:'h3image',en:'H3 Image (Pruna) · recommended',pt:'H3 Image (Pruna) · recomendado',es:'H3 Image (Pruna) · recomendado',note:['Edits frames on the H3 model you already have (two small files): add, remove or change things with your words.','Edita quadros no modelo H3 que você já tem (dois arquivos pequenos): adicione, remova ou mude coisas com as suas palavras.','Edita fotogramas con el modelo H3 que ya tienes (dos archivos pequeños): añade, quita o cambia cosas con tus palabras.']},
  {profile:'qwen21',en:'Qwen-Image 2.1 + BFS Body Swap (Selective)',pt:'Qwen-Image 2.1 + BFS Body Swap (Seletivo)',es:'Qwen-Image 2.1 + BFS Body Swap (Selectivo)',note:['Replaces only the person you click in frames with several people.','Troca só a pessoa que você clicar em quadros com várias pessoas.','Cambia solo la persona en la que haces clic en fotogramas con varias personas.']},
  {profile:'fibo',en:'FIBO 2.0',pt:'FIBO 2.0',es:'FIBO 2.0',note:['Keeps pose, camera and composition of the frame it edits.','Mantém pose, câmera e composição do quadro que edita.','Mantiene pose, cámara y composición del fotograma que edita.']},
  {profile:'klein',en:'FLUX.2 Klein',pt:'FLUX.2 Klein',es:'FLUX.2 Klein',note:['General image editor.','Editor de imagem geral.','Editor de imagen general.']},
  {profile:'klein3',en:'FLUX.3 Klein',pt:'FLUX.3 Klein',es:'FLUX.3 Klein',note:['General image editor; redraws the shot more freely.','Editor de imagem geral; redesenha o quadro com mais liberdade.','Editor de imagen general; redibuja la toma con más libertad.']},
];
const active=(s?:string)=>['queued','running','cancelling'].includes(s || '');

export default function ModelSettings({lang}:{lang:Language}) {
  const tr=(en:string,pt:string,es:string)=>({en,pt,es})[lang];
  const [data,setData]=useState<Catalog|null>(null),[selected,setSelected]=useState('turbo_pika6'),[error,setError]=useState(''),[sending,setSending]=useState(false);
  // Catalog ids still to install for the editor row the user chose, installed one at a time.
  const [queue,setQueue]=useState<string[]>([]);
  useEffect(()=>{
    let disposed=false;let timer:ReturnType<typeof setTimeout>;
    async function load(){
      try{const response=await fetch('/api/backend/models',{cache:'no-store'});const body=await readJson(response);if(!response.ok)throw Error(body.detail || `HTTP ${response.status}`);if(!disposed){setData(body);setError('');}}
      catch(e){if(!disposed)setError(e instanceof Error?e.message:String(e));}
      if(!disposed)timer=setTimeout(load,2500);
    }
    void load();return()=>{disposed=true;clearTimeout(timer);};
  },[]);
  async function action(name:string,model=selected){
    setSending(true);setError('');
    try{
      const response=await fetch(`/api/backend/models/${name}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({model_id:model})});
      const body=await readJson(response);if(!response.ok)throw Error(body.detail || `HTTP ${response.status}`);
      setData(d=>d?{...d,installation:body}:d);
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setSending(false);}
  }
  const current=data?.models.find(m=>m.id===selected),state=data?.installation,busy=sending||active(state?.status);
  useEffect(()=>{
    if(!data||!queue.length||busy)return;
    if(state?.status==='failed'){setQueue([]);return;}
    const [next,...rest]=queue;setQueue(rest);
    if(!data.models.find(m=>m.id===next)?.installed)void action('install',next);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[data,queue,busy]);
  const bundle=(profile:string)=>(data?.models||[]).filter(m=>(m.profiles||[]).includes(profile));
  return <section className="model-settings"><h3>{tr('Models','Modelos','Modelos')}</h3>
    <p className="muted model-checklist-row">{tr('The missing-models checklist shows once; ','A lista de modelos faltando aparece uma vez; ','La lista de modelos que faltan aparece una vez; ')}<button type="button" className="quiet-button" onClick={()=>{dispatchEvent(new CustomEvent('henge:model-checklist'));dispatchEvent(new CustomEvent('henge:close-settings'));}}>{tr('Show the model checklist','Mostrar a lista de modelos','Mostrar la lista de modelos')}</button></p>
    <p>{data?.provider==='runpod'
      ?tr('Downloads run on your existing Serverless worker and go directly to its shared volume. GPU time is billed during installation; no temporary pod is created.','Os downloads rodam no seu worker Serverless e vão direto para o volume compartilhado. O tempo de GPU é cobrado durante a instalação; nenhum pod temporário é criado.','Las descargas se ejecutan en tu worker Serverless y van directamente al volumen compartido. Se cobra tiempo de GPU durante la instalación; no se crea un pod temporal.')
      :tr('Downloads go directly to the configured local ComfyUI models folder. No model is loaded onto the GPU.','Os downloads vão direto para a pasta de modelos do ComfyUI local configurado. Nenhum modelo é carregado na GPU.','Las descargas van directamente a la carpeta de modelos del ComfyUI local configurado. No se carga ningún modelo en la GPU.')}</p>
    {!data?<p role="status">{tr('Loading catalog…','Carregando catálogo…','Cargando catálogo…')}</p>:<>
      {!data.catalog_online&&<p className="muted">{tr('GitHub is unavailable; showing the bundled catalog.','GitHub indisponível; exibindo o catálogo incluído nesta versão.','GitHub no está disponible; se muestra el catálogo incluido en esta versión.')}</p>}
      <div className="editor-bundles"><h4>{tr('Image editors (optional)','Editores de imagem (opcional)','Editores de imagen (opcional)')}</h4>
        <p className="muted">{tr('They edit the first frame (swap a character, change the scene). Install only the ones you want.','Eles editam o primeiro quadro (trocar um personagem, mudar a cena). Instale só os que quiser.','Editan el primer fotograma (cambiar un personaje, cambiar la escena). Instala solo los que quieras.')}</p>
        {EDITOR_BUNDLES.filter(b=>bundle(b.profile).length).map(b=>{const items=bundle(b.profile),done=items.filter(m=>m.installed).length,all=done===items.length,installing=queue.length>0&&items.some(m=>queue.includes(m.id));
          return <div className="editor-bundle" key={b.profile}><div><strong>{tr(b.en,b.pt,b.es)}</strong><small className="muted">{tr(...b.note)}</small></div>
            <span className={all?'mini-badge ok':'mini-badge'}>{all?tr('Installed','Instalado','Instalado'):tr(`${done}/${items.length} files`,`${done}/${items.length} arquivos`,`${done}/${items.length} archivos`)}</span>
            <button type="button" className="quiet-button" disabled={all||!data.ready||data.generation_active||busy||installing||items.some(m=>!m.installed&&!m.installable)} onClick={()=>setQueue(items.filter(m=>!m.installed).map(m=>m.id))}>{installing?tr('Installing…','Instalando…','Instalando…'):tr('Install','Instalar','Instalar')}</button></div>;})}
      </div>
      <label>{tr('Model to install','Modelo para instalar','Modelo a instalar')}<Select aria-label={tr('Model to install','Modelo para instalar','Modelo a instalar')} value={selected} disabled={busy} onChange={e=>setSelected(e.target.value)}>{data.models.map(m=><option value={m.id} key={m.id} disabled={!m.installable}>{m.label}{m.installed?tr(' · installed',' · instalado',' · instalado'):''}</option>)}</Select></label>
      {!data.ready&&<p className="job-callout warn">{data.provider==='runpod'
        ?tr('This worker has not reported model-install support. Update the worker image once, then refresh its inventory below.','Este worker ainda não informou suporte à instalação. Atualize a imagem do worker uma vez e atualize seu inventário abaixo.','Este worker aún no informó soporte de instalación. Actualiza su imagen una vez y después actualiza el inventario abajo.')
        :tr('Local installation needs COMFY_ROOT pointing to your ComfyUI installation on this machine. Remote ComfyUI requires installation on its host.','A instalação local exige COMFY_ROOT apontando para o ComfyUI nesta máquina. ComfyUI remoto exige instalação no host dele.','La instalación local necesita COMFY_ROOT apuntando al ComfyUI de este equipo. Un ComfyUI remoto necesita instalación en su host.')}</p>}
      {data.generation_active&&<p className="muted">{tr('Wait for the active generation to finish before installing.','Aguarde a geração ativa terminar antes de instalar.','Espera a que termine la generación activa antes de instalar.')}</p>}
      <div className="model-install-actions"><button type="button" className="primary" disabled={!data.ready||data.generation_active||busy||!current?.installable||current.installed} onClick={()=>void action('install')}>{current?.installed?tr('Installed','Instalado','Instalado'):tr('Install model','Instalar modelo','Instalar modelo')}</button>
        {data.provider==='runpod'&&<button type="button" className="quiet-button" disabled={busy||data.generation_active} onClick={()=>void action('refresh')}>{tr('Refresh worker inventory','Atualizar inventário do worker','Actualizar inventario del worker')}</button>}
        {active(state?.status)&&<button type="button" className="quiet-button" disabled={sending||state?.status==='cancelling'} onClick={()=>void action('cancel')}>{tr('Cancel','Cancelar','Cancelar')}</button>}</div>
      {state?.status!=='idle'&&<div className="model-install-progress" role="status" aria-live="polite">
        <span>{state?.status==='completed'?(state.model_id==='__inventory__'?(data.ready?tr('Worker inventory updated','Inventário do worker atualizado','Inventario del worker actualizado'):tr('Inventory updated, but the worker that answered still runs an image without model installs','Inventário atualizado, mas o worker que respondeu ainda usa uma imagem sem instalação de modelos','Inventario actualizado, pero el worker que respondió aún usa una imagen sin instalación de modelos')):tr('Installation finished','Instalação concluída','Instalación completada')):state?.status==='failed'?tr('Installation failed','Falha na instalação','Error de instalación'):state?.status==='cancelled'?tr('Installation cancelled','Instalação cancelada','Instalación cancelada'):state?.stage==='downloading'?tr('Downloading…','Baixando…','Descargando…'):state?.stage==='verifying'?tr('Verifying model…','Verificando modelo…','Verificando modelo…'):state?.stage==='refreshing'?tr('Refreshing inventory…','Atualizando inventário…','Actualizando inventario…'):tr('Waiting for the worker…','Aguardando o worker…','Esperando al worker…')}</span>
        {active(state?.status)&&<progress max={state?.total||undefined} value={state?.total?state.received||0:undefined}/>}
        {!!state?.received&&<small>{(state.received/1e6).toFixed(1)}{state.total?` / ${(state.total/1e6).toFixed(1)}`:''} MB</small>}
        {state?.message&&state.status==='failed'&&<small className="validation">{state.message}</small>}
      </div>}
      <small className="muted">{tr('The catalog follows GitHub updates. Installing weights does not update code or nodes; a new model may also require an application or worker update.','O catálogo acompanha as atualizações do GitHub. Instalar pesos não atualiza código ou nodes; um modelo novo também pode exigir atualização do aplicativo ou worker.','El catálogo sigue las actualizaciones de GitHub. Instalar pesos no actualiza código ni nodos; un modelo nuevo también puede necesitar actualizar la aplicación o el worker.')}</small>
      {['turbo_pika6','turbo_pika6_kijai'].includes(selected)&&<small className="muted">{tr('Pika uses the MiniMax H3 Community License, not MIT.','Pika usa a MiniMax H3 Community License, não MIT.','Pika usa la MiniMax H3 Community License, no MIT.')}</small>}
    </>}{error&&<p className="validation" role="alert">{error}</p>}
  </section>;
}
