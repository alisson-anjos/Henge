"""The local ComfyUI path of execute_graph (pods, a ComfyUI on this machine) must return the prompt's outputs.

v2026.11.01.1 lost the line that runs the async loop, so every local render returned None and failed with
"'NoneType' object has no attribute 'get'" (issue #3). This drives the real loop against a fake ComfyUI."""
import asyncio,os,socket,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('HENGE_DATA_DIR',tempfile.mkdtemp())
import server
from aiohttp import web


def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


class LocalExecuteTests(unittest.TestCase):
    def test_local_comfyui_returns_the_outputs(self):
        outputs={'17':{'videos':[{'filename':'r.mp4','subfolder':'henge','type':'output'}]}}
        async def prompt(request):return web.json_response({'prompt_id':'p1'})
        async def history(request):return web.json_response({'p1':{'status':{'status_str':'success'},'outputs':outputs}})
        async def ws(request):
            sock=web.WebSocketResponse();await sock.prepare(request)
            await asyncio.sleep(5);return sock
        app=web.Application();app.add_routes([web.post('/prompt',prompt),web.get('/history/{pid}',history),web.get('/ws',ws)])
        port=free_port();loop=asyncio.new_event_loop();runner=web.AppRunner(app)
        def serve():
            asyncio.set_event_loop(loop);loop.run_until_complete(runner.setup())
            loop.run_until_complete(web.TCPSite(runner,'127.0.0.1',port).start());loop.run_forever()
        threading.Thread(target=serve,daemon=True).start()
        import time;time.sleep(.5)
        job={'id':'a'*32,'status':'running'}
        server.job_path(job['id']).mkdir(parents=True,exist_ok=True)
        with patch.object(server,'REMOTE',None),patch.object(server,'URL',f'http://127.0.0.1:{port}'),\
             patch.object(server,'load',return_value=job),patch.object(server,'save'),patch.object(server,'known_loras'),\
             patch.object(server.FILES,'upload_graph_inputs',side_effect=lambda g:g),patch.object(server.molmo_pointing,'release'):
            result=server.execute_graph(job,{'1':{'class_type':'LoadImage','inputs':{'image':'x.png'}}},'h3_segment_000')
        self.assertEqual(result,outputs)
        loop.call_soon_threadsafe(loop.stop)


if __name__=='__main__':unittest.main()
