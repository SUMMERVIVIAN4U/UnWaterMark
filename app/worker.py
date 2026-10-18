"""One isolated process group per model job; all child ffmpeg/model processes inherit it."""
import hashlib,json,subprocess,sys,time,os,math
from pathlib import Path
from .media import inspect_video
BASE=Path(__file__).resolve().parents[1]

def file_hash(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def prepare_video(source,prepared,meta,mode,cmd):
    count=min(meta['frames'],math.ceil(30*meta['fps'])) if mode=='preview' else meta['frames']
    args=['ffmpeg','-y','-v','error','-i',str(source),'-map','0:v:0','-an']
    if mode=='preview':
        args+=['-frames:v',str(count),'-c:v','libx264','-crf','0','-preset','fast','-pix_fmt','yuv420p','-r',meta['fps_fraction']]
    else:args+=['-c:v','copy']
    cmd(args+[str(prepared)])
    result=inspect_video(prepared)
    if result['frames']!=count or any(result[k]!=meta[k] for k in ('width','height')) or abs(result['fps']-meta['fps'])>.0001 or abs(result['duration']-count/meta['fps'])>1e-4:
        raise RuntimeError('Prepared input does not match requested source frames and timing')
    return result

def run(root,id):
    folder=root/'jobs'/id;j=json.loads((folder/'job.json').read_text());upload=root/'uploads'/j['upload_id'];saved=json.loads((upload/'upload.json').read_text()) if (upload/'upload.json').exists() else {};source=upload/saved.get('working_file','video');meta=inspect_video(source);prepared=folder/'input.mp4';commands=[]
    engine=j.get('engine','propainter')
    if engine not in {'fast','propainter'}:raise ValueError('无效处理引擎')
    vendor=BASE/'vendor'/'ProPainter';launcher=BASE/'app'/'propainter_cpu.py'
    model_engine=dict(name='official ProPainter',device='cpu',source_commit='e870e79321c31b733e2031af5aa2fb1fe3ac7eec',source_sha256=hashlib.sha256((vendor/'inference_propainter.py').read_bytes()).hexdigest(),launcher_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest()) if engine=='propainter' else {}
    if engine=='fast':
        import cv2
        model_engine=dict(name='OpenCV fast CPU',algorithm='INPAINT_TELEA',opencv_version=cv2.__version__,device='cpu',source_sha256=hashlib.sha256((BASE/'app'/'fast.py').read_bytes()).hexdigest())
    manifest=dict(engine=model_engine,job_id=id,source_metadata=meta,source_sha256=file_hash(source),mask_sha256=hashlib.sha256((folder/'mask.png').read_bytes()).hexdigest(),started_at=time.time(),parameters=dict(subvideo_length=24,neighbor_length=10,ref_stride=10,mask_dilation=4),commands=commands,dimension_note='Official model internally processes multiples of 8 and restores source dimensions.',audio_note='AAC stream copied; other audio transcoded to AAC.')
    if saved.get('normalization'):
        manifest.update(normalization=saved['normalization'],original_sha256=saved['normalization']['original_sha256'],working_sha256=file_hash(source))
    if engine=='fast':
        manifest.update(parameters=dict(inpaint_radius=3,mask_dilation=1,mask_kernel=3),dimension_note='Original dimensions and frame sequence; no resize or frame dropping.')
    def record(args):
        commands.append(args);(folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
    def stage(name):
        p=folder/'stage.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(dict(stage=name,stage_started_at=time.time())));tmp.replace(p)
    def cmd(args,cwd=None):
        commands.append(args);(folder/'manifest.json').write_text(json.dumps(manifest,indent=2));subprocess.run(args,check=True,cwd=cwd,timeout=21600 if cwd else 180,env={**os.environ,"OMP_NUM_THREADS":"4","MKL_NUM_THREADS":"4","MPLCONFIGDIR":"/tmp/unwatermark-matplotlib"})
    stage('prepare')
    expected=prepare_video(source,prepared,meta,j['mode'],cmd)
    stage('model')
    if engine=='fast':
        from .fast import repair
        model=folder/'fast.mp4'
        repair(prepared,folder/'mask.png',model,expected,record)
    else:
        cmd([sys.executable,'-u',str(launcher),str(vendor/'inference_propainter.py'),'-i',str(prepared),'-m',str(folder/'mask.png'),'-o',str(folder/'model'), '--subvideo_length','24','--neighbor_length','10','--ref_stride','10','--mask_dilation','4'],cwd=vendor)
        model=folder/'model'/'input'/'inpaint_out.mp4'
    stage('mux')
    # Re-encode timing from frame sequence to the exact original CFR rational.
    args=['ffmpeg','-y','-v','error','-i',str(model),'-i',str(source),'-map','0:v:0','-map','1:a:0?','-vf',f"setpts=N/({expected['fps_fraction']}*TB)",'-r',expected['fps_fraction'],'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','copy' if meta.get('audio_codec')=='aac' else 'aac','-t',str(expected['duration']),'-movflags','+faststart',str(folder/'result.mp4')]
    cmd(args)
    stage('validate');out=inspect_video(folder/'result.mp4')
    if any(out[k]!=expected[k] for k in ('width','height','frames')) or abs(out['fps']-expected['fps'])>.0001 or abs(out['duration']-expected['duration'])>1/expected['fps'] or out['has_audio']!=meta['has_audio']:raise RuntimeError('Output dimensions, frames, timing or audio validation failed')
    manifest.update(finished_at=time.time(),output=out,output_sha256=file_hash(folder/'result.mp4'));(folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    root=Path(args[0]).resolve();id=args[1];folder=root/'jobs'/id
    try:run(root,id)
    except Exception as e:
        phase='initialization'
        try:phase=json.loads((folder/'stage.json').read_text())['stage']
        except (OSError,ValueError,KeyError):pass
        cause=f'{type(e).__name__}: {e}'
        if isinstance(e,subprocess.CalledProcessError):
            # The inherited log contains the actual downstream exception, not just its exit code.
            try:
                with (folder/'worker.log').open('rb') as log:
                    log.seek(0,2);size=log.tell();log.seek(max(0,size-16384));lines=log.read().decode('utf-8','replace').splitlines()
                detail=next((line.strip() for line in reversed(lines) if line.strip().startswith(('RuntimeError:','ValueError:','OSError:','FileNotFoundError:','Exception:'))),None)
                if detail:cause=detail
            except OSError:pass
        (folder/'workererror.json').write_text(json.dumps(dict(phase=str(phase)[:40],cause=' '.join(cause.split())[:500]),ensure_ascii=False))
        raise

if __name__=='__main__':main()
