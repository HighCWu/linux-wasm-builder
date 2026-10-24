#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Shell orchestration/cleanup contract with command models; never alters host IPC."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "sources/distro/distro/util-linux"
source = (PACKAGE / "ipc-test.sh").read_text()
recipe = (PACKAGE / "package.nix").read_text()
for program in ("ipcmk", "ipcrm", "ipcs", "lsipc"):
    assert '"--disable-' + program + '"' not in recipe
    assert program in (PACKAGE / "programs-test.sh").read_text()
assert 'ipc = check "ipc" ./ipc-test.sh;' in recipe
assert (
    "UL_BUILD_INIT([lsipc])"
    not in (PACKAGE / "configure-platform-programs.patch").read_text()
)
assert "ipcrm -a" not in source and "ipcrm --all" not in source
subprocess.run(["sh", "-n", str(PACKAGE / "ipc-test.sh")], check=True)
subprocess.run(["sh", "-n", str(PACKAGE / "programs-test.sh")], check=True)
MODEL = r"""
import json, os, pathlib, sys
root = pathlib.Path(os.environ['IPC_MODEL_ROOT'])
state_path = root / 'state.json'
state = json.loads(state_path.read_text())
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
mode = os.environ['IPC_MODEL_CASE']
def done(code=0):
    state_path.write_text(json.dumps(state))
    raise SystemExit(code)
if name == 'mount': done()
if args == ['--version']:
    print('BusyBox' if mode == 'wrong-owner' else name+' from util-linux 2.42.2'); done()
if name == 'ipcmk':
    if args == ['-Q','-p','600']:
        state['queue'] = '0'; print('Message queue id: 0'); done()
    if args == ['-S','2','-p','600']:
        state['sem'] = '1'; print('Semaphore id: 1'); done()
    if args == ['-M','4096']:
        print('Permission denied' if mode == 'wrong-shm-error' else 'create shared memory failed: Function not implemented', file=sys.stderr)
        done(1)
if name == 'ipcs':
    if args == ['-q','-i','0'] and state['queue']:
        print('Message Queue msqid=0'); done()
    if args == ['-s','-i','1'] and state['sem']:
        print('Semaphore Array semid=1\nnsems = '+('3' if mode == 'wrong-count' else '2')); done()
if name == 'lsipc':
    if args == ['-q','-i','0','--raw','--noheadings','-o','ID'] and state['queue']:
        print('0'); done()
    if args == ['-s','-i','1','--raw','--noheadings','-o','ID,NSEMS'] and state['sem']:
        print('1 2'); done()
    if args == ['-q','--raw','--noheadings','-o','ID']:
        if state['queue'] or mode == 'stale-object': print('0')
        done()
    if args == ['-s','--raw','--noheadings','-o','ID']:
        if state['sem']: print('1')
        done()
if name == 'ipcrm':
    if args == ['-q','0'] and state['queue']:
        state['queue'] = ''; state['removed'].append('queue:0'); done()
    if args == ['-s','1'] and state['sem']:
        state['sem'] = ''; state['removed'].append('sem:1'); done()
print('unexpected model command', name, args, file=sys.stderr); done(99)
"""
markers = [
    "util-linux IPC: upstream creation, object identities and semaphore metadata pass",
    "util-linux IPC: smartcols-backed lsipc reports live objects pass",
    "util-linux IPC: unsupported shared memory leaves supported objects intact pass",
    "util-linux IPC: explicit-ID removal, absent objects and cleanup pass",
]
with tempfile.TemporaryDirectory(prefix="util-linux-ipc-contract-") as tmp:
    path = Path(tmp)
    commands = path / "commands"
    commands.mkdir()
    for name in ("mount", "ipcmk", "ipcrm", "ipcs", "lsipc"):
        file = commands / name
        file.write_text("#!" + sys.executable + "\n" + MODEL)
        file.chmod(0o755)
    path_line = "export PATH=/bin:/sbin:/usr/bin:/usr/sbin"
    proc_line = '[ -r /proc/sysvipc/msg ] && [ -r /proc/sysvipc/sem ] || fail "kernel IPC proc interfaces"'
    loop = "while :; do sleep 1; done"
    assert path_line in source and proc_line in source and loop in source
    tested = source.replace(
        path_line, "export PATH=" + shlex.quote(str(commands) + os.pathsep + os.defpath)
    )
    # The model supplies proc availability and stops the target's final loop;
    # neither override is installed in the real target script.
    tested = tested.replace(proc_line, ": # model kernel proc availability").replace(
        loop, "exit 0"
    )
    script = path / "test.sh"
    script.write_text(tested)
    for mode, reason in (
        ("pass", None),
        ("wrong-owner", "must be the upstream"),
        ("wrong-count", "semaphore identity/count"),
        ("wrong-shm-error", "shared memory must report ENOSYS"),
        ("stale-object", "removed queue still listed"),
    ):
        state = path / "state.json"
        state.write_text(json.dumps({"queue": "", "sem": "", "removed": []}))
        result = subprocess.run(
            ["sh", str(script)],
            env={**os.environ, "IPC_MODEL_ROOT": tmp, "IPC_MODEL_CASE": mode},
            capture_output=True,
            text=True,
            timeout=15,
        )
        after = json.loads(state.read_text())
        assert not after["queue"] and not after["sem"], (mode, after)
        if reason is None:
            assert result.returncode == 0 and all(
                marker in result.stdout for marker in markers
            ), result.stdout + result.stderr
            assert result.stdout.count("::vm-test::pass") == 1
            assert after["removed"] == ["queue:0", "sem:1"]
        else:
            assert result.returncode != 0 and reason in result.stdout, (
                mode,
                result.stdout,
                result.stderr,
            )
            assert "::vm-test::pass" not in result.stdout
print(
    "util-linux IPC shell ownership, exact IDs, cleanup and negative controls passed with models; no host IPC mutation"
)
