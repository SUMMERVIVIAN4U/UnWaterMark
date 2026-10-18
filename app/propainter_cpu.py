"""Application-owned CPU launcher; the pinned upstream source stays untouched."""
import runpy
import sys
from pathlib import Path

def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    script=Path(args[0]).resolve()
    sys.path.insert(0,str(script.parent))
    import torch
    import model.misc as misc
    detected=str(misc.get_device())
    misc.get_device=lambda:torch.device('cpu')
    print(f'ProPainter device forced=cpu; upstream autodetection={detected}',flush=True)
    sys.argv=[str(script),*args[1:]]
    runpy.run_path(str(script),run_name='__main__')

if __name__=='__main__':main()
