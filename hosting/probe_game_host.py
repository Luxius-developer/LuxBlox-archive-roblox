"""Read-only host report. Can be renamed to the panel's existing Python entrypoint.

Does not install packages, start processes, bind ports, read credentials or
modify the server's other files. Output can be shared without account keys.
"""
import json,os,platform,shutil,sys
from pathlib import Path


def read(path):
    try:return Path(path).read_text().strip()
    except OSError:return None


def report():
    return {
        'system':platform.system(),'release':platform.release(),
        'architecture':platform.machine(),'python':platform.python_version(),
        'memory_limit_v2':read('/sys/fs/cgroup/memory.max'),
        'memory_limit_v1':read('/sys/fs/cgroup/memory/memory.limit_in_bytes'),
        'cpu_quota_v2':read('/sys/fs/cgroup/cpu.max'),
        'cpu_quota_v1':read('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'),
        'cpu_period_v1':read('/sys/fs/cgroup/cpu/cpu.cfs_period_us'),
        'tools':{name:bool(shutil.which(name)) for name in ('wine','wine64','docker','podman','Xvfb','dotnet')},
        'assigned_port':os.environ.get('SERVER_PORT') or os.environ.get('PORT'),
        'note':'This report does not confirm public UDP reachability or RCC compatibility.'
    }


if __name__=='__main__':print(json.dumps(report(),ensure_ascii=False,indent=2))
