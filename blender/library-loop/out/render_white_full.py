"""Run the user-approved 300-frame white-light revision with resumable output and validation."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import traceback

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/'out'
BLEND = ROOT/'library_loop_white_reference.blend'
EXPECTED_SHA = '89bf55a7b9dccb7b90b74765a6cef102a5581f0d0094374a0ef1313290ef7331'
FRAMES = ROOT/'renders/white_reference_full'
VIDEO = OUT/'library_loop_white_reference.mp4'
STATE = OUT/'white-reference-full-status.json'
MANIFEST = OUT/'white-reference-full-manifest.json'
spec = importlib.util.spec_from_file_location('output_validation', OUT/'render_pipeline.py')
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)

def now():
    return datetime.now(timezone.utc).isoformat()

def save(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    temporary.replace(path)

def main():
    started = time.monotonic()
    status = dict(stage='preflight',pid=os.getpid(),started_at=now(),completed_frames=0,
                  authorization='User confirmed the reviewed white-footlight version and the 60–90 minute estimate.',
                  tripo_additional_credits=0,source=str(BLEND),source_sha256=EXPECTED_SHA)
    save(STATE,status)
    awake = subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())])
    try:
        blender = shutil.which('blender')
        if not blender or hashlib.sha256(BLEND.read_bytes()).hexdigest()!=EXPECTED_SHA:
            raise RuntimeError('Blender unavailable or approved scene hash changed')
        preview = json.loads((OUT/'white-reference-preview-status.json').read_text())
        if preview['stage']!='complete' or preview['source_sha256']!=EXPECTED_SHA:
            raise RuntimeError('The validated preview does not match this scene')
        if not (ROOT/'reference/audio_loop.wav').is_file():
            raise RuntimeError('Required music is missing')
        expected_preview = {item['file']:item['sha256'] for item in json.loads((OUT/'white-reference-preview-frame-validation.json').read_text())}
        FRAMES.mkdir(parents=True,exist_ok=True)
        previous = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else None
        existing = list(FRAMES.glob('*.png'))
        if existing and (not previous or previous.get('source_sha256')!=EXPECTED_SHA):
            raise RuntimeError('Existing render frames are not tied to the approved scene')
        for path in existing:
            validation.check_png(path)
        for frame in range(1,33):
            path = ROOT/'renders/white_reference_cycle'/('f_%04d.png'%frame)
            verified = validation.check_png(path)
            if verified['sha256']!=expected_preview.get(path.name):
                raise RuntimeError('Preview frame changed: '+path.name)
            target = FRAMES/path.name
            if not target.exists():
                shutil.copy2(path,target)
        save(MANIFEST,dict(source=str(BLEND),source_sha256=EXPECTED_SHA,scene='HERO',frame_range=[1,300],
                           resolution=[1920,744],fps=30,samples=96,reused_frames=list(range(1,33)),started_at=status['started_at']))
        child_env = {key:value for key,value in os.environ.items() if key!='TRIPO_API_KEY'}

        def run(stage, command, logfile):
            status.update(stage=stage,updated_at=now(),log=str(logfile))
            save(STATE,status)
            with logfile.open('a') as log:
                log.write('\nSTART '+now()+'\n')
                log.flush()
                process = subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=child_env)
                status['child_pid'] = process.pid
                last = -1
                while process.poll() is None:
                    count = sum(path.stat().st_size>0 for path in FRAMES.glob('f_*.png'))
                    elapsed = time.monotonic()-started
                    status.update(completed_frames=count,elapsed_seconds=round(elapsed,1),updated_at=now())
                    if stage=='render' and count>42:
                        status['estimated_remaining_seconds'] = round(elapsed/(count-32)*(300-count))
                    save(STATE,status)
                    if count!=last:
                        print('[white full] %s frames=%d/300 elapsed=%.0fs'%(stage,count,elapsed),flush=True)
                        last = count
                    time.sleep(5)
                if process.returncode:
                    raise RuntimeError('%s exited %d; original output:\n%s'%(stage,process.returncode,'\n'.join(logfile.read_text().splitlines()[-70:])))
            status.pop('child_pid',None)

        run('render',[blender,'-b',str(BLEND),'--python-exit-code','2','-P',str(ROOT/'scripts/render.py'),
                      '--','--scene','HERO','--out',str(FRAMES),'--start','1','--end','300'],OUT/'render-white-reference.log')
        expected = {'f_%04d.png'%frame for frame in range(1,301)}
        if {path.name for path in FRAMES.glob('*.png')}!=expected:
            raise RuntimeError('Full render frame set is incomplete or contains unexpected images')
        checked = [validation.check_png(FRAMES/name) for name in sorted(expected)]
        save(OUT/'white-reference-full-frame-validation.json',dict(count=300,resolution=[1920,744],png_crc_and_pixels='passed',frames=checked))
        status.update(render_completed_at=now(),render_elapsed_seconds=round(time.monotonic()-started,2))
        run('assemble',[blender,'-b','--python-exit-code','2','-P',str(ROOT/'scripts/assemble.py'),
                        '--','--hero',str(FRAMES),'--out',str(VIDEO)],OUT/'assemble-white-reference.log')
        video = validation.check_mp4(VIDEO)
        save(OUT/'white-reference-full-video-validation.json',video)
        status.update(stage='complete_pending_visual_qa',completed_frames=300,completed_at=now(),
                      elapsed_seconds=round(time.monotonic()-started,2),video=str(VIDEO),validation='passed')
        status.pop('estimated_remaining_seconds',None)
        save(STATE,status)
        print('[white full] COMPLETE '+json.dumps(video),flush=True)
    except BaseException as error:
        status.update(stage='failed',error=str(error),failed_at=now(),elapsed_seconds=round(time.monotonic()-started,2))
        save(STATE,status)
        traceback.print_exc()
        raise
    finally:
        if awake.poll() is None:
            awake.terminate()

if __name__=='__main__':
    main()
