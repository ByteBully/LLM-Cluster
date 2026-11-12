"""Windows/WSL GPUCluster engine. No GUI framework dependencies."""
import ctypes, json, os, queue, re, shlex, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'cluster_config.json'
STATE = Path(os.environ.get('LOCALAPPDATA',str(ROOT))) / 'GPUClusterConfigurator' / 'state.json'
USER = 'gpucluster'
DISTRO = 'Ubuntu-24.04'
REPO = 'https://github.com/ggml-org/llama.cpp.git'
DEFAULTS = {'peer':'','iperf_port':'5201','rpc_port':'50052','api_port':'8080','model':'','llama_dir':'/home/gpucluster/llama.cpp/build/bin','wsl_distro':'Ubuntu-24.04','role':'host','baseline_tps':'','payload_mb':'8','sync_per_token':'2','target_tps':'10','context':'16384','gpu_layers':'99','tensor_split':''}

def execute(args, timeout=25):
    try:
        p = subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=timeout, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return p.returncode, (p.stdout + ('\n' + p.stderr if p.stderr else '')).strip()
    except (OSError,subprocess.TimeoutExpired) as exc: return -1, str(exc)

def wsl(distro, command, timeout=30): return execute(['wsl.exe','-d',distro,'--','bash','-lc',command],timeout)
def shell_quote(value): return shlex.quote(value)
def wsl_root(distro, script, timeout=120): return execute(['wsl.exe','-d',distro,'-u','root','--','bash','-lc',script],timeout)
def wsl_user(distro, script, timeout=120): return execute(['wsl.exe','-d',distro,'-u',USER,'--','bash','-lc',script],timeout)
def parse_wsl_list(s): return [line.replace('\x00','').strip().lstrip('*').strip() for line in s.splitlines()]
def wsl_path_from_windows(path):
    p=Path(path).resolve()
    if not re.match(r'^[A-Za-z]:',str(p)): return None
    return f'/mnt/{str(p)[0].lower()}/'+str(p)[3:].replace('\\','/')
def admin():
    if os.name!='nt': return False
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False

def elevate():
    if os.name!='nt': return False
    params=subprocess.list2cmdline([str(Path(__file__).resolve().parent/'app.py'),*sys.argv[1:]])
    return ctypes.windll.shell32.ShellExecuteW(None,'runas',sys.executable,params,str(ROOT),1)>32

class Var:
    def __init__(self, value): self.value=str(value)
    def get(self): return self.value
    def set(self, value): self.value=str(value)

