import json, os, signal, subprocess, sys, time, types, runpy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.media import inspect_video

def ff(*args):
    subprocess.run(['ffmpeg','-v','error','-y',*map(str,args)],check=True,stderr=subprocess.PIPE)

@pytest.fixture
def base(tmp_path):
    p=tmp_path/'base.mp4'
    ff('-f','lavfi','-i','color=blue:s=128x128:r=4','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','2','-c:v','libx264','-c:a','aac',p)
    return p

@pytest.mark.parametrize('kind,message',[('rotation','旋转'),('sar','像素'),('video_offset','起始'),('audio_offset','音频'),('two_audio','音轨')])
def test_reject_unsupported_media(base,tmp_path,kind,message):
    p=tmp_path/(kind+'.mp4')
    if kind=='rotation':ff('-display_rotation:v:0','90','-i',base,'-c','copy',p)
    elif kind=='sar':ff('-i',base,'-vf','setsar=2','-c:v','libx264','-c:a','copy',p)
    elif kind=='video_offset':ff('-itsoffset','0.5','-i',base,'-map','0:v','-c','copy',p)
    elif kind=='audio_offset':ff('-i',base,'-itsoffset','0.5','-i',base,'-map','0:v','-map','1:a','-c','copy',p)
    else:ff('-i',base,'-map','0:v','-map','0:a','-map','0:a','-c','copy',p)
    with pytest.raises(ValueError,match=message):inspect_video(p)

def test_zero_start_aac_supported(base):
    m=inspect_video(base)
    assert m['frames']==8 and m['has_audio'] and m['audio_codec']=='aac'

def test_cpu_adapter_overrides_available_mps(tmp_path,monkeypatch,capsys):
    from app.propainter_cpu import main
    misc=types.ModuleType('model.misc');misc.get_device=lambda:'mps'
    model=types.ModuleType('model');model.misc=misc
    monkeypatch.setitem(sys.modules,'model',model);monkeypatch.setitem(sys.modules,'model.misc',misc)
    torch=types.ModuleType('torch');torch.device=lambda name:name
    monkeypatch.setitem(sys.modules,'torch',torch)
    script=tmp_path/'inference_propainter.py'
    script.write_text('from model.misc import get_device\nimport sys,json,os\nopen("called.json","w").write(json.dumps([get_device(),sys.argv,os.getcwd()]))')
    monkeypatch.chdir(tmp_path)
    main([str(script),'-i','source','-m','mask'])
    data=json.loads((tmp_path/'called.json').read_text())
    assert data==['cpu',[str(script),'-i','source','-m','mask'],str(tmp_path)]
    assert 'mps' in capsys.readouterr().out

@pytest.mark.parametrize('exitcode',[0,1])
def test_exited_leader_descendant_cleaned_before_next_job(tmp_path,exitcode):
    from app.jobs import JobManager
    marker=tmp_path/'child';next_marker=tmp_path/'next'
    child='import time;time.sleep(120)'
    first=f'import subprocess; p=subprocess.Popen([{sys.executable!r},"-c",{child!r}]);open({str(marker)!r},"w").write(str(p.pid));raise SystemExit({exitcode})'
    second=f'import os; pid=int(open({str(marker)!r}).read());\ntry: os.kill(pid,0); alive=True\nexcept ProcessLookupError: alive=False\nopen({str(next_marker)!r},"w").write(str(alive))'
    calls=[]
    def command(j):
        calls.append(j);return [sys.executable,'-c',first if len(calls)==1 else second]
    mgr=JobManager(tmp_path,command_factory=command)
    try:
        mgr.create('a'*32,'full',b'mask');mgr.create('a'*32,'full',b'mask')
        for _ in range(200):
            if next_marker.exists():break
            time.sleep(.025)
        assert next_marker.read_text()=='False'
    finally:
        mgr.close()
        if marker.exists():
            try:os.kill(int(marker.read_text()),signal.SIGKILL)
            except ProcessLookupError:pass

def test_failure_summary_is_visible_bounded_and_actual(tmp_path):
    from app.jobs import JobManager
    def command(j):
        folder=tmp_path/'jobs'/j['id']
        (folder/'workererror.json').write_text(json.dumps({'phase':'model','cause':'RuntimeError: Conv3D is not supported on MPS'+'x'*1000}))
        return [sys.executable,'-c','raise SystemExit(1)']
    mgr=JobManager(tmp_path,command_factory=command)
    try:
        j=mgr.create('a'*32,'full',b'mask')
        for _ in range(100):
            if mgr.get(j['id'])['status']=='failed':break
            time.sleep(.025)
        error=mgr.get(j['id'])['error']
        assert 'model' in error and 'Conv3D is not supported on MPS' in error and len(error)<650
    finally:mgr.close()

