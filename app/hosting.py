"""Opt-in limits for a small, trusted-user trial behind an authenticated proxy."""
import math,os,shutil
from dataclasses import dataclass,asdict
from fractions import Fraction

@dataclass(frozen=True)
class HostingPolicy:
    enabled: bool=False
    retention_hours: int=24
    cleanup_interval_seconds: int=60
    max_bytes: int=25*1024*1024
    max_seconds: int=30
    max_edge: int=1280
    max_pixels: int=1280*720
    max_fps: int=60
    storage_budget: int=2*1024**3
    free_reserve: int=5*1024**3

    @classmethod
    def from_env(cls):return cls(enabled=os.getenv('VIDEO_REMOVER_HOSTED')=='1')

    def public(self):return asdict(self)

    def check_storage(self,root):
        if not self.enabled:return
        if shutil.disk_usage(root).free<self.free_reserve:raise ValueError('服务器剩余空间不足，请联系管理员')
        used=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        # Leave room for one upload, working copy and bounded job output.
        if used>self.storage_budget-512*1024**2:raise ValueError('试用站存储额度已满，请联系管理员清理后再试')

    def check_stream(self,stream):
        if not self.enabled:return
        w,h=int(stream.get('width',0)),int(stream.get('height',0))
        if min(w,h)<2 or max(w,h)>self.max_edge or w*h>self.max_pixels:raise ValueError('试用站尺寸限制：长边不超过1280，像素总量不超过1280×720')
        try:duration=float(stream['duration'])
        except (KeyError,ValueError,TypeError):raise ValueError('试用站无法确认视频时长，请重新导出后上传')
        if not math.isfinite(duration) or not 0<duration<=self.max_seconds+.05:raise ValueError('试用站视频时长不能超过30秒')
        try:fps=float(Fraction(stream.get('avg_frame_rate','0/1')))
        except (ValueError,ZeroDivisionError):fps=0
        if not math.isfinite(fps) or not 1<=fps<=self.max_fps:raise ValueError('试用站帧率需为1–60 fps')

    def check_working(self,meta):
        self.check_stream(dict(width=meta['width'],height=meta['height'],duration=meta['duration'],avg_frame_rate=str(meta['fps'])))