class Engine:
    def __init__(self, emit):
        self.emit=emit
        self.vars={k:Var(v) for k,v in DEFAULTS.items()}
        if CONFIG.exists():
            try:
                for k,v in json.loads(CONFIG.read_text(encoding='utf-8')).items():
                    if k in self.vars: self.vars[k].set(v)
            except (OSError,ValueError): pass
        self.stage={}
        try: self.stage=json.loads(STATE.read_text(encoding='utf-8'))
        except (OSError,ValueError): pass
        self.models={}
        self.busy=False
    def log(self,text): self.emit('log',str(text))
    def step(self,text,progress=None):
        self.log('[SETUP] '+text)
        self.emit('status',{'message':text,'progress':progress})
    def save(self):
        CONFIG.write_text(json.dumps({k:v.get() for k,v in self.vars.items()},indent=2,ensure_ascii=False),encoding='utf-8')
    def persist(self,name):
        self.stage[name]=True
        STATE.parent.mkdir(parents=True,exist_ok=True)
        STATE.write_text(json.dumps(self.stage,indent=2),encoding='utf-8')
    def require(self,args,label,timeout=120):
        code,out=execute(args,timeout)
        self.log(f'[{label}] exit={code}\n{out[-3500:]}')
        if code!=0: raise RuntimeError(f'{label}: {out[-900:]}')
        return out
    def require_root(self,script,label,timeout=120):
        return self.require(['wsl.exe','-d',self.vars['wsl_distro'].get(),'-u','root','--','bash','-lc',script],label,timeout)
    def require_user(self,script,label,timeout=120):
        return self.require(['wsl.exe','-d',self.vars['wsl_distro'].get(),'-u',USER,'--','bash','-lc',script],label,timeout)

    def prepare_wsl(self):
            distro = self.vars['wsl_distro'].get().strip()
            if not re.fullmatch(r'[A-Za-z0-9][\w.-]{0,63}', distro):
                raise RuntimeError('Invalid WSL distribution name')
            code, out = execute(['wsl.exe','--list','--quiet'], 25)
            names = [x.casefold() for x in parse_wsl_list(out)] if code == 0 else []
            if distro.casefold() not in names:
                self.step('Installing WSL2 and Ubuntu. A Windows restart may be required.', 8)
                code, out = execute(['wsl.exe','--install','-d',distro,'--no-launch'], 1200)
                self.log('[WSL install]\n' + out)
                if code != 0:
                    raise RuntimeError('WSL installation did not complete. Restart Windows and run setup again. ' + out[-500:])
                code, out = execute(['wsl.exe','--list','--quiet'], 30)
                if distro.casefold() not in [x.casefold() for x in parse_wsl_list(out)]:
                    raise RuntimeError('WSL requires a restart or additional installation steps. Restart Windows and launch the application again.')
            code, out = execute(['wsl.exe','--list','--verbose'], 30)
            self.log('[WSL versions]\n' + out)
            clean = out.replace('\x00', '')
            for line in clean.splitlines():
                if distro.casefold() in line.casefold() and re.search(r'\s1\s*$', line):
                    self.require(['wsl.exe','--set-version',distro,'2'], 'Convert to WSL2', 1200)
            # First WSL boot can fail until Windows restart; do not falsely mark complete.
            self.require(['wsl.exe','-d',distro,'-u','root','--','id','-u'], 'Start Ubuntu as root', 120)
            self.persist('wsl')

    def prepare_user(self):
            check, _ = wsl_root(self.vars['wsl_distro'].get(), 'id -u gpucluster >/dev/null 2>&1', 20)
            if check != 0:
                self.require_root('useradd -m -s /bin/bash gpucluster', 'Create gpucluster account')
            self.require_root('install -d -o gpucluster -g gpucluster /home/gpucluster/models', 'Models directory')
            # WSL default user; don't overwrite other distro config beyond the selected distro.
            self.require_root("printf '[user]\\ndefault=gpucluster\\n' > /etc/wsl.conf.gpucluster.tmp && (test ! -e /etc/wsl.conf || cp /etc/wsl.conf /etc/wsl.conf.gpucluster.bak) && python3 - <<'PY2'\nfrom pathlib import Path\np=Path('/etc/wsl.conf'); t=p.read_text() if p.exists() else ''; lines=t.splitlines(); out=[]; section=''; seen=False\nfor line in lines:\n if line.strip().startswith('[') and line.strip().endswith(']'):\n  if section=='user' and not seen: out.append('default=gpucluster'); seen=True\n  section=line.strip()[1:-1].lower()\n if section=='user' and line.strip().lower().startswith('default='):\n  line='default=gpucluster'; seen=True\n out.append(line)\nif section=='user' and not seen: out.append('default=gpucluster'); seen=True\nif '[user]' not in t.lower(): out += ['[user]','default=gpucluster']\np.write_text('\\n'.join(out)+'\\n')\nPY2", 'Set default user', 45)
            self.persist('user')

    def prepare_packages(self):
            self.require_root('apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y git cmake ninja-build build-essential pkg-config curl ca-certificates libcurl4-openssl-dev iperf3 python3', 'Ubuntu dependencies', 900)
            code, out = wsl_user(self.vars['wsl_distro'].get(), 'nvidia-smi -L', 30)
            if code != 0:
                raise RuntimeError('NVIDIA GPU is unavailable in WSL2. Update the NVIDIA Windows driver and check nvidia-smi in Ubuntu. ' + out[-500:])
            self.log('[GPU WSL]\n' + out)
            self.persist('packages')

    def prepare_cuda(self):
            code, out = wsl_user(self.vars['wsl_distro'].get(), 'command -v nvcc || test -x /usr/local/cuda/bin/nvcc', 20)
            if code == 0:
                self.log('CUDA Toolkit (nvcc) is available.')
                return
            # Installing a Linux display driver in WSL is unsafe; prefer toolkit-only.
            self.step('nvcc not found. Checking CUDA Toolkit packages in the repositories…', 49)
            code, out = wsl_root(self.vars['wsl_distro'].get(), "apt-cache search '^cuda-toolkit-[0-9]+-[0-9]+$' | sort -V | tail -1", 20)
            match = re.search(r'^(cuda-toolkit-\d+-\d+)\s', out, re.M) if code == 0 else None
            if not match:
                # Official NVIDIA Ubuntu 24.04 toolkit repository, keyring only; no Linux GPU driver.
                distro = self.vars['wsl_distro'].get()
                code, release = wsl_root(distro, '. /etc/os-release; printf "%s %s" "$ID" "$VERSION_ID"', 15)
                if code != 0 or release.strip() != 'ubuntu 24.04':
                    raise RuntimeError('Automatic CUDA Toolkit installation supports Ubuntu 24.04. Select Ubuntu-24.04 or configure CUDA manually.')
                self.require_root('curl -fL --retry 3 https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb -o /tmp/gpucluster-cuda-keyring.deb && dpkg -i /tmp/gpucluster-cuda-keyring.deb && apt-get update -y', 'NVIDIA CUDA Toolkit repository', 300)
                code, out = wsl_root(distro, "apt-cache search '^cuda-toolkit-[0-9]+-[0-9]+$' | sort -V | tail -1", 20)
                match = re.search(r'^(cuda-toolkit-\d+-\d+)\s', out, re.M) if code == 0 else None
                if not match:
                    raise RuntimeError('CUDA Toolkit was not found in the official NVIDIA repository. Check the logs and your internet connection.')
            pkg = match.group(1)
            self.require_root(f'DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg}', 'CUDA Toolkit ' + pkg, 1200)
            self.require_root("test -e /usr/local/cuda || ln -s $(ls -d /usr/local/cuda-* | sort -V | tail -1) /usr/local/cuda", 'CUDA path')
            self.require_user('test -x /usr/local/cuda/bin/nvcc', 'Verify nvcc')
            self.persist('cuda')

    def prepare_llama(self):
            base = '/home/gpucluster/llama.cpp'
            code, _ = wsl_user(self.vars['wsl_distro'].get(), f'test -d {base}/.git', 15)
            if code != 0:
                self.require_user(f'git clone --depth 1 {shell_quote(REPO)} {base}', 'Download llama.cpp', 600)
            # Avoid overwriting local changes; a pre-existing repo is built as is.
            self.require_user(f'cd {base} && cmake -S . -B build -G Ninja -DGGML_CUDA=ON -DGGML_RPC=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc', 'CMake CUDA RPC', 600)
            self.require_user(f'cd {base} && cmake --build build --parallel 4', 'Build llama.cpp', 3600)
            self.require_user(f'test -x {base}/build/bin/llama-server && test -x {base}/build/bin/rpc-server', 'Verify binaries')
            self.vars['llama_dir'].set(base + '/build/bin')
            self.persist('llama')

    def tailscale_cli(self):
            return shutil.which('tailscale') or next((p for p in [r'C:\Program Files\Tailscale\tailscale.exe',r'C:\Program Files (x86)\Tailscale\tailscale.exe'] if Path(p).is_file()), None)

    def prepare_tailscale(self):
            cli = self.tailscale_cli()
            if not cli:
                if not shutil.which('winget'):
                    raise RuntimeError('Tailscale and winget are unavailable. Install Tailscale: https://tailscale.com/download/windows')
                self.require(['winget','install','--id','Tailscale.Tailscale','-e','--accept-package-agreements','--accept-source-agreements','--silent'], 'Install Tailscale', 600)
                cli = self.tailscale_cli()
            if not cli:
                raise RuntimeError('Tailscale is installed, but its CLI is not available yet. Restart the application.')
            code, out = execute([cli,'ip','-4'], 20)
            if code != 0 or not re.search(r'100(?:\.\d{1,3}){3}', out):
                gui = Path(cli).with_name('tailscale-ipn.exe')
                if gui.is_file():
                    subprocess.Popen([str(gui)])
                raise RuntimeError('Sign in to Tailscale in the Windows app, then resume setup.')
            ip = re.search(r'100(?:\.\d{1,3}){3}', out).group(0)
            self.emit('ip', ip)
            self.persist('tailscale')

    def prepare_worker(self):
            # Do not expose unauthenticated RPC on the Internet. Bind portproxy only to Tailscale IPv4.
            cli = self.tailscale_cli()
            if not cli:
                raise RuntimeError('Tailscale is not installed')
            code, out = execute([cli,'ip','-4'], 15)
            m = re.search(r'100(?:\.\d{1,3}){3}', out)
            if code != 0 or not m:
                raise RuntimeError('Could not retrieve the worker Tailscale IP address')
            ts_ip = m.group(0)
            distro = self.vars['wsl_distro'].get()
            rpc_port = int(self.vars['rpc_port'].get())
            if not 1 <= rpc_port <= 65535:
                raise RuntimeError('Invalid RPC port')
            code, out = wsl_root(distro, "hostname -I | awk '{print $1}'", 20)
            ip = out.strip().split()[0] if code == 0 and out.strip() else ''
            if not re.fullmatch(r'(?:\d{1,3}\.){3}\d{1,3}', ip):
                raise RuntimeError('Could not determine the WSL2 IP address for port forwarding.')
            # Restrict inbound to Tailscale address and tailnet IPv4. Only this interface is exposed.
            rule = 'GPUCluster-RPC-Tailscale'
            ps = (f"$ErrorActionPreference='Stop'; "
                  f"netsh interface portproxy delete v4tov4 listenaddress={ts_ip} listenport={rpc_port} 2>$null | Out-Null; "
                  f"netsh interface portproxy add v4tov4 listenaddress={ts_ip} listenport={rpc_port} connectaddress={ip} connectport={rpc_port}; "
                  f"Get-NetFirewallRule -DisplayName '{rule}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; "
                  f"New-NetFirewallRule -DisplayName '{rule}' -Direction Inbound -Action Allow -Protocol TCP -LocalAddress {ts_ip} -LocalPort {rpc_port} -RemoteAddress '100.64.0.0/10' -Profile Any | Out-Null")
            self.require(['powershell.exe','-NoProfile','-Command',ps], 'RPC port forwarding and firewall', 60)
            self.vars['llama_dir'].set('/home/gpucluster/llama.cpp/build/bin')
            self.vars['role'].set('worker')
            # Launch RPC via background shell. RPC listens in WSL, portproxy listens only on Tailscale IP.
            self.require_user(f"nohup /home/gpucluster/llama.cpp/build/bin/rpc-server -H 0.0.0.0 -p {rpc_port} > /home/gpucluster/rpc-server.log 2>&1 < /dev/null & sleep 2; pgrep -af '[r]pc-server'", 'Start RPC server', 40)
            self.persist('worker')
            self.log(f'WORKER RPC: {ts_ip}:{rpc_port} → WSL2 {ip}:{rpc_port}. The WSL2 IP may change after a restart; run setup again to update port forwarding.')
    def setup(self,role):
        self.vars['role'].set(role)
        self.save()
        self.step('Checking WSL2 and Ubuntu…',5)
        self.prepare_wsl()
        self.step('Creating gpucluster account…',20)
        self.prepare_user()
        self.step('Installing build tools and checking NVIDIA GPU…',35)
        self.prepare_packages()
        self.step('Checking CUDA Toolkit…',48)
        self.prepare_cuda()
        self.step('Building llama.cpp with CUDA and RPC…',60)
        self.prepare_llama()
        self.step('Connecting Tailscale…',80)
        self.prepare_tailscale()
        if role=='worker':
            self.step('Configuring private worker RPC endpoint…',88)
            self.prepare_worker()
            self.step('Worker is ready. Connect from the host.',100)
        else: self.step('Host is ready. Select a worker and a model, then start the server.',100)
        self.save()
    def tailscale_ip(self):
        cli=self.tailscale_cli()
        if not cli: raise RuntimeError('Tailscale is not installed. Use Setup to install it.')
        code,out=execute([cli,'ip','-4'],20)
        if code!=0: raise RuntimeError(out or 'Tailscale is not connected. Sign in to Tailscale.')
        m=re.search(r'100(?:\.\d{1,3}){3}',out)
        if not m: raise RuntimeError('No Tailscale IPv4. Sign in to the tailnet.')
        self.emit('ip',m.group(0))
        return m.group(0)
    def peers(self):
        cli=self.tailscale_cli()
        if not cli: raise RuntimeError('Tailscale is not installed.')
        out=self.require([cli,'status','--json'],'Tailscale discovery',30)
        data=json.loads(out)
        result=[]
        for node in (data.get('Peer') or {}).values():
            ips=[x for x in node.get('TailscaleIPs',[]) if x.startswith('100.')]
            if ips: result.append({'name':node.get('HostName') or node.get('DNSName') or 'Device','ip':ips[0],'online':bool(node.get('Online'))})
        result.sort(key=lambda x:(not x['online'],x['name']))
        self.emit('peers',result)
        return result
    def scan_models(self):
        found={}
        distro=self.vars['wsl_distro'].get()
        script="find /home/gpucluster/models /home/gpucluster/.ollama/models/blobs -maxdepth 5 -type f \\( -iname '*.gguf' -o -name 'sha256-*' \\) -print 2>/dev/null | head -150"
        code,out=wsl_user(distro,script,90)
        if code==0 or out:
            for path in out.splitlines():
                path=path.strip()
                if path.startswith('/home/gpucluster/'):
                    check,header=wsl_user(distro,'head -c 4 '+shell_quote(path)+' | od -An -tx1',12)
                    if check==0 and header.strip().replace(' ','')=='47475546':
                        found[Path(path).name+' (WSL)']=path
        candidates=[Path.home()/'.ollama'/'models'/'blobs',Path.home()/'models',Path.home()/'Downloads',Path.home()/'Documents'/'models']
        for folder in candidates:
            if not folder.is_dir(): continue
            count=0
            for path in folder.rglob('*'):
                if count>=200: break
                if not path.is_file() or not (path.suffix.lower()=='.gguf' or path.name.startswith('sha256-')): continue
                count+=1
                try:
                    with path.open('rb') as f:
                        if f.read(4)!=b'GGUF': continue
                    linux_path=wsl_path_from_windows(path)
                    if linux_path: found[f'{path.name} ({path.parent.name}, Windows)']=linux_path
                except OSError: continue
        self.models=found
        self.emit('models',[{'name':k,'path':v} for k,v in found.items()])
        self.log(f'Found {len(found)} GGUF model files.')
    def command(self):
        directory=self.vars['llama_dir'].get().rstrip('/')
        role=self.vars['role'].get()
        port=int(self.vars['rpc_port'].get() if role=='worker' else self.vars['api_port'].get())
        if not 1<=port<=65535: raise ValueError('Invalid port')
        if role=='worker': return f'{shell_quote(directory+"/rpc-server")} -H 0.0.0.0 -p {port}'
        peer=self.vars['peer'].get().strip()
        if not re.fullmatch(r'100(?:\.\d{1,3}){3}',peer): raise ValueError('Select a worker from the tailnet')
        model=self.vars['model'].get()
        if not model.startswith('/'): raise ValueError('Select a GGUF model')
        args=[shell_quote(directory+'/llama-server'),'-m',shell_quote(model),'--rpc',f'{peer}:{self.vars["rpc_port"].get()}','--split-mode','layer','-ngl',str(int(self.vars['gpu_layers'].get())),'-c',str(int(self.vars['context'].get())),'-a','gpucluster','--host','127.0.0.1','--port',str(port)]
        split=self.vars['tensor_split'].get().strip()
        if split:
            if not re.fullmatch(r'\d+(?:\.\d+)?(?:,\d+(?:\.\d+)?)+',split): raise ValueError('Invalid tensor split')
            args.extend(['--tensor-split',split])
        return ' '.join(args)
    def launch(self):
        cmd=self.command()
        if self.vars['role'].get()=='host': self.require_user('test -f '+shell_quote(self.vars['model'].get()),'Verify model')
        self.require_user('nohup '+cmd+' > /home/gpucluster/llm-cluster.log 2>&1 < /dev/null & sleep 2; echo PID:$!','Launch llama.cpp',30)
        self.step('Service launched. Check the logs and verify the endpoint.')
    def diagnostics(self):
        for name,args in [('WSL',['wsl.exe','--list','--verbose']),('Tailscale',[self.tailscale_cli() or 'tailscale','status']),('NVIDIA',['nvidia-smi','-L'])]:
            code,out=execute(args,25);self.log(f'[{name}] exit={code}\n{out}')
    def check_api(self):
        port=int(self.vars['api_port'].get())
        code,out=execute(['curl.exe','--max-time','5',f'http://127.0.0.1:{port}/v1/models'],10)
        self.log(f'[API] exit={code}\n{out}')

