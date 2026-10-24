"""Install the optional TARA one-pass Comfy Kitchen kernel for the local GPU.

Uses the prebuilt per-architecture library from alisson-anjos/comfy-kitchen
(feat/h3-native-temporal), verified against the release SHA256SUMS before anything loads
it, then that fork's overlay installer, which keeps the normal Kitchen operators. Without
the kernel, TARA still runs (BFS falls back to frame-wise Kitchen or Flash Partitions).

    python scripts/install_tara_kernel.py            # use this Python's comfy_kitchen
    python scripts/install_tara_kernel.py --source /opt/comfy-kitchen-tara
"""
import argparse,hashlib,os,subprocess,sys,urllib.request
from pathlib import Path

COMMIT='0413d43878606425a84aa400f1e5da50ed9dcdad'
RELEASE=f'https://github.com/alisson-anjos/comfy-kitchen/releases/download/temporal-native-{COMMIT}'
REPO='https://github.com/alisson-anjos/comfy-kitchen.git'
LINUX_ARCHES={'80','86','89','90','100','120'}

def installed():
    try:
        import comfy_kitchen.temporal_attention as temporal
        return bool(temporal.is_available())
    except Exception:
        return False

def gpu_arch():
    import torch
    if not torch.cuda.is_available():return None
    major,minor=torch.cuda.get_device_capability(0)
    return f'{major}{minor}'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',default=os.environ.get('HENGE_TARA_SOURCE',str(Path(__file__).resolve().parents[1]/'.runtime/comfy-kitchen-tara')))
    parser.add_argument('--arch',default=None)
    args=parser.parse_args()
    if installed():print('[tara-kernel] already installed for this GPU',flush=True);return
    arch=args.arch or gpu_arch()
    if arch not in LINUX_ARCHES:print(f'[tara-kernel] no prebuilt kernel for SM{arch}; TARA uses the frame-wise fallback',flush=True);return
    source=Path(args.source)
    if not (source/'scripts/install_temporal_overlay.py').is_file():
        subprocess.run(['git','clone','--quiet',REPO,str(source)],check=True)
        subprocess.run(['git','-C',str(source),'checkout','--quiet',COMMIT],check=True)
    work=source.parent/'tara-kernel-download';work.mkdir(parents=True,exist_ok=True)
    name=f'libck_temporal_sm{arch}.so'
    for item in (name,'SHA256SUMS'):urllib.request.urlretrieve(f'{RELEASE}/{item}',work/item)
    sums={line.split()[-1]:line.split()[0] for line in (work/'SHA256SUMS').read_text().splitlines() if line.strip()}
    if name not in sums:raise SystemExit(f'[tara-kernel] {name} has no checksum entry; not installing')
    # Verify before anything loads the library (this installer version has no --sha256 option).
    digest=hashlib.sha256((work/name).read_bytes()).hexdigest()
    if digest!=sums[name]:raise SystemExit(f'[tara-kernel] checksum mismatch for {name}; not installing')
    # Run outside the source tree so Python imports the installed comfy_kitchen package.
    subprocess.run([sys.executable,str(source/'scripts/install_temporal_overlay.py'),'--arch',arch,'--prebuilt',str(work/name)],check=True,cwd=str(work))
    print(f'[tara-kernel] installed SM{arch}: {"ok" if installed() else "installed, but is_available() is False"}',flush=True)

if __name__=='__main__':main()
