"""Render the user-approved golden-library revision and verify the resulting MP4."""
from datetime import datetime, timezone
import fcntl
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
BLEND = ROOT/'library_loop_gallery.blend'
EXPECTED_SHA = 'df4fcd36c82ecc3e7188bd60ab80744a2019d8dc60536c3fbc91a87aaaca7a5f'
FRAMES = ROOT/'renders/gallery_full'
VIDEO = OUT/'library_loop_gallery.mp4'
STATE = OUT/'gallery-full-status.json'
MANIFEST = OUT/'gallery-full-manifest.json'
REUSED = [1,76,151,226]
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
    lock = (OUT/'gallery-full.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    os.environ.pop('TRIPO_API_KEY',None)
    started = time.monotonic()
    status = dict(stage='preflight',pid=os.getpid(),started_at=now(),completed_frames=0,
                  authorization='User confirmed the reviewed golden-library design and 2.5–3 hour estimate.',
                  tripo_additional_credits=0,source=str(BLEND),source_sha256=EXPECTED_SHA)
    save(STATE,status)
    awake = subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())])
    try:
        blender = shutil.which('blender')
        if not blender or hashlib.sha256(BLEND.read_bytes()).hexdigest()!=EXPECTED_SHA:
            raise RuntimeError('Blender unavailable or approved scene hash changed')
        preview = json.loads((OUT/'gallery-preview-status.json').read_text())
        if not preview.get('visual_review_passed') or preview['blend_sha256']!=EXPECTED_SHA:
            raise RuntimeError('Reviewed preview does not match this scene')
        if not (ROOT/'reference/audio_loop.wav').is_file():
            raise RuntimeError('Required music is missing')
        expected_preview = {item['file']:item['sha256'] for item in preview['verified_pngs']}
        FRAMES.mkdir(parents=True,exist_ok=True)
        previous = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else None
        existing = list(FRAMES.glob('*.png'))
        if existing and (not previous or previous.get('source_sha256')!=EXPECTED_SHA):
            raise RuntimeError('Existing frames are not tied to the approved scene')
        for path in existing:
            validation.check_png(path)
        for frame in REUSED:
            path = ROOT/'renders/gallery_checks'/('f_%04d.png'%frame)
            verified = validation.check_png(path)
            if verified['sha256']!=expected_preview.get(path.name):
                raise RuntimeError('Check frame changed: '+path.name)
            target = FRAMES/path.name
            if not target.exists():
                shutil.copy2(path,target)
        save(MANIFEST,dict(source=str(BLEND),source_sha256=EXPECTED_SHA,scene='HERO',frame_range=[1,300],
                           resolution=[1920,744],fps=30,samples=96,reused_frames=REUSED,
                           started_at=status['started_at']))
        preview.update(stage='approved_rendering',production_render_started=True,approved_at=now())
        save(OUT/'gallery-preview-status.json',preview)
        initial_count = len(list(FRAMES.glob('*.png')))
        status['reused_or_existing_frames'] = initial_count

        def run(stage, command, logfile):
            status.update(stage=stage,updated_at=now(),log=str(logfile))
            save(STATE,status)
            with logfile.open('a') as log:
                log.write('\nSTART '+now()+'\n')
                log.flush()
                process = subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                status['child_pid'] = process.pid
                last = -1
                while process.poll() is None:
                    count = sum(path.stat().st_size>0 for path in FRAMES.glob('f_*.png'))
                    elapsed = time.monotonic()-started
                    status.update(completed_frames=count,elapsed_seconds=round(elapsed,1),updated_at=now())
                    if stage=='render' and count>initial_count+10:
                        status['estimated_remaining_seconds'] = round(elapsed/(count-initial_count)*(300-count))
                    save(STATE,status)
                    if count!=last:
                        print('[gallery full] %s frames=%d/300 elapsed=%.0fs'%(stage,count,elapsed),flush=True)
                        last = count
                    time.sleep(5)
                if process.returncode:
                    raise RuntimeError('%s exited %d; original output:\n%s'%(stage,process.returncode,
                        '\n'.join(logfile.read_text().splitlines()[-70:])))
            status.pop('child_pid',None)

        run('render',[blender,'-b',str(BLEND),'--python-exit-code','2','-P',str(ROOT/'scripts/render.py'),
                      '--','--scene','HERO','--out',str(FRAMES),'--start','1','--end','300'],OUT/'render-gallery.log')
        expected = {'f_%04d.png'%frame for frame in range(1,301)}
        if {path.name for path in FRAMES.glob('*.png')}!=expected:
            raise RuntimeError('Frame set incomplete or contains unexpected images')
        checked = [validation.check_png(FRAMES/name) for name in sorted(expected)]
        save(OUT/'gallery-full-frame-validation.json',dict(count=300,resolution=[1920,744],png_crc_and_pixels='passed',frames=checked))
        status.update(render_completed_at=now(),render_elapsed_seconds=round(time.monotonic()-started,2))
        run('assemble',[blender,'-b','--python-exit-code','2','-P',str(ROOT/'scripts/assemble.py'),
                        '--','--hero',str(FRAMES),'--out',str(VIDEO)],OUT/'assemble-gallery.log')
        video = validation.check_mp4(VIDEO)
        save(OUT/'gallery-full-video-validation.json',video)
        run('video_qa',[blender,'-b','--python-exit-code','2','-P',str(OUT/'verify_gallery_full.py')],
            OUT/'verify-gallery.log')
        status.update(stage='complete_pending_visual_qa',completed_frames=300,completed_at=now(),
                      elapsed_seconds=round(time.monotonic()-started,2),video=str(VIDEO),validation='passed')
        status.pop('estimated_remaining_seconds',None)
        save(STATE,status)
        print('[gallery full] COMPLETE '+json.dumps(video),flush=True)
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
