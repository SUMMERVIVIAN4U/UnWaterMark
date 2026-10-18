"""Bounded-memory CPU Telea repair; ffmpeg owns decoding and H.264 encoding."""
import subprocess
import cv2
import numpy as np
from PIL import Image

def repair(source,mask_path,output,meta,record):
    cv2.setNumThreads(4)
    with Image.open(mask_path) as image:
        mask=np.asarray(image.convert('L'))
    if mask.shape!=(meta['height'],meta['width']):raise ValueError('Mask dimensions differ from source')
    mask=cv2.dilate((mask>0).astype(np.uint8)*255,np.ones((3,3),np.uint8),iterations=1)
    if not mask.any():raise ValueError('Empty repair mask')
    # Preserve decoded presentation frames; container tail duration must not duplicate them.
    decode=['ffmpeg','-v','error','-i',str(source),'-map','0:v:0','-an','-fps_mode','passthrough','-f','rawvideo','-pix_fmt','bgr24','pipe:1']
    encode=['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','bgr24','-s',f"{meta['width']}x{meta['height']}",'-r',meta['fps_fraction'],'-i','pipe:0','-an','-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p',str(output)]
    record(decode);record(encode)
    # stderr inherits worker.log: no unconsumed pipe or unbounded error buffer.
    decoder=encoder=None
    try:
        decoder=subprocess.Popen(decode,stdout=subprocess.PIPE)
        encoder=subprocess.Popen(encode,stdin=subprocess.PIPE)
        frame_bytes=meta['width']*meta['height']*3
        for _ in range(meta['frames']):
            data=bytearray()
            while len(data)<frame_bytes:
                chunk=decoder.stdout.read(frame_bytes-len(data))
                if not chunk:raise RuntimeError('Decoder ended before expected frame count')
                data.extend(chunk)
            frame=np.frombuffer(data,dtype=np.uint8).reshape(meta['height'],meta['width'],3)
            encoder.stdin.write(cv2.inpaint(frame,mask,3,cv2.INPAINT_TELEA).tobytes())
        if decoder.stdout.read(1):raise RuntimeError('Decoder produced extra frames')
        decoder.stdout.close();encoder.stdin.close()
        for process,args in ((decoder,decode),(encoder,encode)):
            code=process.wait(timeout=180)
            if code:raise subprocess.CalledProcessError(code,args)
    finally:
        # Exceptions (including broken pipes) terminate both children. Queue cancellation
        # additionally kills the entire inherited process group, including these children.
        for process in (decoder,encoder):
            if process is not None and process.poll() is None:process.kill()
        for process in (decoder,encoder):
            if process is not None:
                process.wait()
                for pipe in (process.stdin,process.stdout):
                    if pipe is not None:
                        try:pipe.close()
                        except BrokenPipeError:pass