def test_worker_reinspects_legacy_metadata_and_dispatches_cpu(base,tmp_path,monkeypatch):
    from app import worker
    root=tmp_path/'runtime';folder=root/'jobs'/'job';folder.mkdir(parents=True);upload=root/'uploads'/'old';upload.mkdir(parents=True)
    (upload/'video').write_bytes(base.read_bytes());(upload/'upload.json').write_text(json.dumps({'width':1}))
    (folder/'job.json').write_text(json.dumps({'upload_id':'old','mode':'full'}));(folder/'mask.png').write_bytes(b'mask')
    observed=[]
    def prepare(source,prepared,meta,mode,cmd):
        assert meta['width']==128 and meta['frames']==8
        return meta
    monkeypatch.setattr(worker,'prepare_video',prepare)
    original_run=subprocess.run
    def execute(args,**kwargs):
        if not any(str(x).endswith('propainter_cpu.py') for x in args):return original_run(args,**kwargs)
        observed.append((args,kwargs))
        raise RuntimeError('injected actual model failure')
    monkeypatch.setattr(worker.subprocess,'run',execute)
    with pytest.raises(RuntimeError,match='injected'):worker.run(root,'job')
    args,kw=observed[0]
    assert args[2].endswith('propainter_cpu.py') and args[3].endswith('inference_propainter.py')
    assert kw['cwd']==worker.BASE/'vendor'/'ProPainter'
    assert kw['env']['OMP_NUM_THREADS']=='4'
    manifest=json.loads((folder/'manifest.json').read_text())
    assert manifest['engine']['device']=='cpu' and len(manifest['engine']['launcher_sha256'])==64

def test_top_level_worker_records_actual_subprocess_cause(tmp_path,monkeypatch):
    from app import worker
    folder=tmp_path/'jobs'/'job';folder.mkdir(parents=True)
    (folder/'stage.json').write_text(json.dumps({'stage':'model'}))
    def fail(*args):raise RuntimeError('Conv3D is not supported on MPS')
    monkeypatch.setattr(worker,'run',fail)
    with pytest.raises(RuntimeError):worker.main([str(tmp_path),'job'])
    detail=json.loads((folder/'workererror.json').read_text())
    assert detail['phase']=='model' and detail['cause']=='RuntimeError: Conv3D is not supported on MPS'

def test_cleanup_failure_blocks_next_queued_work(tmp_path,monkeypatch):
    import app.jobs as jobs
    calls=[]
    def fail_cleanup(proc):raise PermissionError('live group denied')
    monkeypatch.setattr(jobs,'stop_group',fail_cleanup)
    mgr=jobs.JobManager(tmp_path,command_factory=lambda j:calls.append(j) or [sys.executable,'-c','raise SystemExit(1)'])
    try:
        first=mgr.create('a'*32,'full',b'mask');second=mgr.create('a'*32,'full',b'mask')
        for _ in range(100):
            if mgr.get(first['id'])['status']=='failed':break
            time.sleep(.025)
        assert '进程清理失败' in mgr.get(first['id'])['error']
        assert len(calls)==1 and mgr.get(second['id'])['status']=='queued'
    finally:
        monkeypatch.undo();mgr.close()

def test_subprocess_failure_extracts_bounded_actual_log(tmp_path,monkeypatch):
    from app import worker
    folder=tmp_path/'jobs'/'job';folder.mkdir(parents=True)
    (folder/'stage.json').write_text(json.dumps({'stage':'model'}));(folder/'worker.log').write_text('noise\nRuntimeError: Conv3D is not supported on MPS\n')
    def fail(*args):raise subprocess.CalledProcessError(1,['model'])
    monkeypatch.setattr(worker,'run',fail)
    with pytest.raises(subprocess.CalledProcessError):worker.main([str(tmp_path),'job'])
    assert json.loads((folder/'workererror.json').read_text())['cause']=='RuntimeError: Conv3D is not supported on MPS'


def test_current_short_quality_fixture_dimensions_unchanged(tmp_path):
    p=tmp_path/'short.mp4'
    ff('-f','lavfi','-i','color=blue:s=512x320:r=24','-t','4','-c:v','libx264',p)
    m=inspect_video(p)
    assert (m['width'],m['height'],m['frames'],m['fps'],m['duration'])==(512,320,96,24,4)
